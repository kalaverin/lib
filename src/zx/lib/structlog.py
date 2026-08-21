# ruff: noqa: ANN401

import logging.config
import re
import sys
from collections.abc import Collection, Iterable, Mapping
from fnmatch import translate
from functools import cached_property, lru_cache
from logging import (
    Filter,
    LogRecord,
    StreamHandler,
    getLevelName,
    getLogger,
    root,
)
from os import getenv
from typing import Any, TextIO, final, override

import orjson
import structlog
from structlog import get_logger
from structlog.dev import ConsoleRenderer, RichTracebackFormatter
from structlog.processors import (
    CallsiteParameter,
    CallsiteParameterAdder,
    JSONRenderer,
    StackInfoRenderer,
    TimeStamper,
    UnicodeDecoder,
    dict_tracebacks,
)
from structlog.stdlib import (
    ExtraAdder,
    LoggerFactory,
    PositionalArgumentsFormatter,
    ProcessorFormatter,
    add_log_level,
    add_logger_name,
)
from structlog.types import Processor
from structlog.typing import EventDict

from zx.lib.serial import dumps

__all__ = (
    "configure",
    "get_logger",
)

# options for orjson serialization
# we want to sort keys, serialize dataclasses, numpy and uuid objects,
# and use naive UTC datetimes

DEFAULT_JSON_OPTIONS: int = (
    orjson.OPT_SORT_KEYS
    | orjson.OPT_NAIVE_UTC
    | orjson.OPT_SERIALIZE_DATACLASS
    | orjson.OPT_SERIALIZE_NUMPY
    | orjson.OPT_SERIALIZE_UUID
)

# processors that will be called for each log entry before rendering

DEFAULT_PROCESSORS: tuple[Processor, ...] = (
    structlog.contextvars.merge_contextvars,
    ExtraAdder(),
    PositionalArgumentsFormatter(),
    StackInfoRenderer(),
    TimeStamper(fmt="iso"),
    UnicodeDecoder(),
    add_logger_name,
    add_log_level,
)


def frozenset_from_env(name: str) -> frozenset[str]:
    raw = getenv(name, "") or ""
    return frozenset(filter(bool, re.split(r"[^\w.*]+", raw)))


def nothing_to_do(*_: Any, **__: Any) -> None:
    """No-op function used to disable logging.config.dictConfig.

    After structlog is configured, we prevent further reconfiguration
    by replacing dictConfig with this no-op.
    """


def static_processor(fields: Mapping[str, Any]) -> Processor:
    def processor(
        _logger: Any,
        _method: str,
        event_dict: EventDict,
    ) -> EventDict:
        for key, value in fields.items():
            event_dict.setdefault(key, value)
        return event_dict

    return processor


def is_serializable(value: Any) -> bool:
    try:
        dumps(value)
    except TypeError:
        return False
    return True


IGNORE_FILES = frozenset_from_env("LOGGING_IGNORE_FILES")
IGNORE_MODULES = frozenset_from_env("LOGGING_IGNORE_MODULES")


@final
class SuppressSpamFilter(Filter):
    def __init__(
        self,
        modules: Collection[str],
        files: Collection[str],
    ) -> None:
        super().__init__()
        self._files: frozenset[str] = frozenset(filter(bool, files))
        self._modules: frozenset[str] = frozenset(filter(bool, modules))

    @cached_property
    def regex_files(self) -> re.Pattern[str]:
        order = sorted(self._files, key=len, reverse=True)
        body = "|".join(translate(i) for i in order)
        return re.compile(f"^(?:{body})")

    @cached_property
    def regex_modules(self) -> re.Pattern[str]:
        order = sorted(self._modules, key=len, reverse=True)
        body = "|".join(translate(i) for i in order)
        return re.compile(f"^(?:{body})")

    @lru_cache(maxsize=2**10)  # noqa: B019
    def is_ignored_file(self, name: str) -> bool:
        if not self._files:
            return False
        return bool(self.regex_files.search(name))

    @lru_cache(maxsize=2**10)  # noqa: B019
    def is_ignored_modules(self, name: str) -> bool:
        if not self._modules:
            return False
        return bool(self.regex_modules.search(name))

    @override
    def filter(self, record: LogRecord) -> bool:
        return not (
            self.is_ignored_file(record.filename)
            or self.is_ignored_modules(record.name)
        )


def configure(
    level: str | int = "info",
    is_textual: bool = False,
    descriptor: TextIO = sys.stdout,
    processors: Iterable[Processor] = DEFAULT_PROCESSORS,
    ignore_files: Collection[str] | None = None,
    ignore_modules: Collection[str] | None = None,
    static_fields: Mapping[str, Any] | None = None,
) -> None:
    # convert integer level to string name
    if isinstance(level, int):
        level = getLevelName(level)

    # in development we look for native tracebacks (with better-exceptions too)
    # but in production we want json in the logs

    order: list[Processor] = list(processors)

    if static_fields:
        order.append(static_processor(static_fields))

    # in production we want to serialize exception info as part of the json

    if not is_textual:
        order.append(dict_tracebacks)
    else:
        order.extend(
            (
                CallsiteParameterAdder(
                    parameters=[
                        CallsiteParameter.FILENAME,
                        CallsiteParameter.FUNC_NAME,
                        CallsiteParameter.LINENO,
                    ],
                ),
            ),
        )

    # main structlog configuration

    structlog.configure(
        processors=[*order, ProcessorFormatter.wrap_for_formatter],
        logger_factory=LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # create renderer: JSON in production, colored console in development

    renderer: ConsoleRenderer | JSONRenderer

    if not is_textual:

        def safe_serialize(value: object, **_: Any) -> str:
            return dumps(value, on_error="name").decode()

        renderer = JSONRenderer(serializer=safe_serialize)
    else:
        renderer = ConsoleRenderer(
            colors=True,
            exception_formatter=RichTracebackFormatter(
                extra_lines=4,
                max_frames=20,
                theme=getenv("PYGMENTS_THEME", "vim"),
            ),
        )

    # formatter for handler, it will call all processors before render

    formatter: ProcessorFormatter = ProcessorFormatter(
        keep_exc_info=is_textual,
        keep_stack_info=is_textual,
        foreign_pre_chain=order,
        processors=[ProcessorFormatter.remove_processors_meta, renderer],
    )

    # override all loggers to use our handler and formatter

    handler: StreamHandler[TextIO] = StreamHandler(descriptor)

    # add a filter to suppress logs from those sources

    files = IGNORE_FILES | frozenset(ignore_files or ())
    modules = IGNORE_MODULES | frozenset(ignore_modules or ())

    if files or modules:
        handler.addFilter(
            SuppressSpamFilter(
                files=files,
                modules=modules,
            ),
        )

    handler.setFormatter(fmt=formatter)

    for logger in (getLogger(), *map(getLogger, root.manager.loggerDict)):
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(level.upper())
        logger.propagate = False

    # disable logging config dictConfig
    logging.config.dictConfig = nothing_to_do

    logger = structlog.get_logger()
    logger.info(
        "structlog configured",
        level=level,
        is_textual=is_textual,
        ignore_files=list(files),
        ignore_modules=list(modules),
    )
