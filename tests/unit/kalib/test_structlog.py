"""Tests for `zx.lib.structlog` — logging configuration and spam filters."""

import io
import json
import logging
import logging.config
from collections.abc import Collection, Iterator
from typing import Any

import orjson
import pytest
import structlog
from faker import Faker
from structlog.processors import (
    StackInfoRenderer,
    TimeStamper,
    UnicodeDecoder,
)
from structlog.stdlib import (
    ExtraAdder,
    PositionalArgumentsFormatter,
    add_log_level,
    add_logger_name,
)

from zx.core import Who
from zx.lib.structlog import (
    DEFAULT_JSON_OPTIONS,
    DEFAULT_PROCESSORS,
    SuppressSpamFilter,
    configure,
    frozenset_from_env,
    get_logger,
    is_serializable,
    nothing_to_do,
    static_processor,
)

pytestmark = pytest.mark.serial

StructlogSnapshot = Iterator[None]

ENV_NAME = "KALIB_TEST_STRUCTLOG_ENV"
ANSI_ESCAPE = "\x1b"
RECORD_LEVEL = logging.INFO
DEBUG_LEVEL = logging.DEBUG
RECORD_LINENO = 1


def make_record(name: str, filename: str) -> logging.LogRecord:
    """Synthesize a LogRecord with the given logger name and basename."""
    return logging.LogRecord(
        name=name,
        level=RECORD_LEVEL,
        pathname=f"/srv/app/{filename}",
        lineno=RECORD_LINENO,
        msg="test message",
        args=(),
        exc_info=None,
    )


# --- helpers: frozenset_from_env ---


@pytest.mark.parametrize(
    "raw,expected",
    (
        ("a,b", frozenset({"a", "b"})),
        ("a;b:c", frozenset({"a", "b", "c"})),
        ("*.log *.tmp", frozenset({"*.log", "*.tmp"})),
        ("a.b,c", frozenset({"a.b", "c"})),
        (
            "error.py\ndebug.py\tspam.py",
            frozenset({"error.py", "debug.py", "spam.py"}),
        ),
        ("word", frozenset({"word"})),
        ("", frozenset()),
    ),
    ids=(
        "single-comma",
        "mixed-separators",
        "glob-and-space",
        "dots-stay-in-tokens",
        "whitespace-runs",
        "single-word",
        "empty",
    ),
)
def test_frozenset_from_env_splits_on_separators(
    monkeypatch: pytest.MonkeyPatch,
    raw: str,
    expected: frozenset[str],
) -> None:
    """
    Given: an environment variable holding a parametrized raw string.
    When: frozenset_from_env reads it.
    Then: only the tokens land in the frozenset — dots and glob stars
        stay inside tokens; empty input gives an empty frozenset.
    """
    # --- Arrange ---
    monkeypatch.setenv(ENV_NAME, raw)

    # --- Act ---
    result = frozenset_from_env(ENV_NAME)

    # --- Assert ---
    assert result == expected


