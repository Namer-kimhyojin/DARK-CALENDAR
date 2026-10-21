# -*- coding: utf-8 -*-
"""Bound untrusted HTTP framing as well as the ICS response body."""

from io import BufferedReader, RawIOBase
import socket

import pytest

from calendar_app.application.calendar_sync_contract import CalendarSyncError
from calendar_app.infrastructure.ics import ics_fetcher, subscription_http
from tests.test_ics_request_security import FEED, fetch, network, wire
from tests.test_ics_snapshot_safety import KEY, URL, event, feed, rows, snapshot


class DripStream(RawIOBase):
    """A socket-like stream that advances a clock for each received byte."""

    def __init__(self, data, slow_start, clock):
        super().__init__()
        self.data = data
        self.position = 0
        self.slow_start = slow_start
        self.clock = clock
        self.slow_reads = 0

    def readable(self):
        return True

    def readinto(self, buffer):
        if self.position == len(self.data):
            return 0
        if self.position >= self.slow_start:
            self.slow_reads += 1
            self.clock[0] += 0.1
        buffer[0] = self.data[self.position]
        self.position += 1
        return 1


def drip_response(phase, clock):
    if phase == "status":
        prefix = b""
        suffix = b"HTTP/1.1 200 " + b"a" * 100 + b"\r\nContent-Length: 0\r\n\r\n"
    elif phase == "header":
        prefix = b"HTTP/1.1 200 OK\r\nX-Slow: "
        suffix = b"a" * 100 + b"\r\nContent-Length: 0\r\n\r\n"
    else:
        headers = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
        length = f"{len(FEED):x}".encode("utf-8", errors="strict")
        if phase == "chunk":
            prefix = headers + length + b";slow="
            suffix = b"a" * 100 + b"\r\n" + FEED + b"\r\n0\r\n\r\n"
        else:
            prefix = headers + length + b"\r\n" + FEED + b"\r\n0\r\nX-Slow: "
            suffix = b"a" * 100 + b"\r\n\r\n"
    return DripStream(prefix + suffix, len(prefix), clock)


@pytest.mark.parametrize("scheme", ["http", "https"])
@pytest.mark.parametrize("phase", ["status", "header", "chunk", "trailer"])
@pytest.mark.parametrize("cancel", [False, True])
def test_slow_http_framing_cannot_reset_total_budget(network, monkeypatch, scheme, phase, cancel):
    clock = [100.0]
    raw = drip_response(phase, clock)
    network.file_factory = lambda _data: BufferedReader(raw)
    monkeypatch.setattr(subscription_http.time, "monotonic", lambda: clock[0])
    expected = CalendarSyncError if cancel else TimeoutError
    with pytest.raises(expected, match="^cancelled$" if cancel else None):
        fetch(
            f"{scheme}://feed.example/feed.ics",
            deadline=101.0,
            cancelled=lambda: cancel and raw.slow_reads >= 4,
        )
    assert raw.slow_reads <= 11
    assert raw.position < len(raw.data)
    assert raw.closed
    assert all(sock.closed for sock in network.sockets)


@pytest.mark.parametrize("phase", ["status", "header", "chunk", "trailer"])
def test_slow_http_failure_retains_cached_snapshot(snapshot, network, monkeypatch, phase):
    conn, synchronize = snapshot
    assert synchronize(feed(event("one"), event("old"))) == (2, 0, None)
    before = rows(conn), conn.execute("SELECT * FROM calendar").fetchall()
    clock = [100.0]
    raw = drip_response(phase, clock)
    network.file_factory = lambda _data: BufferedReader(raw)
    monkeypatch.setattr(subscription_http.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(ics_fetcher, "MAX_FETCH_SECONDS", 1)
    monkeypatch.setattr(ics_fetcher, "open_subscription", subscription_http.open_subscription)

    assert ics_fetcher.fetch_and_sync(KEY, URL) == (0, 0, "network_unavailable")
    assert (rows(conn), conn.execute("SELECT * FROM calendar").fetchall()) == before
    assert raw.slow_reads <= 11
    assert raw.closed


def test_budgeted_response_reads_real_socket_after_connection_handoff(monkeypatch):
    # urllib closes its socket reference after returning the response; the file
    # reference must still support bounded reads until the response is closed.
    client, server = socket.socketpair()
    try:
        server.sendall(wire())
        server.shutdown(socket.SHUT_WR)
        monkeypatch.setattr(subscription_http, "_connect_public", lambda *a, **k: client)
        assert fetch() == FEED
    finally:
        client.close()
        server.close()
