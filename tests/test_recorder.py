"""Exercise the real OpenCV writer without a camera, microphone or GUI."""

from pathlib import Path

import cv2
import numpy as np

from app.recorder import Recorder


def test_recorded_frames_keep_configured_dimensions(tmp_path, monkeypatch):
    width, height = 96, 64
    monkeypatch.setattr(Recorder, "_check_ffmpeg", staticmethod(lambda: False))
    recorder = Recorder()
    recorder.configure(width, height, fps=12, fmt="mp4")
    assert recorder.start(str(tmp_path))

    try:
        recorder.write_frame(np.full((height, width, 3), 64, dtype=np.uint8))
        # A frame with different dimensions must be resized to the writer size.
        recorder.write_frame(np.full((height * 2, width * 2, 3), 192, dtype=np.uint8))
    finally:
        output = recorder.stop()

    assert not recorder.recording
    assert output is not None
    path = Path(output)
    assert path.parent == tmp_path
    assert path.is_file()
    assert path.stat().st_size > 0

    decoded_shapes = []
    video = cv2.VideoCapture(str(path))
    try:
        assert video.isOpened()
        while True:
            ok, frame = video.read()
            if not ok:
                break
            decoded_shapes.append(frame.shape)
    finally:
        video.release()

    assert decoded_shapes == [(height, width, 3), (height, width, 3)]
