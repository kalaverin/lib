"""Tests for zx.lib.hypertext.response — facade, adapters, decoders, Catch."""

import asyncio
import importlib
import inspect
import json
import sys
from collections.abc import Callable
from http import HTTPStatus
from typing import ClassVar

import httpx
import msgpack
import orjson
import pytest
import requests

from zx.lib.hypertext.exceptions import (
    Created,
    HTTPError,
    InternalServerError,
    NotFound,
)
from zx.lib.hypertext.response import decoders
from zx.lib.hypertext.response.core import (
    Catch,
    HTTPResponseError,
    NoDecoderError,
    Response,
    register,
)

pytestmark = pytest.mark.serial

RAW_URL = "http://api.test/resource"
REQUESTS_ADAPTER_MODULE = "zx.lib.hypertext.response.adapters.requests"
HTTPX_ADAPTER_MODULE = "zx.lib.hypertext.response.adapters.httpx"
AIOHTTP_ADAPTER_MODULE = "zx.lib.hypertext.response.adapters.aiohttp"

JSON_CONTENT = b'{"key": "value", "n": 1}'
JSON_HEADERS = {"Content-Type": "application/json; charset=utf-8"}
HTML_CONTENT = b"<html><body><p>Hi</p></body></html>"
XML_CONTENT = b"<root><item>1</item></root>"
RSS_CONTENT = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<rss version="2.0"><channel><title>Feed Title</title></channel></rss>'
)
TEXT_CONTENT = b"hello world"
MSGPACK_CONTENT = msgpack.packb({"key": "value"}, use_bin_type=True)
BINARY_CONTENT = b"\x00\xff\x01\x02\xfe\xfd" * 4


class _DomainServerError(HTTPError.Server):
    """Domain error standing in for a user-supplied replacement."""

    status: ClassVar[HTTPStatus] = HTTPStatus.INTERNAL_SERVER_ERROR


def _replace_with_domain(
    error: HTTPError,
    response: Response[object],
) -> HTTPError | None:
    """Handler returning a domain error replacement."""
    return _DomainServerError(response=error.response)


def _keep_original(
    error: HTTPError,
    response: Response[object],
) -> HTTPError | None:
    """Handler declining to replace the original error."""
    return None


# --- registration & dispatch ---


def test_importing_adapter_module_registers_it(
    requests_raw: Callable[..., requests.Response],
    adapters_registry: None,
) -> None:
    """
    Given: the requests adapter module is not in sys.modules.
    When: it is imported.
    Then: the raw type dispatches through the freshly registered adapter.
    """
    # --- Arrange ---
    sys.modules.pop(REQUESTS_ADAPTER_MODULE, None)

    # --- Act ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)

    # --- Assert ---
    response = Response.read(requests_raw(status=200))
    assert isinstance(response, Response)
    assert response.status_code == 200


def test_duplicate_adapter_registration_raises(
    adapters_registry: None,
) -> None:
    """
    Given: the requests adapter module is imported (adapter registered).
    When: an adapter for the same raw type is registered again.
    Then: HTTPResponseError reports the conflict.
    """
    # --- Arrange ---
    sys.modules.pop(REQUESTS_ADAPTER_MODULE, None)
    module = importlib.import_module(REQUESTS_ADAPTER_MODULE)

    # --- Act / Assert ---
    with pytest.raises(HTTPResponseError, match="already registered"):
        register(module.RequestsAdapter())


