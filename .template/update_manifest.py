"""Update file hashes after editing the template. Run before tests and commits."""

import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
excluded = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".ty_cache"}
manifest = root / ".template/manifest.json"
files = {
    str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(root.rglob("*"))
    if path.is_file() and path != manifest and not excluded.intersection(path.relative_to(root).parts)
}
manifest.write_text(json.dumps(files, indent=2) + "\n")
