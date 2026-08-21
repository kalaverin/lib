"""Tests for `zx.lib.settings` — settings models and environment reporting."""

import logging
from pathlib import Path

import orjson
import pytest
from faker import Faker
from pydantic import BaseModel, ValidationError

from zx.lib.settings import (
    BaseConfig,
    BaseLogging,
    KubernetesPod,
    show_environment,
)

SETTINGS_LOGGER = "zx.lib.settings"
PACKAGES_DOCUMENT = "packages.json"
PACKAGE_ENTRY_COUNT = 3

K8S_ENV_VARS: tuple[str, ...] = (
    "K8S_NAMESPACE",
    "K8S_INSTANCE",
    "K8S_POD",
    "K8S_NODE",
    "K8S_ADDR",
)

K8S_DEFAULTS: dict[str, str] = {
    "namespace": "local",
    "instance": "local",
    "pod": "local",
    "node": "localhost",
    "addr": "127.0.0.1",
}

K8S_FIELD_ENV: tuple[tuple[str, str], ...] = (
    ("namespace", "K8S_NAMESPACE"),
    ("instance", "K8S_INSTANCE"),
    ("pod", "K8S_POD"),
    ("node", "K8S_NODE"),
    ("addr", "K8S_ADDR"),
)
K8S_FIELD_IDS = tuple(field for field, _ in K8S_FIELD_ENV)

LEVEL_MATRIX: tuple[tuple[str, int], ...] = (
    ("critical", 50),
    ("error", 40),
    ("warning", 30),
    ("warn", 30),
    ("info", 20),
    ("debug", 10),
)
LEVEL_MATRIX_IDS = tuple(f"name-{level}" for level, _ in LEVEL_MATRIX)

DIGIT_LEVEL_MATRIX: tuple[tuple[str, int, str], ...] = (
    ("10", 10, "DEBUG"),
    ("0", 0, "NOTSET"),
    ("51", 51, "LEVEL 51"),
)
DIGIT_LEVEL_IDS = tuple(f"digit-{level}" for level, _, _ in DIGIT_LEVEL_MATRIX)

STRING_LEVEL_MATRIX: tuple[tuple[str, str], ...] = (
    ("critical", "CRITICAL"),
    ("warning", "WARNING"),
    ("info", "INFO"),
    ("debug", "DEBUG"),
)
STRING_LEVEL_IDS = tuple(f"level-{level}" for level, _ in STRING_LEVEL_MATRIX)


class AppConfig(BaseModel):
    """Minimal config stub exposing the surface show_environment uses."""

    name: str
    version: str


@pytest.fixture
def app_config(fake: Faker) -> AppConfig:
    """A faker-driven config stub for show_environment tests."""
    return AppConfig(name=fake.word(), version=fake.word())


def _clear_k8s_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delete every K8S_* variable (no error when one is absent)."""
    for env_var in K8S_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)


# --- kubernetes pod ---


@pytest.mark.parametrize("field", K8S_FIELD_IDS, ids=K8S_FIELD_IDS)
def test_kubernetes_pod_env_cleared_returns_defaults(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    """
    Given: every K8S_* variable cleared from the environment.
    When: a KubernetesPod is built.
    Then: the parametrized field carries its documented default.
    """
    # --- Arrange ---
    _clear_k8s_env(monkeypatch)

    # --- Act ---
    pod = KubernetesPod()

    # --- Assert ---
    assert getattr(pod, field) == K8S_DEFAULTS[field]


@pytest.mark.parametrize("field,env_var", K8S_FIELD_ENV, ids=K8S_FIELD_IDS)
def test_kubernetes_pod_env_override_sets_field(
    fake: Faker,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    env_var: str,
) -> None:
    """
    Given: cleared K8S_* variables with one parametrized override set.
    When: a KubernetesPod is built.
    Then: the overridden field carries the env value, others stay default.
    """
    # --- Arrange ---
    value = fake.word()
    _clear_k8s_env(monkeypatch)
    monkeypatch.setenv(env_var, value)

    # --- Act ---
    pod = KubernetesPod()

    # --- Assert ---
    assert getattr(pod, field) == value
    for other_field, other_env in K8S_FIELD_ENV:
        if other_env != env_var:
            assert getattr(pod, other_field) == K8S_DEFAULTS[other_field]


def test_kubernetes_pod_as_dict_emits_k8s_prefixed_keys(
    fake: Faker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: a pod built from faker-driven K8S_* env overrides.
    When: as_dict is called.
    Then: k8s_* keys mirror the field values.
    """
    # --- Arrange ---
    values = {env_var: fake.word() for _, env_var in K8S_FIELD_ENV}
    for env_var, value in values.items():
        monkeypatch.setenv(env_var, value)

    # --- Act ---
    result = KubernetesPod().as_dict

    # --- Assert ---
    expected = {
        f"k8s_{field}": values[env_var] for field, env_var in K8S_FIELD_ENV
    }
    assert result == expected


