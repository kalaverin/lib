"""Content decoders and the Content-Type -> decoder matching table.

Every decoder is a plain function taking raw response content. The
table maps MIME type patterns to decoders; patterns support exact
matches, ``type/*`` wildcards, and structured suffixes (``*+xml``).

The ``feedparser`` and ``lxml`` imports are lazy: they live in the
optional ``decoders`` extra, so importing this module must not require
them (the ImportError surfaces only when the matching decoder runs).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from orjson import loads as to_orjson

from zx.str import varchar

if TYPE_CHECKING:
    import feedparser
    from lxml.etree import _Element
    from lxml.html import HtmlElement

    from zx.lib.serial.json import JSONType

__all__ = (
    "DECODERS",
    "Decoder",
    "find",
    "to_bytes",
    "to_feed",
    "to_html",
    "to_json",
    "to_text",
    "to_xml",
)

type Decoder = Callable[[bytes], Any]  # type: ignore[explicit-any]


def to_bytes(content: bytes, /) -> bytes:
    return varchar.to_bytes(content)


def to_text(content: bytes, /) -> str:
    return varchar.to_text(content)


def to_feed(content: bytes, /) -> feedparser.FeedParserDict:
    import feedparser  # noqa: PLC0415

    return feedparser.parse(content)


def to_json(content: bytes, /) -> JSONType:
    return cast("JSONType", to_orjson(content))


def to_html(content: bytes, /) -> HtmlElement:
    from lxml import html  # noqa: PLC0415

    return html.document_fromstring(content)


def to_xml(content: bytes, /) -> _Element:
    from lxml import etree  # noqa: PLC0415

    return etree.fromstring(content)


_MIME_PARTS = 2

_RANK_ANY = 0
_RANK_ANY_SUFFIX = 1
_RANK_TYPE_SUFFIX = 2
_RANK_TYPE = 3
_RANK_EXACT = 4


def _split(mime: str, /) -> tuple[str, str] | None:
    parts = mime.lower().split("/")
    if len(parts) != _MIME_PARTS or not all(parts):
        return None
    return parts[0], parts[1]


def _specificity(  # noqa: PLR0911  # ranked matching is inherently multi-return
    pattern: str,
    mime: tuple[str, str],
    /,
) -> int | None:
    """Rank how specifically a pattern matches the parsed MIME type.

    Ranks: exact 4, ``type/*`` 3, ``type/*+suffix`` 2, ``*+suffix`` 1
    (RFC 6838 structured suffix), ``*/*`` 0; None when there is no match.
    A pattern without a slash (``*+xml``) means any type.
    """
    pattern = pattern.lower()
    if "/" in pattern:
        kind, subtype = pattern.split("/", 1)
    else:
        kind, subtype = "*", pattern

    if not kind or not subtype:
        return None

    mime_type, mime_subtype = mime

    if kind == "*" and subtype == "*":
        return _RANK_ANY

    if kind not in (mime_type, "*"):
        return None

    if subtype == "*":
        return _RANK_TYPE

    if subtype == mime_subtype:
        return _RANK_EXACT

    if (
        subtype.startswith("*+")
        and "+" in mime_subtype
        and mime_subtype.rsplit("+", 1)[1] == subtype[2:]
    ):
        return _RANK_ANY_SUFFIX if kind == "*" else _RANK_TYPE_SUFFIX

    return None


DECODERS: list[tuple[str, Decoder]] = [
    ("application/atom+xml", to_feed),
    ("application/rdf+xml", to_feed),
    ("application/rss+xml", to_feed),
    ("application/x-rss+xml", to_feed),
    ("text/x-opml", to_feed),
    ("application/xhtml+xml", to_html),
    ("text/html", to_html),
    ("application/xml", to_xml),
    ("application/rsd+xml", to_xml),
    ("text/xml", to_xml),
    ("*+xml", to_xml),
    ("application/json", to_json),
    ("application/*+json", to_json),
    ("text/plain", to_text),
]


def find(content_type: str | None, /) -> Decoder | None:
    """Locate the best decoder for a Content-Type value.

    Patterns are ranked by specificity (exact > type/* > *+suffix > */*),
    not by table order; malformed input and no-match yield None.
    """
    if not content_type:
        return None

    mime = _split(content_type.split(";", 1)[0].strip())
    if mime is None:
        return None

    best: tuple[int, int, Decoder] | None = None
    for order, (pattern, decoder) in enumerate(DECODERS):
        rank = _specificity(pattern, mime)
        if rank is not None and (
            best is None or (rank, -order) > (best[0], -best[1])
        ):
            best = (rank, order, decoder)

    return best[2] if best else None
