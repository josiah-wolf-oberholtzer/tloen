import asyncio

import pytest
from supriya.synthdefs import SynthDefCompiler, SynthDefFactory
from uqbar.strings import normalize

from tloen.domain import (
    Application,
    AudioEffect,
    DeviceIn,
    DeviceOut,
    Instrument,
)


@pytest.fixture
def synthdef_factory():
    factory = (
        SynthDefFactory()
        .with_channel_count(2)
        .with_input()
        .with_signal_block(lambda builder, source, state: (source * -3) + 0.25)
        .with_gate(0.01, 0.01)
        .with_output(replacing=True)
    )
    return factory


@pytest.mark.asyncio
async def test_AudioEffect_1(synthdef_factory):
    """
    Add one device
    """
    application = Application()
    context = await application.add_context()
    track = await context.add_track()
    device = await track.add_device(AudioEffect, synthdef=synthdef_factory)
    assert isinstance(device, AudioEffect)
    assert device.synthdef == synthdef_factory
    assert list(track.devices) == [device]
    assert device.application is context.application
    assert device.graph_order == (2, 0, 0, 0, 6, 0)
    assert device.parent is track.devices
    assert device.provider is context.provider


@pytest.mark.asyncio
async def test_AudioEffect_2(synthdef_factory):
    """
    Add two devices
    """
    application = Application()
    context = await application.add_context()
    track = await context.add_track()
    device_one = await track.add_device(AudioEffect, synthdef=synthdef_factory)
    device_two = await track.add_device(AudioEffect, synthdef=synthdef_factory)
    assert list(track.devices) == [device_one, device_two]
    assert device_one.application is context.application
    assert device_one.graph_order == (2, 0, 0, 0, 6, 0)
    assert device_one.parent is track.devices
    assert device_one.provider is context.provider
    assert device_two.application is context.application
    assert device_two.graph_order == (2, 0, 0, 0, 6, 1)
    assert device_two.parent is track.devices
    assert device_two.provider is context.provider


@pytest.mark.asyncio
async def test_AudioEffect_3(synthdef_factory):
    """
    Boot, add one device
    """
    synthdef = synthdef_factory.build(channel_count=2)
    application = Application()
    context = await application.add_context()
    track = await context.add_track()
    await application.boot()
    with context.provider.server.osc_protocol.capture() as transcript:
        device = await track.add_device(AudioEffect, synthdef=synthdef_factory)
    assert list(track.devices) == [device]
    assert device.application is context.application
    assert device.graph_order == (2, 0, 0, 0, 6, 0)
    assert device.parent is track.devices
    assert device.provider is context.provider
    assert len(transcript.sent_messages) == 1
    _, message = transcript.sent_messages[0]
    compiled_synthdefs = bytearray(
        SynthDefCompiler.compile_synthdefs(
            [synthdef, DeviceOut.build_synthdef(2, 2), DeviceIn.build_synthdef(2, 2)]
        )
    )
    bundle_contents = [
        ["/g_new", 1044, 1, 1013],
        ["/g_new", 1045, 1, 1044],
        ["/s_new", synthdef.anonymous_name, 1046, 0, 1045, "out", 28.0],
        ["/s_new", "mixer/patch[replace]/2x2", 1047, 0, 1044, "in_", 18.0, "out", 28.0],
        [
            "/s_new",
            "mixer/patch[hard,mix]/2x2",
            1048,
            1,
            1044,
            "in_",
            28.0,
            "out",
            18.0,
        ],
    ]
    assert message.to_list() == [
        None,
        [["/d_recv", compiled_synthdefs, [None, bundle_contents]]],
    ]
    await asyncio.sleep(0.1)
    assert track.peak_levels == dict(
        input=(0.0, 0.0), postfader=(0.25, 0.25), prefader=(0.25, 0.25)
    )
    assert context.master_track.peak_levels == dict(
        input=(0.25, 0.25), postfader=(0.25, 0.25), prefader=(0.25, 0.25)
    )


@pytest.mark.asyncio
async def test_AudioEffect_4(synthdef_factory):
    """
    Add one device, boot, add second device
    """
    synthdef = synthdef_factory.build(channel_count=2)
    application = Application()
    context = await application.add_context()
    track = await context.add_track()
    device_one = await track.add_device(AudioEffect, synthdef=synthdef_factory)
    await application.boot()
    with context.provider.server.osc_protocol.capture() as transcript:
        device_two = await track.add_device(AudioEffect, synthdef=synthdef_factory)
    assert list(track.devices) == [device_one, device_two]
    assert device_one.application is context.application
    assert device_one.graph_order == (2, 0, 0, 0, 6, 0)
    assert device_one.parent is track.devices
    assert device_one.provider is context.provider
    assert device_two.application is context.application
    assert device_two.graph_order == (2, 0, 0, 0, 6, 1)
    assert device_two.parent is track.devices
    assert device_two.provider is context.provider
    assert len(transcript.sent_messages) == 1
    _, message = transcript.sent_messages[0]
    assert message.to_list() == [
        None,
        [
            ["/g_new", 1049, 1, 1013],
            ["/g_new", 1050, 1, 1049],
            ["/s_new", synthdef.anonymous_name, 1051, 0, 1050, "out", 30.0],
            [
                "/s_new",
                "mixer/patch[replace]/2x2",
                1052,
                0,
                1049,
                "in_",
                18.0,
                "out",
                30.0,
            ],
            [
                "/s_new",
                "mixer/patch[hard,mix]/2x2",
                1053,
                1,
                1049,
                "in_",
                30.0,
                "out",
                18.0,
            ],
        ],
    ]
    await asyncio.sleep(0.1)
    assert track.peak_levels == dict(
        input=(0.0, 0.0), postfader=(0.5, 0.5), prefader=(0.5, 0.5)
    )
    assert context.master_track.peak_levels == dict(
        input=(0.5, 0.5), postfader=(0.5, 0.5), prefader=(0.5, 0.5)
    )


