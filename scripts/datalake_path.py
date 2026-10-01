"""Print the absolute path of the data lake folder, for the k3d volume mount.

  python scripts/datalake_path.py datalake
  python scripts/datalake_path.py D:/my-notes

Docker needs an absolute host path. Fails when the folder does not exist, so that the cluster
is not created with an empty mount in place of the notes.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    src = Path(sys.argv[1]).expanduser()
    if not src.is_absolute():
        src = ROOT / src
    if not src.is_dir():
        sys.exit(f"data lake not found: {src} is not a folder")
    print(src.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
