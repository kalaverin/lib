"""Tests for zx.lib.hypertext.url — canonical URL value object."""

import operator
from collections.abc import Callable
from itertools import product

import can_ada
import pytest
from faker import Faker

from zx.lib.hypertext.url import (
    URL,
    IncompleteURLError,
    InvalidURLError,
    URLJoinError,
)

pytestmark = pytest.mark.serial

CANON_SOURCE = "http://user:pass@example.com:8080/p?q=1#f"
CANON_COMPONENTS: dict[str, object] = {
    "scheme": "http",
    "host": "example.com",
    "port": 8080,
    "user": "user",
    "password": "pass",
    "path": "/p",
    "query": "q=1",
    "fragment": "f",
}
NON_DEFAULT_PORT = 8080
CUSTOM_SCHEME = "mydb"
CUSTOM_PORT = 6380

LOWERCASE_CASES = (
    ("HTTP://EXAMPLE.com/", "http", "example.com"),
    ("Https://WWW.Example.COM/path", "https", "www.example.com"),
)
LOWERCASE_IDS = ("upper-case", "mixed-case")

EMPTY_PATH_CASES = (
    "http://example.com",
    "http://example.com?q=1",
    "http://example.com#frag",
)
EMPTY_PATH_IDS = ("bare-authority", "with-query", "with-fragment")

DEFAULT_PORT_CASES = (("http", 80), ("https", 443), ("redis", 6379))
DEFAULT_PORT_IDS = ("http-80", "https-443", "redis-6379")

CREDENTIAL_CASES = (
    ("http://user:pass@x.com/", "user", "pass"),
    ("http://user@x.com/", "user", None),
)
CREDENTIAL_IDS = ("user-with-password", "user-without-password")

INVALID_SOURCE_CASES = (
    "not a url",
    "http://",
    "://broken",
    "http://exa mple.com",
)
INVALID_SOURCE_IDS = (
    "no-scheme",
    "missing-host",
    "leading-colons",
    "space-in-host",
)

STR_CASES = (
    ("http://example.com/", "http://example.com/"),
    ("http://example.com:80/", "http://example.com/"),
    (
        f"http://example.com:{NON_DEFAULT_PORT}/",
        f"http://example.com:{NON_DEFAULT_PORT}/",
    ),
)
STR_IDS = ("no-port", "default-port-dropped", "non-default-port-kept")

NETLOC_CASES = (
    ("http://user:pass@x.com/", "http://x.com"),
    ("http://user:pass@x.com:8080/", "http://x.com:8080"),
    ("https://x.com:443/", "https://x.com"),
)
NETLOC_IDS = ("no-port", "non-default-port", "default-port-dropped")


# --- construction: canonical form ---


@pytest.mark.parametrize(
    "source,expected_scheme,expected_host",
    LOWERCASE_CASES,
    ids=LOWERCASE_IDS,
)
def test_init_mixed_case_source_lowercases_scheme_and_host(
    source: str,
    expected_scheme: str,
    expected_host: str,
) -> None:
    """
    Given: a URL string with mixed-case scheme and host.
    When: it is constructed.
    Then: scheme and host are stored lowercased.
    """
    # --- Arrange ---

    # --- Act ---
    url = URL(source)

    # --- Assert ---
    assert url.scheme == expected_scheme
    assert url.host == expected_host


@pytest.mark.parametrize("source", EMPTY_PATH_CASES, ids=EMPTY_PATH_IDS)
def test_init_empty_path_defaults_to_root(source: str) -> None:
    """
    Given: a URL string without a path component.
    When: it is constructed.
    Then: the path defaults to "/".
    """
    # --- Arrange ---

    # --- Act ---
    url = URL(source)

    # --- Assert ---
    assert url.path == "/"


@pytest.mark.parametrize(
    "scheme,default_port",
    DEFAULT_PORT_CASES,
    ids=DEFAULT_PORT_IDS,
)
def test_init_default_port_dropped_to_none(
    scheme: str,
    default_port: int,
) -> None:
    """
    Given: a URL string carrying the scheme's registered default port.
    When: it is constructed.
    Then: the port is stored as None.
    """
    # --- Arrange ---
    source = f"{scheme}://example.com:{default_port}/"

    # --- Act ---
    url = URL(source)

    # --- Assert ---
    assert url.port is None


def test_init_non_default_port_kept_verbatim() -> None:
    """
    Given: a URL string carrying a port that is not the scheme default.
    When: it is constructed.
    Then: the port is kept as the parsed integer.
    """
    # --- Arrange ---
    source = f"http://example.com:{NON_DEFAULT_PORT}/"

    # --- Act ---
    url = URL(source)

    # --- Assert ---
    assert url.port == NON_DEFAULT_PORT


def test_init_dot_segments_resolved_by_parser() -> None:
    """
    Given: a URL string with relative dot segments in the path.
    When: it is constructed.
    Then: the parser resolves them, leaving a plain absolute path.
    """
    # --- Arrange ---
    source = "http://x.com/./a/../b"

    # --- Act ---
    url = URL(source)

    # --- Assert ---
    assert url.path == "/b"


def test_init_duplicate_path_slashes_preserved() -> None:
    """
    Given: a URL string with consecutive slashes in the path.
    When: it is constructed.
    Then: the empty segment survives — canonical form is spec-strict.
    """
    # --- Arrange ---
    source = "http://x.com/a//b"

    # --- Act ---
    url = URL(source)

    # --- Assert ---
    assert url.path == "/a//b"


@pytest.mark.parametrize(
    "source,expected_user,expected_password",
    CREDENTIAL_CASES,
    ids=CREDENTIAL_IDS,
)
def test_init_credentials_populate_user_and_password(
    source: str,
    expected_user: str,
    expected_password: str | None,
) -> None:
    """
    Given: a URL string with userinfo in the authority.
    When: it is constructed.
    Then: user is always set; password is None when absent.
    """
    # --- Arrange ---

    # --- Act ---
    url = URL(source)

    # --- Assert ---
    assert url.user == expected_user
    assert url.password == expected_password


