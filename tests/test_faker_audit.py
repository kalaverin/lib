"""Audit of the Faker provider surface the suite relies on."""

from importlib.metadata import version

from faker import Faker

USED_PROVIDERS = frozenset(
    {
        "first_name",
        "pyint",
        "word",
    },
)

FIXED_SEED = 12345


def test_faker_version_is_available_for_audit() -> None:
    """
    Given: Faker is installed.
    When: the installed version is queried.
    Then: a version string starting with a digit is returned.
    """
    # --- Arrange ---

    # --- Act ---
    installed = version("Faker")

    # --- Assert ---
    assert installed
    assert installed[0].isdigit()


def test_faker_provider_surface_includes_used_providers() -> None:
    """
    Given: a fresh Faker instance.
    When: the provider surface is inspected.
    Then: every provider the suite uses is present.
    """
    # --- Arrange ---
    instance = Faker()

    # --- Act ---
    missing = USED_PROVIDERS - set(dir(instance))

    # --- Assert ---
    assert not missing, missing


def test_faker_instances_with_same_seed_are_reproducible() -> None:
    """
    Given: two Faker instances seeded with the same value.
    When: values are drawn from both.
    Then: the sequences are identical.
    """
    # --- Arrange ---
    first = Faker()
    first.seed_instance(FIXED_SEED)
    second = Faker()
    second.seed_instance(FIXED_SEED)

    # --- Act ---
    first_draw = (first.pyint(), first.first_name())
    second_draw = (second.pyint(), second.first_name())

    # --- Assert ---
    assert first_draw == second_draw
