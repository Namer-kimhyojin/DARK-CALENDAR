# -*- coding: utf-8 -*-
"""Windows user-bound credential encryption; fail closed without DPAPI."""

import ctypes
from ctypes import wintypes
import os


def crypt(data: bytes, encrypt: bool) -> bytes:
    if os.name != "nt":
        raise OSError("Windows credential protection unavailable")

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]

    buffer = ctypes.create_string_buffer(data, len(data))
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    target = Blob()
    function = (
        ctypes.windll.crypt32.CryptProtectData
        if encrypt
        else ctypes.windll.crypt32.CryptUnprotectData
    )
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise OSError("Windows credential protection failed")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)