def test_init_query_and_fragment_stripped_of_markers() -> None:
    """
    Given: a URL string with query and fragment components.
    When: it is constructed.
    Then: query and fragment are stored without '?' and '#' markers.
    """
    # --- Arrange ---
    source = "http://x.com/p?a=1&b=2#section-1"

    # --- Act ---
    url = URL(source)

    # --- Assert ---
    assert url.query == "a=1&b=2"
    assert url.fragment == "section-1"


# --- construction: input types ---


def test_init_from_str_parses_components() -> None:
    """
    Given: a URL string.
    When: it is passed as the source.
    Then: all components land in canonical form.
    """
    # --- Arrange ---

    # --- Act ---
    url = URL(CANON_SOURCE)

    # --- Assert ---
    assert url.as_dict() == CANON_COMPONENTS


def test_init_from_mapping_parses_components() -> None:
    """
    Given: a mapping of components.
    When: it is passed as the source.
    Then: the assembled string parses to the same canonical form.
    """
    # --- Arrange ---
    components = dict(CANON_COMPONENTS)

    # --- Act ---
    url = URL(components)

    # --- Assert ---
    assert url.as_dict() == CANON_COMPONENTS


def test_init_from_keywords_parses_components() -> None:
    """
    Given: components passed as keyword arguments.
    When: no source is given.
    Then: the merged mapping parses to the canonical form.
    """
    # --- Arrange ---

    # --- Act ---
    url = URL(
        scheme="http",
        host="example.com",
        port=NON_DEFAULT_PORT,
        user="user",
        password="pass",  # noqa: S106  # test credential fixture, not real
        path="/p",
        query="q=1",
        fragment="f",
    )

    # --- Assert ---
    assert url.as_dict() == CANON_COMPONENTS


def test_init_from_url_instance_round_trips() -> None:
    """
    Given: an existing URL instance.
    When: it is passed as the source of a new one.
    Then: both instances are equal by value.
    """
    # --- Arrange ---
    original = URL(CANON_SOURCE)

    # --- Act ---
    clone = URL(original)

    # --- Assert ---
    assert clone == original
    assert clone.as_dict() == original.as_dict()


def test_init_from_can_ada_url_parses_components() -> None:
    """
    Given: a can_ada.URL produced by the strict WHATWG parser.
    When: it is passed as the source.
    Then: its href parses to the same canonical form.
    """
    # --- Arrange ---
    source = can_ada.parse(CANON_SOURCE)

    # --- Act ---
    url = URL(source)

    # --- Assert ---
    assert url.as_dict() == CANON_COMPONENTS


def test_init_from_as_dict_round_trips(fake: Faker) -> None:
    """
    Given: a URL built from faker-generated host and path segment.
    When: it is rebuilt from its as_dict() components.
    Then: both instances are equal — the frozen value round-trips.
    """
    # --- Arrange ---
    original = URL(f"https://{fake.domain_name()}/{fake.word()}")

    # --- Act ---
    rebuilt = URL(**original.as_dict())

    # --- Assert ---
    assert rebuilt == original


def test_init_source_with_components_raises_type_error() -> None:
    """
    Given: both a source string and keyword components.
    When: the constructor is called.
    Then: TypeError demands exactly one of the two.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(
        TypeError,
        match="exactly one of source or components",
    ):
        URL("http://example.com/", scheme="http")


def test_init_without_source_or_components_raises_type_error() -> None:
    """
    Given: neither a source nor keyword components.
    When: the constructor is called.
    Then: TypeError demands exactly one of the two.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(
        TypeError,
        match="exactly one of source or components",
    ):
        URL()


# --- construction: failures ---


@pytest.mark.parametrize(
    "source",
    INVALID_SOURCE_CASES,
    ids=INVALID_SOURCE_IDS,
)
def test_init_unparseable_source_raises_invalid_url_error(
    source: str,
) -> None:
    """
    Given: a string the WHATWG parser rejects outright.
    When: it is constructed.
    Then: InvalidURLError explains the parse failure.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(InvalidURLError, match="couldn't parse URL"):
        URL(source)


def test_init_hostless_url_raises_incomplete_url_error() -> None:
    """
    Given: a parseable string with no host (file scheme, empty authority).
    When: it is constructed.
    Then: IncompleteURLError demands scheme and host.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(IncompleteURLError, match="scheme and host required"):
        URL("file:///etc/passwd")


def test_can_parse_garbage_returns_false() -> None:
    """
    Given: a string the parser rejects.
    When: can_parse is asked about it.
    Then: False is returned without raising.
    """
    # --- Arrange ---

    # --- Act ---
    result = URL.can_parse("not a url")

    # --- Assert ---
    assert result is False


def test_can_parse_valid_source_returns_true() -> None:
    """
    Given: a well-formed URL string.
    When: can_parse is asked about it.
    Then: True is returned.
    """
    # --- Arrange ---

    # --- Act ---
    result = URL.can_parse("http://example.com/")

    # --- Assert ---
    assert result is True


def test_try_parse_garbage_returns_none() -> None:
    """
    Given: a string the constructor rejects.
    When: try_parse is asked about it.
    Then: None is returned instead of an exception.
    """
    # --- Arrange ---

    # --- Act ---
    result = URL.try_parse("not a url")

    # --- Assert ---
    assert result is None


def test_try_parse_valid_source_returns_url() -> None:
    """
    Given: a well-formed URL string.
    When: try_parse is asked about it.
    Then: a URL instance equal to direct construction is returned.
    """
    # --- Arrange ---
    source = "http://example.com/"

    # --- Act ---
    result = URL.try_parse(source)

    # --- Assert ---
    assert isinstance(result, URL)
    assert result == URL(source)


# --- ports registry ---


@pytest.mark.usefixtures("default_ports_snapshot")
def test_register_port_default_port_dropped_to_none() -> None:
    """
    Given: a custom scheme registered with a default port.
    When: a URL carries exactly that port.
    Then: the port canonicalizes to None.
    """
    # --- Arrange ---
    URL.register_port(CUSTOM_SCHEME, CUSTOM_PORT)

    # --- Act ---
    url = URL(scheme=CUSTOM_SCHEME, host="db.local", port=CUSTOM_PORT)

    # --- Assert ---
    assert url.port is None