# --- base logging ---


@pytest.mark.parametrize("level,expected", LEVEL_MATRIX, ids=LEVEL_MATRIX_IDS)
def test_base_logging_name_level_returns_numeric_level(
    level: str,
    expected: int,
) -> None:
    """
    Given: a parametrized level name.
    When: numeric_level is requested.
    Then: the corresponding numeric logging level is returned.
    """
    # --- Arrange ---
    logging_config = BaseLogging(level=level)

    # --- Act ---
    result = logging_config.numeric_level

    # --- Assert ---
    assert result == expected


@pytest.mark.parametrize(
    "level,expected,expected_name",
    DIGIT_LEVEL_MATRIX,
    ids=DIGIT_LEVEL_IDS,
)
def test_base_logging_digit_level_returns_numeric_level(
    level: str,
    expected: int,
    expected_name: str,
) -> None:
    """
    Given: a parametrized digit-string level assigned post-construction
        (pydantic Literal rejects digit strings in the constructor).
    When: numeric_level and string_level are requested.
    Then: the digits are coerced to the numeric level and its name.
    """
    # --- Arrange ---
    logging_config = BaseLogging()
    logging_config.level = level  # type: ignore[assignment]

    # --- Act / Assert ---
    assert logging_config.numeric_level == expected
    assert logging_config.string_level == expected_name


def test_base_logging_digit_level_rejected_at_construction() -> None:
    """
    Given: a digit-string level passed to the constructor.
    When: the model is built.
    Then: pydantic Literal validation rejects it — the digit branch of
        numeric_level is unreachable through the constructor.
    """
    # --- Arrange ---

    # --- Act / Assert ---
    with pytest.raises(ValidationError):
        BaseLogging(level="10")  # type: ignore[arg-type]


def test_base_logging_invalid_level_name_raises_value_error() -> None:
    """
    Given: a logging config whose level is reassigned an unknown name.
    When: numeric_level is requested.
    Then: a ValueError naming the invalid level is raised.
    """
    # --- Arrange ---
    logging_config = BaseLogging()
    # Literal validation rejects unknown names at construction time,
    # so the invalid value is assigned afterwards to reach the check.
    logging_config.level = "verbose"

    # --- Act / Assert ---
    with pytest.raises(ValueError, match="Invalid log level"):
        _ = logging_config.numeric_level


@pytest.mark.parametrize(
    "level,expected",
    STRING_LEVEL_MATRIX,
    ids=STRING_LEVEL_IDS,
)
def test_base_logging_string_level_returns_uppercase_name(
    level: str,
    expected: str,
) -> None:
    """
    Given: a parametrized level input.
    When: string_level is requested.
    Then: the canonical uppercase level name is returned.
    """
    # --- Arrange ---
    logging_config = BaseLogging(level=level)

    # --- Act ---
    result = logging_config.string_level

    # --- Assert ---
    assert result == expected


# --- base config ---


