# Contributing to PixelMorph

Thanks for stopping by! Small, clearly-scoped PRs are the best PRs.

## Setup

```bash
git clone https://github.com/GUURUUU/PixelMorph.git
cd PixelMorph
pip install -r requirements.txt
python scripts/download_models.py     # or point models_path.txt at your own ONNX folder
python pixelmorph.py
```

Windows 10/11 + Python 3.10+ is the supported combo today (PyQt6 UI, DirectShow
camera stack). Python 3.12 tested.

## Tests

```bash
pip install pytest
pytest tests/ -q
python scripts/e2e_selftest.py      # full pipeline, needs models
python scripts/vcam_feed_test.py    # virtual-camera plumbing, no models needed
```

CI runs a dep-free subset; tests that need models skip automatically.

## Ground rules

- **Face math changes** must keep `app/ffcompat.py` self-contained — if you
  borrow logic from other projects, make sure the license is compatible and
  note the source in a comment.
- **No model weights in git.** Never commit `*.onnx`; the downloader script is
  the distribution path.
- **No secrets in history.** If you spot one, tell me privately first.
- The UI is PyQt6 + custom stylesheet — keep new widgets consistent with
  `app/styles.py`.

## Merge process

1. Fork / branch (`fix-something`)
2. `pytest tests/ -q` green locally
3. PR with a short description and what you verified
4. Reply to every review comment — force-push is fine before review, never after merge