@pytest.mark.usefixtures("default_ports_snapshot")
def test_register_port_scheme_case_insensitive() -> None:
    """
    Given: a default port registered under an upper-case scheme name.
    When: a URL uses the lower-case scheme with that port.
    Then: the port canonicalizes to None.
    """
    # --- Arrange ---
    URL.register_port(CUSTOM_SCHEME.upper(), CUSTOM_PORT)

    # --- Act ---
    url = URL(scheme=CUSTOM_SCHEME, host="db.local", port=CUSTOM_PORT)

    # --- Assert ---
    assert url.port is None


@pytest.mark.usefixtures("default_ports_snapshot")
def test_register_port_unrelated_scheme_keeps_port() -> None:
    """
    Given: a default port registered for one custom scheme.
    When: another scheme carries the same numeric port.
    Then: that port is kept — the registry is per-scheme.
    """
    # --- Arrange ---
    URL.register_port(CUSTOM_SCHEME, CUSTOM_PORT)

    # --- Act ---
    url = URL(scheme="otherdb", host="db.local", port=CUSTOM_PORT)

    # --- Assert ---
    assert url.port == CUSTOM_PORT


# --- representations ---


@pytest.mark.parametrize("source,expected", STR_CASES, ids=STR_IDS)
def test_str_reassembles_canonical_url(
    source: str,
    expected: str,
) -> None:
    """
    Given: parametrized URL strings around the default-port boundary.
    When: the canonical instance is stringified.
    Then: the default port is absent, all other parts are present.
    """
    # --- Arrange ---

    # --- Act ---
    text = str(URL(source))

    # --- Assert ---
    assert text == expected


def test_as_dict_returns_all_eight_components() -> None:
    """
    Given: a fully populated canonical URL.
    When: as_dict is called.
    Then: all eight components are present with their canonical values.
    """
    # --- Arrange ---
    url = URL(CANON_SOURCE)

    # --- Act ---
    components = url.as_dict()

    # --- Assert ---
    assert set(components) == {
        "scheme",
        "host",
        "port",
        "user",
        "password",
        "path",
        "query",
        "fragment",
    }
    assert components == CANON_COMPONENTS


@pytest.mark.parametrize("source,expected", NETLOC_CASES, ids=NETLOC_IDS)
def test_netloc_omits_credentials_and_default_port(
    source: str,
    expected: str,
) -> None:
    """
    Given: parametrized URLs around credentials and the default port.
    When: the netloc pooling key is read.
    Then: credentials never appear; the default port is dropped.
    """
    # --- Arrange ---

    # --- Act ---
    netloc = URL(source).netloc

    # --- Assert ---
    assert netloc == expected


# --- with_* replacers ---

REPLACER_BASE_SOURCE = "http://u:p@x.com:8080/p?q=1#f"
REPLACER_CASES = (
    ("with_scheme", ("https",), "https://u:p@x.com:8080/p?q=1#f"),
    ("with_host", ("h2.x",), "http://u:p@h2.x:8080/p?q=1#f"),
    ("with_port", (None,), "http://u:p@x.com/p?q=1#f"),
    ("with_user", ("adm",), "http://adm:p@x.com:8080/p?q=1#f"),
    ("with_password", ("pw",), "http://u:pw@x.com:8080/p?q=1#f"),
    ("with_path", ("/n",), "http://u:p@x.com:8080/n?q=1#f"),
    ("with_query", ({"a": "9"},), "http://u:p@x.com:8080/p?a=9#f"),
    ("with_fragment", ("g2",), "http://u:p@x.com:8080/p?q=1#g2"),
)
REPLACER_IDS = (
    "scheme",
    "host",
    "port",
    "user",
    "password",
    "path",
    "query-mapping",
    "fragment",
)

REDIS_DEFAULT_PORT = 6379


@pytest.mark.parametrize(
    "method,args,expected_text",
    REPLACER_CASES,
    ids=REPLACER_IDS,
)
def test_with_replacer_returns_new_modified_instance(
    method: str,
    args: tuple[object, ...],
    expected_text: str,
) -> None:
    """
    Given: a fully populated canonical URL.
    When: any of the eight with_* replacers is applied.
    Then: a new instance carries the replaced component, and the
        original string is unchanged.
    """
    # --- Arrange ---
    original = URL(REPLACER_BASE_SOURCE)

    # --- Act ---
    replacement = getattr(original, method)(*args)

    # --- Assert ---
    assert replacement is not original
    assert replacement != original
    assert str(replacement) == expected_text
    assert str(original) == REPLACER_BASE_SOURCE


def test_with_scheme_to_new_scheme_keeps_non_default_port() -> None:
    """
    Given: an http URL carrying a non-default port.
    When: the scheme is replaced with https.
    Then: the port survives — 8080 is not the new scheme's default.
    """
    # --- Arrange ---
    original = URL(f"http://x.com:{NON_DEFAULT_PORT}/")

    # --- Act ---
    replaced = original.with_scheme("https")

    # --- Assert ---
    assert replaced.port == NON_DEFAULT_PORT
    assert str(replaced) == f"https://x.com:{NON_DEFAULT_PORT}/"


def test_with_scheme_from_default_port_stays_dropped() -> None:
    """
    Given: a redis URL whose explicit port equals the scheme default,
        so construction already dropped it.
    When: the scheme is replaced with http.
    Then: the port stays absent — nothing reintroduces it.
    """
    # --- Arrange ---
    original = URL(f"redis://x.com:{REDIS_DEFAULT_PORT}/")

    # --- Act ---
    replaced = original.with_scheme("http")

    # --- Assert ---
    assert original.port is None
    assert replaced.port is None
    assert str(replaced) == "http://x.com/"


def test_with_replacers_leave_original_fields_unchanged() -> None:
    """
    Given: a canonical URL and an as_dict snapshot of its fields.
    When: replacers are chained off it.
    Then: every original field still matches the snapshot.
    """
    # --- Arrange ---
    original = URL(REPLACER_BASE_SOURCE)
    snapshot = original.as_dict()

    # --- Act ---
    original.with_scheme("https").with_query({"z": "0"})

    # --- Assert ---
    assert original.as_dict() == snapshot


# --- join and truediv ---

FULL_URL_PATH_CASES = (
    "http://other.com/x",
    "HTTPS://other.com/x",
    "redis://other.com:6379/x",
)
FULL_URL_PATH_IDS = ("http", "upper-https", "redis")


