# -*- coding: utf-8 -*-
"""Public-network-only ICS requests with pinned DNS and explicit redirects."""

from functools import partial
import http.client
import io
import ipaddress
import socket
import time
import urllib.error
from urllib.parse import urljoin, urlsplit
import urllib.request

from calendar_app.application.calendar_sync_contract import CalendarSyncError
from calendar_app.infrastructure.ics.subscriptions import normalize_subscription_url

MAX_REDIRECTS = 5
_REDIRECT_CODES = {301, 302, 303, 307, 308}


def _public_address(value):
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        raise CalendarSyncError("invalid_subscription_url") from None
    if (
        "%" in str(value)
        or not address.is_global
        or address.is_reserved
        or address.is_multicast
        or address.is_loopback
        or address.is_link_local
        or address.is_unspecified
        # Transition tunnels can embed another destination, and their global
        # classification differs between supported Python versions.
        or (
            isinstance(address, ipaddress.IPv6Address)
            and (address.sixtofour is not None or address.teredo is not None)
        )
    ):
        raise CalendarSyncError("invalid_subscription_url")
    return address


def _remaining_timeout(timeout, cancelled, deadline):
    if cancelled():
        raise CalendarSyncError("cancelled")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError
    return min(timeout, remaining)


def _connect_public(address, timeout, source_address=None, *, cancelled, deadline):
    """Resolve once and connect to a checked sockaddr before sending any HTTP data."""
    host, port = address
    if "%" in host:
        raise CalendarSyncError("invalid_subscription_url")
    _remaining_timeout(timeout, cancelled, deadline)
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    # Reject mixed public/private answers before trying any of them. Numeric and
    # legacy numeric host spellings are classified through the same OS resolver.
    for family, _kind, _proto, _name, sockaddr in addresses:
        if family not in {socket.AF_INET, socket.AF_INET6}:
            raise CalendarSyncError("invalid_subscription_url")
        _public_address(sockaddr[0])
    failure = OSError("No usable ICS destination")
    for family, kind, proto, _name, sockaddr in addresses:
        sock = None
        try:
            sock = socket.socket(family, kind, proto)
            sock.settimeout(_remaining_timeout(timeout, cancelled, deadline))
            if source_address:
                sock.bind(source_address)
            # Do not pass the hostname to create_connection: that would resolve
            # again and let a rebinding response bypass the address check.
            sock.connect(sockaddr)
            peer = sock.getpeername()
            if _public_address(peer[0]) != _public_address(sockaddr[0]) or peer[1] != port:
                raise CalendarSyncError("invalid_subscription_url")
            sock.settimeout(_remaining_timeout(timeout, cancelled, deadline))
            return sock
        except BaseException as exc:
            if sock is not None:
                sock.close()
            if not isinstance(exc, OSError):
                raise
            failure = exc
    raise failure


class _DeadlineReader(io.RawIOBase):
    """Check the shared request budget around every underlying socket read."""

    def __init__(self, stream, sock, timeout, cancelled, deadline):
        super().__init__()
        self._stream = stream
        self._sock = sock
        self._timeout = timeout
        self._cancelled = cancelled
        self._deadline = deadline

    def readable(self):
        return True

    def readinto(self, buffer):
        timeout = _remaining_timeout(self._timeout, self._cancelled, self._deadline)
        self._sock.settimeout(timeout)
        # read1 performs at most one raw read. Buffered read/readline may receive
        # indefinitely while a server drips bytes within each socket timeout.
        data = self._stream.read1(len(buffer))
        _remaining_timeout(self._timeout, self._cancelled, self._deadline)
        buffer[: len(data)] = data
        return len(data)

    def close(self):
        try:
            self._stream.close()
        finally:
            super().close()


class _DeadlineHTTPResponse(http.client.HTTPResponse):
    def __init__(self, sock, *args, timeout, cancelled, deadline, **kwargs):
        super().__init__(sock, *args, **kwargs)
        # Keep stdlib HTTP framing/size validation. Its status lines, headers,
        # chunk extensions and trailers must all use the same absolute budget
        # as the body, including reads performed before opener.open returns.
        self.fp = io.BufferedReader(_DeadlineReader(self.fp, sock, timeout, cancelled, deadline))


def _connection_factory(connection_type, cancelled, deadline):
    def create(host, **kwargs):
        connection = connection_type(host, **kwargs)
        # Keep HTTP Host and HTTPS certificate/SNI verification on the original
        # hostname; only replace the stdlib's socket-creation hook.
        connection._create_connection = partial(
            _connect_public, cancelled=cancelled, deadline=deadline
        )
        connection.response_class = partial(
            _DeadlineHTTPResponse,
            timeout=connection.timeout,
            cancelled=cancelled,
            deadline=deadline,
        )
        return connection

    return create


class _PublicHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, cancelled, deadline):
        super().__init__()
        self._connection = _connection_factory(http.client.HTTPConnection, cancelled, deadline)

    def http_open(self, request):
        return self.do_open(self._connection, request)


class _PublicHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, cancelled, deadline):
        super().__init__()
        self._connection = _connection_factory(http.client.HTTPSConnection, cancelled, deadline)

    def https_open(self, request):
        return self.do_open(self._connection, request, context=self._context)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def http_error_302(self, request, response, code, message, headers):
        return None  # Let HTTPError surface without reading the redirect body.

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


def open_subscription(url, *, timeout=15, cancelled, deadline):
    """Open a public HTTP(S) feed; callers own and must close the final response."""
    url = normalize_subscription_url(url)
    opener = urllib.request.build_opener(
        # A system proxy would resolve/connect elsewhere and evade peer checks.
        urllib.request.ProxyHandler({}),
        _NoRedirect(),
        _PublicHTTPHandler(cancelled, deadline),
        _PublicHTTPSHandler(cancelled, deadline),
    )
    for hop in range(MAX_REDIRECTS + 1):
        request = urllib.request.Request(url, headers={"User-Agent": "AirCalendar/1.0 ICS-Fetcher"})
        try:
            return opener.open(request, timeout=_remaining_timeout(timeout, cancelled, deadline))
        except urllib.error.HTTPError as exc:
            if exc.code not in _REDIRECT_CODES:
                raise
            try:
                location = exc.headers.get("Location")
                if not location or hop == MAX_REDIRECTS:
                    raise CalendarSyncError("ics_fetch_failed")
                # urljoin/urlsplit discard some control characters; check first.
                if any(ord(char) < 32 or char.isspace() for char in location):
                    raise CalendarSyncError("invalid_subscription_url")
                try:
                    target = normalize_subscription_url(urljoin(url, location))
                except ValueError:
                    raise CalendarSyncError("invalid_subscription_url") from None
                if urlsplit(url).scheme == "https" and urlsplit(target).scheme != "https":
                    raise CalendarSyncError("invalid_subscription_url")
                url = target
            finally:
                exc.close()
