import dataclasses
from collections import deque
from typing import Optional, Tuple
from uuid import UUID, uuid4

from supriya.clock import TimeUnit
from supriya.intervals import IntervalTree

from tloen.midi import NoteOffMessage, NoteOnMessage

from ..bases import Event
from .bases import ApplicationObject


@dataclasses.dataclass(frozen=True, order=True)
class Note:
    start_offset: Optional[float] = None
    stop_offset: Optional[float] = None
    pitch: float = 0.0
    velocity: float = 100.0

    def __post_init__(self):
        if self.start_offset >= self.stop_offset:
            raise ValueError

    def _serialize(self):
        return dict(
            start_offset=self.start_offset,
            stop_offset=self.stop_offset,
            pitch=self.pitch,
            velocity=self.velocity,
        )

    def transpose(self, transposition):
        return dataclasses.replace(self, self.pitch + transposition)

    def translate(self, start_translation=None, stop_translation=None):
        start_offset = self.start_offset + (start_translation or 0)
        stop_offset = self.stop_offset + (stop_translation or 0)
        return dataclasses.replace(
            self, start_offset=start_offset, stop_offset=stop_offset
        )


@dataclasses.dataclass(frozen=True)
class NoteMoment:
    offset: float = 0.0
    local_offset: float = 0.0
    next_offset: Optional[float] = None
    start_notes: Optional[Tuple[Note]] = None
    stop_notes: Optional[Tuple[Note]] = None
    overlap_notes: Optional[Tuple[Note]] = None

    @property
    def note_on_messages(self):
        return [
            NoteOnMessage(pitch=note.pitch, velocity=note.velocity)
            for note in self.start_notes or ()
        ]

    @property
    def note_off_messages(self):
        return [
            NoteOffMessage(pitch=note.pitch, velocity=note.velocity)
            for note in self.stop_notes or ()
        ]


class Envelope:
    """
    An automation envelope, in a Clip or Timeline.
    """

    pass


class ClipObject(ApplicationObject):

    ### INITIALIZER ###

    def __init__(self, *, name=None, uuid=None):
        ApplicationObject.__init__(self, name=name)
        self._uuid = uuid or uuid4()

    ### INITIALIZER ###

    def at(self, offset, start_delta=0.0, force_stop=False):
        pass

    ### PUBLIC PROPERTIES ###

    @property
    def uuid(self):
        return self._uuid


