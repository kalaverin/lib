from __future__ import annotations

from typing import ClassVar

import aiohttp
import aiohttp.client_reqrep
from multidict import CIMultiDict

from zx.lib.hypertext.response.core import (
    Internals,
    register,
)

__all__ = ["aiohttp"]


class AioHttpAdapter:
    raw_type: ClassVar[type[aiohttp.client_reqrep.ClientResponse]] = (
        aiohttp.client_reqrep.ClientResponse
    )

    def sync_read(self, _raw: aiohttp.client_reqrep.ClientResponse, /) -> None:
        return None

    async def async_read(
        self,
        raw: aiohttp.client_reqrep.ClientResponse,
        /,
    ) -> Internals:
        return Internals(
            url=str(raw.url),
            status=int(raw.status),
            reason=raw.reason or None,
            headers=CIMultiDict(raw.headers.items()),
            content=await raw.read(),
        )


register(AioHttpAdapter())
