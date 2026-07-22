"""Horloge système — seule implémentation Infrastructure du port ClockPort."""

from __future__ import annotations

from datetime import UTC, datetime

from facereco.domain.ports.clock import ClockPort


class SystemClock(ClockPort):
    def now(self) -> datetime:
        return datetime.now(UTC)