def test_unknown_raw_type_raises_no_adapter() -> None:
    """
    Given: a raw object no adapter handles.
    When: Response.read dispatches on it.
    Then: HTTPResponseError names the gap and the import hint.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(HTTPResponseError, match="no adapter") as excinfo:
        Response.read(object())

    # --- Assert ---
    assert "zx.lib.hypertext.response" in str(excinfo.value)
    assert "to add one" in str(excinfo.value)


# --- sync backends ---

SYNC_BACKENDS = ("requests", "httpx")
SYNC_BACKEND_IDS = ("requests", "httpx")


@pytest.mark.parametrize("backend", SYNC_BACKENDS, ids=SYNC_BACKEND_IDS)
def test_read_sync_backend_materializes_internals(
    backend: str,
    requests_raw: Callable[..., requests.Response],
    httpx_raw: Callable[..., httpx.Response],
) -> None:
    """
    Given: parametrized sync backend raw response with headers and body.
    When: Response.read materializes it.
    Then: the normalized surface mirrors the internals; the result is a
        Response, never a coroutine.
    """
    # --- Arrange ---
    importlib.import_module(f"zx.lib.hypertext.response.adapters.{backend}")
    make_raw = requests_raw if backend == "requests" else httpx_raw
    raw = make_raw(
        status=200,
        reason="OK",
        headers=JSON_HEADERS,
        content=JSON_CONTENT,
    )

    # --- Act ---
    result = Response.read(raw)

    # --- Assert ---
    assert isinstance(result, Response)
    assert not inspect.iscoroutine(result)
    response = result
    assert response.url == RAW_URL
    assert response.status_code == HTTPStatus.OK
    assert response.status is HTTPStatus.OK
    assert response.reason == "OK"
    assert response.ok is True
    assert response.content == JSON_CONTENT
    assert response.headers["content-type"] == JSON_HEADERS["Content-Type"]
    assert response.headers["CONTENT-TYPE"] == JSON_HEADERS["Content-Type"]
    assert response.content_type == "application/json"


OK_FLAG_CASES = (
    (200, True),
    (302, True),
    (404, False),
    (500, False),
)
OK_FLAG_IDS = ("ok", "redirect", "not-found", "server-error")


@pytest.mark.parametrize("status,expected", OK_FLAG_CASES, ids=OK_FLAG_IDS)
def test_ok_flag_follows_error_range(
    requests_raw: Callable[..., requests.Response],
    status: int,
    expected: bool,
) -> None:
    """
    Given: parametrized statuses around the 400-599 error range.
    When: the ok flag is read.
    Then: only client and server errors report False.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)

    # --- Act ---
    response = Response.read(requests_raw(status=status))

    # --- Assert ---
    assert response.ok is expected


def test_exception_property_maps_status_to_leaf_error(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a 404 response built by the requests factory.
    When: the exception property is read.
    Then: it is the NotFound leaf class from zx.lib.hypertext.exceptions.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)

    # --- Act ---
    response = Response.read(requests_raw(status=404, reason="Not Found"))

    # --- Assert ---
    assert response.exception is NotFound


def test_headerstring_renders_headers_as_json(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a response carrying two custom headers.
    When: the headerstring property is read.
    Then: headers render as a JSON object with original casing.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)
    response = Response.read(
        requests_raw(headers={"X-A": "1", "X-B": "2"}),
    )

    # --- Act ---
    headerstring = response.headerstring

    # --- Assert ---
    assert json.loads(headerstring) == {"X-A": "1", "X-B": "2"}


def test_httpx_duplicate_headers_exposed_via_getall(
    httpx_raw: Callable[..., httpx.Response],
) -> None:
    """
    Given: an httpx response with two Set-Cookie headers.
    When: it is materialized through the httpx adapter.
    Then: the case-insensitive multi-dict preserves both values.
    """
    # --- Arrange ---
    importlib.import_module(HTTPX_ADAPTER_MODULE)
    raw = httpx_raw(headers=[("Set-Cookie", "a=1"), ("Set-Cookie", "b=2")])

    # --- Act ---
    response = Response.read(raw)

    # --- Assert ---
    assert response.headers.getall("set-cookie") == ["a=1", "b=2"]


