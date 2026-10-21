# -*- coding: utf-8 -*-
"""Exercise actual urllib redirect/HTTP handling without real network traffic."""

from io import BytesIO
import ipaddress
import socket
import ssl
import time
from unittest.mock import Mock

import pytest

from calendar_app.application.calendar_sync_contract import CalendarSyncError
from calendar_app.infrastructure.ics import ics_fetcher, subscription_http
from tests.test_ics_snapshot_safety import KEY, URL, event, feed, rows, snapshot

PUBLIC_IP = "93.184.216.34"
FEED = b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n"


def wire(status=200, location=None, body=FEED):
    headers = f"HTTP/1.1 {status} Synthetic\r\nContent-Length: {len(body)}\r\n"
    if location is not None:
        headers += f"Location: {location}\r\n"
    return headers.encode("utf-8", errors="strict") + b"\r\n" + body


class WireFile(BytesIO):
    reads = 0

    def read(self, *args):
        self.reads += 1
        return super().read(*args)


@pytest.fixture
def network(monkeypatch):
    class Network:
        def __init__(self):
            self.answers = {}
            self.resolutions = []
            self.sockets = []
            self.requests = []
            self.files = []
            self.wires = [wire()]
            self.peer = None
            self.tls_hosts = []
            self.connect_failure = None
            self.file_factory = WireFile

        def resolve(self, host, port, **kwargs):
            self.resolutions.append(host)
            try:
                literal = str(ipaddress.ip_address(host))
            except ValueError:
                literal = PUBLIC_IP
            answers = self.answers.get(host, [literal])
            return [
                (
                    socket.AF_INET6 if ":" in address else socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    (address, port, 0, 0) if ":" in address else (address, port),
                )
                for address in answers
            ]

        def create_socket(self, *args):
            sock = Socket()
            self.sockets.append(sock)
            return sock

    net = Network()

    class Socket:
        closed = False

        def settimeout(self, timeout):
            self.timeout = timeout

        def setsockopt(self, *args):
            pass

        def connect(self, address):
            self.address = address
            if net.connect_failure:
                raise net.connect_failure

        def getpeername(self):
            return (net.peer, self.address[1]) if net.peer else self.address

        def sendall(self, data):
            net.requests.append(data)

        def makefile(self, *args):
            response = net.file_factory(net.wires.pop(0))
            net.files.append(response)
            return response

        def close(self):
            self.closed = True

    def tls(context, sock, *, server_hostname):
        assert context.check_hostname
        assert context.verify_mode == ssl.CERT_REQUIRED
        net.tls_hosts.append(server_hostname)
        return sock

    monkeypatch.setattr(subscription_http.socket, "getaddrinfo", net.resolve)
    monkeypatch.setattr(subscription_http.socket, "socket", net.create_socket)
    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", tls)
    # Even a configured proxy must not bypass the destination/peer policy.
    monkeypatch.setattr("urllib.request.getproxies", lambda: {"http": "http://127.0.0.1:9"})
    yield net


def fetch(url="http://feed.example/calendar.ics?key=A%2FB&sig=a+b", **kwargs):
    with subscription_http.open_subscription(
        url,
        cancelled=kwargs.pop("cancelled", lambda: False),
        deadline=kwargs.pop("deadline", time.monotonic() + 45),
        **kwargs,
    ) as response:
        return response.read()


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "0.0.0.0",
        "10.1.2.3",
        "172.16.0.1",
        "192.168.1.2",
        "169.254.169.254",
        "100.64.0.1",
        "192.0.2.1",
        "198.18.0.1",
        "224.0.0.1",
        "240.0.0.1",
        "255.255.255.255",
        "::",
        "::1",
        "fc00::1",
        "fe80::1",
        "ff02::1",
        "2001:db8::1",
        "::ffff:127.0.0.1",
        "64:ff9b::7f00:1",
        "2002:7f00:1::",
        "2002:808:808::",
        "2001:0:1:2:3:4:5:6",
    ],
)
@pytest.mark.parametrize("redirect", [False, True])
def test_nonpublic_direct_and_redirect_destinations_send_no_request(network, address, redirect):
    host = f"[{address}]" if ":" in address else address
    url = f"http://{host}/internal"
    if redirect:
        network.wires = [wire(302, url)]
    with pytest.raises(CalendarSyncError, match="^invalid_subscription_url$"):
        fetch() if redirect else fetch(url)
    assert len(network.requests) == int(redirect)
    assert len(network.sockets) == int(redirect)
    assert all(response.closed and response.reads == 0 for response in network.files)


