from __future__ import annotations

from typing import TYPE_CHECKING, Final

from zx.core import Is
from zx.prop import mixed_property, pin

if TYPE_CHECKING:
    from fake_useragent import UserAgent


def _user_agent(platforms: list[str], fallback: str, /) -> UserAgent:
    """Build a UserAgent; the import is lazy (optional ``backend`` extras)."""
    from fake_useragent import UserAgent  # noqa: PLC0415

    return UserAgent(platforms=platforms, fallback=fallback)


DEFAULT_PLATFORMS: Final = ["desktop"]
FALLBACK_USER_AGENT: Final = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36"
)
USER_AGENT_HEADER: Final = "user-agent"


class Agent:
    @pin.cls
    def default_agent(
        cls,
    ) -> UserAgent:  # zx class-property idiom
        return _user_agent(list(DEFAULT_PLATFORMS), FALLBACK_USER_AGENT)

    @mixed_property
    def header(
        node,
    ) -> dict[str, str]:  # zx mixed-property idiom
        result = node.default_agent.random if Is.Class(node) else node.random
        return {USER_AGENT_HEADER: result}

    def __init__(
        self,
        platforms: list[str] = DEFAULT_PLATFORMS,
        fallback: str = FALLBACK_USER_AGENT,
    ) -> None:
        self.agent = _user_agent(list(platforms), fallback)

    @property
    def random(self) -> str:
        return self.agent.random
