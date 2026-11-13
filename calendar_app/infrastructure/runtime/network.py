# -*- coding: utf-8 -*-
"""Centralized Network Access Manager for the application."""

from __future__ import annotations

import logging

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QObject
from PyQt6.QtNetwork import QNetworkAccessManager

logger = logging.getLogger(__name__)


class NetworkManager(QObject):
    """Singleton wrapper for QNetworkAccessManager."""

    _instance: NetworkManager | None = None

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._qnam = QNetworkAccessManager(self)
        logger.info("Shared NetworkManager initialized.")

    @classmethod
    def instance(cls) -> NetworkManager:
        if cls._instance is None or sip.isdeleted(cls._instance):
            cls._instance = NetworkManager(QCoreApplication.instance())
        return cls._instance

    @classmethod
    def release(cls) -> None:
        """Dispose an existing service after its clients stop, without creating one."""
        instance, cls._instance = cls._instance, None
        if instance is not None and not sip.isdeleted(instance):
            instance.deleteLater()

    def qnam(self) -> QNetworkAccessManager:
        return self._qnam


def get_network_manager() -> QNetworkAccessManager:
    return NetworkManager.instance().qnam()
