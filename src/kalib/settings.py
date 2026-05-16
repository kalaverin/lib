from contextlib import suppress
from functools import cached_property
from logging import (
    getLevelName,
    getLevelNamesMapping,
    getLogger,
)
from pathlib import Path
from typing import Any, ClassVar, Protocol, TypeVar

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
    """Kubernetes pod information from environment variables.

    Reads pod metadata from K8S_* environment variables injected by Kubernetes.

    Attributes:
        namespace: Kubernetes namespace (default: 'local').
        pod: Pod name (default: 'local').
        pod_ip: Pod IP address (default: '127.0.0.1').
        node: Node name (default: 'localhost').
        instance: Instance identifier (default: 'local').

    Example:
        >>> pod = KubernetesPod()
        >>> pod.namespace
        'production'
        >>> pod.as_dict
        {'k8s_namespace': 'production', 'k8s_pod': 'api-abc123', ...}
    """

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="K8S_",
    )
    namespace: str = "local"
    pod: str = "local"
    pod_ip: str = "127.0.0.1"
    node: str = "localhost"
    instance: str = "local"

    @property
    def as_dict(self) -> dict[str, str]:
        """Return pod info as a dictionary with standardized keys.

        Returns:
            Dictionary with keys: k8s_namespace, k8s_pod, k8s_pod_ip,
            k8s_node, k8s_instance.
        """
        return {
            "k8s_namespace": self.namespace,
            "k8s_pod": self.pod,
            "k8s_pod_ip": self.pod_ip,
            "k8s_node": self.node,
            "k8s_instance": self.instance,
        }


class BaseLogging(BaseSettings):
    """Base logging configuration settings.

    Provides configuration for log level with conversion between
    string names and numeric levels.

    Attributes:
        level: Log level as string or integer (default: 'info').
        format: Log output format (default: 'json').

    Example:
        >>> logging_cfg = BaseLogging(level="DEBUG", format="default")
        >>> logging_cfg.numeric_level
        10
    """

    level: int | str = "info"
    format: str = "json"

    @cached_property
    def numeric_level(self) -> int:
        """Convert string log level to numeric value.

        Returns:
            Numeric log level (e.g., 10 for 'DEBUG', 20 for 'INFO').

        Raises:
            ValueError: If the log level string is invalid.
        """
        if isinstance(self.level, int) or self.level.isdigit():
            return int(self.level)
        try:
            return getLevelNamesMapping()[self.level.upper()]
        except KeyError as e:
            msg = f"Invalid log level: {self.level}"
            raise ValueError(msg) from e

    @cached_property
    def string_level(self) -> str:
        """Return log level as uppercase string.

        Returns:
            Uppercase log level name (e.g., 'INFO', 'DEBUG').
        """
        return getLevelName(self.numeric_level).upper()


class BaseConfig(BaseSettings):
    """Base application configuration.

    Provides common configuration fields for all applications,
    including Kubernetes pod information.

    Attributes:
        kube: Kubernetes pod settings (auto-populated from env vars).

    Example:
        >>> class MyConfig(BaseConfig):
        ...     debug: bool = False
        >>> cfg = MyConfig(debug=True)
        >>> cfg.kube.namespace
        'local'
    """

    kube: KubernetesPod = Field(default_factory=KubernetesPod)


class ConfigProtocol(Protocol):
    """Protocol defining configuration interface for show_environment().

    Any config object passed to show_environment() must implement this
    protocol.

    Attributes:
        name: Application or service name.
        version: Application version.
    """

    name: str
    version: str

    @staticmethod
    def model_dump() -> dict[str, Any]: ...


TConfig = TypeVar("TConfig", bound=ConfigProtocol)


def show_environment(  # noqa: UP047
    config: Any | type[TConfig],  # noqa: ANN401
    /,
) -> None:
    """Log environment information and installed packages.

    Reads packages.json if available and logs environment variables
    from the provided configuration object.

    Args:
        config: Configuration object with 'name', 'version', and 'model_dump()'
            method, or a class that implements ConfigProtocol.

    Example:
        >>> class AppConfig:
        ...     name = "myapp"
        ...     version = "1.0.0"
        ...     @staticmethod
        ...     def model_dump():
        ...         return {"debug": True}
        >>> show_environment(AppConfig())
        # logs: Used libraries, Environment variables

    Note:
        Silently handles any exceptions to prevent startup failures.
    """
    with suppress(Exception):
        path: Path = Path("packages.json").resolve()
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