def test_headerstring_renders_duplicate_headers_as_tuple(
    httpx_raw: Callable[..., httpx.Response],
) -> None:
    """
    Given: an httpx response with two Set-Cookie headers.
    When: the headerstring property is read.
    Then: the duplicate values collapse into a single JSON array.
    """
    # --- Arrange ---
    importlib.import_module(HTTPX_ADAPTER_MODULE)
    response = Response.read(
        httpx_raw(headers=[("Set-Cookie", "a=1"), ("Set-Cookie", "b=2")]),
    )

    # --- Act ---
    rendered = json.loads(response.headerstring)

    # --- Assert ---
    assert rendered["set-cookie"] == ["a=1", "b=2"]


# --- async backend ---


def test_catch_read_returns_coroutine_for_aiohttp(
    aiohttp_raw: Callable[..., object],
) -> None:
    """
    Given: an aiohttp stub response (async-only backend).
    When: Catch.read dispatches on it.
    Then: a coroutine is returned, not a materialized Response.
    """
    # --- Arrange ---
    importlib.import_module(AIOHTTP_ADAPTER_MODULE)
    raw = aiohttp_raw(status=200, content=TEXT_CONTENT)

    # --- Act ---
    result = Catch(raw).read()

    # --- Assert ---
    assert inspect.iscoroutine(result)

    # drain it so the inner materialization coroutine is awaited too
    async def _drain() -> None:
        assert (await result).content == TEXT_CONTENT

    asyncio.run(_drain())


def test_await_catch_returns_response_with_content(
    aiohttp_raw: Callable[..., object],
) -> None:
    """
    Given: an aiohttp stub response with a JSON body.
    When: the Catch object is awaited.
    Then: the materialized Response exposes the parsed content.
    """

    # --- Arrange ---
    async def scenario() -> None:
        importlib.import_module(AIOHTTP_ADAPTER_MODULE)
        raw = aiohttp_raw(
            status=200,
            reason="OK",
            headers=JSON_HEADERS,
            content=JSON_CONTENT,
        )

        # --- Act ---
        response = await Catch(raw)

        # --- Assert ---
        assert isinstance(response, Response)
        assert response.url == RAW_URL
        assert response.status_code == HTTPStatus.OK
        assert response.content == JSON_CONTENT
        assert response.json == {"key": "value", "n": 1}

    asyncio.run(scenario())


def test_await_materialized_response_returns_itself(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: an already materialized Response.
    When: it is awaited.
    Then: it resolves to itself — uniform `await resp` for every backend.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)
    response = Response.read(requests_raw(status=200))

    async def scenario() -> None:
        # --- Act ---
        same = await response

        # --- Assert ---
        assert same is response

    asyncio.run(scenario())


def test_aread_on_sync_only_backend_raises(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a requests raw response (sync-only backend).
    When: the strict aread path is awaited.
    Then: HTTPResponseError explains the backend is sync-only.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)

    # --- Act / Assert ---
    with pytest.raises(HTTPResponseError, match="sync-only"):
        asyncio.run(Response.aread(requests_raw(status=200)))


# --- decoders ---

FIND_CASES = (
    ("application/rss+xml", "to_feed"),
    ("application/atom+xml", "to_feed"),
    ("application/ld+json", "to_json"),
    ("application/unknown+xml", "to_xml"),
    ("text/rss+xml", "to_xml"),
    ("text/html", "to_html"),
    ("application/json; charset=utf-8", "to_json"),
    ("APPLICATION/RSS+XML", "to_feed"),
    ("application/octet-stream", None),
)
FIND_IDS = (
    "exact-feed",
    "exact-atom",
    "type-suffix-json",
    "any-suffix-unknown-type",
    "any-suffix-other-type",
    "exact-html",
    "charset-tolerated",
    "case-insensitive",
    "no-match",
)


@pytest.mark.parametrize("content_type,expected", FIND_CASES, ids=FIND_IDS)
def test_find_selects_best_decoder(
    content_type: str,
    expected: str | None,
) -> None:
    """
    Given: parametrized Content-Type values covering the ranking table.
    When: decoders.find locates the best decoder.
    Then: identity matches — exact beats suffix patterns; the unknown
        type yields None.
    """
    # --- Arrange ---
    expected_decoder = getattr(decoders, expected) if expected else None

    # --- Act ---
    decoder = decoders.find(content_type)

    # --- Assert ---
    assert decoder is expected_decoder


