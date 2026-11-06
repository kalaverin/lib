from __future__ import annotations

from typing import ClassVar

import httpx2 as httpx
from multidict import CIMultiDict

from zx.lib.hypertext.response.core import (
    Internals,
    register,
)

__all__ = ["httpx"]


class HTTPxAdapter:
    raw_type: ClassVar[type[httpx.Response]] = httpx.Response

    def sync_read(self, raw: httpx.Response, /) -> Internals:
        return Internals(
            url=str(raw.url),
            status=int(raw.status_code),
            reason=raw.reason_phrase or None,
            headers=CIMultiDict(raw.headers.multi_items()),
            content=raw.read(),
        )

    async def async_read(self, raw: httpx.Response, /) -> Internals:
        return Internals(
            url=str(raw.url),
            status=int(raw.status_code),
            reason=raw.reason_phrase or None,
            headers=CIMultiDict(raw.headers.multi_items()),
            content=await raw.aread(),
        )


register(HTTPxAdapter())
