"""Tests for zx.lib.hypertext.exceptions — static HTTP error hierarchy."""

import importlib
from collections.abc import Callable
from http import HTTPStatus
from typing import Any, Final

import pytest

from zx.lib.hypertext.exceptions import (
    REGISTRY,
    BadGateway,
    BadRequest,
    ClientError,
    Continue,
    Forbidden,
    Found,
    GatewayTimeout,
    HTTPError,
    HttpVersionNotSupported,
    ImATeapot,
    InformationalError,
    InternalServerError,
    MethodNotAllowed,
    MultipleChoices,
    NonAuthoritativeInformation,
    NotFound,
    Ok,
    RedirectionError,
    ServerError,
    ServiceUnavailable,
    SuccessfulError,
    TooManyRequests,
    Unauthorized,
    UnavailableForLegalReasons,
)
from zx.lib.hypertext.response.core import Response

pytestmark = pytest.mark.serial


def _http_response(
    requests_raw: "Callable[..., object]",
    status: int,
    reason: str,
) -> Response[Any]:
    importlib.import_module("zx.lib.hypertext.response.adapters.requests")
    return Response.read(requests_raw(status=status, reason=reason))


CLIENT_ERROR_LEAVES = (
    BadRequest,
    Unauthorized,
    Forbidden,
    NotFound,
    MethodNotAllowed,
    ImATeapot,
    TooManyRequests,
    UnavailableForLegalReasons,
)
CLIENT_ERROR_IDS = (
    "bad-request",
    "unauthorized",
    "forbidden",
    "not-found",
    "method-not-allowed",
    "im-a-teapot",
    "too-many-requests",
    "unavailable-for-legal-reasons",
)

SERVER_ERROR_LEAVES = (
    InternalServerError,
    BadGateway,
    ServiceUnavailable,
    GatewayTimeout,
    HttpVersionNotSupported,
)
SERVER_ERROR_IDS = (
    "internal-server-error",
    "bad-gateway",
    "service-unavailable",
    "gateway-timeout",
    "http-version-not-supported",
)

FAMILY_PARENTS = (
    InformationalError,
    SuccessfulError,
    RedirectionError,
    ClientError,
    ServerError,
)
FAMILY_PARENT_IDS = (
    "informational",
    "successful",
    "redirection",
    "client",
    "server",
)

LEAF_STATUS_CASES = (
    (Continue, HTTPStatus.CONTINUE),
    (Ok, HTTPStatus.OK),
    (Found, HTTPStatus.FOUND),
    (BadRequest, HTTPStatus.BAD_REQUEST),
    (Unauthorized, HTTPStatus.UNAUTHORIZED),
    (Forbidden, HTTPStatus.FORBIDDEN),
    (NotFound, HTTPStatus.NOT_FOUND),
    (MethodNotAllowed, HTTPStatus.METHOD_NOT_ALLOWED),
    (ImATeapot, HTTPStatus.IM_A_TEAPOT),
    (TooManyRequests, HTTPStatus.TOO_MANY_REQUESTS),
    (UnavailableForLegalReasons, HTTPStatus.UNAVAILABLE_FOR_LEGAL_REASONS),
    (GatewayTimeout, HTTPStatus.GATEWAY_TIMEOUT),
)
LEAF_STATUS_IDS = (
    "continue",
    "ok",
    "found",
    "bad-request",
    "unauthorized",
    "forbidden",
    "not-found",
    "method-not-allowed",
    "im-a-teapot",
    "too-many-requests",
    "unavailable-for-legal-reasons",
    "gateway-timeout",
)