MALFORMED_CONTENT_TYPES = ("bogus", "a/b/c", "")
MALFORMED_IDS = ("no-slash", "three-parts", "empty")


@pytest.mark.parametrize(
    "content_type",
    MALFORMED_CONTENT_TYPES,
    ids=MALFORMED_IDS,
)
def test_find_malformed_content_type_returns_none(content_type: str) -> None:
    """
    Given: parametrized malformed Content-Type values.
    When: decoders.find is asked about them.
    Then: None is returned instead of a decoder.
    """
    # --- Arrange ---

    # --- Act ---
    decoder = decoders.find(content_type)

    # --- Assert ---
    assert decoder is None


def test_find_none_content_type_returns_none() -> None:
    """
    Given: no Content-Type at all.
    When: decoders.find is asked about it.
    Then: None is returned.
    """
    # --- Arrange ---

    # --- Act ---
    decoder = decoders.find(None)

    # --- Assert ---
    assert decoder is None


def test_json_property_decodes_payload(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a response with a JSON body and a JSON Content-Type.
    When: the json property is read.
    Then: the pinned payload decodes to the matching mapping.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)
    response = Response.read(
        requests_raw(headers=JSON_HEADERS, content=JSON_CONTENT),
    )

    # --- Act ---
    payload = response.json

    # --- Assert ---
    assert payload == {"key": "value", "n": 1}


def test_html_property_decodes_payload(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a response with an HTML body and a text/html Content-Type.
    When: the html property is read.
    Then: lxml hands back the document element with the pinned text.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)
    response = Response.read(
        requests_raw(
            headers={"Content-Type": "text/html"},
            content=HTML_CONTENT,
        ),
    )

    # --- Act ---
    document = response.html

    # --- Assert ---
    assert document.tag == "html"
    assert document.xpath("//p/text()") == ["Hi"]


def test_xml_property_decodes_payload(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a response with an XML body and an application/xml Content-Type.
    When: the xml property is read.
    Then: lxml hands back the root element with the pinned tag.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)
    response = Response.read(
        requests_raw(
            headers={"Content-Type": "application/xml"},
            content=XML_CONTENT,
        ),
    )

    # --- Act ---
    root = response.xml

    # --- Assert ---
    assert root.tag == "root"


def test_feed_property_decodes_payload(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a response with an RSS body and an application/rss+xml type.
    When: the feed property is read.
    Then: feedparser hands back the channel with the pinned title.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)
    response = Response.read(
        requests_raw(
            headers={"Content-Type": "application/rss+xml"},
            content=RSS_CONTENT,
        ),
    )

    # --- Act ---
    feed = response.feed

    # --- Assert ---
    assert feed["feed"]["title"] == "Feed Title"


def test_msgpack_property_decodes_payload(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a response with a msgpack body and an application/msgpack type.
    When: the msgpack property is read.
    Then: the pinned mapping round-trips through packb/loads.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)
    response = Response.read(
        requests_raw(
            headers={"Content-Type": "application/msgpack"},
            content=MSGPACK_CONTENT,
        ),
    )

    # --- Act ---
    payload = response.msgpack

    # --- Assert ---
    assert payload == {"key": "value"}


def test_text_property_decodes_payload(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a response with a plain-text body.
    When: the text property is read.
    Then: the pinned ASCII payload decodes verbatim.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)
    response = Response.read(requests_raw(content=TEXT_CONTENT))

    # --- Act ---
    text = response.text

    # --- Assert ---
    assert text == "hello world"


def test_bytes_property_returns_raw_content(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a response with a plain-text body.
    When: the bytes property is read.
    Then: the raw body bytes come back unchanged.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)
    response = Response.read(requests_raw(content=TEXT_CONTENT))

    # --- Act ---
    content = response.bytes

    # --- Assert ---
    assert content == TEXT_CONTENT


