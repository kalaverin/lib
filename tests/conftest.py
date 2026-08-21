"""Shared test fixtures for the zx.lib suite."""

import os
import random
from collections.abc import Iterator
from datetime import UTC

import pytest
import time_machine
from faker import Faker

FAKER_LOCALES = ["en_US"]
FAKER_SEED_ENV = "PYTEST_FAKER_SEED"
FAKER_SEED_MAX = 2**32


@pytest.fixture
def fake() -> Faker:
    """A function-scoped Faker instance with a reproducible seed.

    The seed comes from the PYTEST_FAKER_SEED environment variable when
    set, otherwise a fresh one is drawn per test — the only permitted
    use of stdlib `random` in the suite.
    """
    instance = Faker(FAKER_LOCALES)

    seed_text = os.environ.get(FAKER_SEED_ENV)
    seed = (
        int(seed_text)
        if seed_text is not None
        else random.randint(0, FAKER_SEED_MAX)  # noqa: S311
    )
    instance.seed_instance(seed)
    return instance


@pytest.fixture
def frozen_time(fake: Faker) -> Iterator[time_machine.travel]:
    """A time-machine traveller frozen at a faker-seeded UTC destination.

    tick=False — time stands still; no real clock involved anywhere.
    """
    destination = fake.date_time(tzinfo=UTC)
    with time_machine.travel(destination, tick=False) as traveller:
        yield traveller