def test_frozenset_from_env_unset_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: an environment variable that does not exist.
    When: frozenset_from_env reads it.
    Then: an empty frozenset is returned.
    """
    # --- Arrange ---
    monkeypatch.delenv(ENV_NAME, raising=False)

    # --- Act ---
    result = frozenset_from_env(ENV_NAME)

    # --- Assert ---
    assert result == frozenset()


# --- helpers: static_processor ---


def test_static_processor_merges_without_overwriting() -> None:
    """
    Given: an event dict carrying an already-set key and a static field
        mapping redefining that same key.
    When: the processor runs.
    Then: missing keys are added, existing keys keep their values.
    """
    # --- Arrange ---
    fields = {"shared": "new", "added": "value"}
    event = {"existing": 1, "shared": "old"}

    # --- Act ---
    result = static_processor(fields)(None, "info", event)

    # --- Assert ---
    assert result == {"existing": 1, "shared": "old", "added": "value"}


def test_static_processor_empty_dict_receives_all_fields(
    fake: Faker,
) -> None:
    """
    Given: an empty event dict and a faker-generated static field mapping.
    When: the processor runs.
    Then: every static field is present in the returned event dict.
    """
    # --- Arrange ---
    fields = {"app": fake.slug(), "env": fake.word()}

    # --- Act ---
    result = static_processor(fields)(None, "info", {})

    # --- Assert ---
    assert result == fields


# --- helpers: is_serializable ---


def test_is_serializable_dict_returns_true(
    fake: Faker,
) -> None:
    """
    Given: a plain dict with a faker-generated value.
    When: is_serializable checks it.
    Then: True is returned.
    """
    # --- Arrange ---
    value = {"name": fake.name()}

    # --- Act / Assert ---
    assert is_serializable(value) is True


def test_is_serializable_unregistered_object_returns_false() -> None:
    """
    Given: an instance of a throwaway class absent from SERIALIZER_REGISTRY.
    When: is_serializable checks it.
    Then: False is returned without registering anything.
    """
    # --- Arrange ---

    class Unregistered: ...

    # --- Act / Assert ---
    assert is_serializable(Unregistered()) is False


# --- SuppressSpamFilter ---


@pytest.mark.parametrize(
    "files,filename,expected_kept",
    (
        ({"*.log"}, "app.log", False),
        ({"noise*"}, "noise_generator.py", False),
        ({"core.py", "spam.py"}, "spam.py", False),
        ({"*.tmp"}, "keep.py", True),
        (frozenset(), "anything.py", True),
    ),
    ids=(
        "glob-suffix-drop",
        "glob-prefix-drop",
        "exact-name-drop",
        "non-match-keep",
        "empty-files-keep",
    ),
)
def test_suppress_spam_filter_matches_record_filename(
    files: Collection[str],
    filename: str,
    *,
    expected_kept: bool,
) -> None:
    """
    Given: a filter with parametrized file globs and a record whose
        filename is parametrized.
    When: the record passes the filter.
    Then: matching filenames are dropped, others and empty sets keep.
    """
    # --- Arrange ---
    spam_filter = SuppressSpamFilter(modules=(), files=files)
    record = make_record(name="any.module", filename=filename)

    # --- Act ---
    kept = spam_filter.filter(record)

    # --- Assert ---
    assert kept is expected_kept


@pytest.mark.parametrize(
    "modules,name,expected_kept",
    (
        ({"spam.module"}, "spam.module", False),
        ({"spam.*"}, "spam.sub.module", False),
        ({"a.b", "c.d"}, "c.d", False),
        ({"other.*"}, "app.module", True),
        (frozenset(), "any.module", True),
    ),
    ids=(
        "exact-module-drop",
        "glob-prefix-drop",
        "multi-glob-drop",
        "non-match-keep",
        "empty-modules-keep",
    ),
)
def test_suppress_spam_filter_matches_record_name(
    modules: Collection[str],
    name: str,
    *,
    expected_kept: bool,
) -> None:
    """
    Given: a filter with parametrized module globs and a record whose
        logger name is parametrized.
    When: the record passes the filter.
    Then: matching names are dropped, others and empty sets keep.
    """
    # --- Arrange ---
    spam_filter = SuppressSpamFilter(modules=modules, files=())
    record = make_record(name=name, filename="keep.py")

    # --- Act ---
    kept = spam_filter.filter(record)

    # --- Assert ---
    assert kept is expected_kept


# --- configure ---


def test_configure_json_mode_emits_parseable_json_with_static_fields(
    structlog_snapshot: StructlogSnapshot,
    fake: Faker,
) -> None:
    """
    Given: a StringIO descriptor and faker-generated static fields.
    When: configure runs in JSON mode.
    Then: the emitted line parses as JSON carrying the static fields.
    """
    # --- Arrange ---
    stream = io.StringIO()
    app_name = fake.slug()

    # --- Act ---
    configure(descriptor=stream, static_fields={"app": app_name})

    # --- Assert ---
    lines = stream.getvalue().splitlines()
    assert lines
    payload = json.loads(lines[-1])
    assert payload["app"] == app_name
    assert payload["event"] == "structlog configured"


def test_configure_json_mode_renders_unserializable_fields_as_names(
    structlog_snapshot: StructlogSnapshot,
    fake: Faker,
) -> None:
    """
    Given: JSON mode with a StringIO descriptor.
    When: a log event carries an unserializable object.
    Then: the line stays valid JSON with the field rendered as type name.
    """

    # --- Arrange ---
    class Unsupported: ...

    stream = io.StringIO()
    configure(descriptor=stream)
    event = fake.word()
    instance = Unsupported()

    # --- Act ---
    get_logger().info(event, payload=instance)

    # --- Assert ---
    line = stream.getvalue().splitlines()[-1]
    parsed = json.loads(line)
    assert parsed["event"] == event
    assert parsed["payload"] == Who.Is(instance)


def test_configure_textual_mode_emits_console_output(
    structlog_snapshot: StructlogSnapshot,
) -> None:
    """
    Given: a StringIO descriptor.
    When: configure runs in textual mode.
    Then: the ConsoleRenderer emits a human-readable colored line that
        is not JSON.
    """
    # --- Arrange ---
    stream = io.StringIO()

    # --- Act ---
    configure(descriptor=stream, is_textual=True)

    # --- Assert ---
    output = stream.getvalue()
    assert "structlog configured" in output
    assert ANSI_ESCAPE in output


def test_configure_int_level_is_coerced_to_uppercased_name(
    structlog_snapshot: StructlogSnapshot,
) -> None:
    """
    Given: an integer logging level.
    When: configure runs.
    Then: the root logger ends up with the matching named level.
    """
    # --- Arrange ---
    stream = io.StringIO()

    # --- Act ---
    configure(level=DEBUG_LEVEL, descriptor=stream)

    # --- Assert ---
    assert logging.getLogger().level == DEBUG_LEVEL


def test_configure_dict_config_is_swapped_for_noop(
    structlog_snapshot: StructlogSnapshot,
) -> None:
    """
    Given: a fresh configure call.
    When: logging.config.dictConfig is inspected afterwards.
    Then: it is the module's nothing_to_do no-op.
    """
    # --- Arrange ---
    stream = io.StringIO()

    # --- Act ---
    configure(descriptor=stream)

    # --- Assert ---
    assert logging.config.dictConfig is nothing_to_do


def test_configure_attaches_spam_filter_to_root_handler(
    structlog_snapshot: StructlogSnapshot,
) -> None:
    """
    Given: configure called with ignore_files and ignore_modules.
    When: the root handler is inspected and fed synthesized records.
    Then: a SuppressSpamFilter is attached and drops matching records.
    """
    # --- Arrange ---
    stream = io.StringIO()
    files = {"*.py"}
    modules = {"spam.*"}

    # --- Act ---
    configure(
        descriptor=stream,
        ignore_files=files,
        ignore_modules=modules,
    )

    # --- Assert ---
    root = logging.getLogger()
    assert root.handlers
    filters: list[Any] = [
        item for handler in root.handlers for item in handler.filters
    ]
    spam_filters = [
        item for item in filters if isinstance(item, SuppressSpamFilter)
    ]
    assert len(spam_filters) == 1
    spam_filter = spam_filters[0]
    assert (
        spam_filter.filter(make_record(name="spam.module", filename="keep.py"))
        is False
    )
    assert (
        spam_filter.filter(make_record(name="app.module", filename="app.py"))
        is False
    )
    assert (
        spam_filter.filter(make_record(name="app.module", filename="keep.log"))
        is True
    )


# --- edge cases: frozenset_from_env ---


@pytest.mark.parametrize(
    "raw,expected",
    (
        ("café,x", frozenset({"café", "x"})),
        ("123,*", frozenset({"123", "*"})),
        ("   ", frozenset()),
    ),
    ids=("unicode-tokens", "digits-and-bare-glob", "whitespace-only"),
)
def test_frozenset_from_env_preserves_unicode_and_glob_tokens(
    monkeypatch: pytest.MonkeyPatch,
    raw: str,
    expected: frozenset[str],
) -> None:
    """
    Given: an environment variable holding a parametrized raw string.
    When: frozenset_from_env reads it.
    Then: unicode word chars stay inside tokens, digits and a bare "*"
        survive the separator split, and whitespace-only input filters
        down to an empty frozenset.
    """
    # --- Arrange ---
    monkeypatch.setenv(ENV_NAME, raw)

    # --- Act ---
    result = frozenset_from_env(ENV_NAME)

    # --- Assert ---
    assert result == expected


# --- edge cases: is_serializable ---


def test_is_serializable_nested_unserializable_returns_false() -> None:
    """
    Given: a container with an unregistered object nested inside.
    When: is_serializable checks it.
    Then: the TypeError from the nested leaf propagates and False is
        returned.
    """

    # --- Arrange ---
    class Unregistered: ...

    value = {"items": [Unregistered()]}

    # --- Act / Assert ---
    assert is_serializable(value) is False


# --- edge cases: SuppressSpamFilter ---


def test_suppress_spam_filter_drops_falsy_entries() -> None:
    """
    Given: a filter built from collections containing falsy entries.
    When: records pass the filter.
    Then: filter(bool) dropped the empty strings — a module glob still
        matches, and an unmatched record is kept.
    """
    # --- Arrange ---
    spam_filter = SuppressSpamFilter(modules=["", "spam.*"], files=[""])

    # --- Act / Assert ---
    assert (
        spam_filter.filter(make_record(name="spam.mod", filename="keep.py"))
        is False
    )
    assert (
        spam_filter.filter(make_record(name="app.mod", filename="keep.py"))
        is True
    )


def test_suppress_spam_filter_matching_file_and_module_drops_once() -> None:
    """
    Given: a filter whose file glob and module glob both match one record.
    When: the record passes the filter.
    Then: a single boolean False is produced — the record is suppressed.
    """
    # --- Arrange ---
    spam_filter = SuppressSpamFilter(modules={"spam.*"}, files={"*.py"})
    record = make_record(name="spam.mod", filename="app.py")

    # --- Act ---
    kept = spam_filter.filter(record)

    # --- Assert ---
    assert kept is False


def test_suppress_spam_filter_file_glob_requires_full_filename_match() -> None:
    """
    Given: a file glob "spam.py" and a filename "xspam.py".
    When: is_ignored_file checks the filename.
    Then: the record is kept — globs must match the whole filename, not
        a substring of it.
    """
    # --- Arrange ---
    spam_filter = SuppressSpamFilter(modules=(), files={"spam.py"})

    # --- Act / Assert ---
    assert spam_filter.is_ignored_file("xspam.py") is False
    assert spam_filter.is_ignored_file("spam.py") is True


# --- edge cases: configure ---


def test_configure_without_ignore_sets_attaches_no_spam_filter(
    structlog_snapshot: StructlogSnapshot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: no ignore arguments and no LOGGING_IGNORE_* environment.
    When: configure runs.
    Then: no SuppressSpamFilter is attached to any root handler.
    """
    # --- Arrange ---
    monkeypatch.delenv("LOGGING_IGNORE_FILES", raising=False)
    monkeypatch.delenv("LOGGING_IGNORE_MODULES", raising=False)
    stream = io.StringIO()

    # --- Act ---
    configure(descriptor=stream)

    # --- Assert ---
    root = logging.getLogger()
    filters: list[Any] = [
        item for handler in root.handlers for item in handler.filters
    ]
    assert not any(isinstance(item, SuppressSpamFilter) for item in filters)


