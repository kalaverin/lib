"""Backend-agnostic HTTP response facade with per-backend adapters.

`Response[B]` normalizes any supported raw response object (requests,
httpx, aiohttp) into a common surface. Adapters live in sibling modules
and register themselves on import; the core knows nothing about
backends beyond the `BackendAdapter` protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from inspect import iscoroutine
from logging import getLogger
from typing import (
    TYPE_CHECKING,
    Any,
    Protocol,
    Self,
    cast,
    overload,
)

from zx.core import Who
from zx.lib.hypertext.exceptions import ExpectedStatus, HTTPError
from zx.lib.hypertext.response import decoders
from zx.lib.serial.json import stringify
from zx.str import varchar

if TYPE_CHECKING:
    import builtins
    from collections.abc import Callable, Coroutine, Generator

    import aiohttp.client_reqrep
    import feedparser
    import httpx2 as httpx
    import multidict
    import requests
    from lxml.etree import _Element
    from lxml.html import HtmlElement

    from zx.lib.serial.json import JSONType

    CIMultiDict = multidict.CIMultiDict[str]
    FeedParserDict = feedparser.FeedParserDict

__all__ = (
    "BackendAdapter",
    "Catch",
    "HTTPResponseError",
    "Internals",
    "MimeType",
    "NoDecoderError",
    "Response",
    "register",
)

_ERROR_CODES = range(400, 600)

logger = getLogger(__name__)


class HTTPResponseError(Exception):
    """No adapter matched, parity mismatch, or registry conflict."""


class NoDecoderError(HTTPResponseError):
    """No decoder matches the response content type."""

    def __init__(self, content_type: str | None, url: str, /) -> None:
        self.content_type = content_type
        self.url = url
        msg = (
            f"no decoder for content type {content_type!r} of {url!r} response"
        )
        super().__init__(msg)


@dataclass(frozen=True)
class Internals:
    """Normalized response data: the seam between adapters and the core."""

    url: str
    status: int
    reason: str | None
    headers: CIMultiDict
    content: bytes


@dataclass(frozen=True)
class MimeType:
    """Detected MIME type of the response content."""

    type: str | None
    text: str | None

    def as_dict(self) -> dict[str, str | None]:
        """Render as a plain mapping for diagnostics."""
        return {"type": self.type, "text": self.text}


class BackendAdapter[B](Protocol):
    """Adapter contract: how to read one backend's raw response.

    Read-only property so implementations may use a plain ClassVar
    attribute while the protocol stays covariant in B.
    """

    @property
    def raw_type(self) -> type[B]: ...

    def sync_read(self, raw: B, /) -> Internals | None:
        """Read the response synchronously, or None if unsupported."""
        ...

    async def async_read(self, raw: B, /) -> Internals | None:
        """Read the response asynchronously, or None if unsupported."""
        ...


_ADAPTERS: list[BackendAdapter[object]] = []


def register[B](adapter: BackendAdapter[B], /) -> BackendAdapter[B]:
    """Register a backend adapter; importing the module is the trigger."""
    for existing in _ADAPTERS:
        if existing.raw_type is adapter.raw_type:
            msg = f"adapter for {Who.Is(adapter.raw_type)} already registered"
            raise HTTPResponseError(msg)
    _ADAPTERS.append(cast("BackendAdapter[object]", adapter))
    return adapter


def _find_adapter(raw: object, /) -> BackendAdapter[object]:
    """Locate an adapter by exact type, then by isinstance."""
    for adapter in _ADAPTERS:
        if type(raw) is adapter.raw_type:
            return adapter

    for adapter in _ADAPTERS:
        if isinstance(raw, adapter.raw_type):
            return adapter

    known = ", ".join(Who.Is(a.raw_type) for a in _ADAPTERS) or "none"
    msg = (
        f"no adapter for {Who.Is(raw)}; "
        f"registered: {known}; "
        f"import zx.lib.hypertext.response.adapters.<backend> to add one"
    )
    raise HTTPResponseError(msg)


class Response[B]:
    """Backend-agnostic response; B is the raw backend type (inference)."""

    def __init__(self, internals: Internals, raw: B, /) -> None:
        self._internals = internals
        self.raw = raw

    # --- construction -------------------------------------------------

    @overload
    @classmethod
    def read(cls, raw: requests.Response, /) -> Self: ...

    @overload
    @classmethod
    def read(
        cls,
        raw: aiohttp.client_reqrep.ClientResponse,
        /,
    ) -> Coroutine[None, None, Self]: ...

    @overload
    @classmethod
    def read(
        cls,
        raw: httpx.Response,
        /,
    ) -> Self | Coroutine[None, None, Self]: ...

    @overload
    @classmethod
    def read(cls, raw: B, /) -> Self | Coroutine[None, None, Self]: ...

    @classmethod
    def read(cls, raw: object, /) -> Self | Coroutine[None, None, Self]:
        """Materialize now, or return a coroutine for async-only backends."""
        adapter = _find_adapter(raw)
        internals = adapter.sync_read(raw)
        if internals is None:
            return cls.aread(cast("B", raw))
        return cls(internals, cast("B", raw))

    @classmethod
    async def aread(cls, raw: B, /) -> Self:
        """Strictly-typed async materialization path."""
        adapter = _find_adapter(raw)
        internals = await adapter.async_read(raw)
        if internals is None:
            msg = f"{Who.Is(raw)} is sync-only, use read()"
            raise HTTPResponseError(msg)
        return cls(internals, raw)

    @classmethod
    def from_disk(cls, *_args: object, **_kw: object) -> Self:
        """Disk-cached response loading; not implemented yet."""
        msg = "from_disk is not implemented yet"
        raise NotImplementedError(msg)

    def __await__(self) -> Generator[None, None, Self]:
        """A materialized response awaits to itself: uniform `await resp`."""
        return self._self().__await__()

    async def _self(self) -> Self:
        return self

    # --- normalized surface -------------------------------------------

    @property
    def url(self) -> str:
        """Final URL of the response."""
        return self._internals.url

    @property
    def status_code(self) -> int:
        """Raw status code as reported by the backend."""
        return self._internals.status

    @property
    def status(self) -> HTTPStatus | int:
        """stdlib HTTPStatus constant; non-standard codes stay int."""
        try:
            return HTTPStatus(self._internals.status)
        except ValueError:
            return self._internals.status

    @property
    def reason(self) -> str:
        """Reason phrase, falling back to the status phrase."""
        if (reason := self._internals.reason) and reason != "<none>":
            return reason
        try:
            return HTTPStatus(self.status_code).phrase
        except ValueError:
            return f"Unknown ({self.status_code})"

    @property
    def headers(self) -> CIMultiDict:
        """Case-insensitive multi-value headers."""
        return self._internals.headers

    @property
    def content(self) -> builtins.bytes:
        """Raw response body."""
        return self._internals.content

    @property
    def ok(self) -> bool:
        """True when the status is not a client or server error."""
        return self.status_code not in _ERROR_CODES

    @property
    def exception(self) -> type[HTTPError]:
        """Exception class matching the status code."""
        return HTTPError.by_code(self.status_code)

    @property
    def headerstring(self) -> str:
        """JSON rendering of headers for diagnostics and catch.args."""
        plain: dict[str, str | tuple[str, ...]] = {}
        for key in dict.fromkeys(self.headers.keys()):
            values = self.headers.getall(key)
            plain[key] = values[0] if len(values) == 1 else tuple(values)
        return stringify(plain)

    @property
    def mime(self) -> MimeType:
        """Sniffed MIME type of the content."""
        msg = (
            f"could't detect mime-type for {self.url!r} response: "
            f"{self.headerstring}: {self.content!r}"
        )

        if not self.content:
            logger.info(msg)
            return MimeType(None, None)

        try:
            if detected := varchar(self.content).mime:
                result = MimeType(
                    type=detected["type"],
                    text=detected.get("description"),
                )
            else:
                logger.info(msg)
                return MimeType(None, None)
        except Exception:
            logger.exception(msg)
            raise

        logger.debug("mime-type for %r is %r", self.url, result.type)
        return result

    @property
    def content_type(self) -> str | None:
        """Content-Type header value: lowercase, without parameters."""
        raw = self.headers.get("Content-Type", "")
        if stripped := raw.split(";", 1)[0].strip():
            return stripped.lower()
        return None

    # --- content decoders ----------------------------------------------

    @property
    def bytes(self) -> builtins.bytes:
        return decoders.to_bytes(self.content)

    @property
    def text(self) -> str:
        return decoders.to_text(self.content)

    @property
    def feed(self) -> FeedParserDict:
        return decoders.to_feed(self.content)

    @property
    def json(self) -> JSONType:
        return decoders.to_json(self.content)

    @property
    def html(self) -> HtmlElement:
        return decoders.to_html(self.content)

    @property
    def xml(self) -> _Element:
        return decoders.to_xml(self.content)

    @property
    def data(self) -> Any:  # noqa: ANN401
        """Content decoded per Content-Type, falling back to mime sniffing."""
        decoder = decoders.find(self.content_type)
        if decoder is None:
            logger.warning(
                "couldn't select decoder by content_type=%r for %r, "
                "falling back to mime sniffing",
                self.content_type,
                self.url,
            )
            content_type = self.mime.type
            if (decoder := decoders.find(content_type)) is None:
                raise NoDecoderError(content_type, self.url)

        return decoder(self.content)


class Catch[B]:  # public API name
    def __init__(
        self,
        raw: B,
        /,
        *,
        expect: ExpectedStatus = None,
        handler: (
            Callable[[HTTPError, Response[Any]], HTTPError | None] | None
        ) = None,
    ) -> None:
        self._raw = raw
        self._expect = expect
        self._handler = handler

    @staticmethod
    def _normalize(expected: ExpectedStatus, /) -> set[int]:
        if expected is None:
            return set()
        if isinstance(expected, int | HTTPStatus):
            return {int(expected)}
        return {int(code) for code in expected}

    def _check(self, response: Response[B], /) -> Response[B]:
        expected = self._normalize(self._expect)
        if self._expect is None:
            if response.status_code not in _ERROR_CODES:
                return response
        elif response.status_code in expected:
            return response

        error = HTTPError.by_code(response.status_code)(response)
        if self._handler and (replacement := self._handler(error, response)):
            raise replacement
        raise error

    @overload
    def read(
        self: Catch[requests.Response],
    ) -> Response[requests.Response]: ...

    @overload
    def read(
        self: Catch[aiohttp.client_reqrep.ClientResponse],
    ) -> Coroutine[
        Any,
        Any,
        Response[aiohttp.client_reqrep.ClientResponse],
    ]: ...

    @overload
    def read(
        self: Catch[httpx.Response],
    ) -> (
        Response[httpx.Response]
        | Coroutine[None, None, Response[httpx.Response]]
    ): ...

    @overload
    def read(self) -> Response[B] | Coroutine[None, None, Response[B]]: ...

    def read(self) -> Response[B] | Coroutine[None, None, Response[B]]:
        """Materialize + status-check: sync now, or a coroutine."""
        result = Response.read(self._raw)
        if iscoroutine(result):
            return self._checked(result)
        return self._check(result)

    async def _checked(
        self,
        awaited: Coroutine[None, None, Response[B]],
        /,
    ) -> Response[B]:
        return self._check(await awaited)

    async def aread(self) -> Response[B]:
        """Strictly-typed async materialization + status-check."""
        return self._check(await Response.aread(self._raw))

    def __await__(self) -> Generator[None, None, Response[B]]:
        """Uniform `response = await Catch(raw)` for every backend."""

        async def _resolve() -> Response[B]:
            result = self.read()
            if iscoroutine(result):
                return await result
            return result

        return _resolve().__await__()
