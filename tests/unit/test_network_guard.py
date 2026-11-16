import socket

import pytest


def test_tests_cannot_open_network_connections():
    with socket.socket() as connection, pytest.raises(AssertionError, match="Network access is disabled"):
        connection.connect(("127.0.0.1", 1))