BY_CODE_CASES = (
    (100, HTTPStatus.CONTINUE, Continue),
    (200, HTTPStatus.OK, Ok),
    (302, HTTPStatus.FOUND, Found),
    (400, HTTPStatus.BAD_REQUEST, BadRequest),
    (404, HTTPStatus.NOT_FOUND, NotFound),
    (418, HTTPStatus.IM_A_TEAPOT, ImATeapot),
    (429, HTTPStatus.TOO_MANY_REQUESTS, TooManyRequests),
    (500, HTTPStatus.INTERNAL_SERVER_ERROR, InternalServerError),
    (502, HTTPStatus.BAD_GATEWAY, BadGateway),
    (504, HTTPStatus.GATEWAY_TIMEOUT, GatewayTimeout),
)
BY_CODE_IDS = (
    "100-continue",
    "200-ok",
    "302-found",
    "400-bad-request",
    "404-not-found",
    "418-im-a-teapot",
    "429-too-many-requests",
    "500-internal-server-error",
    "502-bad-gateway",
    "504-gateway-timeout",
)

REGISTRY_MEMBER_CASES = (
    HTTPStatus.CONTINUE,
    HTTPStatus.OK,
    HTTPStatus.FOUND,
    HTTPStatus.NOT_FOUND,
    HTTPStatus.IM_A_TEAPOT,
    HTTPStatus.GATEWAY_TIMEOUT,
)
REGISTRY_MEMBER_IDS = (
    "continue",
    "ok",
    "found",
    "not-found",
    "im-a-teapot",
    "gateway-timeout",
)


# --- hierarchy ---


@pytest.mark.parametrize("leaf", CLIENT_ERROR_LEAVES, ids=CLIENT_ERROR_IDS)
def test_client_error_is_parent_of_four_hundred_leaves(
    leaf: type[HTTPError],
) -> None:
    """
    Given: a representative four-hundred-series leaf class.
    When: its parentage is inspected.
    Then: ClientError is a direct-or-indirect base of it.
    """
    # --- Arrange ---

    # --- Act ---

    # --- Assert ---
    assert issubclass(leaf, ClientError)


@pytest.mark.parametrize("leaf", SERVER_ERROR_LEAVES, ids=SERVER_ERROR_IDS)
def test_server_error_is_parent_of_five_hundred_leaves(
    leaf: type[HTTPError],
) -> None:
    """
    Given: a representative five-hundred-series leaf class.
    When: its parentage is inspected.
    Then: ServerError is a direct-or-indirect base of it.
    """
    # --- Arrange ---

    # --- Act ---

    # --- Assert ---
    assert issubclass(leaf, ServerError)


@pytest.mark.parametrize("family", FAMILY_PARENTS, ids=FAMILY_PARENT_IDS)
def test_family_parents_subclass_http_error(family: type[HTTPError]) -> None:
    """
    Given: one parent per status family (informational through server).
    When: its parentage is inspected.
    Then: HTTPError is the base of every family parent.
    """
    # --- Arrange ---

    # --- Act ---

    # --- Assert ---
    assert issubclass(family, HTTPError)


# --- interception ---


def test_not_found_intercepted_by_family_and_leaf_tuple(
    requests_raw: "Callable[..., object]",
) -> None:
    """
    Given: a NotFound instance built around a 404 facade response.
    When: it propagates against except (Client, Server.GatewayTimeout).
    Then: the tuple intercepts it, and isinstance confirms both views.
    """
    # --- Arrange ---
    error = NotFound(_http_response(requests_raw, 404, "Not Found"))

    # --- Act / Assert ---
    with pytest.raises((HTTPError.Client, HTTPError.Server.GatewayTimeout)):
        raise error

    # --- Assert ---
    assert isinstance(error, HTTPError.Client)
    assert isinstance(error, HTTPError)


def test_gateway_timeout_intercepted_by_family_and_leaf_tuple(
    requests_raw: "Callable[..., object]",
) -> None:
    """
    Given: a GatewayTimeout instance built around a 504 facade response.
    When: it propagates against the same except tuple.
    Then: the tuple intercepts it, and isinstance confirms both views.
    """
    # --- Arrange ---
    error = GatewayTimeout(
        _http_response(requests_raw, 504, "Gateway Timeout"),
    )

    # --- Act / Assert ---
    with pytest.raises((HTTPError.Client, HTTPError.Server.GatewayTimeout)):
        raise error

    # --- Assert ---
    assert isinstance(error, HTTPError.Server.GatewayTimeout)
    assert isinstance(error, HTTPError.Server)


# --- leaf constants ---


