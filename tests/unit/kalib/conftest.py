"""Fixtures local to the zx.lib unit-test package.

Three seams live here:

- `fake_redis` — in-memory Redis clients; no sockets, ever.
- `registry_snapshot` — restores `SERIALIZER_REGISTRY` after tests that
  register throwaway serializers.
- `structlog_snapshot` — restores process-global logging and structlog
  state after tests that call `zx.lib.structlog.configure`.
"""

import logging.config
from collections.abc import Callable, Iterator

import fakeredis
import pytest
import structlog

from zx.lib.serial.registry import SERIALIZER_REGISTRY


@pytest.fixture
def fake_redis() -> Callable[..., fakeredis.FakeRedis]:
    """A factory of isolated in-memory Redis clients.

    decode_responses=True matches `zx.lib.redis.Config` defaults; each
    call returns a fresh, fully isolated client.
    """

    def _make_fake_redis(
        **overrides: object,
    ) -> fakeredis.FakeRedis:
        return fakeredis.FakeRedis(decode_responses=True, **overrides)

    return _make_fake_redis


@pytest.fixture
def registry_snapshot() -> Iterator[None]:
    """Snapshot SERIALIZER_REGISTRY; drop keys the test added."""
    before = set(SERIALIZER_REGISTRY)

    yield

    for cls in set(SERIALIZER_REGISTRY) - before:
        del SERIALIZER_REGISTRY[cls]


@pytest.fixture
def structlog_snapshot() -> Iterator[None]:
    """Snapshot and restore process-global logging/structlog state.

    `zx.lib.structlog.configure` rewires every known logger (handlers,
    level, propagate), swaps `logging.config.dictConfig` for a no-op and
    reconfigures structlog itself — all of that is rolled back here.
    """
    original_dict_config = logging.config.dictConfig
    original_structlog_config = structlog.get_config()

    observed = [
        logging.root,
        *map(logging.getLogger, list(logging.root.manager.loggerDict)),
    ]
    saved = [
        (entry, entry.handlers[:], entry.level, entry.propagate)
        for entry in observed
    ]

    yield

    logging.config.dictConfig = original_dict_config
    structlog.configure(**original_structlog_config)
    for entry, handlers, level, propagate in saved:
        entry.handlers[:] = handlers
        entry.setLevel(level)
        entry.propagate = propagate
