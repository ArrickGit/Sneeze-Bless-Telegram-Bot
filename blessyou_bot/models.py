from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Participant:
    key: str
    handle: str


@dataclass(frozen=True)
class Actor:
    user_id: int | None
    username: str | None
    full_name: str