@pytest.mark.parametrize(
    "host", ["localhost", "internal.example", "2130706433", "0x7f000001", "0177.0.0.1"]
)
def test_hostnames_and_legacy_numeric_hosts_use_resolved_address_policy(network, host):
    network.answers[host] = ["127.0.0.1"]
    with pytest.raises(CalendarSyncError, match="invalid_subscription_url"):
        fetch(f"http://{host}/feed.ics")
    assert not network.sockets


@pytest.mark.parametrize("answers", [[PUBLIC_IP, "::1"], ["10.0.0.1", PUBLIC_IP]])
def test_mixed_dns_answers_are_rejected_before_any_connection(network, answers):
    network.answers["feed.example"] = answers
    with pytest.raises(CalendarSyncError, match="invalid_subscription_url"):
        fetch()
    assert not network.sockets


@pytest.mark.parametrize("peer", ["127.0.0.1", "::1", "10.0.0.1", "8.8.8.8"])
def test_changed_peer_is_rejected_before_http_is_sent(network, peer):
    network.peer = peer
    with pytest.raises(CalendarSyncError, match="invalid_subscription_url"):
        fetch()
    assert not network.requests
    assert network.sockets[0].closed


def test_dns_is_pinned_without_a_second_hostname_resolution(network, monkeypatch):
    resolver = network.resolve

    def rebind(host, port, **kwargs):
        result = resolver(host, port, **kwargs)
        network.answers[host] = ["127.0.0.1"]
        return result

    monkeypatch.setattr(subscription_http.socket, "getaddrinfo", rebind)
    fallback = Mock(side_effect=AssertionError("Hostname must not be resolved again"))
    monkeypatch.setattr(subscription_http.socket, "create_connection", fallback)
    assert fetch() == FEED
    assert network.resolutions == ["feed.example"]
    assert network.sockets[0].address == (PUBLIC_IP, 80)
    fallback.assert_not_called()


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_https_downgrades_are_rejected_and_redirect_body_is_not_read(network, status):
    network.wires = [wire(status, "http://other.example/feed.ics")]
    with pytest.raises(CalendarSyncError, match="invalid_subscription_url"):
        fetch("https://feed.example/feed.ics")
    assert len(network.requests) == 1
    assert network.files[0].closed and network.files[0].reads == 0


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize(
    "target", ["/new.ics?key=A%2FB&sig=a+b", "https://other.example/new.ics?key=A%2FB&sig=a+b"]
)
def test_public_redirects_preserve_signed_query_host_and_verified_tls(network, status, target):
    network.wires = [wire(status, target), wire()]
    assert fetch("https://feed.example/old.ics") == FEED
    assert network.resolutions == [
        "feed.example",
        "other.example" if "other.example" in target else "feed.example",
    ]
    assert network.tls_hosts == network.resolutions
    assert b"GET /new.ics?key=A%2FB&sig=a+b HTTP/1.1\r\n" in network.requests[1]
    assert (
        b"Host: " + network.resolutions[1].encode("utf-8", errors="strict") in network.requests[1]
    )
    assert b"User-Agent: AirCalendar/1.0 ICS-Fetcher" in network.requests[1]
    assert all(response.closed for response in network.files)


