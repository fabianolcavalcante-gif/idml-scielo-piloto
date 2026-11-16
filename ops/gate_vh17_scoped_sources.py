"""Bind changed validator transport sources to the two native runs and their negative controls."""

import hashlib
import json

from ops.prepare_vh1_scoped_socket import SOURCES

OLD = "benchmarks/qualification/reports/vh1-scoped-socket-v1.json"
NEW = "benchmarks/qualification/reports/vh17-scoped-native-v1.json"
PINS = {
    OLD: "714b88c95049e2842c42c4d717d4361b3522585f1adad6269f97a0f2022a95b4",
    NEW: "e0b30041a3b99d6dfe1859d16c0132db742bf8d4244db557b67b128ea1746b73",
}
CHANGED = {
    SOURCES[k]: k
    for k in (
        "scoped_validator_broker.py",
        "scoped_validator_transport.py",
        "package_validation.py",
    )
}
DEPENDENCIES = (*PINS, *SOURCES.values(), "config/validator-registry-vh1-scoped.json")


def source_matches(path, expected, reader):
    if path not in CHANGED:
        return False
    try:
        reports = {}
        for name, digest in PINS.items():
            data = reader(name)
            if hashlib.sha256(data).hexdigest() != digest:
                return False
            reports[name] = json.loads(data)
        old, new = reports[OLD], reports[NEW]
        return (
            old["code_sha256"][CHANGED[path]] == expected
            and set(new["code_sha256"]) == SOURCES.keys()
            and all(
                hashlib.sha256(reader(p)).hexdigest() == new["code_sha256"][n]
                for n, p in SOURCES.items()
            )
            and hashlib.sha256(reader("config/validator-registry-vh1-scoped.json")).hexdigest()
            == old["registry_sha256"]
            == new["registry_sha256"]
            and old["negative_controls"] == new["negative_controls"]
            and len(new["cases"]) == 2
            and new["formal_xml_approved"] is False
        )
    except (KeyError, ValueError, TypeError, OSError):
        return False
