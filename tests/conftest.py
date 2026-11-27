import socket

import pytest

from story_teller import service

_network_patch = pytest.MonkeyPatch()


@pytest.fixture(autouse=True)
def isolated_background_videos(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "BACKGROUND_DIR", tmp_path / "background_videos")


def _reject_network(*args, **kwargs):
    raise AssertionError("Network access is disabled during tests")


def pytest_configure():
    _network_patch.setattr(socket.socket, "connect", _reject_network)
    _network_patch.setattr(socket.socket, "connect_ex", _reject_network)


def pytest_unconfigure():
    _network_patch.undo()
