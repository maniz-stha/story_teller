from types import SimpleNamespace
from unittest.mock import patch

import httpx

from story_teller.app import check_environment


def test_missing_ollama_is_reported():
    with patch("story_teller.app.shutil.which", side_effect=lambda name: None if name == "ollama" else name):
        assert any(c.name == "ollama" and not c.ok for c in check_environment())


def test_missing_ffmpeg_is_reported():
    with patch("story_teller.app.shutil.which", side_effect=lambda name: None if name == "ffmpeg" else name):
        assert any(c.name == "ffmpeg" and not c.ok for c in check_environment())


def test_unreachable_ollama_service_is_reported():
    with patch("story_teller.app.httpx.get", side_effect=httpx.ConnectError("refused")):
        assert any(c.name == "ollama_model" and not c.ok for c in check_environment())


def test_low_disk_and_unwritable_data_root_are_reported(tmp_path):
    with patch("story_teller.app.shutil.disk_usage", return_value=SimpleNamespace(free=100)), patch("story_teller.app.os.access", return_value=False):
        checks = check_environment(tmp_path)
    assert any(c.name == "disk" and not c.ok for c in checks)
    assert any(c.name == "data_root" and not c.ok for c in checks)