def test_configure_with_custom_processors_uses_them(
    structlog_snapshot: StructlogSnapshot,
    fake: Faker,
) -> None:
    """
    Given: a custom processor chain built around static_processor.
    When: configure runs and an event is logged.
    Then: the custom processors participate — the static marker lands in
        the emitted JSON line.
    """
    # --- Arrange ---
    stream = io.StringIO()
    marker = fake.slug()
    configure(
        descriptor=stream,
        processors=[static_processor({"marker": marker})],
    )
    event = fake.word()

    # --- Act ---
    get_logger().info(event)

    # --- Assert ---
    line = stream.getvalue().splitlines()[-1]
    payload = json.loads(line)
    assert payload["event"] == event
    assert payload["marker"] == marker


@pytest.mark.parametrize(
    "container,expected",
    (
        (lambda instance: {"inner": instance}, lambda name: {"inner": name}),
        (lambda instance: [instance], lambda name: [name]),
    ),
    ids=("nested-in-dict", "nested-in-list"),
)
def test_configure_json_mode_renders_nested_unserializable_as_name(
    structlog_snapshot: StructlogSnapshot,
    fake: Faker,
    container: object,
    expected: object,
) -> None:
    """
    Given: JSON mode with a StringIO descriptor.
    When: a log event carries a container holding an unserializable object.
    Then: the line stays valid JSON with the nested leaf replaced by the
        class name.
    """

    # --- Arrange ---
    class Unsupported: ...

    stream = io.StringIO()
    configure(descriptor=stream)
    event = fake.word()
    instance = Unsupported()

    # --- Act ---
    get_logger().info(event, payload=container(instance))

    # --- Assert ---
    line = stream.getvalue().splitlines()[-1]
    parsed = json.loads(line)
    assert parsed["event"] == event
    assert parsed["payload"] == expected(Who.Is(instance))


