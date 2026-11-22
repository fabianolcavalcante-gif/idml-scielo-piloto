"""Content-free health probe for the validator brokers (no request, no article data).

Intended for the VPS 'status' command: tells whether each configured broker socket
exists, accepts connections and is owned by root (the brokers check peer credentials).
"""

import json
import socket
import struct
from pathlib import Path
from typing import Any

from idml_foundation.settings import Settings, get_settings


def probe_socket(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"configured": False}
    result: dict[str, Any] = {"configured": True, "exists": path.exists()}
    if not result["exists"]:
        return {**result, "status": "socket-missing"}
    peer_option = getattr(socket, "SO_PEERCRED", None)
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(3)
            connection.connect(str(path))
            if peer_option is not None:
                uid = struct.unpack(
                    "3i", connection.getsockopt(socket.SOL_SOCKET, peer_option, 12)
                )[1]
                result["peer_is_root"] = uid == 0
    except (OSError, TimeoutError) as exc:
        return {**result, "status": f"connect-failed:{type(exc).__name__}"}
    return {**result, "status": "listening"}


def validator_status(settings: Settings | None = None) -> dict[str, Any]:
    config = settings or get_settings()
    return {
        "scoped_authorities": config.validator_scoped_authorities,
        "modern": probe_socket(config.validator_socket),
        "xpm": probe_socket(config.xpm_socket),
    }


def main() -> None:
    print(json.dumps(validator_status(), sort_keys=True))


if __name__ == "__main__":
    main()