def test_truediv_relative_segments_append_through_single_slash() -> None:
    """
    Given: a base URL whose path has no trailing slash.
    When: two relative segments are joined via '/'.
    Then: both append through single slashes.
    """
    # --- Arrange ---
    base = URL("http://x.com/v1")

    # --- Act ---
    url = base / "users" / "42"

    # --- Assert ---
    assert str(url) == "http://x.com/v1/users/42"


def test_truediv_trailing_slash_collapses_at_seam() -> None:
    """
    Given: a base URL whose path ends in a slash.
    When: a relative segment is joined via '/'.
    Then: the seam collapses to a single slash.
    """
    # --- Arrange ---
    base = URL("http://x.com/v1/")

    # --- Act ---
    url = base / "users"

    # --- Assert ---
    assert url.path == "/v1/users"


def test_truediv_absolute_path_replaces_current_path() -> None:
    """
    Given: a base URL with an established path.
    When: an absolute path is joined via '/'.
    Then: it replaces the current path entirely.
    """
    # --- Arrange ---
    base = URL("http://x.com/v1")

    # --- Act ---
    url = base / "/root"

    # --- Assert ---
    assert str(url) == "http://x.com/root"


def test_truediv_empty_path_returns_equal_new_instance() -> None:
    """
    Given: a base URL and an empty path segment.
    When: it is joined via '/'.
    Then: an equal but distinct instance is returned — a no-op.
    """
    # --- Arrange ---
    original = URL("http://x.com/v1")

    # --- Act ---
    joined = original / ""

    # --- Assert ---
    assert joined == original
    assert joined is not original


def test_join_method_appends_relative_path() -> None:
    """
    Given: a base URL and a relative path.
    When: join is called directly (the engine behind '/').
    Then: the segment appends through a single slash.
    """
    # --- Arrange ---
    base = URL("http://x.com/v1")

    # --- Act ---
    url = base.join("users")

    # --- Assert ---
    assert str(url) == "http://x.com/v1/users"


def test_join_base_with_query_raises_join_error() -> None:
    """
    Given: a base URL carrying a query.
    When: a path segment is joined onto it.
    Then: URLJoinError refuses to mix query with path building.
    """
    # --- Arrange ---
    base = URL("http://x.com/p?a=1")

    # --- Act / Assert ---
    with pytest.raises(URLJoinError, match="must not contain query"):
        base / "users"


@pytest.mark.parametrize("path", FULL_URL_PATH_CASES, ids=FULL_URL_PATH_IDS)
def test_join_full_url_path_raises_join_error(path: str) -> None:
    """
    Given: parametrized full-URL strings passed as a path.
    When: join is asked to append them.
    Then: URLJoinError rejects them regardless of scheme case.
    """
    # --- Arrange ---
    base = URL("http://x.com/v1")

    # --- Act / Assert ---
    with pytest.raises(URLJoinError, match="not a full URL"):
        base / path


def test_join_preserves_segment_case_in_canonical_form() -> None:
    """
    Given: a mixed-case segment and an upper-case source URL.
    When: the segment is joined onto the base.
    Then: re-canonicalization lowercases scheme and host but
        preserves the path case verbatim.
    """
    # --- Arrange ---
    base = URL("HTTP://X.COM/v1")

    # --- Act ---
    url = base / "Users"

    # --- Assert ---
    assert str(url) == "http://x.com/v1/Users"


# --- normalize ---


def test_normalize_collapses_duplicate_path_slashes() -> None:
    """
    Given: a URL with consecutive slashes in the path.
    When: normalize is applied.
    Then: every run collapses to a single slash.
    """
    # --- Arrange ---
    url = URL("http://x.com/a//b///c")

    # --- Act ---
    normalized = url.normalize()

    # --- Assert ---
    assert normalized.path == "/a/b/c"
    assert str(normalized) == "http://x.com/a/b/c"


def test_normalize_twice_equals_normalize_once() -> None:
    """
    Given: a URL already normalized once.
    When: normalize is applied again.
    Then: the result equals the first pass — idempotent.
    """
    # --- Arrange ---
    url = URL("http://x.com/a//b///c")

    # --- Act ---
    once = url.normalize()
    twice = once.normalize()

    # --- Assert ---
    assert twice == once


def test_normalize_returns_new_object_for_root_path() -> None:
    """
    Given: a URL whose path is already the root '/'.
    When: normalize is applied.
    Then: an equal but distinct instance is returned.
    """
    # --- Arrange ---
    original = URL("http://x.com/")

    # --- Act ---
    normalized = original.normalize()

    # --- Assert ---
    assert normalized is not original
    assert normalized == original


def test_without_normalize_duplicate_slashes_preserved() -> None:
    """
    Given: a URL with consecutive slashes in the path.
    When: it is constructed but never normalized.
    Then: the canonical form keeps the empty segments.
    """
    # --- Arrange ---
    url = URL("http://x.com/a//b")

    # --- Act ---
    text = str(url)

    # --- Assert ---
    assert url.path == "/a//b"
    assert text == "http://x.com/a//b"


# --- query algebra ---

QUERY_BASE_SOURCE = "http://x.com/?a=1&b=2"
QUERY_REPEATED_SOURCE = "http://x.com/?a=1&a=9"

QUERY_SUB_CASES = (
    (QUERY_BASE_SOURCE, "b=2"),
    (QUERY_REPEATED_SOURCE, ""),
)
QUERY_SUB_IDS = ("single-pairs", "repeated-keys")

QUERY_AND_CASES = (
    (QUERY_BASE_SOURCE, {"b"}, "b=2"),
    (QUERY_REPEATED_SOURCE, {"a"}, "a=1&a=9"),
)
QUERY_AND_IDS = ("single-pair", "repeated-keys")

QUERY_TYPE_ERROR_CASES = (
    ("update", operator.or_),
    ("append", operator.add),
    ("toggle", operator.xor),
)
QUERY_TYPE_ERROR_IDS = ("or-update", "add-append", "xor-toggle")


def test_query_or_overwrites_existing_key_and_adds_new_one() -> None:
    """
    Given: a base URL with keys 'a' and 'b'.
    When: '|' overwrites 'a' and introduces 'c'.
    Then: 'a' is overwritten, 'c' is appended, original untouched.
    """
    # --- Arrange ---
    original = URL(QUERY_BASE_SOURCE)

    # --- Act ---
    updated = original | {"a": "9", "c": "3"}

    # --- Assert ---
    assert updated.query == "a=9&b=2&c=3"
    assert original.query == "a=1&b=2"


