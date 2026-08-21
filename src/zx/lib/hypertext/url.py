"""Canonical URL value object over the can_ada (WHATWG) parser.

Single facade owning the RFC 3986 components; every input is rendered to
a string and strictly parsed by can_ada, so a URL instance always exists
in canonical form. Manipulations produce new frozen instances by routing
the edited components back through the constructor.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import (
    ClassVar,
    Final,
    Self,
    TypedDict,
    Unpack,
    cast,
    override,
)
from urllib.parse import parse_qsl, unquote, urlencode

import can_ada
import yarl

from zx.core import Who
from zx.core.classes import Nothing

__all__ = (
    "URL",
    "IncompleteURLError",
    "InvalidURLError",
    "URLError",
    "URLJoinError",
)

FULL_URL_RE = re.compile(r"(?i)^[a-z][a-z0-9+.-]*://")
MULTI_SLASH_RE = re.compile(r"/+")


class URLComponents(TypedDict, total=False):
    """Component keywords accepted by the URL constructor."""

    scheme: str
    host: str
    port: int | None
    user: str | None
    password: str | None
    path: str
    query: str
    fragment: str


_KNOWN_COMPONENTS: Final = frozenset(URLComponents.__annotations__)

# cleared values for strip(): optional fields drop to None, strings to ""
_STRIPPED: Final[dict[str, object]] = {
    "scheme": "",
    "host": "",
    "port": None,
    "user": None,
    "password": None,
    "path": "",
    "query": "",
    "fragment": "",
}


class URLError(ValueError):
    """Base for all URL contour errors (ValueError-compatible)."""


class InvalidURLError(URLError):
    """The input string could not be parsed (can_ada rejected it)."""


class IncompleteURLError(URLError):
    """The input parsed, but the scheme or host is missing."""


class URLJoinError(URLError):
    """The join()/operator '/' contract was violated."""


@dataclass(frozen=True)
class URL:
    """Canonical RFC 3986 URL: strictly parsed, frozen, self-assembling."""

    scheme: str
    host: str
    port: int | None  # None means the scheme's default port
    user: str | None
    password: str | None
    path: str  # '/' when empty
    query: str  # raw query string without '?'
    fragment: str  # without '#'

    DEFAULT_PORTS: ClassVar[dict[str, int]] = {
        "http": 80,
        "https": 443,
        "ftp": 21,
        "ssh": 22,
        "amqp": 5672,
        "redis": 6379,
    }

    # --- construction -------------------------------------------------

    def __init__(
        self,
        source: URLSource = Nothing,
        /,
        **components: Unpack[URLComponents],
    ) -> None:
        """Build a canonical URL from any supported source.

        Args:
            source: A string, a Mapping of components, a yarl.URL,
                a can_ada.URL, or another URL. Everything is rendered to
                a string and strictly parsed by can_ada.
            **components: Component keywords (scheme=..., host=..., ...),
                merged into the Mapping branch when source is omitted.

        Raises:
            InvalidURLError: The rendered string is not parseable.
            IncompleteURLError: The scheme or host is missing.
            TypeError: The source type is unsupported, or both/neither of
                source and components were given.
        """
        if (source is Nothing) == (not components):
            msg = (
                "pass exactly one of source or components, "
                f"got {Who.Is(source)}"
            )
            raise TypeError(msg)

        text = self._stringify(components if source is Nothing else source)
        parsed = self._parse(text)

        scheme = parsed.protocol.removesuffix(":")
        host = parsed.hostname
        if not scheme or not host:
            msg = "invalid URL, scheme and host required"
            raise IncompleteURLError(msg)

        port = int(parsed.port) if parsed.port else None
        if port == self.DEFAULT_PORTS.get(scheme):
            port = None

        set_field: Callable[[object, str, object], None] = object.__setattr__
        set_field(self, "scheme", scheme)
        set_field(self, "host", host)
        set_field(self, "port", port)
        set_field(self, "user", parsed.username or None)
        set_field(self, "password", parsed.password or None)
        set_field(self, "path", parsed.pathname or "/")
        set_field(self, "query", parsed.search.removeprefix("?"))
        set_field(self, "fragment", parsed.hash.removeprefix("#"))

    @staticmethod
    def _stringify(source: object) -> str:
        """Render any supported source type to a URL string."""
        if isinstance(source, str):
            return source

        if isinstance(source, can_ada.URL):
            return source.href

        if isinstance(source, yarl.URL | URL):
            return str(source)

        if isinstance(source, Mapping):
            return _assemble(source)

        msg = f"unsupported URL source: {Who.Is(source)}"
        raise TypeError(msg)

    @staticmethod
    def _parse(text: str) -> can_ada.URL:
        """Strictly parse a string, translating ada's failure to ours."""
        try:
            return can_ada.parse(text)
        except ValueError as error:
            msg = f"couldn't parse URL {text!r}"
            raise InvalidURLError(msg) from error

    @classmethod
    def can_parse(cls, source: URLSource) -> bool:
        """Check whether the source would parse, without raising."""
        try:
            text = cls._stringify(source)
        except TypeError:
            return False
        return can_ada.can_parse(text)

    @classmethod
    def try_parse(cls, source: URLSource) -> Self | None:
        """Parse the source into a URL, returning None on any failure."""
        try:
            return cls(source)
        except (URLError, TypeError):
            return None

    @classmethod
    def register_port(cls, scheme: str, port: int) -> None:
        """Register a default port for a scheme for the whole runtime.

        Startup-phase API: the registry is process-global and not
        thread-safe by design.
        """
        cls.DEFAULT_PORTS[scheme.lower()] = int(port)

    # --- representations ----------------------------------------------

    def as_dict(self) -> URLComponents:
        """Return the component mapping; URL(**url.as_dict()) round-trips."""
        return {
            "scheme": self.scheme,
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "path": self.path,
            "query": self.query,
            "fragment": self.fragment,
        }

    @override
    def __str__(self) -> str:
        """Assemble the canonical string from fields (default port dropped)."""
        return _assemble(self.as_dict())

    @property
    def netloc(self) -> str:
        """Connection-pooling key: scheme://host[:port], no credentials."""
        base = f"{self.scheme}://{self.host}"
        return f"{base}:{self.port}" if self.port is not None else base

    @property
    def human(self) -> str:
        """Human-readable form for display: IDNA-decoded host,
        percent-decoded userinfo, path, query, and fragment.

        Strictly a rendering: the canonical fields stay in their
        ASCII/punycode form, and identity (__eq__/__hash__) never
        involves this representation.
        """
        host = self.host
        if "xn--" in host:
            host = can_ada.idna_decode(host.encode())

        return _assemble(
            {
                **self.as_dict(),
                "host": host,
                "user": unquote(self.user) if self.user else self.user,
                "password": (
                    unquote(self.password) if self.password else self.password
                ),
                "path": unquote(self.path),
                "query": unquote(self.query),
                "fragment": unquote(self.fragment),
            },
        )

    # --- manipulations --------------------------------------------------

    def _replace(self, **changes: object) -> Self:
        """Rebuild through the constructor with some components replaced."""
        merged = cast("URLComponents", {**self.as_dict(), **changes})
        return type(self)(**merged)

    def with_scheme(self, scheme: str, /) -> Self:
        """Return a copy with the scheme replaced (port re-canonicalized)."""
        return self._replace(scheme=scheme)

    def with_host(self, host: str, /) -> Self:
        """Return a copy with the host replaced."""
        return self._replace(host=host)

    def with_port(self, port: int | None, /) -> Self:
        """Return a copy with the port replaced (None drops it)."""
        return self._replace(port=port)

    def with_user(self, user: str | None, /) -> Self:
        """Return a copy with the user replaced (None drops it)."""
        return self._replace(user=user)

    def with_password(self, password: str | None, /) -> Self:
        """Return a copy with the password replaced (None drops it)."""
        return self._replace(password=password)

    def with_path(self, path: str, /) -> Self:
        """Return a copy with the path replaced."""
        return self._replace(path=path)

    def with_query(self, query: str | Mapping[str, str], /) -> Self:
        """Return a copy with the query replaced (mapping is urlencoded)."""
        if isinstance(query, Mapping):
            query = urlencode(list(query.items()))
        return self._replace(query=query)

    def with_fragment(self, fragment: str, /) -> Self:
        """Return a copy with the fragment replaced."""
        return self._replace(fragment=fragment)

    def join(self, path: str, /) -> Self:
        """Join a path segment onto this URL (SDK join_url_path semantics).

        A relative path is appended to the current path through a single
        slash; an absolute path replaces it. An empty path is a no-op.

        Raises:
            URLJoinError: This URL carries a query, or path is a full URL.
        """
        if self.query:
            msg = "base URL must not contain query"
            raise URLJoinError(msg)

        if FULL_URL_RE.match(path):
            msg = "path must be relative, not a full URL"
            raise URLJoinError(msg)

        if not path:
            return self._replace()

        if not path.startswith("/"):
            path = f"{self.path.rstrip('/')}/{path.lstrip('/')}"

        return self._replace(path=path)

    def __truediv__(self, path: str) -> Self:
        """Sugar for join: url / 'segment'."""
        return self.join(path)

    def normalize(self) -> Self:
        """Return a copy with duplicate slashes in the path collapsed.

        Opt-in cleanup beyond the spec-strict canon; the designated
        growth point for future RFC 3986 relative resolution.
        """
        return self._replace(path=MULTI_SLASH_RE.sub("/", self.path))

    # --- query algebra ----------------------------------------------------

    def _query_pairs(self) -> list[tuple[str, str]]:
        return parse_qsl(self.query, keep_blank_values=True)

    def _with_pairs(self, pairs: list[tuple[str, str]]) -> Self:
        return self._replace(query=urlencode(pairs))

    @staticmethod
    def _keys_of(keys: str | Iterable[str]) -> set[str]:
        return {keys} if isinstance(keys, str) else set(keys)

    def __or__(self, params: Mapping[str, str]) -> Self:
        """Update query params, overwriting existing keys: url | {...}."""
        if not isinstance(params, Mapping):  # type: ignore[redundant-expr]
            msg = f"query update expects a mapping, got {Who.Is(params)}"  # type: ignore[unreachable]
            raise TypeError(msg)
        merged = dict(self._query_pairs()) | dict(params)
        return self._with_pairs(list(merged.items()))

    def __add__(self, params: Mapping[str, str]) -> Self:
        """Append query params, repeated keys allowed: url + {...}."""
        if not isinstance(params, Mapping):  # type: ignore[redundant-expr]
            msg = f"query append expects a mapping, got {Who.Is(params)}"  # type: ignore[unreachable]
            raise TypeError(msg)
        return self._with_pairs([*self._query_pairs(), *params.items()])

    def __sub__(self, keys: str | Iterable[str]) -> Self:
        """Remove query keys: url - 'a' or url - {'a', 'b'}."""
        drop = self._keys_of(keys)
        pairs = [p for p in self._query_pairs() if p[0] not in drop]
        return self._with_pairs(pairs)

    def __and__(self, keys: str | Iterable[str]) -> Self:
        """Keep only the given query keys: url & {'a', 'b'}."""
        keep = self._keys_of(keys)
        pairs = [p for p in self._query_pairs() if p[0] in keep]
        return self._with_pairs(pairs)

    def __xor__(self, params: Mapping[str, str]) -> Self:
        """Toggle query keys: present keys are removed, absent are added."""
        if not isinstance(params, Mapping):  # type: ignore[redundant-expr]
            msg = f"query toggle expects a mapping, got {Who.Is(params)}"  # type: ignore[unreachable]
            raise TypeError(msg)
        existing = dict(self._query_pairs())
        toggle = set(params)
        pairs = [pair for pair in self._query_pairs() if pair[0] not in toggle]
        pairs.extend((k, v) for k, v in params.items() if k not in existing)
        return self._with_pairs(pairs)

    def strip(self, /, *components: str) -> Self:
        """Return a copy without the named components.

        Args:
            components: Names from the component contract: ``scheme``,
                ``host``, ``port``, ``user``, ``password``, ``path``,
                ``query``, ``fragment``.

        Raises:
            ValueError: If no components are given, or an unknown
                component name is passed.
            InvalidURLError: If stripping breaks the URL beyond parsing
                (e.g. removing the scheme).
        """
        if not components:
            msg = "no components given"
            raise ValueError(msg)

        unknown = set(components).difference(_KNOWN_COMPONENTS)
        if unknown:
            msg = f"unknown components: {', '.join(sorted(unknown))}"
            raise ValueError(msg)

        changes = {name: _STRIPPED[name] for name in components}
        return self._replace(**changes)


def _assemble(components: Mapping[str, object]) -> str:
    """Assemble a URL string from raw components (pre-parse form)."""
    scheme = components.get("scheme")
    host = components.get("host")
    port = components.get("port")
    user = components.get("user")
    password = components.get("password")
    path = components.get("path")
    query = components.get("query")
    fragment = components.get("fragment")

    authority = str(host or "")
    if port:
        authority = f"{authority}:{port}"
    if user:
        credentials = f"{user}:{password}" if password else str(user)
        authority = f"{credentials}@{authority}"

    text = f"{scheme or ''}://{authority}{path or ''}"
    if query:
        text = f"{text}?{query}"
    if fragment:
        text = f"{text}#{fragment}"
    return text


type URLSource = str | Mapping[str, object] | yarl.URL | can_ada.URL | URL
