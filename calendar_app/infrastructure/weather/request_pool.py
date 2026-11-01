# -*- coding: utf-8 -*-
"""Bounded, process-local forecast sharing with independent widget cancellation."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import json

from PyQt6 import sip
from PyQt6.QtCore import QByteArray, QObject, QTimer, pyqtSignal
from PyQt6.QtNetwork import QNetworkReply, QNetworkRequest

_HEADERS = (b"Expires", b"Last-Modified", b"Retry-After")
_MAX_BODY = 2 * 1024 * 1024


@dataclass(frozen=True)
class _Response:
    status: object
    error: QNetworkReply.NetworkError
    body: bytes
    headers: dict[bytes, bytes]

    def fresh(self) -> bool:
        try:
            expires = parsedate_to_datetime(
                self.headers.get(b"Expires", b"").decode("utf-8", errors="replace")
            )
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            return expires > datetime.now(UTC)
        except (TypeError, ValueError, OverflowError):
            return False


class ForecastReply(QObject):
    """A private response cursor; aborting it does not cancel another widget."""

    finished = pyqtSignal()

    def __init__(self, pool, key: str, parent=None):
        super().__init__(parent)
        self.pool, self.key = pool, key
        self.response: _Response | None = None
        self.running = True

    def complete(self, response: _Response) -> None:
        if self.running:
            self.response, self.running = response, False
            self.finished.emit()

    def abort(self) -> None:
        if self.running:
            self.pool.release(self)
            self.complete(
                _Response(None, QNetworkReply.NetworkError.OperationCanceledError, b"", {})
            )

    def isRunning(self) -> bool:  # noqa: N802
        return self.running

    def isFinished(self) -> bool:  # noqa: N802
        return not self.running

    def attribute(self, _attribute):
        return self.response.status if self.response else None

    def error(self):
        return self.response.error if self.response else QNetworkReply.NetworkError.NoError

    def rawHeader(self, name):  # noqa: N802
        return QByteArray(self.response.headers.get(bytes(name), b"") if self.response else b"")

    def readAll(self):  # noqa: N802
        return QByteArray(self.response.body if self.response else b"")


class WeatherForecastPool(QObject):
    def __init__(self, manager):
        super().__init__(manager if isinstance(manager, QObject) else None)
        self.manager = manager
        self.cache: OrderedDict[str, _Response] = OrderedDict()
        self.pending: dict[str, tuple[object, list[ForecastReply]]] = {}

    def acquire(self, request: QNetworkRequest, parent=None) -> ForecastReply:
        key = request.url().toString()
        client = ForecastReply(self, key, parent)
        client.destroyed.connect(
            lambda _obj=None, ident=id(client): self._release_destroyed(key, ident)
        )
        cached = self.cache.get(key)
        if cached is not None and cached.fresh():
            self.cache.move_to_end(key)
            QTimer.singleShot(
                0, lambda: client.complete(cached) if not sip.isdeleted(client) else None
            )
            return client
        if key in self.pending:
            self.pending[key][1].append(client)
            return client
        request = QNetworkRequest(request)
        if cached is not None and cached.headers.get(b"Last-Modified"):
            request.setRawHeader(b"If-Modified-Since", cached.headers[b"Last-Modified"])
        physical = self.manager.get(request)
        self.pending[key] = (physical, [client])
        physical.finished.connect(lambda: self._finish(key, physical))
        timeout = QTimer(physical)
        timeout.setSingleShot(True)
        timeout.timeout.connect(lambda: physical.abort() if physical.isRunning() else None)
        physical.finished.connect(timeout.stop)
        timeout.start(10_000)
        return client

    def release(self, client: ForecastReply) -> None:
        pending = self.pending.get(client.key)
        if pending is None:
            return
        physical, clients = pending
        if client in clients:
            clients.remove(client)
        if not clients:
            self.pending.pop(client.key, None)
            if physical.isRunning():
                physical.abort()
            physical.deleteLater()

    def _release_destroyed(self, key: str, ident: int) -> None:
        pending = self.pending.get(key)
        if pending is not None:
            for client in list(pending[1]):
                if id(client) == ident:
                    self.release(client)
                    break

    def _finish(self, key: str, physical) -> None:
        pending = self.pending.get(key)
        if pending is None or pending[0] is not physical:
            return
        self.pending.pop(key)
        headers = {name: bytes(physical.rawHeader(name)) for name in _HEADERS}
        status = physical.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        error = physical.error()
        body = bytes(physical.readAll()) if status != 304 else b""
        if len(body) > _MAX_BODY:
            body, error = b"", QNetworkReply.NetworkError.UnknownContentError
        cached = self.cache.get(key)
        if status == 304 and cached is not None:
            body, status, error = cached.body, 200, QNetworkReply.NetworkError.NoError
            headers = {
                name: value or cached.headers.get(name, b"") for name, value in headers.items()
            }
        response = _Response(status, error, body, headers)
        valid = False
        if status == 200 and error == QNetworkReply.NetworkError.NoError:
            try:
                parsed = json.loads(body)
                valid = bool(parsed["properties"]["timeseries"])
            except (ValueError, KeyError, TypeError, UnicodeError):
                pass
        if valid:
            self.cache[key] = response
            self.cache.move_to_end(key)
            while (
                len(self.cache) > 12
                or sum(len(item.body) for item in self.cache.values()) > 8 * _MAX_BODY
            ):
                self.cache.popitem(last=False)
        physical.deleteLater()
        for client in list(pending[1]):
            if not sip.isdeleted(client):
                client.complete(response)


def pooled_weather_reply(manager, request: QNetworkRequest, parent=None) -> ForecastReply:
    pool = getattr(manager, "_air_calendar_weather_pool", None)
    if not isinstance(pool, WeatherForecastPool):
        pool = WeatherForecastPool(manager)
        manager._air_calendar_weather_pool = pool
    return pool.acquire(request, parent)