def test_configure_unknown_int_level_raises_value_error(
    structlog_snapshot: StructlogSnapshot,
) -> None:
    """
    Given: an unregistered integer level (15 coerces to "LEVEL 15").
    When: configure assigns it to every logger via setLevel.
    Then: ValueError is raised for the unknown level name.
    """
    # expected: verify
    # --- Arrange ---
    stream = io.StringIO()

    # --- Act / Assert ---
    with pytest.raises(ValueError, match="Unknown level"):
        configure(level=15, descriptor=stream)


# --- module-level pins ---


def test_default_json_options_pin_orjson_mask() -> None:
    """
    Given: the module-level DEFAULT_JSON_OPTIONS constant.
    When: it is compared against the orjson flags named in the source.
    Then: the composition matches exactly.
    """
    # --- Arrange / Act / Assert ---
    assert DEFAULT_JSON_OPTIONS == (
        orjson.OPT_SORT_KEYS
        | orjson.OPT_NAIVE_UTC
        | orjson.OPT_SERIALIZE_DATACLASS
        | orjson.OPT_SERIALIZE_NUMPY
        | orjson.OPT_SERIALIZE_UUID
    )


def test_default_processors_pin_composition() -> None:
    """
    Given: the module-level DEFAULT_PROCESSORS tuple.
    When: its composition is inspected.
    Then: every position matches the source: merge_contextvars first,
        then the stdlib processors and stdlib logging positions.
    """
    # --- Arrange / Act / Assert ---
    assert len(DEFAULT_PROCESSORS) == 8
    assert DEFAULT_PROCESSORS[0] is structlog.contextvars.merge_contextvars
    assert isinstance(DEFAULT_PROCESSORS[1], ExtraAdder)
    assert isinstance(DEFAULT_PROCESSORS[2], PositionalArgumentsFormatter)
    assert isinstance(DEFAULT_PROCESSORS[3], StackInfoRenderer)
    assert isinstance(DEFAULT_PROCESSORS[4], TimeStamper)
    assert isinstance(DEFAULT_PROCESSORS[5], UnicodeDecoder)
    assert DEFAULT_PROCESSORS[6] is add_logger_name
    assert DEFAULT_PROCESSORS[7] is add_log_level