@pytest.mark.asyncio
async def test_AudioEffect_query(synthdef_factory):
    application = Application()
    context = await application.add_context()
    track = await context.add_track()
    await application.boot()
    await track.add_device(AudioEffect, synthdef=synthdef_factory)
    assert format(await track.query(), "unindexed") == normalize(
        """
        NODE TREE ... group (Track)
            ... group (Parameters)
                ... group (gain)
                ... group (panning)
            ... group (Receives)
            ... mixer/patch[fb,gain]/2x2 (Input)
                active: 1.0, gain: 0.0, gate: 1.0, in_: 16.0, lag: 0.01, out: 18.0
            ... group (SubTracks)
            ... mixer/levels/2 (InputLevels)
                out: 18.0, gate: 1.0, lag: 0.01
            ... group (Devices)
                ... group (AudioEffect)
                    ... mixer/patch[replace]/2x2 (DeviceIn)
                        active: 1.0, gate: 1.0, in_: 18.0, lag: 0.01, out: 28.0
                    ... group (Body)
                        ... e2f7071cbafa6a2884524e116f015fa9
                            out: 28.0, gate: 1.0
                    ... mixer/patch[hard,mix]/2x2 (DeviceOut)
                        active: 1.0, gate: 1.0, hard_gate: 1.0, in_: 28.0, lag: 0.01, mix: 1.0, out: 18.0
            ... mixer/levels/2 (PrefaderLevels)
                out: 18.0, gate: 1.0, lag: 0.01
            ... group (PreFaderSends)
            ... mixer/patch[gain,hard,replace]/2x2 (Output)
                active: 1.0, gain: c0, gate: 1.0, hard_gate: 1.0, in_: 18.0, lag: 0.01, out: 18.0
            ... group (PostFaderSends)
                ... mixer/patch[gain]/2x2 (Send)
                    active: 1.0, gain: 0.0, gate: 1.0, in_: 18.0, lag: 0.01, out: 22.0
            ... mixer/levels/2 (PostfaderLevels)
                out: 18.0, gate: 1.0, lag: 0.01
        """
    )


@pytest.mark.asyncio
async def test_Instrument_query(dc_instrument_synthdef_factory):
    application = Application()
    context = await application.add_context()
    track = await context.add_track()
    await application.boot()
    await track.add_device(Instrument, synthdef=dc_instrument_synthdef_factory)
    assert format(await track.query(), "unindexed") == normalize(
        """
        NODE TREE ... group (Track)
            ... group (Parameters)
                ... group (gain)
                ... group (panning)
            ... group (Receives)
            ... mixer/patch[fb,gain]/2x2 (Input)
                active: 1.0, gain: 0.0, gate: 1.0, in_: 16.0, lag: 0.01, out: 18.0
            ... group (SubTracks)
            ... mixer/levels/2 (InputLevels)
                out: 18.0, gate: 1.0, lag: 0.01
            ... group (Devices)
                ... group (Instrument)
                    ... mixer/patch[replace]/2x2 (DeviceIn)
                        active: 1.0, gate: 1.0, in_: 18.0, lag: 0.01, out: 28.0
                    ... group (Body)
                    ... mixer/patch[hard,mix]/2x2 (DeviceOut)
                        active: 1.0, gate: 1.0, hard_gate: 1.0, in_: 28.0, lag: 0.01, mix: 1.0, out: 18.0
            ... mixer/levels/2 (PrefaderLevels)
                out: 18.0, gate: 1.0, lag: 0.01
            ... group (PreFaderSends)
            ... mixer/patch[gain,hard,replace]/2x2 (Output)
                active: 1.0, gain: c0, gate: 1.0, hard_gate: 1.0, in_: 18.0, lag: 0.01, out: 18.0
            ... group (PostFaderSends)
                ... mixer/patch[gain]/2x2 (Send)
                    active: 1.0, gain: 0.0, gate: 1.0, in_: 18.0, lag: 0.01, out: 22.0
            ... mixer/levels/2 (PostfaderLevels)
                out: 18.0, gate: 1.0, lag: 0.01
        """
    )
