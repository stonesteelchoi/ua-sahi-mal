"""Process-local outbound-network guard for reproducible model commands."""

from __future__ import annotations

import ipaddress
import os
import socket
from typing import Any

_INSTALLED = False
_ORIGINAL_CONNECT = socket.socket.connect
_ORIGINAL_CONNECT_EX = socket.socket.connect_ex
_ORIGINAL_CREATE_CONNECTION = socket.create_connection


class OfflineNetworkError(OSError):
    """Raised when a library attempts an outbound connection in offline mode."""


def _is_loopback_address(address: Any) -> bool:
    # AF_UNIX and Windows named-pipe-like addresses are local.
    if not isinstance(address, tuple) or not address:
        return True
    host = address[0]
    if not isinstance(host, str):
        return False
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        # Do not perform DNS resolution: a hostname could resolve externally.
        return False


def enforce_offline_network() -> None:
    """Block non-loopback socket connections for the current Python process.

    Environment flags alone do not cover every third-party asset fetch. This
    guard makes an unexpected download fail closed while preserving loopback
    traffic needed by local tooling.
    """

    global _INSTALLED
    os.environ["ULTRALYTICS_SAFE_LOAD"] = "true"
    os.environ["YOLO_OFFLINE"] = "true"
    os.environ["YOLO_AUTOINSTALL"] = "false"
    os.environ["PIP_NO_INDEX"] = "1"
    os.environ["WANDB_MODE"] = "offline"
    if _INSTALLED:
        return

    def guarded_connect(instance: socket.socket, address: Any) -> Any:
        if not _is_loopback_address(address):
            raise OfflineNetworkError(f"outbound network is disabled: {address!r}")
        return _ORIGINAL_CONNECT(instance, address)

    def guarded_connect_ex(instance: socket.socket, address: Any) -> int:
        if not _is_loopback_address(address):
            raise OfflineNetworkError(f"outbound network is disabled: {address!r}")
        return _ORIGINAL_CONNECT_EX(instance, address)

    def guarded_create_connection(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
        if not _is_loopback_address(address):
            raise OfflineNetworkError(f"outbound network is disabled: {address!r}")
        return _ORIGINAL_CREATE_CONNECTION(address, *args, **kwargs)

    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    socket.create_connection = guarded_create_connection
    _INSTALLED = True