class Clip(ClipObject):

    ### INITIALIZER ###

    def __init__(
        self, *, duration=4 / 4, is_looping=True, name=None, notes=None, uuid=None
    ):
        ClipObject.__init__(self, name=name, uuid=uuid)
        self._duration = float(duration)
        self._is_looping = is_looping
        self._is_playing = False
        self._start_delta = 0.0
        self._interval_tree = IntervalTree()
        self._add_notes(notes or [])

    ### SPECIAL METHODS ###

    def __str__(self):
        obj_name = type(self).__name__
        return "\n".join(
            [
                f"<{obj_name} {self.uuid}>",
                *(f"    {line}" for child in self for line in str(child).splitlines()),
            ]
        )

    ### PRIVATE METHODS ###

    def _add_notes(self, notes):
        def validate_new_notes(new_notes):
            validated_new_notes = [new_notes.popleft()]
            while new_notes:
                current_note = new_notes.popleft()
                previous_note = validated_new_notes[-1]
                if current_note.start_offset < previous_note.stop_offset:
                    # simultaneous new note starts: longer note wins
                    if current_note.start_offset == previous_note.start_offset:
                        new_stop_offset = max(
                            (current_note.stop_offset, previous_note.stop_offset)
                        )
                        new_velocity = max(
                            (current_note.velocity, previous_note.velocity)
                        )
                        validated_new_notes[-1] = dataclasses.replace(
                            previous_note,
                            stop_offset=new_stop_offset,
                            velocity=new_velocity,
                        )
                        continue
                    # new note overlaps: later notes masks earlier note
                    else:
                        validated_new_notes[-1] = dataclasses.replace(
                            previous_note, stop_offset=current_note.start_offset
                        )
                validated_new_notes.append(current_note)
            return validated_new_notes

        def invalidate_old_notes(new_notes, old_notes):
            invalidated_old_notes = []
            truncated_old_notes = []
            if not old_notes:
                return invalidated_old_notes, truncated_old_notes
            iterator = iter(new_notes)
            new_note = next(iterator)
            for old_note in old_notes:
                while new_note.stop_offset <= old_note.start_offset:
                    try:
                        new_note = next(iterator)
                    except StopIteration:
                        return invalidated_old_notes, truncated_old_notes
                if (
                    new_note.start_offset
                    <= old_note.start_offset
                    < new_note.stop_offset
                ):
                    invalidated_old_notes.append(old_note)
                elif (
                    old_note.start_offset < new_note.start_offset < old_note.stop_offset
                ):
                    invalidated_old_notes.append(old_note)
                    truncated_old_notes.append(
                        dataclasses.replace(old_note, stop_offset=new_note.start_offset)
                    )
            return invalidated_old_notes, truncated_old_notes

        self._debug_tree(self, "Editing")
        to_add = []
        to_remove = []
        new_notes_by_pitch = {}
        for note in sorted(notes):
            new_notes_by_pitch.setdefault(note.pitch, deque()).append(note)
        old_notes_by_pitch = {}
        for note in self._interval_tree:
            old_notes_by_pitch.setdefault(note.pitch, []).append(note)
        for pitch, new_notes in new_notes_by_pitch.items():
            validated_new_notes = validate_new_notes(new_notes)
            invalidated_old_notes, truncated_old_notes = invalidate_old_notes(
                validated_new_notes, old_notes_by_pitch.get(pitch, [])
            )
            to_add.extend(validated_new_notes)
            to_add.extend(truncated_old_notes)
            to_remove.extend(invalidated_old_notes)
        self._remove_notes(to_remove)
        self._interval_tree.update(to_add)

    @classmethod
    async def _deserialize(cls, data, application) -> bool:
        parent_uuid = UUID(data["meta"]["parent"])
        parent = application.registry.get(parent_uuid)
        if parent is None:
            return True
        clip = cls(
            duration=data["spec"].get("duration", 4 / 4),
            is_looping=bool(data["spec"].get("is_looping", True)),
            name=data["meta"].get("name"),
            notes=[Note(**note_spec) for note_spec in data["spec"].get("notes", [])],
            uuid=UUID(data["meta"]["uuid"]),
        )
        parent._append(clip)
        return False

    async def _notify(self):
        self._debug_tree(self, "Notifying")
        if self.application is None:
            return
        if self.is_playing:
            track = self.parent.parent.parent
            await self.transport.reschedule(
                track._clip_perform_event_id,
                schedule_at=self.transport._clock.get_current_time(),
                time_unit=TimeUnit.SECONDS,
            )
        self.application.pubsub.publish(ClipModified(self.uuid))

    def _remove_notes(self, notes):
        self._debug_tree(self, "Editing")
        for note in notes:
            self._interval_tree.remove(note)

    def _serialize(self):
        serialized, auxiliary_entities = super()._serialize()
        if self.parent is not None:
            serialized["meta"]["parent"] = str(self.parent.uuid)
        serialized["spec"]["notes"] = []
        for note in self.notes:
            serialized["spec"]["notes"].append(note._serialize())
        return serialized, auxiliary_entities

    ### PUBLIC METHODS ###

    async def add_notes(self, notes):
        self._add_notes(notes)
        await self._notify()

    def at(self, offset, start_delta=0.0, force_stop=False):
        start_notes, stop_notes, overlap_notes = [], [], []
        local_offset = loop_local_offset = offset - start_delta
        count = 0
        if self.is_looping and local_offset >= 0.0:
            count, loop_local_offset = divmod(local_offset, self.clip_stop)
        moment = self._interval_tree.get_moment_at(loop_local_offset)
        start_notes = moment.start_intervals
        stop_notes = moment.stop_intervals
        overlap_notes = moment.overlap_intervals
        if count and not loop_local_offset:  # at a non-zero loop boundary
            moment_two = self._interval_tree.get_moment_at(self.duration)
            stop_notes.extend(moment_two.overlap_intervals)
            stop_notes.extend(moment_two.stop_intervals)
        next_offset = self._interval_tree.get_offset_after(loop_local_offset)
        if next_offset is None and self.is_looping:
            next_offset = self.duration
        if next_offset is not None:
            if self.is_looping:
                next_offset = min([next_offset, self.duration])
            next_offset += start_delta + (count * self.duration)
        if force_stop:
            start_notes[:] = []
            stop_notes.extend(overlap_notes)
            overlap_notes[:] = []
            next_offset = None
        return NoteMoment(
            offset=offset,
            local_offset=loop_local_offset,
            next_offset=next_offset,
            start_notes=start_notes or None,
            stop_notes=stop_notes or None,
            overlap_notes=overlap_notes or None,
        )

    async def remove_notes(self, notes):
        self._remove_notes(notes)
        await self._notify()

    ### PUBLIC PROPERTIES ###

    @property
    def clip_start(self):
        return 0.0

    @property
    def clip_stop(self):
        return self._duration if self.is_looping else self._notes.stop_offset

    @property
    def duration(self):
        return self._duration

    @property
    def is_looping(self):
        return self._is_looping

    @property
    def is_playing(self):
        return self._is_playing

    @property
    def notes(self):
        return sorted(self._interval_tree)

    @property
    def clip_delta(self):
        return self._clip_delta