def test_data_selects_decoder_by_content_type(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a response with a JSON Content-Type and a JSON body.
    When: the data property is read.
    Then: the Content-Type decoder parses the payload.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)
    response = Response.read(
        requests_raw(headers=JSON_HEADERS, content=JSON_CONTENT),
    )

    # --- Act ---
    payload = response.data

    # --- Assert ---
    assert payload == {"key": "value", "n": 1}


def test_data_falls_back_to_mime_sniffing(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a response with a JSON body but no Content-Type header.
    When: the data property is read.
    Then: mime sniffing detects the JSON type and the payload parses.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)
    response = Response.read(requests_raw(content=JSON_CONTENT))

    # --- Act ---
    payload = response.data

    # --- Assert ---
    assert payload == {"key": "value", "n": 1}


def test_data_without_decoder_raises_no_decoder_error(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a response with an octet-stream body no decoder handles.
    When: the data property is read.
    Then: NoDecoderError carries the content type and the url.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)
    response = Response.read(
        requests_raw(
            headers={"Content-Type": "application/octet-stream"},
            content=BINARY_CONTENT,
        ),
    )

    # --- Act / Assert ---
    with pytest.raises(NoDecoderError, match="no decoder") as excinfo:
        _ = response.data

    # --- Assert ---
    assert isinstance(excinfo.value, HTTPResponseError)
    assert isinstance(excinfo.value.content_type, str)
    assert excinfo.value.url == RAW_URL


# --- Catch policy ---

NON_ERROR_STATUSES = (200, 302)
NON_ERROR_IDS = ("ok", "redirect")


