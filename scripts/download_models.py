"""
Download the four ONNX models PixelMorph needs, into a target folder.

Sources are the official facefusion-assets GitHub releases (checked 2026-11).

Usage:
    python scripts/download_models.py            # -> ./models
    python scripts/download_models.py --dir C:\my\models
    python scripts/download_models.py --models inswapper_128 scrfd_2.5g
"""
import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

BASE = "https://github.com/facefusion/facefusion-assets/releases/download"

MODELS = {
    "inswapper_128": {
        "file": "inswapper_128.onnx",
        "url": f"{BASE}/models-3.0.0/inswapper_128.onnx",
        "size_mb": 530,
        "shasum_url": f"{BASE}/models-3.0.0/inswapper_128.hash",
    },
    "scrfd_2.5g": {
        "file": "scrfd_2.5g.onnx",
        "url": f"{BASE}/models-3.0.0/scrfd_2.5g.onnx",
        "size_mb": 4,
        "shasum_url": f"{BASE}/models-3.0.0/scrfd_2.5g.hash",
    },
    "arcface_w600k_r50": {
        "file": "arcface_w600k_r50.onnx",
        "url": f"{BASE}/models-3.0.0/arcface_w600k_r50.onnx",
        "size_mb": 167,
        "shasum_url": f"{BASE}/models-3.0.0/arcface_w600k_r50.hash",
    },
    "hyperswap_1a_256": {
        "file": "hyperswap_1a_256.onnx",
        "url": f"{BASE}/models-3.3.0/hyperswap_1a_256.onnx",
        "size_mb": 385,
        "shasum_url": f"{BASE}/models-3.3.0/hyperswap_1a_256.hash",
    },
}


def _mb(bytes_downloaded: int) -> float:
    return bytes_downloaded / (1024 * 1024)


def _print_progress(blocks: int, block_size: int, total: int):
    if total <= 0:
        return
    done = min(1.0, blocks * block_size / total)
    bar = "#" * int(30 * done)
    sys.stdout.write(f"\r  [{bar:<30}] {_mb(blocks * block_size):6.1f}/{_mb(total):6.1f} MB ")
    sys.stdout.flush()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(name: str, spec: dict, dest_dir: Path, verify: bool = True) -> bool:
    dest = dest_dir / spec["file"]
    if dest.exists():
        if verify and spec.get("shasum_url"):
            ok = check_hash(name, spec, dest_dir)
            if ok:
                print(f"  {name}: already present, hash OK")
                return True
            dest.unlink()
            print(f"  {name}: present but hash MISMATCH -> re-downloading")
        else:
            print(f"  {name}: already present")
            return True
    print(f"  {name}: {spec['size_mb']} MB from {spec['url']}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        urllib.request.urlretrieve(spec["url"], tmp, reporthook=_print_progress)
        print()
    except Exception as e:
        print(f"\n  FAILED to download {name}: {e}")
        return False
    tmp.rename(dest)

    if verify:
        try:
            expected = urllib.request.urlopen(spec["shasum_url"], timeout=30)\
                .read().decode().strip().split(" ")[0].lower()
            actual = _sha256_file(dest)
            if actual != expected:
                print(f"  {name}: SHA256 MISMATCH ({actual[:16]}... != {expected[:16]}...)")
                dest.unlink()
                return False
            print(f"  {name}: hash verified OK")
        except Exception as e:
            print(f"  {name}: hash check skipped ({e})")
    return True


def check_hash(name: str, spec: dict, dest_dir: Path) -> bool:
    dest = dest_dir / spec["file"]
    try:
        expected = urllib.request.urlopen(spec["shasum_url"], timeout=30)\
            .read().decode().strip().split(" ")[0].lower()
        return _sha256_file(dest) == expected
    except Exception:
        return dest.exists() and dest.stat().st_size > 1000


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(REPO_ROOT / "models"))
    ap.add_argument("--models", nargs="*", default=None,
                    help="subset: inswapper_128 scrfd_2.5g arcface_w600k_r50 hyperswap_1a_256")
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()

    wanted = args.models or list(MODELS)
    unknown = [w for w in wanted if w not in MODELS]
    if unknown:
        print("Unknown model names:", ", ".join(unknown))
        print("Valid:", ", ".join(MODELS))
        return 1

    dest_dir = Path(args.dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    print(f"PixelMorph model downloader -> {dest_dir}")

    failed = [n for n in wanted if not download(n, MODELS[n], dest_dir, verify=not args.no_verify)]

    if failed:
        print("\nfailed:", ", ".join(failed))
        return 1
    print("\nAll models ready. PixelMorph auto-detects them in this folder"
          " (models_path.txt or PIXELMORPH_MODELS env also work).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
