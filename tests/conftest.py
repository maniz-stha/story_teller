import socket

import pytest

_network_patch = pytest.MonkeyPatch()


def _reject_network(*args, **kwargs):
    raise AssertionError("Network access is disabled during tests")


def pytest_configure():
    _network_patch.setattr(socket.socket, "connect", _reject_network)
    _network_patch.setattr(socket.socket, "connect_ex", _reject_network)


def pytest_unconfigure():
    _network_patch.undo()
