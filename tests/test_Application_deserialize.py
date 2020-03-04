import pytest
import yaml

from tloen.domain import Application, Arpeggiator, BasicSampler, RackDevice


@pytest.mark.asyncio
async def test_1():
    app_one = await Application.new(1, 1, 1)
    app_two = await Application.deserialize(app_one.serialize())
    assert app_one is not app_two
    assert yaml.dump(app_one.serialize()) == yaml.dump(app_two.serialize())


@pytest.mark.asyncio
async def test_2():
    app_one = await Application.new(1, 2, 1)
    track_one = app_one.contexts[0].tracks[0]
    track_two = app_one.contexts[0].tracks[1]
    await track_one.add_send(track_one)
    await track_one.add_send(track_two)
    await track_two.add_send(track_one)
    app_two = await Application.deserialize(app_one.serialize())
    assert app_one is not app_two
    assert yaml.dump(app_one.serialize()) == yaml.dump(app_two.serialize())


@pytest.mark.asyncio
async def test_3():
    app_one = Application()
    context = await app_one.add_context()
    track_one = await context.add_track(name="One")
    track_two = await context.add_track(name="Two")
    await track_one.solo(exclusive=False)
    await track_two.solo(exclusive=False)
    assert track_one.is_soloed and track_two.is_soloed
    app_two = await Application.deserialize(app_one.serialize())
    assert app_one is not app_two
    assert yaml.dump(app_one.serialize()) == yaml.dump(app_two.serialize())


@pytest.mark.asyncio
async def test_4():
    app_one = Application()
    context = await app_one.add_context()
    track_one = await context.add_track(name="One")
    track_two = await context.add_track(name="Two")
    await track_one.add_send(track_two)
    await track_one.solo(exclusive=False)
    await track_two.add_send(track_one)
    await track_two.solo(exclusive=False)
    await track_two.mute()
    await track_two.cue()
    rack = await track_one.add_device(RackDevice, channel_count=4)
    chain = await rack.add_chain()
    await chain.parameters["gain"].set_(-6.0)
    await chain.add_device(Arpeggiator)
    sampler = await chain.add_device(BasicSampler)
    await sampler.parameters["active"].set_(False)
    await sampler.parameters["buffer_id"].set_("tloen:samples/808/bd-long-03.wav")
    app_two = await Application.deserialize(app_one.serialize())
    assert app_one is not app_two
    assert yaml.dump(app_one.serialize()) == yaml.dump(app_two.serialize())
