"""Relógio injetável. Application não lê o relógio de parede."""

from __future__ import annotations

import datetime as dt
from typing import Protocol


class Clock(Protocol):
    def now(self) -> dt.datetime: ...


class FixedClock:
    def __init__(self, instant: dt.datetime) -> None:
        if instant.tzinfo is None:
            raise ValueError("clock exige datetime timezone-aware")
        self._instant = instant

    def now(self) -> dt.datetime:
        return self._instant