@pytest.mark.parametrize("status", NON_ERROR_STATUSES, ids=NON_ERROR_IDS)
def test_catch_default_passes_non_error_statuses(
    requests_raw: Callable[..., requests.Response],
    status: int,
) -> None:
    """
    Given: parametrized non-error statuses and the default Catch policy.
    When: the response is read through Catch.
    Then: the response passes and reports ok.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)

    # --- Act ---
    response = Catch(requests_raw(status=status)).read()

    # --- Assert ---
    assert response.ok is True


def test_catch_default_raises_not_found(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a 404 response and the default Catch policy.
    When: the response is read through Catch.
    Then: the NotFound leaf raises, catchable through the Client family.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)

    # --- Act ---
    with pytest.raises(NotFound) as excinfo:
        Catch(requests_raw(status=404, reason="Not Found")).read()

    # --- Assert ---
    assert isinstance(excinfo.value, HTTPError.Client)
    assert not isinstance(excinfo.value, HTTPError.Server.GatewayTimeout)
    assert type(excinfo.value).__name__ == "NotFound"


def test_catch_default_error_catchable_by_family_tuple(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a 404 response and the default Catch policy.
    When: the read is wrapped in a family-tuple except clause.
    Then: the Client family arm catches the NotFound leaf.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)

    # --- Act / Assert ---
    with pytest.raises((HTTPError.Client, HTTPError.Server.GatewayTimeout)):
        Catch(requests_raw(status=404, reason="Not Found")).read()


STRICT_EXPECT = (HTTPStatus.OK, HTTPStatus.NOT_FOUND)


def test_catch_strict_expect_passes_listed_statuses(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a strict expect tuple of OK and NOT_FOUND.
    When: responses carrying exactly those statuses are read.
    Then: both pass — 404 is ok under an explicit expectation.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)

    # --- Act ---
    ok_response = Catch(
        requests_raw(status=200),
        expect=STRICT_EXPECT,
    ).read()
    missing_response = Catch(
        requests_raw(status=404, reason="Not Found"),
        expect=STRICT_EXPECT,
    ).read()

    # --- Assert ---
    assert ok_response.ok is True
    assert missing_response.status_code == 404


def test_catch_strict_expect_rejects_unlisted_success(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a strict expect tuple of OK and NOT_FOUND.
    When: a 201 response is read.
    Then: the Created leaf raises — the leaf name is Created.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)

    # --- Act ---
    with pytest.raises(Created) as excinfo:
        Catch(requests_raw(status=201), expect=STRICT_EXPECT).read()

    # --- Assert ---
    assert type(excinfo.value).__name__ == "Created"


def test_catch_strict_expect_rejects_unlisted_server_error(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a strict expect tuple of OK and NOT_FOUND.
    When: a 500 response is read.
    Then: the Server family arm catches the InternalServerError leaf.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)

    # --- Act / Assert ---
    with pytest.raises(HTTPError.Server):
        Catch(requests_raw(status=500), expect=STRICT_EXPECT).read()


def test_catch_handler_replacement_raises_domain_error(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a 500 response and a handler returning a domain Server error.
    When: the response is read through Catch.
    Then: the domain replacement raises instead of the original error.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)

    # --- Act ---
    with pytest.raises(_DomainServerError) as excinfo:
        Catch(
            requests_raw(status=500),
            handler=_replace_with_domain,
        ).read()

    # --- Assert ---
    assert isinstance(excinfo.value, HTTPError.Server)
    assert excinfo.value.status is HTTPStatus.INTERNAL_SERVER_ERROR


def test_catch_handler_none_raises_original(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a 500 response and a handler declining to replace the error.
    When: the response is read through Catch.
    Then: the original InternalServerError leaf raises.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)

    # --- Act / Assert ---
    with pytest.raises(InternalServerError):
        Catch(
            requests_raw(status=500),
            handler=_keep_original,
        ).read()


# --- boundary and contract audits ---


def test_mime_sniffs_json_body_without_content_type(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a JSON body with no Content-Type header.
    When: the mime property is read.
    Then: sniffing detects application/json.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)
    response = Response.read(requests_raw(content=JSON_CONTENT))

    # --- Act ---
    mime = response.mime

    # --- Assert ---
    assert mime.type == "application/json"


def test_mime_empty_content_returns_none_none(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a response with empty content.
    When: the mime property is read.
    Then: both MimeType fields are None — nothing to sniff.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)
    response = Response.read(requests_raw(content=b""))

    # --- Act ---
    mime = response.mime

    # --- Assert ---
    assert mime.type is None
    assert mime.text is None


def test_data_empty_content_without_content_type_raises_no_decoder_error(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: empty content and no Content-Type header.
    When: the data property is read.
    Then: the content-type fallback chain ends at None and
        NoDecoderError carries content_type None.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)
    response = Response.read(requests_raw(content=b""))

    # --- Act / Assert ---
    with pytest.raises(NoDecoderError, match="no decoder") as excinfo:
        _ = response.data

    # --- Assert ---
    assert excinfo.value.content_type is None
    assert excinfo.value.url == RAW_URL


REASON_FALLBACK_CASES = (
    ("<none>", "OK"),
    ("", "OK"),
)
REASON_FALLBACK_IDS = ("none-marker", "empty-string")


@pytest.mark.parametrize(
    "reason,expected",
    REASON_FALLBACK_CASES,
    ids=REASON_FALLBACK_IDS,
)
def test_reason_falls_back_to_phrase_for_placeholder_values(
    requests_raw: Callable[..., requests.Response],
    reason: str,
    expected: str,
) -> None:
    """
    Given: a 200 response whose reason is a '<none>' marker or empty
        (the adapter normalizes '' to None).
    When: the reason property is read.
    Then: the HTTPStatus phrase stands in for the missing reason.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)

    # --- Act ---
    response = Response.read(requests_raw(status=200, reason=reason))

    # --- Assert ---
    assert response.reason == expected