def test_base_config_constructs_embedded_kubernetes_pod(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: every K8S_* variable cleared from the environment.
    When: a BaseConfig is built.
    Then: its kube attribute is a KubernetesPod holding the defaults.
    """
    # --- Arrange ---
    _clear_k8s_env(monkeypatch)

    # --- Act ---
    config = BaseConfig()

    # --- Assert ---
    assert isinstance(config.kube, KubernetesPod)
    assert config.kube.as_dict == {
        f"k8s_{field}": K8S_DEFAULTS[field] for field, _ in K8S_FIELD_ENV
    }


# --- show environment ---


def test_show_environment_with_packages_json_logs_used_libraries(
    fake: Faker,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    app_config: AppConfig,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Given: a packages.json in the cwd with faker-driven entries.
    When: show_environment runs.
    Then: a "Used libraries" event with the rendered entries is logged.
    """
    # --- Arrange ---
    entries = [
        {"name": fake.word(), "version": fake.word()}
        for _ in range(PACKAGE_ENTRY_COUNT)
    ]
    (tmp_path / PACKAGES_DOCUMENT).write_bytes(orjson.dumps(entries))
    monkeypatch.chdir(tmp_path)

    # --- Act ---
    with caplog.at_level(logging.INFO, logger=SETTINGS_LOGGER):
        show_environment(app_config)

    # --- Assert ---
    assert "Used libraries" in caplog.messages
    library_record = next(
        record
        for record in caplog.records
        if record.message == "Used libraries"
    )
    assert library_record.versions == [
        f"{entry['name']}={entry['version']}" for entry in entries
    ]


def test_show_environment_without_packages_json_skips_used_libraries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    app_config: AppConfig,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Given: a cwd without a packages.json file.
    When: show_environment runs.
    Then: no "Used libraries" event is logged and nothing crashes.
    """
    # --- Arrange ---
    monkeypatch.chdir(tmp_path)

    # --- Act ---
    with caplog.at_level(logging.INFO, logger=SETTINGS_LOGGER):
        show_environment(app_config)

    # --- Assert ---
    assert "Used libraries" not in caplog.messages


def test_show_environment_logs_model_dump_in_environment_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    app_config: AppConfig,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Given: a config stub in a cwd without packages.json.
    When: show_environment runs.
    Then: an "Environment variables" event carrying the model_dump logs.
    """
    # --- Arrange ---
    monkeypatch.chdir(tmp_path)

    # --- Act ---
    with caplog.at_level(logging.INFO, logger=SETTINGS_LOGGER):
        show_environment(app_config)

    # --- Assert ---
    assert "Environment variables" in caplog.messages
    variables_record = next(
        record
        for record in caplog.records
        if record.message == "Environment variables"
    )
    assert variables_record.variables == app_config.model_dump()


# --- edge cases: kubernetes pod ---


def test_kubernetes_pod_empty_env_value_is_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Given: every K8S_* variable cleared, then K8S_POD set to "".
    When: a KubernetesPod is built.
    Then: the empty string is kept as-is — no fallback to the default.
    """
    # --- Arrange ---
    _clear_k8s_env(monkeypatch)
    monkeypatch.setenv("K8S_POD", "")

    # --- Act ---
    pod = KubernetesPod()

    # --- Assert ---
    assert pod.pod == ""


# --- edge cases: base logging ---


def test_base_logging_numeric_level_is_cached_across_reassignment() -> None:
    """
    Given: a config with level "debug" whose numeric_level was read once.
    When: level is reassigned to "error" and numeric_level read again.
    Then: the cached value 10 is returned — cached_property never recomputes.
    """
    # --- Arrange ---
    logging_config = BaseLogging(level="debug")
    first = logging_config.numeric_level

    # --- Act ---
    logging_config.level = "error"
    second = logging_config.numeric_level

    # --- Assert ---
    assert first == 10
    assert second == 10


def test_base_logging_int_instance_level_returns_numeric_level() -> None:
    """
    Given: a config whose level is reassigned an int instance (pydantic
        Literal validation does not run on plain attribute assignment).
    When: numeric_level is requested.
    Then: the int branch of the cached_property returns it unchanged.
    """
    # --- Arrange ---
    logging_config = BaseLogging()
    logging_config.level = 20  # type: ignore[assignment]

    # --- Act / Assert ---
    assert logging_config.numeric_level == 20


def test_base_logging_invalid_level_name_chains_key_error() -> None:
    """
    Given: a config whose level is reassigned an unknown name.
    When: numeric_level is requested.
    Then: ValueError is raised with the KeyError from the level-name
        lookup preserved as __cause__.
    """
    # --- Arrange ---
    logging_config = BaseLogging()
    logging_config.level = "verbose"

    # --- Act / Assert ---
    with pytest.raises(ValueError, match="Invalid log level") as exc_info:
        _ = logging_config.numeric_level
    assert isinstance(exc_info.value.__cause__, KeyError)


def test_base_logging_format_default_and_override() -> None:
    """
    Given: a default BaseLogging and one constructed with format="text".
    When: the format field is read.
    Then: the default is "json" and the override is honored.
    """
    # --- Arrange / Act ---
    default_config = BaseLogging()
    text_config = BaseLogging(format="text")

    # --- Assert ---
    assert default_config.format == "json"
    assert text_config.format == "text"


# --- edge cases: show environment ---


def test_show_environment_with_corrupt_packages_json_still_logs_variables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    app_config: AppConfig,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Given: a packages.json containing invalid JSON ("{invalid").
    When: show_environment runs.
    Then: the parsing error is suppressed by suppress(Exception) and the
        "Environment variables" record is still logged.
    """
    # --- Arrange ---
    (tmp_path / PACKAGES_DOCUMENT).write_text("{invalid")
    monkeypatch.chdir(tmp_path)

    # --- Act ---
    with caplog.at_level(logging.INFO, logger=SETTINGS_LOGGER):
        show_environment(app_config)

    # --- Assert ---
    assert "Environment variables" in caplog.messages
    assert "Used libraries" not in caplog.messages


def test_show_environment_with_incomplete_entries_skips_used_libraries(
    fake: Faker,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    app_config: AppConfig,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Given: a packages.json whose entries lack the version key, so the
        "{name}={version}" format loop raises KeyError.
    When: show_environment runs.
    Then: the error is suppressed inside suppress(Exception) — no "Used
        libraries" record, but "Environment variables" is still logged.
    """
    # --- Arrange ---
    entries = [{"name": fake.word()} for _ in range(PACKAGE_ENTRY_COUNT)]
    (tmp_path / PACKAGES_DOCUMENT).write_bytes(orjson.dumps(entries))
    monkeypatch.chdir(tmp_path)

    # --- Act ---
    with caplog.at_level(logging.INFO, logger=SETTINGS_LOGGER):
        show_environment(app_config)

    # --- Assert ---
    assert "Used libraries" not in caplog.messages
    assert "Environment variables" in caplog.messages


def test_show_environment_used_libraries_carries_app_and_version(
    fake: Faker,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    app_config: AppConfig,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Given: a valid packages.json in the cwd.
    When: show_environment runs.
    Then: the "Used libraries" record carries the app and version extras
        alongside the rendered versions list.
    """
    # --- Arrange ---
    entries = [
        {"name": fake.word(), "version": fake.word()}
        for _ in range(PACKAGE_ENTRY_COUNT)
    ]
    (tmp_path / PACKAGES_DOCUMENT).write_bytes(orjson.dumps(entries))
    monkeypatch.chdir(tmp_path)

    # --- Act ---
    with caplog.at_level(logging.INFO, logger=SETTINGS_LOGGER):
        show_environment(app_config)

    # --- Assert ---
    library_record = next(
        record
        for record in caplog.records
        if record.message == "Used libraries"
    )
    assert library_record.app == app_config.name
    assert library_record.version == app_config.version
