"""Load KEY=VALUE pairs from .env files into os.environ (optional, no extra deps)."""

from __future__ import annotations

import os
from pathlib import Path


def _strip_inline_comment(value: str) -> str:
    in_single = False
    in_double = False
    for i, ch in enumerate(value):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return value[:i].rstrip()
    return value


def _unquote(value: str) -> str:
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1]
    return v


def load_env_file(path: Path) -> int:
    """Apply variables from one file. Does not override keys already in os.environ.

    Returns number of variables set.
    """
    if not path.is_file():
        return 0
    count = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, rest = line.partition("=")
        key = key.strip()
        if not key:
            continue
        val = _strip_inline_comment(rest)
        val = _unquote(val)
        if key not in os.environ:
            os.environ[key] = val
            count += 1
    return count


def load_dotenv_for_config(config_path: Path) -> int:
    """Load .env from the config file directory, then cwd (deduped). Same rules as load_env_file."""
    candidates = [config_path.resolve().parent / ".env", Path.cwd() / ".env"]
    seen: set[Path] = set()
    total = 0
    for p in candidates:
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        total += load_env_file(p)
    return total
