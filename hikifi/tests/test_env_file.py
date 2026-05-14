from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.utils.env_file import load_env_file


def test_load_env_file_does_not_override_shell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HIK_USER", "from_shell")
    monkeypatch.delenv("HIK_PASS", raising=False)
    p = tmp_path / ".env"
    p.write_text("HIK_USER=from_file\nHIK_PASS=secret\n", encoding="utf-8")
    load_env_file(p)
    assert os.environ["HIK_USER"] == "from_shell"
    assert os.environ["HIK_PASS"] == "secret"


def test_inline_comment_outside_quotes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("FOO", raising=False)
    p = tmp_path / ".env"
    p.write_text('FOO=bar # not part of value\n', encoding="utf-8")
    load_env_file(p)
    assert os.environ["FOO"] == "bar"
