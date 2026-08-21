from contextlib import suppress
from functools import cached_property
from logging import (
    getLevelName,
    getLevelNamesMapping,
    getLogger,
)
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol, TypeVar

import orjson
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = getLogger(__name__)

__all__ = (
    "BaseConfig",
    "BaseLogging",
    "BaseSettings",
    "KubernetesPod",
    "show_environment",
)


class KubernetesPod(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="K8S_",
    )
    namespace: str = "local"
    instance: str = "local"
    pod: str = "local"
    node: str = "localhost"
    addr: str = "127.0.0.1"

    @property
    def as_dict(self) -> dict[str, str]:
        return {
            "k8s_namespace": self.namespace,
            "k8s_instance": self.instance,
            "k8s_pod": self.pod,
            "k8s_node": self.node,
            "k8s_addr": self.addr,
        }


type LoggingFormat = Literal[
    "json",
    "text",
]


type LoggingLevel = Literal[
    "critical",
    "fatal",
    "error",
    "warn",
    "warning",
    "info",
    "debug",
]


class BaseLogging(BaseSettings):
    level: LoggingLevel = "info"
    format: LoggingFormat = "json"

    @cached_property
    def numeric_level(self) -> int:
        if isinstance(self.level, int) or self.level.isdigit():
            return int(self.level)
        try:
            return getLevelNamesMapping()[self.level.upper()]
        except KeyError as e:
            msg = f"Invalid log level: {self.level}"
            raise ValueError(msg) from e

    @cached_property
    def string_level(self) -> str:
        return getLevelName(self.numeric_level).upper()


class BaseConfig(BaseSettings):
    kube: KubernetesPod = Field(default_factory=KubernetesPod)


class ConfigProtocol(Protocol):
    name: str
    version: str

    @staticmethod
    def model_dump() -> dict[str, Any]: ...


TConfig = TypeVar("TConfig", bound=ConfigProtocol)


def show_environment(  # noqa: UP047
    config: Any | type[TConfig],  # noqa: ANN401
    /,
) -> None:
    with suppress(Exception):
        path: Path = Path("packages.json")
        if path.is_file():
            with path.open() as fd:
                packages: list[str] = [
                    "{name}={version}".format(**x)
                    for x in orjson.loads(fd.read().strip())
                ]

            logger.info(
                "Used libraries",
                extra={
                    "app": config.name,
                    "version": config.version,
                    "versions": packages,
                },
            )

    variables: dict[str, Any] = config.model_dump()
    logger.info(
        "Environment variables",
        extra={
            "app": config.name,
            "variables": variables,
            "version": config.version,
        },
    )
