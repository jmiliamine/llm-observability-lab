"""Copy the notes to index into build/corpus/, the only notes folder the Docker build can see.

  python scripts/stage_notes.py samples/notes
  python scripts/stage_notes.py D:/my-notes

Only .md and .txt files are copied (what `obslab ingest` reads), so a notes folder that also
holds images, PDFs or a .git directory does not bloat the image or leak into it.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "build" / "corpus"
SUFFIXES = {".md", ".txt"}


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    src = Path(sys.argv[1]).expanduser()
    if not src.is_absolute():
        src = ROOT / src
    if not src.is_dir():
        sys.exit(f"notes folder not found: {src}")
    shutil.rmtree(DEST, ignore_errors=True)
    n = 0
    for f in sorted(src.rglob("*")):
        rel = f.relative_to(src)
        if f.is_file() and f.suffix.lower() in SUFFIXES and not any(p.startswith(".") for p in rel.parts):
            (DEST / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, DEST / rel)
            n += 1
    if n == 0:
        sys.exit(f"no .md/.txt files under {src}")
    print(f"staged {n} notes from {src} into build/corpus/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
