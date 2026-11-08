"""CI secret scan — greps tracked files for common credential patterns."""
import re
import sys
from pathlib import Path

PATTERNS = [
    r"ghp_[A-Za-z0-9]{30,}",
    r"github_pat_[A-Za-z0-9_]{30,}",
    r"AKIA[0-9A-Z]{16}",
    r"sk-[A-Za-z0-9]{20,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"(api[_-]?key|secret|token)\s*[=:]\s*['\"][^'\"]{12,}",
]
SKIP_DIRS = {".git", "__pycache__", "models", "facefusion", ".idea"}
SKIP_EXT = {".onnx", ".dll", ".exe", ".jar", ".png", ".jpg", ".gif",
            ".webp", ".tlog", ".bin", ".obj", ".h", ".cpp", ".kt", ".xml",
            ".slnx", ".vcxproj", ".filters", ".sln", ".lastbuildstate"}


def main() -> int:
    offenders = []
    for f in Path(".").rglob("*"):
        parts = f.parts
        if any(p in SKIP_DIRS for p in parts) or f.suffix.lower() in SKIP_EXT:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for p in PATTERNS:
            if re.search(p, text, flags=re.IGNORECASE):
                offenders.append(f"{f}: pattern {p!r}")
    if offenders:
        for o in offenders:
            print("SECRET-LIKE:", o)
        return 1
    print("no secrets found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
