"""Test the broadcast discovery of heatpumps."""
import socket
from unittest.mock import patch

import pytest

from custom_components.luxtronik.helpers import lux_helper

REQUEST = b"2000;111;1;\x00"


class FakeSocket:
    """A UDP socket that answers with the answers given for its port."""

    def __init__(self, answers: dict[int, list[tuple[bytes, str]]]) -> None:
        self._answers = answers
        self.port = None
        self.sent = []
        self.closed = False

    def setsockopt(self, *args):
        pass

    def settimeout(self, timeout):
        pass

    def bind(self, address):
        self.port = address[1]

    def sendto(self, data, address):
        self.sent.append((data, address))

    def recvfrom(self, size):
        answers = self._answers.get(self.port, [])
        if not answers:
            raise socket.timeout
        data, ip = answers.pop(0)
        return data, (ip, self.port)

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _discover(answers):
    sockets = []

    def create(*args):
        sockets.append(FakeSocket(answers))
        return sockets[-1]

    with patch.object(lux_helper.socket, "socket", create):
        return lux_helper.discover(), sockets


def test_discover():
    """The first heatpump that answers is found, with the port it sends."""
    result, sockets = _discover({4444: [(b"2500;111;8889;", "10.0.0.2")]})

    assert result == ("10.0.0.2", 8889)
    assert sockets[0].sent == [(REQUEST, ("<broadcast>", 4444))]


def test_discover_skips_other_answers():
    """The own request and answers without the magic bytes are skipped."""
    result, _ = _discover({4444: [
        (REQUEST, "10.0.0.1"),
        (b"something else", "10.0.0.3"),
        (b"2500;111;8888;", "10.0.0.2"),
    ]})

    assert result == ("10.0.0.2", 8888)


def test_discover_second_port():
    """Without an answer on the first port, the second port is tried."""
    result, sockets = _discover({47808: [(b"2500;111;8889;", "10.0.0.2")]})

    assert result == ("10.0.0.2", 8889)
    assert [s.port for s in sockets] == [4444, 47808]


def test_discover_without_port():
    """Old firmware answers without a valid port."""
    result, _ = _discover({4444: [(b"2500;111;;", "10.0.0.2")]})

    assert result == ("10.0.0.2", None)


def test_discover_nothing():
    """Without an answer on either port, nothing is found."""
    result, sockets = _discover({})

    assert result is None
    assert len(sockets) == 2


@pytest.mark.parametrize("answers", [{}, {4444: [(b"2500;111;8889;", "10.0.0.2")]}])
def test_discover_closes_sockets(answers):
    """The sockets are closed after the discovery."""
    _, sockets = _discover(answers)

    assert sockets
    assert all(s.closed for s in sockets)
