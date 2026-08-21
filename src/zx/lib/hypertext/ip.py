from contextlib import suppress
from functools import cached_property, lru_cache
from ipaddress import IPv4Address, IPv4Network
from logging import getLogger
from typing import ClassVar, Self

logger = getLogger(__name__)


class IP4Address(IPv4Address):
    RESERVED: ClassVar[tuple[IPv4Network, ...]] = (
        IPv4Network("0.0.0.0/8"),
        IPv4Network("10.0.0.0/8"),
        IPv4Network("127.0.0.0/8"),
        IPv4Network("169.254.0.0/16"),
        IPv4Network("172.16.0.0/12"),
        IPv4Network("192.0.0.0/24"),
        IPv4Network("192.0.0.170/31"),
        IPv4Network("192.0.2.0/24"),
        IPv4Network("192.168.0.0/16"),
        IPv4Network("198.18.0.0/15"),
        IPv4Network("198.51.100.0/24"),
        IPv4Network("203.0.113.0/24"),
        IPv4Network("240.0.0.0/4"),
        IPv4Network("255.255.255.255/32"),
    )

    @classmethod
    @lru_cache(maxsize=2**10, typed=True)
    def parse(cls, addr: str) -> Self | None:
        with suppress(ValueError):
            return cls(addr)

        logger.debug(
            "Couldn't parse IPv4",
            extra={"address": addr},
        )
        return None

    @classmethod
    @lru_cache(maxsize=2**10, typed=True)
    def get_routable_state(cls, addr: str) -> bool:

        if ip := cls.parse(addr):
            # Checks for non-routable private networks
            if any(ip in net for net in cls.RESERVED):
                return False

            # Carrier-Grade NAT
            return ip not in IPv4Network("100.64.0.0/10")

        return False

    @cached_property
    def is_routable(self) -> bool:
        return self.get_routable_state(str(self))