@pytest.mark.parametrize("leaf,status", LEAF_STATUS_CASES, ids=LEAF_STATUS_IDS)
def test_leaf_binds_status_constant_and_default_reason(
    leaf: type[HTTPError],
    status: HTTPStatus,
    requests_raw: "Callable[..., object]",
) -> None:
    """
    Given: a leaf class paired with its HTTPStatus constant.
    When: an instance is built around a response carrying the default
        phrase.
    Then: the class and instance bind the status, the reason comes from
        the response, and str renders "value phrase".
    """
    # --- Arrange ---
    facade = _http_response(requests_raw, int(status), status.phrase)

    # --- Act ---
    instance = leaf(facade)

    # --- Assert ---
    assert leaf.status is status
    assert instance.status is status
    assert instance.reason == status.phrase
    assert str(instance) == f"{int(status)} {status.phrase}"


# --- namespace attributes ---


def test_namespace_attributes_bind_families_and_leaves() -> None:
    """
    Given: the HTTPError namespace attributes.
    When: they are compared to the module-level classes.
    Then: every attribute is the identical class object.
    """
    # --- Arrange ---

    # --- Act ---

    # --- Assert ---
    assert HTTPError.Client is ClientError
    assert HTTPError.Server.GatewayTimeout is GatewayTimeout
    assert HTTPError.Client.NotFound is NotFound


# --- by_code ---


@pytest.mark.parametrize("code,status,leaf", BY_CODE_CASES, ids=BY_CODE_IDS)
def test_by_code_maps_int_and_enum_to_leaf(
    code: int,
    status: HTTPStatus,
    leaf: type[HTTPError],
) -> None:
    """
    Given: an int code and its HTTPStatus constant.
    When: by_code is asked for either form.
    Then: both resolve to the identical leaf class.
    """
    # --- Arrange ---

    # --- Act ---
    by_int = HTTPError.by_code(code)
    by_enum = HTTPError.by_code(status)

    # --- Assert ---
    assert by_int is leaf
    assert by_enum is leaf


def test_by_code_accepts_enum_and_int_interchangeably() -> None:
    """
    Given: the same status as enum member and as plain int.
    When: by_code is asked for each form.
    Then: both lookups return the identical class object.
    """
    # --- Arrange ---

    # --- Act ---
    by_enum = HTTPError.by_code(HTTPStatus.NOT_FOUND)
    by_int = HTTPError.by_code(404)

    # --- Assert ---
    assert by_enum is by_int


# --- isXxx checks ---


def test_not_found_instance_flags(
    requests_raw: "Callable[..., object]",
) -> None:
    """
    Given: a NotFound instance built around a 404 facade response.
    When: its isXxx checks are read.
    Then: it flags not-found and client-error, not server-error.
    """
    # --- Arrange ---
    error = NotFound(_http_response(requests_raw, 404, "Not Found"))

    # --- Act ---

    # --- Assert ---
    assert error.isNotFound is True
    assert error.isClientError is True
    assert error.isServerError is False


def test_teapot_instance_flags(
    requests_raw: "Callable[..., object]",
) -> None:
    """
    Given: an ImATeapot instance built around a 418 facade response.
    When: its isXxx checks are read.
    Then: it flags im-a-teapot and client-error, not server-error.
    """
    # --- Arrange ---
    error = ImATeapot(_http_response(requests_raw, 418, "I'm a Teapot"))

    # --- Act ---

    # --- Assert ---
    assert error.isImATeapot is True
    assert error.isClientError is True
    assert error.isServerError is False


