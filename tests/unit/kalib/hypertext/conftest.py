"""Fixtures for hypertext URL and response tests."""

import sys
from collections.abc import Callable, Generator

import aiohttp.client_reqrep
import httpx2 as httpx
import pytest
import requests
import yarl
from multidict import CIMultiDict

from zx.lib.hypertext.response.core import _ADAPTERS
from zx.lib.hypertext.url import URL

RAW_URL_DEFAULT = "http://api.test/resource"


@pytest.fixture
def default_ports_snapshot() -> Generator[None]:
    """Snapshot URL.DEFAULT_PORTS and restore it after the test."""
    saved = dict(URL.DEFAULT_PORTS)
    yield
    URL.DEFAULT_PORTS.clear()
    URL.DEFAULT_PORTS.update(saved)


@pytest.fixture(autouse=True)
def adapters_registry() -> Generator[None]:  # state isolation
    """Snapshot ``core._ADAPTERS`` so registration tests don't leak.

    Adapter modules are also purged from ``sys.modules`` afterwards so
    the import-registers contract stays intact for later tests: a cached
    adapter module must never shadow a cleared registry.
    """
    saved = list(_ADAPTERS)
    yield
    _ADAPTERS.clear()
    _ADAPTERS.extend(saved)
    for name in [
        name
        for name in sys.modules
        if name == "zx.lib.hypertext.response.adapters"
        or name.startswith("zx.lib.hypertext.response.adapters.")
    ]:
        del sys.modules[name]


class _FakePayloadStream:
    """Minimal stand-in for the aiohttp response payload stream."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def exception(self) -> None:
        return None

    def release(self) -> None:
        pass

    def set_exception(self, *args: object, **kwargs: object) -> None:
        pass

    async def read(self) -> bytes:
        return self._payload


@pytest.fixture
def requests_raw() -> Callable[..., requests.Response]:
    """Build a raw requests.Response with pinned internals."""

    def build(
        *,
        status: int = 200,
        reason: str | None = None,
        url: str = RAW_URL_DEFAULT,
        headers: dict[str, str] | None = None,
        content: bytes = b"",
    ) -> requests.Response:
        raw = requests.Response()
        raw.status_code = status
        raw.reason = reason
        raw.url = url
        raw.headers.update(headers or {})
        raw._content = content  # noqa: SLF001  # bypass lazy content read
        return raw

    return build


@pytest.fixture
def httpx_raw() -> Callable[..., httpx.Response]:
    """Build a raw httpx.Response with pinned internals."""

    def build(
        *,
        status: int = 200,
        reason: str | None = None,
        url: str = RAW_URL_DEFAULT,
        headers: dict[str, str] | list[tuple[str, str]] | None = None,
        content: bytes = b"",
    ) -> httpx.Response:
        extensions = {"reason_phrase": reason.encode()} if reason else {}
        return httpx.Response(
            status,
            headers=headers,
            content=content,
            extensions=extensions,
            request=httpx.Request("GET", url),
        )

    return build


@pytest.fixture
def aiohttp_raw() -> Callable[..., aiohttp.client_reqrep.ClientResponse]:
    """Build a raw aiohttp ClientResponse without a connection or loop.

    The object is created via ``__new__`` with a hand-populated ``__dict__``
    because ``ClientResponse.__init__`` demands a connection and a running
    request; the adapter only touches the attributes set here.
    """

    def build(
        *,
        status: int = 200,
        reason: str | None = None,
        url: str = RAW_URL_DEFAULT,
        headers: dict[str, str] | None = None,
        content: bytes = b"",
    ) -> aiohttp.client_reqrep.ClientResponse:
        raw = aiohttp.client_reqrep.ClientResponse.__new__(
            aiohttp.client_reqrep.ClientResponse,
        )
        raw.__dict__.update(
            _cache={},
            content=_FakePayloadStream(content),
            _headers=CIMultiDict(headers or {}),
            _url=yarl.URL(url),
            _loop=None,
            _closed=True,
            _released=True,
            _body=None,
            _traces=[],
            _connection=None,
            _stream_writer=None,
            _session=None,
            _ClientResponse__writer=None,
            status=status,
            reason=reason,
        )
        return raw

    return build