@pytest.mark.parametrize(
    "target",
    [
        "file:///tmp/feed.ics",
        "ftp://other.example/feed.ics",
        "https://user:secret@other.example/feed.ics",
        "http://[::1",
        "http://other.example/has\tspace",
        "http://other.example/has space",
        "http://[fe80::1%25eth0]/feed.ics",
    ],
)
def test_invalid_redirects_are_closed_without_following(network, target):
    network.wires = [wire(302, target)]
    with pytest.raises(CalendarSyncError, match="invalid_subscription_url"):
        fetch()
    assert len(network.requests) == 1
    assert network.files[0].closed


def test_redirect_hops_are_bounded_without_reading_response_bodies(network):
    network.wires = [wire(302, "/again.ics")] * (subscription_http.MAX_REDIRECTS + 2)
    with pytest.raises(CalendarSyncError, match="ics_fetch_failed"):
        fetch()
    assert len(network.requests) == subscription_http.MAX_REDIRECTS + 1
    assert all(response.closed and response.reads == 0 for response in network.files)


def test_same_hostname_is_revalidated_on_each_redirect(network, monkeypatch):
    resolver = network.resolve

    def rebind(host, port, **kwargs):
        result = resolver(host, port, **kwargs)
        network.answers[host] = ["127.0.0.1"]
        return result

    monkeypatch.setattr(subscription_http.socket, "getaddrinfo", rebind)
    network.wires = [wire(302, "/again.ics")]
    with pytest.raises(CalendarSyncError, match="invalid_subscription_url"):
        fetch()
    assert network.resolutions == ["feed.example", "feed.example"]
    assert len(network.requests) == 1


def test_cancelled_or_expired_request_does_not_resolve_or_connect(network):
    with pytest.raises(CalendarSyncError, match="cancelled"):
        fetch(cancelled=lambda: True)
    with pytest.raises(TimeoutError):
        fetch(deadline=time.monotonic() - 1)
    assert not network.resolutions and not network.sockets


def test_failed_connections_are_closed(network):
    from urllib.error import URLError

    network.connect_failure = TimeoutError("synthetic")
    with pytest.raises(URLError):
        fetch()
    assert network.sockets[0].closed
    assert not network.requests


@pytest.mark.parametrize("redirect", [False, True])
def test_rejected_destination_preserves_cached_events_and_last_success(
    snapshot, network, monkeypatch, redirect
):
    conn, synchronize = snapshot
    assert synchronize(feed(event("one"), event("old"))) == (2, 0, None)
    before = rows(conn), conn.execute("SELECT * FROM calendar").fetchall()
    monkeypatch.setattr(ics_fetcher, "open_subscription", subscription_http.open_subscription)
    if redirect:
        network.wires = [wire(302, "https://127.0.0.1/internal")]
    else:
        network.answers["example.invalid"] = ["127.0.0.1"]
    assert ics_fetcher.fetch_and_sync(KEY, URL) == (0, 0, "invalid_subscription_url")
    assert (rows(conn), conn.execute("SELECT * FROM calendar").fetchall()) == before
    assert len(network.requests) == int(redirect)


@pytest.mark.parametrize(
    "url", ["http://feed.example/feed.ics", "https://[2606:4700:4700::1111]/feed.ics"]
)
def test_public_ipv4_and_ipv6_feeds_remain_usable(network, url):
    assert fetch(url) == FEED
    assert len(network.requests) == 1
    assert network.sockets[0].closed


def test_http_to_https_upgrade_remains_usable(network):
    network.wires = [wire(302, "https://feed.example/feed.ics"), wire()]
    assert fetch() == FEED
    assert network.tls_hosts == ["feed.example"]


def test_redirect_without_location_is_closed(network):
    network.wires = [wire(302)]
    with pytest.raises(CalendarSyncError, match="ics_fetch_failed"):
        fetch()
    assert len(network.requests) == 1
    assert network.files[0].closed
