from __future__ import annotations

import re
from dataclasses import dataclass

from blessyou_bot.models import Participant

HANDLE_RE = re.compile(r"^@?([A-Za-z][A-Za-z0-9_]{2,31})$")


class ParseError(ValueError):
    """Raised when user input cannot be parsed."""


@dataclass(frozen=True)
class BlessInput:
    participants: list[Participant]
    amount: int


@dataclass(frozen=True)
class UnblessInput:
    participant: Participant
    amount: int
    reason: str | None


def normalize_handle(raw: str) -> Participant:
    cleaned = raw.strip().rstrip(",")
    match = HANDLE_RE.fullmatch(cleaned)
    if not match:
        raise ParseError(f"Invalid Telegram handle: {raw}")
    username = match.group(1).lower()
    return Participant(key=username, handle=f"@{username}")


def parse_bless_text(text: str) -> BlessInput:
    tokens = [token for token in text.replace(",", " ").split() if token]
    if not tokens:
        raise ParseError("Please provide one or two Telegram handles.")

    amount = 1
    handle_tokens = tokens
    if len(tokens) > 1:
        try:
            amount = int(tokens[-1])
            handle_tokens = tokens[:-1]
        except ValueError:
            amount = 1
            handle_tokens = tokens

    if amount < 1:
        raise ParseError("Bless points must be at least 1.")

    if not handle_tokens:
        raise ParseError("Please provide one or two Telegram handles.")

    if len(handle_tokens) > 2:
        raise ParseError("Please provide at most two Telegram handles, optionally followed by a points amount.")

    participants = [normalize_handle(token) for token in handle_tokens]
    keys = {participant.key for participant in participants}
    if len(keys) != len(participants):
        raise ParseError("The same handle was entered twice.")
    return BlessInput(participants=participants, amount=amount)


def parse_unbless_text(text: str, default_amount: int) -> UnblessInput:
    tokens = [token for token in text.split() if token]
    if not tokens:
        raise ParseError("Please provide a Telegram handle to penalize.")

    participant = normalize_handle(tokens[0])
    amount = default_amount
    reason_start = 1

    if len(tokens) > 1:
        try:
            amount = abs(int(tokens[1]))
            reason_start = 2
        except ValueError:
            amount = default_amount
            reason_start = 1

    if amount < 1:
        raise ParseError("Penalty points must be at least 1.")

    reason = " ".join(tokens[reason_start:]).strip() or None
    return UnblessInput(participant=participant, amount=amount, reason=reason)