class Slot(ApplicationObject):

    ### INITIALIZER ###

    def __init__(self, *, name=None, uuid=None):
        ApplicationObject.__init__(self, name=name)
        self._uuid = uuid or uuid4()

    ### SPECIAL METHODS ###

    def __str__(self):
        obj_name = type(self).__name__
        return "\n".join(
            [
                f"<{obj_name} {self.uuid}>",
                *(f"    {line}" for child in self for line in str(child).splitlines()),
            ]
        )

    ### PRIVATE METHODS ###

    @classmethod
    async def _deserialize(cls, data, application) -> bool:
        parent_uuid = UUID(data["meta"]["parent"])
        parent = application.registry.get(parent_uuid)
        if parent is None:
            return True
        slot = cls(uuid=UUID(data["meta"]["uuid"]))
        parent.slots._append(slot)
        return False

    def _serialize(self):
        serialized, auxiliary_entities = super()._serialize()
        if self.clip is not None:
            serialized["spec"]["clip"] = str(self.clip.uuid)
            clip_entities = self.clip._serialize()
            auxiliary_entities.append(clip_entities[0])
            auxiliary_entities.extend(clip_entities[1])
        return serialized, auxiliary_entities

    async def _set_clip(self, clip):
        async with self.lock([self]):
            if clip is self.clip:
                return
            if self.clip is not None:
                self._remove(self.clip)
            if clip is not None:
                self._append(clip)

    ### PUBLIC METHODS ###

    async def add_clip(self, *, notes=None, is_looping=True):
        clip = Clip(notes=notes, is_looping=is_looping)
        await self._set_clip(clip)
        return clip

    async def duplicate_clip(self):
        pass

    async def fire(self):
        if not self.application:
            return
        track = self.track
        if track is None:
            return
        await track._fire(self.parent.index(self))
        self.application.pubsub.publish(SlotFired(self.uuid))

    async def move_clip(self, slot):
        await slot._set_clip(self.clip)

    async def remove_clip(self):
        await self._set_clip(None)

    ### PUBLIC PROPERTIES ###

    @property
    def clip(self):
        try:
            return self[0]
        except IndexError:
            return None

    @property
    def track(self):
        from .tracks import Track

        for parent in self.parentage[1:]:
            if isinstance(parent, Track):
                return parent
        return None

    @property
    def uuid(self):
        return self._uuid


class Scene(ApplicationObject):

    ### INITIALIZER ###

    def __init__(self, *, name=None, uuid=None):
        ApplicationObject.__init__(self, name=name)
        self._uuid = uuid or uuid4()

    ### SPECIAL METHODS ###

    def __str__(self):
        obj_name = type(self).__name__
        return "\n".join(
            [
                f"<{obj_name} {self.uuid}>",
                *(f"    {line}" for child in self for line in str(child).splitlines()),
            ]
        )

    ### PRIVATE METHODS ###

    @classmethod
    async def _deserialize(cls, data, application) -> bool:
        scene = cls(uuid=UUID(data["meta"]["uuid"]))
        application.scenes._append(scene)
        return False

    ### PUBLIC METHODS ###

    def delete(self):
        pass

    def duplicate(self):
        pass

    async def fire(self):
        pass

    ### PUBLIC PROPERTIES ###

    @property
    def uuid(self):
        return self._uuid


class Timeline:
    pass


@dataclasses.dataclass
class ClipLaunched(Event):
    clip_uuid: UUID


@dataclasses.dataclass
class ClipModified(Event):
    clip_uuid: UUID


@dataclasses.dataclass
class SlotFired(Event):
    slot_uuid: UUID
