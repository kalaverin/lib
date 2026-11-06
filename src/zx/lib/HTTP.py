# ruff: noqa: N999  # legacy module name is part of the public contract
from http import HTTPStatus as Status

from zx.lib.hypertext import (
    URL,
    Agent,
    Catch,
    HTTPError,
    Response,
)

Error = HTTPError

__all__ = (
    "URL",
    "Agent",
    "Catch",
    "Error",
    "Response",
    "Status",
)
