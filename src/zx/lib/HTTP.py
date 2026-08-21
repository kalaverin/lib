# ruff: noqa: N999  # legacy module name is part of the public contract
from http import HTTPStatus as Status
from typing import Final

from zx.lib.hypertext import (
    URL,
    Agent,
    Catch,
    HTTPError,
    Response,
)

Error = HTTPError

Headers: Final[dict[str, str]] = {
    "accept": "*/*",
    "accept-encoding": "br, gzip, deflate, zstd",
}

__all__ = (
    "URL",
    "Agent",
    "Catch",
    "Error",
    "Headers",
    "Response",
    "Status",
)
