from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Literal

_FIGURE_ASSET_NUMBER = re.compile(
    r"(?:^|[\s_-])(?:fig(?:ure)?|gf)[\s_-]*0*([1-9]\d*)$",
    re.IGNORECASE,
)
_INLINE_EQUATION_ASSET = re.compile(
    r"(?:^|[\s_-])eq[\s_-]*txt[\s_-]*0*([1-9]\d*)$",
    re.IGNORECASE,
)
_DISPLAY_EQUATION_ASSET = re.compile(
    r"(?:^|[\s_-])eq[\s_-]*0*[1-9]\d*$",
    re.IGNORECASE,
)


def figure_asset_number(name: str) -> int | None:
    """Return a conservative figure ordinal from a safe asset basename."""
    stem = PurePosixPath(name.replace("\\", "/")).stem
    match = _FIGURE_ASSET_NUMBER.search(stem)
    return int(match.group(1)) if match else None


def equation_asset_placement(name: str) -> Literal["inline", "block"] | None:
    """Return an explicit layout role encoded by a conservative equation basename."""
    stem = PurePosixPath(name.replace("\\", "/")).stem
    if _INLINE_EQUATION_ASSET.search(stem):
        return "inline"
    if _DISPLAY_EQUATION_ASSET.search(stem):
        return "block"
    return None


def inline_equation_asset_number(name: str) -> int | None:
    """Return the source sequence number for an explicitly named inline equation asset."""
    stem = PurePosixPath(name.replace("\\", "/")).stem
    match = _INLINE_EQUATION_ASSET.search(stem)
    return int(match.group(1)) if match else None