def test_query_add_appends_and_allows_repeated_keys() -> None:
    """
    Given: a URL already carrying two 'a' pairs.
    When: '+' appends another 'a' pair.
    Then: all three pairs coexist, original order kept.
    """
    # --- Arrange ---
    original = URL(QUERY_REPEATED_SOURCE)

    # --- Act ---
    appended = original + {"a": "7"}

    # --- Assert ---
    assert appended.query == "a=1&a=9&a=7"


@pytest.mark.parametrize(
    "source,expected_query",
    QUERY_SUB_CASES,
    ids=QUERY_SUB_IDS,
)
def test_query_sub_single_key_removes_all_its_pairs(
    source: str,
    expected_query: str,
) -> None:
    """
    Given: parametrized URLs over single and repeated query keys.
    When: '-' removes the key 'a'.
    Then: every pair carrying 'a' is dropped.
    """
    # --- Arrange ---
    original = URL(source)

    # --- Act ---
    reduced = original - "a"

    # --- Assert ---
    assert reduced.query == expected_query


def test_query_sub_key_set_removes_all_listed_keys() -> None:
    """
    Given: a base URL with keys 'a' and 'b'.
    When: '-' removes both keys via a set.
    Then: the query is empty and the original is unchanged.
    """
    # --- Arrange ---
    original = URL(QUERY_BASE_SOURCE)

    # --- Act ---
    reduced = original - {"a", "b"}

    # --- Assert ---
    assert reduced.query == ""
    assert original.query == "a=1&b=2"


@pytest.mark.parametrize(
    "source,keep,expected_query",
    QUERY_AND_CASES,
    ids=QUERY_AND_IDS,
)
def test_query_and_keeps_only_listed_keys(
    source: str,
    keep: set[str],
    expected_query: str,
) -> None:
    """
    Given: parametrized URLs over single and repeated query keys.
    When: '&' keeps only the listed key.
    Then: every pair with that key survives; the rest are dropped.
    """
    # --- Arrange ---
    original = URL(source)

    # --- Act ---
    filtered = original & keep

    # --- Assert ---
    assert filtered.query == expected_query


def test_query_xor_present_key_removed() -> None:
    """
    Given: a base URL with the key 'a' present.
    When: '^' toggles 'a'.
    Then: the 'a' pair is removed, others survive.
    """
    # --- Arrange ---
    original = URL(QUERY_BASE_SOURCE)

    # --- Act ---
    toggled = original ^ {"a": "9"}

    # --- Assert ---
    assert toggled.query == "b=2"
    assert original.query == "a=1&b=2"


def test_query_xor_absent_key_added() -> None:
    """
    Given: a base URL without the key 'c'.
    When: '^' toggles 'c'.
    Then: the pair is appended with the given value.
    """
    # --- Arrange ---
    original = URL(QUERY_BASE_SOURCE)

    # --- Act ---
    toggled = original ^ {"c": "3"}

    # --- Assert ---
    assert toggled.query == "a=1&b=2&c=3"


@pytest.mark.parametrize(
    "label,operation",
    QUERY_TYPE_ERROR_CASES,
    ids=QUERY_TYPE_ERROR_IDS,
)
def test_query_operator_with_non_mapping_raises_type_error(
    label: str,
    operation: Callable[[URL, object], object],
) -> None:
    """
    Given: parametrized query operators '|', '+', '^'.
    When: the right operand is a set, not a mapping.
    Then: TypeError demands a mapping.
    """
    # --- Arrange ---
    original = URL(QUERY_BASE_SOURCE)

    # --- Act / Assert ---
    with pytest.raises(TypeError, match="expects a mapping"):
        operation(original, {"a"})


# --- regression: bugs/zx.lib/013-014 ---


def test_url_operators_regression_bug013() -> None:
    """
    Given: a simple URL without query.
    When: all five query operators and '/' run over it.
    Then: no AttributeError surfaces — the old build called a
        missing self.load while materializing pairs.
    """
    # --- Arrange ---
    base = URL("http://x.com/p")

    # --- Act ---
    step = base | {"a": "1"}
    step = step + {"b": "2"}
    step = step - "a"
    step = step & {"b"}
    combined = step ^ {"c": "3"}
    joined = base / "seg"

    # --- Assert ---
    assert combined.query == "b=2&c=3"
    assert joined.path == "/p/seg"


def test_url_str_includes_query_regression_bug014() -> None:
    """
    Given: a URL carrying a query string.
    When: it is stringified.
    Then: the text contains the query marker and pairs — the old
        build crashed handing the query to the yarl builder.
    """
    # --- Arrange ---
    url = URL("http://x.com/?a=1")

    # --- Act ---
    text = str(url)

    # --- Assert ---
    assert "?a=1" in text


# --- canonical form: exhaustive sweep ---

CANON_SWEEP_CASES = (
    ("http:/example.com", "http://example.com/"),
    ("http:example.com", "http://example.com/"),
    ("HTTP://EXAMPLE.com", "http://example.com/"),
    ("http:///example.com", "http://example.com/"),
    ("http://example.com", "http://example.com/"),
    ("http://example.com/", "http://example.com/"),
    ("http://example.com//path", "http://example.com//path"),
    ("http://example.com/path//sub", "http://example.com/path//sub"),
    ("http://example.com/a/./b/../c", "http://example.com/a/c"),
    ("http://example.com/%7Euser", "http://example.com/%7Euser"),
    ("https://EXAMPLE.com:443/", "https://example.com/"),
    ("http://example.com:80/", "http://example.com/"),
    ("redis://LOCALHOST:6379/0", "redis://LOCALHOST/0"),
    ("ftp://example.com:21/a", "ftp://example.com/a"),
)
CANON_SWEEP_IDS = (
    "scheme-single-slash",
    "scheme-no-slash",
    "host-uppercase",
    "scheme-triple-slash",
    "bare-authority",
    "explicit-root",
    "duplicate-slash-root",
    "duplicate-slash-inner",
    "dot-segments",
    "percent-encoding",
    "https-default-port",
    "http-default-port",
    "redis-default-port",
    "ftp-default-port",
)