def test_base_error_without_status_raises_attribute_error(
    requests_raw: "Callable[..., object]",
) -> None:
    """
    Given: the bare HTTPError base with no bound status constant.
    When: it is constructed around a facade response.
    Then: AttributeError reports the missing status attribute.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(AttributeError, match="has no attribute 'status'"):
        HTTPError(_http_response(requests_raw, 404, "Not Found"))


def test_reason_derives_from_attached_response(
    requests_raw: "Callable[..., object]",
) -> None:
    """
    Given: a NotFound constructed with a response carrying a custom reason.
    When: its fields are read.
    Then: the status is kept, the reason comes from the response, and str
        renders "404 custom".
    """
    # --- Arrange ---
    facade = _http_response(requests_raw, 404, "custom")

    # --- Act ---
    error = NotFound(facade)

    # --- Assert ---
    assert error.reason == "custom"
    assert error.response is facade
    assert str(error) == "404 custom"


# --- registry ---


@pytest.mark.parametrize(
    "status",
    REGISTRY_MEMBER_CASES,
    ids=REGISTRY_MEMBER_IDS,
)
def test_registry_covers_status_member(status: HTTPStatus) -> None:
    """
    Given: a representative HTTPStatus member.
    When: the module-level REGISTRY is inspected.
    Then: the member is a key of the registry.
    """
    # --- Arrange ---

    # --- Act ---

    # --- Assert ---
    assert status in REGISTRY


def test_registry_covers_every_http_status_member() -> None:
    """
    Given: the module-level REGISTRY keyed by HTTPStatus members.
    When: its size is compared to the HTTPStatus enumeration.
    Then: every status member has exactly one registry entry.
    """
    # --- Arrange ---

    # --- Act ---

    # --- Assert ---
    assert len(REGISTRY) == len(list(HTTPStatus))


# --- full registry sweep ---

CENTURY_FAMILIES: Final[dict[int, type[HTTPError]]] = {
    1: InformationalError,
    2: SuccessfulError,
    3: RedirectionError,
    4: ClientError,
    5: ServerError,
}
ALL_LEAVES = tuple(REGISTRY.items())
ALL_LEAF_IDS = tuple(
    f"{int(status)}-{status.name.lower()}" for status in REGISTRY
)


@pytest.mark.parametrize("status,leaf", ALL_LEAVES, ids=ALL_LEAF_IDS)
def test_every_registry_leaf_matches_its_century_family_parent(
    status: HTTPStatus,
    leaf: type[HTTPError],
) -> None:
    """
    Given: every (status, leaf) pair in the REGISTRY mapping.
    When: the leaf parentage is inspected against its century family.
    Then: the leaf subclasses both the family parent and HTTPError.
    """
    # --- Arrange ---

    # --- Act ---
    family = CENTURY_FAMILIES[int(status) // 100]

    # --- Assert ---
    assert issubclass(leaf, family)
    assert issubclass(leaf, HTTPError)


@pytest.mark.parametrize("status,leaf", ALL_LEAVES, ids=ALL_LEAF_IDS)
def test_every_registry_leaf_instantiates_with_default_phrase(
    status: HTTPStatus,
    leaf: type[HTTPError],
    requests_raw: "Callable[..., object]",
) -> None:
    """
    Given: every leaf class in the REGISTRY mapping.
    When: an instance is built around a response carrying the default
        phrase.
    Then: str renders "value phrase" from the status constant.
    """
    # --- Arrange ---
    facade = _http_response(requests_raw, int(status), status.phrase)

    # --- Act ---
    instance = leaf(facade)

    # --- Assert ---
    assert str(instance) == f"{int(status)} {status.phrase}"


@pytest.mark.parametrize("status,leaf", ALL_LEAVES, ids=ALL_LEAF_IDS)
def test_by_code_resolves_every_registry_member(
    status: HTTPStatus,
    leaf: type[HTTPError],
) -> None:
    """
    Given: every (status, leaf) pair in the REGISTRY mapping.
    When: by_code is asked for both the int and the enum member.
    Then: both lookups return the identical leaf class.
    """
    # --- Arrange ---

    # --- Act ---
    by_int = HTTPError.by_code(int(status))
    by_enum = HTTPError.by_code(status)

    # --- Assert ---
    assert by_int is leaf
    assert by_enum is leaf


@pytest.mark.parametrize("status,leaf", ALL_LEAVES, ids=ALL_LEAF_IDS)
def test_family_parent_namespace_attribute_is_every_registry_leaf(
    status: HTTPStatus,
    leaf: type[HTTPError],
) -> None:
    """
    Given: every (status, leaf) pair in the REGISTRY mapping.
    When: the leaf name is resolved as an attribute of its century family.
    Then: the attribute is the identical leaf class.
    """
    # --- Arrange ---

    # --- Act ---
    family = CENTURY_FAMILIES[int(status) // 100]

    # --- Assert ---
    assert getattr(family, leaf.__name__) is leaf


# --- literal phrase pins ---


def test_multi_word_phrases_render_as_literal_str(
    requests_raw: "Callable[..., object]",
) -> None:
    """
    Given: leaves whose status phrases contain multiple words.
    When: str is rendered on instances built around matching responses.
    Then: the exact literal "value phrase" string is pinned.
    """
    # --- Arrange ---

    # --- Act ---
    teapot = ImATeapot(
        _http_response(requests_raw, 418, "I'm a Teapot"),
    )
    choices = MultipleChoices(
        _http_response(requests_raw, 300, "Multiple Choices"),
    )
    non_authoritative = NonAuthoritativeInformation(
        _http_response(requests_raw, 203, "Non-Authoritative Information"),
    )

    # --- Assert ---
    assert str(teapot) == "418 I'm a Teapot"
    assert str(choices) == "300 Multiple Choices"
    assert str(non_authoritative) == "203 Non-Authoritative Information"


# --- attached response ---


def test_manual_construction_carries_response(
    requests_raw: "Callable[..., object]",
) -> None:
    """
    Given: a NotFound built around a facade response.
    When: its fields are read.
    Then: the response attribute is the identical facade, and the reason
        derives from the response.
    """
    # --- Arrange ---
    facade = _http_response(requests_raw, 404, "Not Found")

    # --- Act ---
    error = NotFound(facade)

    # --- Assert ---
    assert error.response is facade
    assert error.reason == facade.reason


# --- family flags sweep ---

FAMILY_FLAG_NAMES = (
    "isInformational",
    "isSuccess",
    "isRedirection",
    "isClientError",
    "isServerError",
)
FAMILY_FLAG_CASES = (
    (Continue, HTTPStatus.CONTINUE, "isInformational"),
    (Ok, HTTPStatus.OK, "isSuccess"),
    (Found, HTTPStatus.FOUND, "isRedirection"),
    (BadRequest, HTTPStatus.BAD_REQUEST, "isClientError"),
    (InternalServerError, HTTPStatus.INTERNAL_SERVER_ERROR, "isServerError"),
)
FAMILY_FLAG_IDS = (
    "continue",
    "ok",
    "found",
    "bad-request",
    "internal-server-error",
)


@pytest.mark.parametrize(
    "leaf,status,flag",
    FAMILY_FLAG_CASES,
    ids=FAMILY_FLAG_IDS,
)
def test_family_flag_true_only_for_own_family(
    leaf: type[HTTPError],
    status: HTTPStatus,
    flag: str,
    requests_raw: "Callable[..., object]",
) -> None:
    """
    Given: one leaf per status family, built around a matching response.
    When: the five family flags are read on the instance.
    Then: only the own-family flag is True, all others are False.
    """
    # --- Arrange ---
    instance = leaf(_http_response(requests_raw, int(status), status.phrase))

    # --- Act ---

    # --- Assert ---
    assert getattr(instance, flag) is True
    for name in FAMILY_FLAG_NAMES:
        if name != flag:
            assert getattr(instance, name) is False


def test_ok_instance_is_not_a_client_error(
    requests_raw: "Callable[..., object]",
) -> None:
    """
    Given: a successful (2xx) instance built around a 200 response.
    When: its client-error flag is read.
    Then: the cross-family negative is False.
    """
    # --- Arrange ---

    # --- Act ---
    error = Ok(_http_response(requests_raw, 200, "OK"))

    # --- Assert ---
    assert error.isClientError is False


# --- by_code error pin ---


def test_by_code_out_of_range_code_raises_value_error() -> None:
    """
    Given: a status code that is not a member of HTTPStatus.
    When: by_code is asked for it.
    Then: the HTTPStatus constructor raises ValueError.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(ValueError, match="not a valid"):
        HTTPError.by_code(999)
