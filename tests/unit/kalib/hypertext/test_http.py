"""Tests for zx.lib.HTTP — legacy flat namespace over the hypertext contour."""

from http import HTTPStatus

import httpx
import pytest

from zx.lib import HTTP
from zx.lib.hypertext import URL, Agent, Catch, HTTPError

pytestmark = pytest.mark.serial

EXPECTED_HEADERS = {
    "accept": "*/*",
    "accept-encoding": "br, gzip, deflate, zstd",
}
EXPORTED_NAMES = frozenset(
    {"URL", "Agent", "Catch", "Error", "Headers", "Status", "Response"},
)


# --- identity pins ---


def test_namespace_reexports_hypertext_contour() -> None:
    """
    Given: the flat HTTP namespace module.
    When: its attributes are compared to the hypertext originals.
    Then: every name is the identical object from zx.lib.hypertext.
    """
    # --- Arrange ---

    # --- Act ---

    # --- Assert ---
    assert HTTP.URL is URL
    assert HTTP.Agent is Agent
    assert HTTP.Catch is Catch
    assert HTTP.Error is HTTPError
    assert HTTP.Status is HTTPStatus


def test_headers_pin_default_accept_contour() -> None:
    """
    Given: the Headers module constant.
    When: it is read.
    Then: it pins the default accept and accept-encoding values.
    """
    # --- Arrange ---

    # --- Act ---

    # --- Assert ---
    assert HTTP.Headers == EXPECTED_HEADERS


def test_all_exports_exactly_the_namespace_names() -> None:
    """
    Given: the __all__ declaration of the namespace module.
    When: it is compared to the full set of exported names.
    Then: exactly the six public names are exported, no more, no less.
    """
    # --- Arrange ---

    # --- Act ---

    # --- Assert ---
    assert frozenset(HTTP.__all__) == EXPORTED_NAMES


# --- Catch smoke ---


def test_catch_reads_ok_httpx_response() -> None:
    """
    Given: an httpx 200 response and the httpx adapter imported.
    When: Catch materializes it through the registered adapter.
    Then: the normalized response reports ok.
    """
    # --- Arrange ---
    from zx.lib.hypertext.response.adapters import (  # noqa: PLC0415
        httpx as httpx_adapter,
    )

    request = httpx.Request("GET", "http://example.com/")
    raw = httpx.Response(200, request=request)

    # --- Act ---
    response = Catch(raw).read()

    # --- Assert ---
    assert httpx_adapter.HTTPxAdapter.raw_type is httpx.Response
    assert response.ok is True
