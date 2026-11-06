from __future__ import annotations

from typing import ClassVar

import requests
from multidict import CIMultiDict

from zx.lib.hypertext.response.core import (
    Internals,
    register,
)

__all__ = ["requests"]


class RequestsAdapter:
    raw_type: ClassVar[type[requests.Response]] = requests.Response

    def sync_read(self, raw: requests.Response, /) -> Internals:
        return Internals(
            url=str(raw.url),
            status=int(raw.status_code),
            reason=raw.reason or None,
            headers=CIMultiDict(raw.headers.items()),
            content=raw.content,
        )

    async def async_read(self, _raw: requests.Response, /) -> None:
        return None


register(RequestsAdapter())