NORMALIZE_SWEEP_CASES = (
    ("http://example.com//path", "http://example.com/path"),
    ("http://example.com/path//sub", "http://example.com/path/sub"),
    ("http://example.com//a///b", "http://example.com/a/b"),
    ("HTTP://EXAMPLE.com//PATH", "http://example.com/PATH"),
    ("http://example.com/a/./b/../c", "http://example.com/a/c"),
    ("redis://LOCALHOST:6379//0", "redis://LOCALHOST/0"),
)
NORMALIZE_SWEEP_IDS = (
    "root-duplicate-slash",
    "inner-duplicate-slash",
    "multi-slash-run",
    "special-scheme-lowercase",
    "dot-segments",
    "redis-default-port",
)

INVALID_SWEEP_CASES = (
    "//example.com/path",
    "example.com",
    "http://",
    "not a url",
)
INVALID_SWEEP_IDS = (
    "scheme-relative",
    "host-only",
    "missing-host",
    "garbage",
)


@pytest.mark.parametrize(
    "source,expected",
    CANON_SWEEP_CASES,
    ids=CANON_SWEEP_IDS,
)
def test_init_sweep_source_returns_strict_canonical_form(
    source: str,
    expected: str,
) -> None:
    """
    Given: parametrized sources around WHATWG repair edge cases.
    When: each is constructed and stringified.
    Then: mangled special schemes are repaired, host lowercases for
        special schemes but keeps case for non-special (redis),
        duplicate slashes survive, dot segments resolve, registered
        default ports drop.
    """
    # --- Arrange ---

    # --- Act ---
    text = str(URL(source))

    # --- Assert ---
    assert text == expected


@pytest.mark.parametrize(
    "source,expected",
    NORMALIZE_SWEEP_CASES,
    ids=NORMALIZE_SWEEP_IDS,
)
def test_normalize_sweep_collapses_and_recannonicalizes(
    source: str,
    expected: str,
) -> None:
    """
    Given: parametrized sources with duplicate slashes and canon noise.
    When: each is constructed and normalized.
    Then: normalize() collapses duplicate slashes and re-runs the
        canon — lowercasing scheme and host for special schemes,
        resolving dot segments, dropping default ports — while
        preserving the path case verbatim.
    """
    # --- Arrange ---

    # --- Act ---
    text = str(URL(source).normalize())

    # --- Assert ---
    assert text == expected


