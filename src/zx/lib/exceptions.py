from dataclasses import asdict, dataclass
from traceback import format_exception
from typing import Any

from zx.core import Who
from zx.lib.serial import serializer, stringify


@dataclass(frozen=True, slots=True)
class Error:
    type: str
    arguments: list[str] | None
    message: str | None
    reason: str
    trace: list[str] | None


@serializer(Error)
def from_error(error: Error) -> dict[str, Any]:
    return asdict(error)


def exception(e: Exception) -> Error:
    def trim(lines: list[str]) -> list[str]:
        return [i.rstrip() for i in lines]

    arguments = None
    if args := getattr(e, "args", None):
        arguments = [str(stringify(item, on_error="name")) for item in args]

    reason = f"{Who.Is(e)}({stringify(arguments or [])[1:-1]})"
    if message := getattr(e, "message", "").strip():
        reason = f"{reason}: {message}"

    return Error(
        type=Who.Is(e),
        arguments=arguments,
        message=str(e).strip() or None,
        reason=reason,
        trace=trim(format_exception(e)) or None,
    )
