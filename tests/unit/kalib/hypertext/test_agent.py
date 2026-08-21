"""Tests for zx.lib.hypertext.agent — random user-agent facade."""

import pytest

from zx.lib.hypertext.agent import (
    DEFAULT_PLATFORMS,
    FALLBACK_USER_AGENT,
    USER_AGENT_HEADER,
    Agent,
)

pytestmark = pytest.mark.serial

CUSTOM_FALLBACK = "test-ua"

PLATFORM_CASES = (
    (["mobile"], FALLBACK_USER_AGENT),
    (["mobile", "tablet"], CUSTOM_FALLBACK),
)
PLATFORM_IDS = (
    "mobile-default-fallback",
    "mobile-tablet-custom-fallback",
)


# --- header ---


def test_header_returns_single_lowercase_user_agent_key() -> None:
    """
    Given: a default Agent instance.
    When: its header mapping is read.
    Then: exactly one lowercase "user-agent" key holds a non-empty str.
    """
    # --- Arrange ---

    # --- Act ---
    header = Agent().header

    # --- Assert ---
    assert set(header) == {USER_AGENT_HEADER}
    assert isinstance(header[USER_AGENT_HEADER], str)
    assert header[USER_AGENT_HEADER] != ""


# --- random ---


def test_random_returns_non_empty_strings_on_repeated_access() -> None:
    """
    Given: two fresh Agent instances.
    When: random is read from each.
    Then: both values are non-empty strings — equality is not asserted,
        fake_useragent may legitimately repeat a value.
    """
    # --- Arrange ---
    first_agent = Agent()
    second_agent = Agent()

    # --- Act ---
    first = first_agent.random
    second = second_agent.random

    # --- Assert ---
    assert isinstance(first, str)
    assert isinstance(second, str)
    assert first != ""
    assert second != ""


# --- construction with platforms and fallback ---


@pytest.mark.parametrize(
    "platforms,fallback",
    PLATFORM_CASES,
    ids=PLATFORM_IDS,
)
def test_init_with_platforms_and_fallback_returns_header(
    platforms: list[str],
    fallback: str,
) -> None:
    """
    Given: platform filters with either the default or a custom fallback.
    When: an Agent is constructed and its header read.
    Then: the header carries the single user-agent key with a non-empty
        value — the fallback path cannot be forced, only constructed.
    """
    # --- Arrange ---
    agent = Agent(platforms=platforms, fallback=fallback)

    # --- Act ---
    header = agent.header

    # --- Assert ---
    assert set(header) == {USER_AGENT_HEADER}
    assert header[USER_AGENT_HEADER] != ""


# --- module constants ---


def test_default_platforms_is_desktop_only() -> None:
    """
    Given: the DEFAULT_PLATFORMS module constant.
    When: it is read.
    Then: it pins the desktop-only default filter.
    """
    # --- Arrange ---

    # --- Act ---

    # --- Assert ---
    assert DEFAULT_PLATFORMS == ["desktop"]


def test_user_agent_header_constant_is_lowercase_name() -> None:
    """
    Given: the USER_AGENT_HEADER module constant.
    When: it is read.
    Then: it pins the lowercase header field name.
    """
    # --- Arrange ---

    # --- Act ---

    # --- Assert ---
    assert USER_AGENT_HEADER == "user-agent"


def test_fallback_user_agent_is_non_empty_string() -> None:
    """
    Given: the FALLBACK_USER_AGENT module constant.
    When: it is read.
    Then: it is a non-empty string.
    """
    # --- Arrange ---

    # --- Act ---

    # --- Assert ---
    assert isinstance(FALLBACK_USER_AGENT, str)
    assert FALLBACK_USER_AGENT != ""


# --- class-level header ---


def test_class_level_header_uses_shared_default_agent() -> None:
    """
    Given: the Agent class accessed at class level.
    When: its header mixed-property is read via the class branch.
    Then: the shared default_agent supplies one non-empty user-agent key.
    """
    # --- Arrange ---

    # --- Act ---
    header = Agent.header

    # --- Assert ---
    assert set(header) == {USER_AGENT_HEADER}
    assert header[USER_AGENT_HEADER] != ""


# --- fallback on empty platforms ---


def test_empty_platforms_header_falls_back_to_non_empty_agent() -> None:
    """
    Given: an Agent built with an empty platform list.
    When: its header is read.
    Then: the fake_useragent IndexError fallback yields a non-empty UA.
    """
    # --- Arrange ---

    # --- Act ---
    # expected: verify  # fake_useragent IndexError handler -> fallback
    header = Agent(platforms=[]).header

    # --- Assert ---
    assert set(header) == {USER_AGENT_HEADER}
    assert header[USER_AGENT_HEADER] != ""


# --- repeated header access ---


def test_header_returns_fresh_dict_on_each_call() -> None:
    """
    Given: one Agent instance.
    When: .header is read twice in a row.
    Then: each call returns an independent single-key dict.
    """
    # --- Arrange ---
    agent = Agent()

    # --- Act ---
    first = agent.header
    second = agent.header

    # --- Assert ---
    assert set(first) == {USER_AGENT_HEADER}
    assert set(second) == {USER_AGENT_HEADER}
    assert first is not second