@pytest.mark.parametrize("source", INVALID_SWEEP_CASES, ids=INVALID_SWEEP_IDS)
def test_init_sweep_malformed_source_raises_invalid_url_error(
    source: str,
) -> None:
    """
    Given: parametrized malformed strings around the parse boundary.
    When: each is constructed.
    Then: InvalidURLError explains the parse failure.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(InvalidURLError, match="couldn't parse URL"):
        URL(source)


# --- join: exhaustive sweep ---

JOIN_BASES = (
    "http://example.com",
    "http://example.com/",
    "http://example.com/path",
    "http://example.com/path/",
    "http://example.com/path/sub",
)
JOIN_BASE_IDS = (
    "root",
    "root-slash",
    "path",
    "path-slash",
    "path-sub",
)
JOIN_PATHS = ("", "/", "result", "/result", "a/b", "//double")
JOIN_PATH_IDS = (
    "empty",
    "root",
    "relative",
    "absolute",
    "nested",
    "double-slash",
)

JOIN_FULL_URL_PATH_CASES = (
    "http://evil.com/x",
    "HTTPS://EVIL.COM/x",
    "redis://evil.com:6379",
)
JOIN_FULL_URL_PATH_IDS = ("http", "upper-https", "redis")


def expected_join(base: str, path: str) -> str:
    """Hand-derived join expectation; pure table-data construction."""
    origin = "http://example.com"
    base_path = base.removeprefix(origin) or "/"
    if not path:
        expected_path = base_path
    elif path.startswith("/"):
        expected_path = path
    else:
        expected_path = f"{base_path.rstrip('/')}/{path}"
    return f"{origin}{expected_path}"


JOIN_SWEEP_CASES = tuple(
    (base, path, expected_join(base, path))
    for base, path in product(JOIN_BASES, JOIN_PATHS)
)
JOIN_SWEEP_IDS = tuple(
    f"{base_id}--{path_id}"
    for base_id, path_id in product(JOIN_BASE_IDS, JOIN_PATH_IDS)
)


@pytest.mark.parametrize(
    "base,path,expected",
    JOIN_SWEEP_CASES,
    ids=JOIN_SWEEP_IDS,
)
def test_join_sweep_base_path_combinations(
    base: str,
    path: str,
    expected: str,
) -> None:
    """
    Given: parametrized base URLs and path segments, full Cartesian
        sweep of the join contract.
    When: each path is joined onto each base via '/'.
    Then: the canonical string matches the hand-derived expectation —
        empty is a no-op, '/' and absolute paths replace, relative
        paths append through a single slash, a leading duplicate
        slash in an absolute path is preserved.
    """
    # --- Arrange ---

    # --- Act ---
    url = URL(base) / path

    # --- Assert ---
    assert str(url) == expected


@pytest.mark.parametrize(
    "path",
    JOIN_FULL_URL_PATH_CASES,
    ids=JOIN_FULL_URL_PATH_IDS,
)
def test_join_sweep_full_url_path_raises_join_error(path: str) -> None:
    """
    Given: parametrized full-URL strings used as a path segment.
    When: each is joined onto a base URL.
    Then: URLJoinError rejects them regardless of scheme case.
    """
    # --- Arrange ---
    base = URL("http://example.com/path")

    # --- Act / Assert ---
    with pytest.raises(URLJoinError, match="not a full URL"):
        base / path


def test_join_then_normalize_collapses_replaced_double_slash() -> None:
    """
    Given: a joined URL whose absolute replacement preserved a
        duplicate leading slash.
    When: normalize is applied to the join result.
    Then: the composition collapses the seam to a single slash.
    """
    # --- Arrange ---
    url = URL("http://example.com/path") / "//double"

    # --- Act ---
    normalized = url.normalize()

    # --- Assert ---
    assert str(normalized) == "http://example.com/double"


# --- idna and human rendering ---

IDNA_HOST_CASES = (
    ("https://www.GOoglé.com/", "www.xn--googl-fsa.com"),
    ("https://xn--googl-fsa.com/", "xn--googl-fsa.com"),
)
IDNA_HOST_IDS = ("unicode-source", "punycode-source")

UNICODE_SOURCE_TEXT = "https://www.GOoglé.com/pàth?q=✓#frág"
UNICODE_CANON_TEXT = (
    "https://www.xn--googl-fsa.com/p%C3%A0th?q=%E2%9C%93#fr%C3%A1g"
)
UNICODE_HUMAN_TEXT = "https://www.googlé.com/pàth?q=✓#frág"

ASCII_HUMAN_CASES = (
    "http://example.com/a",
    "redis://LOCALHOST/0",
)
ASCII_HUMAN_IDS = ("special-scheme", "non-special-host-case")


@pytest.mark.parametrize(
    "source,expected_host",
    IDNA_HOST_CASES,
    ids=IDNA_HOST_IDS,
)
def test_init_unicode_host_canonicalizes_to_punycode(
    source: str,
    expected_host: str,
) -> None:
    """
    Given: parametrized sources with a unicode host, once raw and
        once already punycode.
    When: each is constructed.
    Then: the canonical host is the lowercased punycode form.
    """
    # --- Arrange ---

    # --- Act ---
    url = URL(source)

    # --- Assert ---
    assert url.host == expected_host


def test_init_unicode_and_punycode_hosts_are_equal() -> None:
    """
    Given: the same domain written once in unicode and once in punycode.
    When: both are constructed.
    Then: the instances are equal and hash identically — canonical
        identity is ASCII-form based.
    """
    # --- Arrange ---
    unicode_url = URL("https://googlé.com/")
    punycode_url = URL("https://xn--googl-fsa.com/")

    # --- Act ---
    equal = unicode_url == punycode_url

    # --- Assert ---
    assert equal
    assert hash(unicode_url) == hash(punycode_url)


def test_human_decodes_idna_and_percent_encoding() -> None:
    """
    Given: a URL with a unicode host and percent-encoded components.
    When: the human rendering is read beside the canonical string.
    Then: human shows the IDNA-decoded host and decoded components,
        while the canonical string stays ASCII and percent-encoded.
    """
    # --- Arrange ---
    url = URL(UNICODE_SOURCE_TEXT)

    # --- Act ---
    human = url.human
    canon = str(url)

    # --- Assert ---
    assert human == UNICODE_HUMAN_TEXT
    assert canon == UNICODE_CANON_TEXT


def test_human_output_round_trips_through_constructor() -> None:
    """
    Given: a unicode URL and its human rendering.
    When: the human form is fed back into the constructor.
    Then: ada re-canonicalizes it — the rebuild equals the original.
    """
    # --- Arrange ---
    url = URL(UNICODE_SOURCE_TEXT)

    # --- Act ---
    rebuilt = URL(url.human)

    # --- Assert ---
    assert rebuilt == url


@pytest.mark.parametrize("source", ASCII_HUMAN_CASES, ids=ASCII_HUMAN_IDS)
def test_human_pure_ascii_url_renders_verbatim(source: str) -> None:
    """
    Given: parametrized URLs with nothing to decode — plain ASCII,
        and a non-special scheme host keeping its case.
    When: the human rendering is compared to the canonical string.
    Then: both renderings are identical — human is a strict display
        form, never a mutation.
    """
    # --- Arrange ---
    url = URL(source)

    # --- Act ---
    human = url.human

    # --- Assert ---
    assert human == str(url)


def test_human_does_not_mutate_instance() -> None:
    """
    Given: a unicode URL with punycode canonical host.
    When: the human property is read.
    Then: the instance stays frozen — canonical string and ASCII
        host are untouched.
    """
    # --- Arrange ---
    url = URL(UNICODE_SOURCE_TEXT)

    # --- Act ---
    human = url.human

    # --- Assert ---
    assert human == UNICODE_HUMAN_TEXT
    assert str(url) == UNICODE_CANON_TEXT
    assert url.host == "www.xn--googl-fsa.com"


# --- boundary and contract audits ---


def test_init_port_zero_kept_on_instance_but_dropped_from_str() -> None:
    """
    Given: a URL string carrying the boundary port 0.
    When: it is constructed and stringified.
    Then: the instance keeps port 0, but _assemble's falsy port check
        drops ':0' from the canonical string.
    """
    # --- Arrange ---

    # --- Act ---
    url = URL("http://x.com:0/")

    # --- Assert ---
    assert url.port == 0  # expected: verify
    assert str(url) == "http://x.com/"  # expected: verify


def test_with_user_none_drops_both_credentials() -> None:
    """
    Given: a credentialed URL.
    When: with_user(None) is applied.
    Then: _assemble omits the whole userinfo block once the user is
        falsy — the password is dropped together with it.
    """
    # --- Arrange ---
    original = URL("http://u:p@x.com/")

    # --- Act ---
    stripped = original.with_user(None)

    # --- Assert ---
    assert stripped.user is None
    assert stripped.password is None
    assert str(stripped) == "http://x.com/"


def test_with_password_none_keeps_user_without_password() -> None:
    """
    Given: a credentialed URL.
    When: with_password(None) is applied.
    Then: the user survives alone — _assemble renders a bare userinfo.
    """
    # --- Arrange ---
    original = URL("http://u:p@x.com/")

    # --- Act ---
    stripped = original.with_password(None)

    # --- Assert ---
    assert stripped.user == "u"
    assert stripped.password is None
    assert str(stripped) == "http://u@x.com/"


def test_with_query_empty_string_clears_query_marker() -> None:
    """
    Given: a URL carrying a query.
    When: with_query("") is applied.
    Then: the query is empty and the canonical string has no '?'.
    """
    # --- Arrange ---
    original = URL("http://x.com/p?a=1")

    # --- Act ---
    cleared = original.with_query("")

    # --- Assert ---
    assert cleared.query == ""
    assert "?" not in str(cleared)


def test_with_fragment_empty_string_clears_fragment_marker() -> None:
    """
    Given: a URL carrying a fragment.
    When: with_fragment("") is applied.
    Then: the fragment is empty and the canonical string has no '#'.
    """
    # --- Arrange ---
    original = URL("http://x.com/p#f")

    # --- Act ---
    cleared = original.with_fragment("")

    # --- Assert ---
    assert cleared.fragment == ""
    assert "#" not in str(cleared)


def test_with_query_mapping_percent_encodes_unicode_value() -> None:
    """
    Given: a query mapping with a non-ASCII value.
    When: with_query is applied.
    Then: urlencode percent-encodes the UTF-8 bytes in the raw query.
    """
    # --- Arrange ---
    original = URL("http://x.com/")

    # --- Act ---
    updated = original.with_query({"q": "✓"})

    # --- Assert ---
    assert updated.query == "q=%E2%9C%93"
    assert str(updated) == "http://x.com/?q=%E2%9C%93"


def test_with_path_percent_encodes_unicode_segment() -> None:
    """
    Given: a non-ASCII path segment.
    When: with_path is applied.
    Then: ada percent-encodes the canonical path.
    """
    # --- Arrange ---
    original = URL("http://x.com/")

    # --- Act ---
    updated = original.with_path("/café")

    # --- Assert ---
    assert updated.path == "/caf%C3%A9"
    assert str(updated) == "http://x.com/caf%C3%A9"


def test_as_dict_round_trip_with_all_none_optionals() -> None:
    """
    Given: a URL with all-None optionals and empty query and fragment.
    When: it is rebuilt from its as_dict() components.
    Then: both instances are equal — the minimal form round-trips.
    """
    # --- Arrange ---
    original = URL("http://x.com/p")

    # --- Act ---
    rebuilt = URL(**original.as_dict())

    # --- Assert ---
    assert original.as_dict() == {
        "scheme": "http",
        "host": "x.com",
        "port": None,
        "user": None,
        "password": None,
        "path": "/p",
        "query": "",
        "fragment": "",
    }
    assert rebuilt == original


JOIN_DOT_CASES = (
    (".", "/a/b/"),
    ("..", "/a/"),
)
JOIN_DOT_IDS = ("dot", "dot-dot")


@pytest.mark.parametrize(
    "segment,expected_path",
    JOIN_DOT_CASES,
    ids=JOIN_DOT_IDS,
)
def test_join_dot_segments_resolved_by_ada(
    segment: str,
    expected_path: str,
) -> None:
    """
    Given: a base URL with a nested non-root path.
    When: '.' or '..' is joined onto it.
    Then: ada resolves the dot segments during re-canonicalization —
        '.' keeps the last segment and adds a slash, '..' pops it.
    """
    # --- Arrange ---
    base = URL("http://x.com/a/b")

    # --- Act ---
    joined = base.join(segment)

    # --- Assert ---
    assert joined.path == expected_path  # expected: verify
    assert str(joined) == f"http://x.com{expected_path}"  # expected: verify


def test_human_decodes_percent_encoded_credentials() -> None:
    """
    Given: a URL with percent-encoded credentials.
    When: the human rendering is read beside the canonical string.
    Then: human shows the decoded userinfo while str stays encoded;
        the stored fields remain in encoded form.
    """
    # --- Arrange ---
    url = URL("http://user%40x:p%40ss@x.com/")

    # --- Act ---
    human = url.human
    canon = str(url)

    # --- Assert ---
    assert url.user == "user%40x"  # expected: verify
    assert url.password == "p%40ss"  # expected: verify
    assert canon == "http://user%40x:p%40ss@x.com/"  # expected: verify
    assert human == "http://user@x:p@ss@x.com/"  # expected: verify


def test_init_out_of_range_port_raises_invalid_url_error() -> None:
    """
    Given: a URL string carrying a port beyond 65535.
    When: it is constructed.
    Then: can_ada rejects the port — InvalidURLError translates the
        parser failure.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(InvalidURLError):  # expected: verify
        URL("http://x.com:99999/")


