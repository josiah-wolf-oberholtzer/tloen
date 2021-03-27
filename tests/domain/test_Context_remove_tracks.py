import pytest

from tloen.domain import Application


@pytest.mark.asyncio
async def test_1():
    """
    Remove one track
    """
    application = Application()
    context = await application.add_context()
    track = await context.add_track()
    await context.remove_tracks(track)
    assert list(context.tracks) == []
    assert track.application is None
    assert track.graph_order == ()
    assert track.parent is None
    assert track.provider is None


@pytest.mark.asyncio
async def test_2():
    """
    Remove two tracks
    """
    application = Application()
    context = await application.add_context()
    track_one = await context.add_track()
    track_two = await context.add_track()
    await context.remove_tracks(track_one, track_two)
    assert list(context.tracks) == []
    assert track_one.application is None
    assert track_one.graph_order == ()
    assert track_one.parent is None
    assert track_one.provider is None
    assert track_two.application is None
    assert track_two.graph_order == ()
    assert track_two.parent is None
    assert track_two.provider is None


@pytest.mark.asyncio
async def test_3():
    """
    Remove first track, leaving second untouched
    """
    application = Application()
    context = await application.add_context()
    track_one = await context.add_track()
    track_two = await context.add_track()
    await context.remove_tracks(track_one)
    assert list(context.tracks) == [track_two]
    assert track_one.application is None
    assert track_one.graph_order == ()
    assert track_one.parent is None
    assert track_one.provider is None
    assert track_two.application is context.application
    assert track_two.graph_order == (3, 0, 0, 0)
    assert track_two.parent is context.tracks
    assert track_two.provider is None


@pytest.mark.asyncio
async def test_4():
    """
    Boot, remove first track, leaving second untouched
    """
    application = Application()
    context = await application.add_context()
    track_one = await context.add_track()
    track_two = await context.add_track()
    await application.boot()
    await context.remove_tracks(track_one)
    assert context.provider is not None
    assert list(context.tracks) == [track_two]
    assert track_one.application is None
    assert track_one.graph_order == ()
    assert track_one.parent is None
    assert track_one.provider is None
    assert track_two.application is context.application
    assert track_two.graph_order == (3, 0, 0, 0)
    assert track_two.parent is context.tracks
    assert track_two.provider is context.provider
