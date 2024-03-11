import asyncio
import dataclasses
import pathlib
from collections import deque
from types import MappingProxyType
from typing import Deque, Dict, Mapping, Optional, Set, Tuple, Union
from uuid import UUID

import yaml
from supriya.clocks import AsyncTempoClock, OfflineTempoClock
from supriya.commands import StatusResponse
from supriya.nonrealtime import Session
from supriya.providers import Provider
from uqbar.containers import UniqueTreeTuple

import tloen.domain  # noqa

from ..bases import Event
from ..pubsub import PubSub
from .bases import ApplicationObject, Container
from .contexts import Context
from .controllers import Controller
from .enums import ApplicationStatus
from .events import TransportStarted, TransportStopped, TransportTicked
from .slots import Scene


class Application(UniqueTreeTuple):

    ### INITIALIZER ###

    def __init__(self, channel_count=2, pubsub=None):
        # non-tree objects
        self._channel_count = int(channel_count)
        self._pubsub = pubsub or PubSub()
        self._status = ApplicationStatus.OFFLINE
        self._registry: Dict[UUID, "tloen.domain.ApplicationObject"] = {}

        # tree objects
        self._contexts = Container(label="Contexts")
        self._controllers = Container(label="Controllers")
        self._scenes = Container(label="Scenes")

        # transport
        self._clock: Union[AsyncTempoClock, OfflineTempoClock] = AsyncTempoClock()
        self._clock_dependencies: Set[ApplicationObject] = set()
        self._is_looping = False
        self._loop_points = (0.0, 4.0)
        self._tempo = 120.0
        self._tick_event_id: Optional[int] = None
        self._time_signature = (4, 4)

        UniqueTreeTuple.__init__(
            self, children=[self._controllers, self._scenes, self._contexts],
        )

    ### SPECIAL METHODS ###

    def __str__(self):
        return "\n".join(
            [
                f"<{type(self).__name__} [{self.status.name}] {hex(id(self))}>",
                *(f"    {line}" for child in self for line in str(child).splitlines()),
            ]
        )

    ### PRIVATE METHODS ###

    async def _callback_midi_perform(self, clock_context, midi_messages):
        from .bases import ApplicationObject

        ApplicationObject._debug_tree(
            self, "Perform", suffix=repr([type(_).__name__ for _ in midi_messages])
        )
        for context in self.contexts:
            await context.perform(midi_messages, moment=clock_context.current_moment)

    def _callback_transport_tick(self, clock_context):
        self.pubsub.publish(TransportTicked(clock_context.desired_moment))
        return 1 / clock_context.desired_moment.time_signature[1] / 4

    def _set_items(self, new_items, old_items, start_index, stop_index):
        UniqueTreeTuple._set_items(self, new_items, old_items, start_index, stop_index)
        for item in new_items:
            item._set(application=self)
        for item in old_items:
            item._set(application=None)

    ### PUBLIC METHODS ###

    async def add_context(self, *, name=None):
        if self.status == ApplicationStatus.NONREALTIME:
            raise ValueError
        context = Context(name=name)
        self._contexts._append(context)
        if self.status == ApplicationStatus.REALTIME:
            await context._boot()
        return context

    def add_controller(self, *, name=None) -> Controller:
        controller = Controller(name=name)
        self._controllers._append(controller)
        return controller

    async def add_scene(self, *, name=None) -> Scene:
        from .slots import Slot
        from .tracks import Track

        scene = Scene(name=name)
        self._scenes._append(scene)
        tracks: Deque[Track] = deque()
        for context in self.contexts:
            tracks.extend(context.tracks)
        while tracks:
            track = tracks.pop()
            if track.tracks:
                tracks.extend(track.tracks)
            while len(track.slots) < len(self.scenes):
                track.slots._append(Slot())
        return scene

    async def boot(self, provider=None, retries=3):
        if self.status == ApplicationStatus.REALTIME:
            return
        elif self.status == ApplicationStatus.NONREALTIME:
            raise ValueError
        elif not self.contexts:
            raise RuntimeError("No contexts to boot")
        self._clock = AsyncTempoClock()
        self.pubsub.publish(ApplicationBooting())
        await asyncio.gather(
            *[
                context._boot(provider=provider, retries=retries)
                for context in self.contexts
            ]
        )
        self.pubsub.publish(
            ApplicationBooted(self.primary_context.provider.server.port,)
        )
        self.pubsub.publish(
            ApplicationStatusRefreshed(self.primary_context.provider.server.status,)
        )
        self._status = ApplicationStatus.REALTIME
        return self

    @classmethod
    async def deserialize(cls, data):
        entities_data = deque(data["entities"])
        entity_data = entities_data.popleft()
        application = cls(channel_count=entity_data["spec"].get("channel_count", 2),)
        application.clock.change(
            beats_per_minute=entity_data["spec"]["tempo"],
            time_signature=[
                int(x) for x in entity_data["spec"]["time_signature"].split("/")
            ],
        )
        while entities_data:
            entity_data = entities_data.popleft()
            if entity_data.get("visits", 0) > 2:
                continue  # discard it
            entity_class = getattr(tloen.domain, entity_data["kind"])
            should_defer = await entity_class._deserialize(entity_data, application)
            if should_defer:
                entity_data["visits"] = entity_data.get("visits", 0) + 1
                entities_data.append(entity_data)
                continue
        return application

    @classmethod
    async def new(cls, context_count=1, track_count=4, scene_count=8, **kwargs):
        application = cls(**kwargs)
        for _ in range(context_count):
            context = await application.add_context()
            for _ in range(track_count):
                await context.add_track()
        for _ in range(scene_count):
            await application.add_scene()
        return application

    async def perform(self, midi_messages):
        if self.status != ApplicationStatus.REALTIME:
            return
        self.clock.schedule(self._callback_midi_perform, args=[midi_messages])
        if not self.clock.is_running:
            await self.start()

    async def quit(self):
        if self.status == ApplicationStatus.OFFLINE:
            return
        elif self.status == ApplicationStatus.NONREALTIME:
            raise ValueError
        self._status = ApplicationStatus.OFFLINE
        self.pubsub.publish(ApplicationQuitting())
        await self.stop()
        for context in self.contexts:
            provider = context.provider
            async with provider.at():
                context._set(provider=None)
            if provider is not None:
                await provider.server.quit()
        self.pubsub.publish(ApplicationQuit())
        return self

    async def remove_contexts(self, *contexts: Context):
        if not all(context in self.contexts for context in contexts):
            raise ValueError
        for context in contexts:
            provider = context.provider
            if provider is not None:
                async with provider.at():
                    self._contexts._remove(context)
                await provider.server.quit()
            else:
                self._contexts._remove(context)
        if not len(self):
            self._status = ApplicationStatus.OFFLINE

    def remove_controllers(self, *controllers: Controller):
        if not all(controller in self.controllers for controller in controllers):
            raise ValueError
        for controller in controllers:
            self._controllers._remove(controller)

    async def remove_scenes(self, *scenes: Scene):
        from .tracks import Track

        if not all(scene in self.scenes for scene in scenes):
            raise ValueError
        indices = sorted(self.scenes.index(scene) for scene in scenes)
        for scene in scenes:
            self.scenes._remove(scene)
        tracks: Deque[Track] = deque()
        for context in self.contexts:
            tracks.extend(context.tracks)
        while tracks:
            track = tracks.pop()
            if track.tracks:
                tracks.extend(track.tracks)
            for index in reversed(indices):
                track.slots._remove(track.slots[index])

    async def render(self) -> Session:
        if self.status != ApplicationStatus.OFFLINE:
            raise ValueError
        self._status == ApplicationStatus.NONREALTIME
        self._clock = OfflineTempoClock()
        provider = Provider.nonrealtime()
        with provider.at():
            for context in self.contexts:
                context._set(provider=provider)
        with provider.at(provider.session.duration or 10):
            for context in self.contexts:
                context._set(provider=None)
        self._status = ApplicationStatus.OFFLINE
        return provider.session

    async def start(self):
        self._tick_event_id = self.clock.cue(self._callback_transport_tick)
        await asyncio.gather(*[_._start() for _ in self._clock_dependencies])
        await self.clock.start()
        self.pubsub.publish(TransportStarted())

    async def stop(self):
        await self.clock.stop()
        await asyncio.gather(*[_._stop() for _ in self._clock_dependencies])
        self.clock.cancel(self._tick_event_id)
        self.pubsub.publish(TransportStopped())

    @classmethod
    def load(cls, file_path: Union[str, pathlib.Path]):
        return cls.deserialize(yaml.safe_load(pathlib.Path(file_path).read_text()))

    def save(self, file_path: Union[str, pathlib.Path], force=False):
        path = pathlib.Path(file_path)
        if path.exists() and not force:
            raise RuntimeError
        path.write_text(yaml.dump(self.serialize()))

    def serialize(self):
        def clean(data):
            for mapping in [data.get("meta", {}), data.get("spec", {}), data]:
                for key in tuple(mapping):
                    value = mapping[key]
                    if value is None or (isinstance(value, (list, dict)) and not value):
                        mapping.pop(key)

        serialized = {
            "kind": type(self).__name__,
            "spec": {
                "channel_count": self.channel_count,
                "contexts": [],
                "scenes": [],
                "tempo": self.clock.beats_per_minute,
                "time_signature": "/".join(str(_) for _ in self.clock.time_signature),
            },
        }
        entities = [serialized]
        for scene in self.scenes:
            serialized["spec"]["scenes"].append(str(scene.uuid))
            aux = scene._serialize()
            entities.append(aux[0])
            entities.extend(aux[1])
        for context in self.contexts:
            serialized["spec"]["contexts"].append(str(context.uuid))
            aux = context._serialize()
            entities.append(aux[0])
            entities.extend(aux[1])
        for entity in entities:
            clean(entity)
        return {"entities": entities}

    async def set_channel_count(self, channel_count: int):
        assert 1 <= channel_count <= 8
        self._channel_count = int(channel_count)
        for context in self.contexts:
            if context.provider:
                async with context.provider.at():
                    context._reconcile()
            else:
                context._reconcile()

    def set_is_looping(self, is_looping):
        self._is_looping = bool(is_looping)
        self.pubsub.publish(ApplicationLoopingChanged(self._is_looping))

    def set_loop_points(self, from_: float, to: float):
        if to <= from_:
            raise ValueError
        elif from_ < 0:
            raise ValueError
        self._loop_points = (from_, to)
        self.pubsub.publish(ApplicationLoopPointsChanged(*self._loop_points))

    def set_pubsub(self, pubsub: PubSub):
        self._pubsub = pubsub

    def set_tempo(self, tempo: float):
        if tempo <= 0.0:
            raise ValueError
        self._tempo = tempo
        self.pubsub.publish(ApplicationTempoChanged(self._tempo))

    def set_time_signature(self, numerator: int, denominator: int):
        if numerator < 1:
            raise ValueError
        if denominator < 1:
            raise ValueError
        self._time_signature = (int(numerator), int(denominator))
        self.pubsub.publish(ApplicationTimeSignatureChanged(*self._time_signature))

    async def play(self):
        pass

    async def seek(self, offset):
        pass

    async def stop(self):
        pass

    ### PUBLIC PROPERTIES ###

    @property
    def channel_count(self) -> int:
        return self._channel_count

    @property
    def clock(self) -> Union[AsyncTempoClock, OfflineTempoClock]:
        return self._clock

    @property
    def contexts(self) -> Tuple[Context, ...]:
        return self._contexts

    @property
    def controllers(self) -> Tuple[Controller, ...]:
        return self._controllers

    @property
    def is_looping(self) -> bool:
        return self._is_looping

    @property
    def loop_points(self) -> Tuple[float, float]:
        return self._loop_points

    @property
    def parent(self) -> None:
        return None

    @property
    def primary_context(self) -> Optional[Context]:
        if not self.contexts:
            return None
        return self.contexts[0]

    @property
    def pubsub(self):
        return self._pubsub

    @property
    def registry(self) -> Mapping[UUID, "tloen.domain.ApplicationObject"]:
        return MappingProxyType(self._registry)

    @property
    def scenes(self):
        return self._scenes

    @property
    def status(self):
        return self._status

    @property
    def tempo(self) -> float:
        return self._tempo

    @property
    def time_signature(self) -> Tuple[int, int]:
        return self._time_signature


@dataclasses.dataclass
class ApplicationBooting(Event):
    ...


@dataclasses.dataclass
class ApplicationBooted(Event):
    port: int


@dataclasses.dataclass
class ApplicationLoaded(Event):
    ...


@dataclasses.dataclass
class ApplicationQuitting(Event):
    ...


@dataclasses.dataclass
class ApplicationQuit(Event):
    ...


@dataclasses.dataclass
class ApplicationStatusRefreshed(Event):
    status: StatusResponse


@dataclasses.dataclass
class ApplicationLoopingChanged(Event):
    is_looping: bool


@dataclasses.dataclass
class ApplicationLoopPointsChanged(Event):
    from_: float
    to: float


@dataclasses.dataclass
class ApplicationTempoChanged(Event):
    tempo: float


@dataclasses.dataclass
class ApplicationTimeSignatureChanged(Event):
    numerator: int
    denominator: int
