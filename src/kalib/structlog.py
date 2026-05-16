# ruff: noqa: ANN401

import logging.config
import sys
from collections.abc import Collection, Iterable
from fnmatch import translate
from functools import cached_property, lru_cache, partial
from logging import (
    Filter,
    LogRecord,
    StreamHandler,
    getLevelName,
    getLogger,
    root,
)
from os import getenv
from re import Pattern, compile
from typing import Any, TextIO, final, override

import orjson
import structlog
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

IGNORE_FILES = frozenset(getenv("LOGGING_IGNORE_FILES", "").split(";"))

IGNORE_MODULES = frozenset(getenv("LOGGING_IGNORE_MODULES", "").split(";"))


###


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
    def regex_files(self) -> Pattern[str]:
        return compile(
            "|".join(
                map(translate, sorted(self._files, key=len, reverse=True)),
            ),
        )

    @cached_property
    def regex_modules(self) -> Pattern[str]:
        return compile(
            "|".join(
                map(translate, sorted(self._modules, key=len, reverse=True)),
            ),
        )

    @lru_cache(maxsize=2**10)
    def is_ignored_file(self, name: str) -> bool:
        if self._files:
            print("here", self._files)
            return bool(self.regex_files.search(name))
        return False

    @lru_cache(maxsize=2**10)
    def is_ignored_modules(self, name: str) -> bool:
        if self._modules:
            return bool(self.regex_modules.search(name))
        return False

    @override
    def filter(self, record: LogRecord) -> bool:
        return not (
            self.is_ignored_file(record.filename)
            or self.is_ignored_modules(record.name)
        )


###


def nothing_to_do(*_: Any, **__: Any) -> None:
    """No-op function used to disable logging.config.dictConfig.

    After structlog is configured, we prevent further reconfiguration
    by replacing dictConfig with this no-op.
    """


def configure(
    level: int | str = "info",
    is_textual: bool = False,
    descriptor: TextIO = sys.stdout,
    serializer_options: int = DEFAULT_JSON_OPTIONS,
    processors: Iterable[Processor] = DEFAULT_PROCESSORS,
    ignore_files: Collection[str] | None = None,
    ignore_modules: Collection[str] | None = None,
) -> None:
    """Configure structured logging with structlog.

    Sets up structlog with either JSON (production) or colored console
    (development) output. Replaces all existing log handlers.

    Args:
        level: Logging level as string (e.g., 'INFO', 'DEBUG') or integer.
        is_textual: If True, use colored console output (development mode).
            If False, use JSON output (production mode).
        descriptor: Output stream for logs (default: sys.stderr).
        serializer_options: orjson options for JSON serialization.
        processors: Additional structlog processors to apply.

    Example:
        >>> # Production (JSON)
        >>> configure(level="INFO", is_textual=False)

        >>> # Development (colored console)
        >>> configure(level="DEBUG", is_textual=True)

    Note:
        This function replaces ALL existing log handlers in the root logger
        and all child loggers. After calling this, logging.config.dictConfig
        becomes a no-op.
    """

    # convert integer level to string name
    if isinstance(level, int):
        level = getLevelName(level)

    # in development we look for native tracebacks (with better-exceptions too)
    # but in production we want json in the logs

    order: list[Processor] = list(processors)

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

    if is_textual:
        renderer = ConsoleRenderer(
            colors=True,
            exception_formatter=RichTracebackFormatter(
                extra_lines=4,
                max_frames=20,
                theme=getenv("PYGMENTS_THEME", "vim"),
            ),
        )

    else:
        # for better performance, we use orjson to serialize log entries

        dumps = partial(orjson.dumps, option=serializer_options)

        def serializer(*args: Any, **kw: Any) -> str:
            return dumps(*args, **kw).decode("utf-8")

        renderer = JSONRenderer(serializer=serializer)

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
