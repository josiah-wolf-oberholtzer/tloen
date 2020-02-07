import logging
import time

import pytest
from supriya.clock import Moment

from tloen import Application, Instrument, Note
from tloen.midi import NoteOffMessage, NoteOnMessage


@pytest.fixture(autouse=True)
def logger(caplog):
    caplog.set_level(logging.DEBUG, logger="supriya.clock")
    caplog.set_level(logging.DEBUG, logger="tloen")


@pytest.fixture
def application():
    application = Application.new(1, 2, 2).boot()
    track = application.contexts[0].tracks[0]
    track.add_device(Instrument)
    track.slots[0].add_clip(
        notes=[
            Note(0, 0.25, pitch=60),
            Note(0.25, 0.5, pitch=62),
            Note(0.5, 0.75, pitch=64),
            Note(0.75, 1.0, pitch=65),
        ]
    )
    yield application
    application.quit()


def test_1(mocker, application):
    """
    Fire non-empty slot, then fire empty-slot
    """
    time_mock = mocker.patch.object(application.transport._clock, "get_current_time")
    time_mock.return_value = 0.0
    with application.contexts[0].tracks[0].devices[0].capture() as transcript:
        application.contexts[0].tracks[0].slots[0].fire()
        time.sleep(0.01)
    assert application.transport.is_running
    assert list(transcript) == [
        Instrument.CaptureEntry(
            moment=Moment(
                beats_per_minute=120.0,
                measure=1,
                measure_offset=0.0,
                offset=0.0,
                seconds=0.0,
                time_signature=(4, 4),
            ),
            label="I",
            message=NoteOnMessage(pitch=60, velocity=100.0),
        )
    ]
    with application.contexts[0].tracks[0].devices[0].capture() as transcript:
        application.contexts[0].tracks[0].slots[1].fire()
        time.sleep(0.01)
    assert list(transcript) == [
        Instrument.CaptureEntry(
            moment=Moment(
                beats_per_minute=120.0,
                measure=1,
                measure_offset=0.0,
                offset=0.0,
                seconds=0.0,
                time_signature=(4, 4),
            ),
            label="I",
            message=NoteOffMessage(pitch=60),
        )
    ]


def test_2(mocker, application):
    """
    Fire non-empty slot, then re-fire same slot
    """
    time_mock = mocker.patch.object(application.transport._clock, "get_current_time")
    time_mock.return_value = 0.0
    with application.contexts[0].tracks[0].devices[0].capture() as transcript:
        application.contexts[0].tracks[0].slots[0].fire()
        time.sleep(0.01)
    assert application.transport.is_running
    assert list(transcript) == [
        Instrument.CaptureEntry(
            moment=Moment(
                beats_per_minute=120.0,
                measure=1,
                measure_offset=0.0,
                offset=0.0,
                seconds=0.0,
                time_signature=(4, 4),
            ),
            label="I",
            message=NoteOnMessage(pitch=60, velocity=100.0),
        )
    ]
    with application.contexts[0].tracks[0].devices[0].capture() as transcript:
        application.contexts[0].tracks[0].slots[0].fire()
        time.sleep(0.01)
    assert list(transcript) == [
        Instrument.CaptureEntry(
            moment=Moment(
                beats_per_minute=120.0,
                measure=1,
                measure_offset=0.0,
                offset=0.0,
                seconds=0.0,
                time_signature=(4, 4),
            ),
            label="I",
            message=NoteOffMessage(pitch=60),
        ),
        Instrument.CaptureEntry(
            moment=Moment(
                beats_per_minute=120.0,
                measure=1,
                measure_offset=0.0,
                offset=0.0,
                seconds=0.0,
                time_signature=(4, 4),
            ),
            label="I",
            message=NoteOnMessage(pitch=60, velocity=100.0),
        ),
    ]