BLANK_QUERY_SOURCE = "http://x.com/?a=&b=2"


def test_query_sub_removes_blank_valued_key() -> None:
    """
    Given: a query mixing a blank-valued key with a normal one.
    When: '-' removes the blank-valued key.
    Then: only the surviving pair is re-encoded into the string.
    """
    # --- Arrange ---
    original = URL(BLANK_QUERY_SOURCE)

    # --- Act ---
    reduced = original - "a"

    # --- Assert ---
    assert str(reduced) == "http://x.com/?b=2"


def test_query_and_keeps_blank_valued_key() -> None:
    """
    Given: a query mixing a blank-valued key with a normal one.
    When: '&' keeps only the blank-valued key.
    Then: the blank pair survives as 'a=' in the string.
    """
    # --- Arrange ---
    original = URL(BLANK_QUERY_SOURCE)

    # --- Act ---
    kept = original & {"a"}

    # --- Assert ---
    assert str(kept) == "http://x.com/?a="


def test_query_or_overwrites_blank_valued_key() -> None:
    """
    Given: a query mixing a blank-valued key with a normal one.
    When: '|' overwrites the blank-valued key.
    Then: the merged mapping re-encodes with the new value in place.
    """
    # --- Arrange ---
    original = URL(BLANK_QUERY_SOURCE)

    # --- Act ---
    updated = original | {"a": "9"}

    # --- Assert ---
    assert str(updated) == "http://x.com/?a=9&b=2"


def test_normalize_on_clean_non_root_path_returns_equal_instance() -> None:
    """
    Given: a URL whose non-root path has no duplicate slashes.
    When: normalize is applied.
    Then: an equal but distinct instance comes back — a no-op rebuild.
    """
    # --- Arrange ---
    original = URL("http://x.com/clean/path")

    # --- Act ---
    normalized = original.normalize()

    # --- Assert ---
    assert normalized is not original
    assert normalized == original
    assert str(normalized) == "http://x.com/clean/path"


def test_explicit_default_port_url_equals_implicit_and_hashes_match() -> None:
    """
    Given: the same URL written once with an explicit default port and
        once without any port.
    When: both are constructed.
    Then: they are equal and hash identically — the default port
        canonicalizes to None on construction.
    """
    # --- Arrange ---
    explicit = URL("http://x.com:80/")
    implicit = URL("http://x.com/")

    # --- Act ---
    equal = explicit == implicit

    # --- Assert ---
    assert equal
    assert hash(explicit) == hash(implicit)