def test_reason_unknown_for_non_standard_status(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a response with a non-standard status 599 and no reason.
    When: the reason and status properties are read.
    Then: the reason renders 'Unknown (599)' and the status stays a
        plain int — never an HTTPStatus member.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)

    # --- Act ---
    response = Response.read(requests_raw(status=599, reason=None))

    # --- Assert ---
    assert response.status_code == 599
    assert response.status == 599
    assert not isinstance(response.status, HTTPStatus)
    assert response.reason == "Unknown (599)"


def test_content_type_lowercases_and_strips_parameters(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a Content-Type header with weird casing and parameters.
    When: the content_type property is read.
    Then: the value is lowercased with parameters stripped.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)
    response = Response.read(
        requests_raw(
            headers={"Content-Type": "Application/JSON; Charset=UTF-8"},
        ),
    )

    # --- Act ---
    content_type = response.content_type

    # --- Assert ---
    assert content_type == "application/json"


def test_content_type_empty_header_returns_none(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: an empty Content-Type header.
    When: the content_type property is read.
    Then: None is returned instead of an empty string.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)
    response = Response.read(requests_raw(headers={"Content-Type": ""}))

    # --- Act ---
    content_type = response.content_type

    # --- Assert ---
    assert content_type is None


def test_data_malformed_json_propagates_decode_error(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a valid application/json Content-Type with a malformed body.
    When: the data property is read.
    Then: orjson.JSONDecodeError propagates — the decoder matched, so
        its failure is not converted to NoDecoderError.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)
    response = Response.read(
        requests_raw(headers=JSON_HEADERS, content=b"not json"),
    )

    # --- Act / Assert ---
    with pytest.raises(orjson.JSONDecodeError):
        _ = response.data


def test_headerstring_without_headers_renders_empty_object(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a response carrying no headers at all.
    When: the headerstring property is read.
    Then: it renders an empty JSON object.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)
    response = Response.read(requests_raw())

    # --- Act ---
    headerstring = response.headerstring

    # --- Assert ---
    assert headerstring == "{}"


def test_catch_single_int_expect_passes_listed_status(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a 404 response and a single-int expect of 404.
    When: the response is read through Catch.
    Then: it passes — a single int is a valid expectation set.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)

    # --- Act ---
    response = Catch(
        requests_raw(status=404, reason="Not Found"),
        expect=404,
    ).read()

    # --- Assert ---
    assert response.status_code == 404


def test_catch_single_http_status_member_expect_passes_listed_status(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a 404 response and a single HTTPStatus member expectation.
    When: the response is read through Catch.
    Then: it passes — the member normalizes to {404}.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)

    # --- Act ---
    response = Catch(
        requests_raw(status=404, reason="Not Found"),
        expect=HTTPStatus.NOT_FOUND,
    ).read()

    # --- Assert ---
    assert response.status_code == 404


def test_catch_single_expect_rejects_unlisted_success(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a strict single-member expectation of NOT_FOUND.
    When: a 200 response is read.
    Then: the Created leaf raises — unlisted statuses fail the check.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)

    # --- Act / Assert ---
    with pytest.raises(Created):
        Catch(requests_raw(status=201), expect=HTTPStatus.NOT_FOUND).read()


def test_catch_expected_status_never_invokes_handler(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a 404 response, an expect of 404, and a handler.
    When: the response is read through Catch.
    Then: the handler is never invoked — the expectation short-circuits
        before error construction.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)
    calls: list[HTTPError] = []

    def recorder(
        error: HTTPError,
        response: Response[object],
    ) -> HTTPError | None:
        calls.append(error)
        return None

    # --- Act ---
    response = Catch(
        requests_raw(status=404, reason="Not Found"),
        expect=404,
        handler=recorder,
    ).read()

    # --- Assert ---
    assert response.status_code == 404
    assert calls == []


OK_BOUNDARY_CASES = (
    (399, True),
    (600, True),
)
OK_BOUNDARY_IDS = ("below-range", "above-range")


