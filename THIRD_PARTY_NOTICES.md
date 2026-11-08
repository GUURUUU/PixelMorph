# Third-party notices

This repository bundles binaries and code from third parties. Their terms
apply unchanged.

## UnityCapture (UnityCapture/)

DirectShow virtual camera filter by schellingb.
Source: https://github.com/schellingb/UnityCapture

MIT License — Permission is hereby granted, free of charge, to any person
obtaining a copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including without
limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, subject to the above copyright
notice and this permission notice being included in all copies or substantial
portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND. IN NO EVENT
SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
OTHER LIABILITY.

Files covered: `UnityCapture/UnityCaptureFilter32.dll`,
`UnityCapture/UnityCaptureFilter64.dll` and the Install/Uninstall batch
scripts in the same folder.

## BestCam (BestCam/, BestCam/android/)

Media Foundation virtual camera source (C++) and an Android MJPEG camera app
written by the PixelMorph author, released under GPL-2.0 — see BestCam/LICENSE
and BestCam/android/LICENSE.

## Face swap model weights (NOT bundled)

- `inswapper_128.onnx` — InsightFace project (research license)
- `hyperswap_1a_256.onnx` — DeepFaceLab/facefusion community model
- `scrfd_2.5g.onnx`, `arcface_w600k_r50.onnx` — InsightFace (research license)

Model weights are obtained via `scripts/download_models.py` or brought by the
user; each carries the license of its originating project, and it is the
user's responsibility to use them in compliance with those licenses.
