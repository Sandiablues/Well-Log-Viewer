"""RFC 9562 UUIDv7 generation and validation for durable WLV identities.

This module owns identifier mechanics only. It deliberately does not decide
when a domain entity should be created, reconciled, restored, or deleted.
Those lifecycle decisions belong to the owning backend repository/service.
"""

from __future__ import annotations

import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

_UUID7_RANDOM_BITS = 74
_UUID7_RANDOM_MAX = (1 << _UUID7_RANDOM_BITS) - 1
_UUID7_TIMESTAMP_MAX = (1 << 48) - 1


def _system_time_ms() -> int:
    return time.time_ns() // 1_000_000


@dataclass
class Uuid7Generator:
    """Thread-safe, process-local monotonic UUIDv7 generator.

    UUIDv7 provides time-ordered identifiers without deriving identity from
    mutable business metadata. Within one process, identifiers generated in
    the same millisecond are monotonically ordered by incrementing the 74-bit
    random payload. Clock rollback is contained by retaining the last emitted
    timestamp until wall-clock time catches up.
    """

    time_ms: Callable[[], int] = _system_time_ms
    random_bits: Callable[[int], int] = secrets.randbits
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _last_timestamp_ms: int = field(default=-1, init=False, repr=False)
    _last_random_payload: int = field(default=-1, init=False, repr=False)

    def new(self) -> uuid.UUID:
        """Return a new RFC 9562 UUIDv7 value."""

        with self._lock:
            timestamp_ms = int(self.time_ms())
            if timestamp_ms < 0 or timestamp_ms > _UUID7_TIMESTAMP_MAX:
                raise ValueError("UUIDv7 timestamp must fit in 48 unsigned bits")

            if timestamp_ms > self._last_timestamp_ms:
                random_payload = int(self.random_bits(_UUID7_RANDOM_BITS))
                if random_payload < 0 or random_payload > _UUID7_RANDOM_MAX:
                    raise ValueError("UUIDv7 random payload must fit in 74 unsigned bits")
            else:
                timestamp_ms = self._last_timestamp_ms
                random_payload = self._last_random_payload + 1
                if random_payload > _UUID7_RANDOM_MAX:
                    if timestamp_ms == _UUID7_TIMESTAMP_MAX:
                        raise OverflowError("UUIDv7 timestamp and random payload exhausted")
                    timestamp_ms += 1
                    random_payload = int(self.random_bits(_UUID7_RANDOM_BITS))
                    if random_payload < 0 or random_payload > _UUID7_RANDOM_MAX:
                        raise ValueError("UUIDv7 random payload must fit in 74 unsigned bits")

            self._last_timestamp_ms = timestamp_ms
            self._last_random_payload = random_payload
            return _compose_uuid7(timestamp_ms, random_payload)


def _compose_uuid7(timestamp_ms: int, random_payload: int) -> uuid.UUID:
    rand_a = (random_payload >> 62) & 0xFFF
    rand_b = random_payload & ((1 << 62) - 1)

    value = timestamp_ms << 80
    value |= 0x7 << 76
    value |= rand_a << 64
    value |= 0b10 << 62
    value |= rand_b
    return uuid.UUID(int=value)


_DEFAULT_GENERATOR = Uuid7Generator()


def new_uuid7() -> uuid.UUID:
    """Generate a canonical UUIDv7 object using the process generator."""

    return _DEFAULT_GENERATOR.new()


def new_uuid7_str() -> str:
    """Generate a lowercase, hyphenated canonical UUIDv7 string."""

    return str(new_uuid7())


def parse_uuid7(value: str | uuid.UUID) -> uuid.UUID:
    """Parse and validate a UUIDv7 value.

    Raises ``ValueError`` for malformed UUIDs, non-v7 UUIDs, and values that do
    not carry the RFC 4122/RFC 9562 variant bits.
    """

    parsed = value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    if parsed.version != 7:
        raise ValueError(f"expected UUIDv7, received UUID version {parsed.version}")
    if parsed.variant != uuid.RFC_4122:
        raise ValueError("expected RFC 4122/RFC 9562 UUID variant")
    return parsed


def is_uuid7(value: object) -> bool:
    """Return whether ``value`` is a valid canonical UUIDv7 value."""

    if not isinstance(value, (str, uuid.UUID)):
        return False
    try:
        parse_uuid7(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def uuid7_timestamp_ms(value: str | uuid.UUID) -> int:
    """Return the 48-bit Unix epoch millisecond timestamp from UUIDv7."""

    parsed = parse_uuid7(value)
    return parsed.int >> 80
