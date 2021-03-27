import pytest

from tloen.domain import Application, Track


@pytest.mark.asyncio
async def test_1():
    """
    Add one track
    """
    application = Application()
    context = await application.add_context()
    track = await context.add_track()
    assert isinstance(track, Track)
    assert len(track.postfader_sends) == 1
    assert list(context.tracks) == [track]
    assert track.application is context.application
    assert track.graph_order == (3, 0, 0, 0)
    assert track.parent is context.tracks
    assert track.postfader_sends[0].effective_target is context.master_track
    assert track.provider is context.provider


@pytest.mark.asyncio
async def test_2():
    """
    Add two tracks
    """
    application = Application()
    context = await application.add_context()
    track_one = await context.add_track()
    track_two = await context.add_track()
    assert list(context.tracks) == [track_one, track_two]
    assert track_one.application is context.application
    assert track_one.graph_order == (3, 0, 0, 0)
    assert track_one.parent is context.tracks
    assert track_one.provider is context.provider
    assert track_two.application is context.application
    assert track_two.graph_order == (3, 0, 0, 1)
    assert track_two.parent is context.tracks
    assert track_two.provider is context.provider


@pytest.mark.asyncio
async def test_3():
    """
    Add one track, boot, add second track
    """
    application = Application()
    context = await application.add_context()
    track_one = await context.add_track()
    await application.boot()
    track_two = await context.add_track()
    assert list(context.tracks) == [track_one, track_two]
    assert track_one.application is context.application
    assert track_one.graph_order == (3, 0, 0, 0)
    assert track_one.parent is context.tracks
    assert track_one.provider is context.provider
    assert track_two.application is context.application
    assert track_two.graph_order == (3, 0, 0, 1)
    assert track_two.parent is context.tracks
    assert track_two.provider is context.provider
