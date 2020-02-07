from tloen import Application


def test_1():
    """
    Remove one track
    """
    application = Application()
    context = application.add_context()
    parent = context.add_track()
    track = parent.add_track()
    parent.remove_tracks(track)
    assert list(parent.tracks) == []
    assert track.application is None
    assert track.graph_order == ()
    assert track.parent is None
    assert track.provider is None


def test_2():
    """
    Remove two tracks
    """
    application = Application()
    context = application.add_context()
    parent = context.add_track()
    track_one = parent.add_track()
    track_two = parent.add_track()
    parent.remove_tracks(track_one, track_two)
    assert list(parent.tracks) == []
    assert track_one.application is None
    assert track_one.graph_order == ()
    assert track_one.parent is None
    assert track_one.provider is None
    assert track_two.application is None
    assert track_two.graph_order == ()
    assert track_two.parent is None
    assert track_two.provider is None


def test_3():
    """
    Remove first track, leaving second untouched
    """
    application = Application()
    context = application.add_context()
    parent = context.add_track()
    track_one = parent.add_track()
    track_two = parent.add_track()
    parent.remove_tracks(track_one)
    assert list(parent.tracks) == [track_two]
    assert track_one.application is None
    assert track_one.graph_order == ()
    assert track_one.parent is None
    assert track_one.provider is None
    assert track_two.application is context.application
    assert track_two.graph_order == (3, 0, 0, 0, 1, 0)
    assert track_two.parent is parent.tracks
    assert track_two.provider is None


def test_4():
    """
    Boot, remove first track, leaving second untouched
    """
    application = Application()
    context = application.add_context()
    parent = context.add_track()
    track_one = parent.add_track()
    track_two = parent.add_track()
    application.boot()
    with context.provider.server.osc_protocol.capture() as transcript:
        parent.remove_tracks(track_one)
    assert list(parent.tracks) == [track_two]
    assert track_one.application is None
    assert track_one.graph_order == ()
    assert track_one.parent is None
    assert track_one.provider is None
    assert track_two.application is context.application
    assert track_two.graph_order == (3, 0, 0, 0, 1, 0)
    assert track_two.parent is parent.tracks
    assert track_two.provider is context.provider
    assert len(transcript.sent_messages) == 1
    _, message = transcript.sent_messages[0]
    assert message.to_list() == [None, [[15, 1009, "gate", 0]]]