@pytest.mark.parametrize(
    "status,expected",
    OK_BOUNDARY_CASES,
    ids=OK_BOUNDARY_IDS,
)
def test_ok_flag_true_outside_error_range(
    requests_raw: Callable[..., requests.Response],
    status: int,
    expected: bool,
) -> None:
    """
    Given: parametrized statuses just outside the 400-599 error range.
    When: the ok flag is read.
    Then: both report True — only the inclusive range reports False.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)

    # --- Act ---
    response = Response.read(requests_raw(status=status))

    # --- Assert ---
    assert response.ok is expected


FIND_EXTRA_CASES = (
    ("  application/json  ", "to_json"),
    ("application/json;", "to_json"),
    ("application/xhtml+xml", "to_html"),
    ("text/x-opml", "to_feed"),
    ("application/msgpack; charset=binary", "to_msgpack"),
    ("text/plain", "to_text"),
    ("text/", None),
    ("*/*", None),
)
FIND_EXTRA_IDS = (
    "whitespace-padded",
    "trailing-semicolon",
    "xhtml-exact-beats-any-suffix",
    "opml-feed",
    "msgpack-with-charset",
    "plain-text",
    "empty-subtype",
    "any-any",
)


@pytest.mark.parametrize(
    "content_type,expected",
    FIND_EXTRA_CASES,
    ids=FIND_EXTRA_IDS,
)
def test_find_boundary_content_type_contracts(
    content_type: str,
    expected: str | None,
) -> None:
    """
    Given: parametrized Content-Type values around normalization edges.
    When: decoders.find locates the best decoder.
    Then: whitespace and trailing semicolons are tolerated, the exact
        xhtml pattern beats the '*+xml' suffix pattern, empty subtype
        and the '*/*' wildcard yield None — no catch-all decoder.
    """
    # --- Arrange ---
    expected_decoder = getattr(decoders, expected) if expected else None

    # --- Act ---
    decoder = decoders.find(content_type)

    # --- Assert ---
    assert decoder is expected_decoder


def test_to_json_empty_payload_raises_decode_error() -> None:
    """
    Given: an empty payload.
    When: decoders.to_json is applied directly.
    Then: orjson.JSONDecodeError pins the failure — empty is not a
        valid JSON document.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(orjson.JSONDecodeError):
        decoders.to_json(b"")


# --- HTTPError.response contract ---


TELEGRAM_LIKE_BODY = (
    b'{"ok": false, "error_code": 404, "description": "Not Found"}'
)


def test_catch_error_carries_response_facade(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a 404 response with a JSON error body, caught through Catch.
    When: the raised HTTPError is inspected.
    Then: it reports its own status flags, and .response is the facade
        Response with parsed body, url, status_code, and headerstring.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)
    raw = requests_raw(
        status=404,
        reason="Not Found",
        headers={"Content-Type": "application/json"},
        content=TELEGRAM_LIKE_BODY,
    )

    # --- Act ---
    with pytest.raises(HTTPError) as exc_info:
        Catch(raw).read()

    # --- Assert ---
    error = exc_info.value
    assert error.isNotFound
    assert error.status is HTTPStatus.NOT_FOUND
    assert error.response is not None
    assert error.response.status_code == 404
    assert error.response.url == RAW_URL
    assert error.response.json == {
        "ok": False,
        "error_code": 404,
        "description": "Not Found",
    }
    assert '"Content-Type"' in error.response.headerstring


def test_catch_strict_whitelist_error_carries_response(
    requests_raw: Callable[..., requests.Response],
) -> None:
    """
    Given: a strict whitelist that rejects an otherwise-successful status.
    When: Catch raises for the unexpected status.
    Then: the raised error still carries the response facade.
    """
    # --- Arrange ---
    importlib.import_module(REQUESTS_ADAPTER_MODULE)
    raw = requests_raw(status=201, reason="Created", content=b"{}")

    # --- Act ---
    with pytest.raises(HTTPError.Created) as exc_info:
        Catch(raw, expect=HTTPStatus.OK).read()

    # --- Assert ---
    assert exc_info.value.response is not None
    assert exc_info.value.response.status_code == 201
