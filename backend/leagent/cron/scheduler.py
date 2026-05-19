"""Enhanced cron scheduler with expression parsing and rate limiting.

This module provides utilities for cron expression parsing,
next run time calculation, timezone handling, and rate limiting.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from croniter import croniter

logger = structlog.get_logger(__name__)

CRON_ALIASES: dict[str, str] = {
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
    "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 0",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@hourly": "0 * * * *",
    "@every_minute": "* * * * *",
    "@every_5min": "*/5 * * * *",
    "@every_10min": "*/10 * * * *",
    "@every_15min": "*/15 * * * *",
    "@every_30min": "*/30 * * * *",
}

CRON_FIELD_RANGES = {
    "minute": (0, 59),
    "hour": (0, 23),
    "day": (1, 31),
    "month": (1, 12),
    "weekday": (0, 6),
}

WEEKDAY_NAMES = {
    "sun": 0, "sunday": 0,
    "mon": 1, "monday": 1,
    "tue": 2, "tuesday": 2,
    "wed": 3, "wednesday": 3,
    "thu": 4, "thursday": 4,
    "fri": 5, "friday": 5,
    "sat": 6, "saturday": 6,
}

MONTH_NAMES = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


@dataclass
class CronField:
    """Parsed cron field with validation."""

    name: str
    expression: str
    values: set[int] = field(default_factory=set)
    is_wildcard: bool = False
    step: int | None = None

    def matches(self, value: int) -> bool:
        """Check if a value matches this field."""
        if self.is_wildcard and self.step is None:
            return True
        return value in self.values


@dataclass
class ParsedCronExpression:
    """Fully parsed and validated cron expression."""

    original: str
    minute: CronField
    hour: CronField
    day: CronField
    month: CronField
    weekday: CronField

    def to_crontab(self) -> str:
        """Convert back to crontab string."""
        return f"{self.minute.expression} {self.hour.expression} {self.day.expression} {self.month.expression} {self.weekday.expression}"

    def describe(self) -> str:
        """Generate human-readable description."""
        parts = []

        if self.minute.is_wildcard and self.minute.step is None:
            parts.append("every minute")
        elif self.minute.step:
            parts.append(f"every {self.minute.step} minutes")
        elif len(self.minute.values) == 1:
            parts.append(f"at minute {list(self.minute.values)[0]}")

        if self.hour.is_wildcard and self.hour.step is None:
            parts.append("every hour")
        elif self.hour.step:
            parts.append(f"every {self.hour.step} hours")
        elif len(self.hour.values) == 1:
            parts.append(f"at {list(self.hour.values)[0]:02d}:00")

        if not self.day.is_wildcard:
            days = sorted(self.day.values)
            if len(days) <= 3:
                parts.append(f"on day {', '.join(map(str, days))}")

        if not self.month.is_wildcard:
            months = sorted(self.month.values)
            month_names = [
                list(MONTH_NAMES.keys())[list(MONTH_NAMES.values()).index(m)][:3].title()
                for m in months
                if m in MONTH_NAMES.values()
            ]
            if month_names:
                parts.append(f"in {', '.join(month_names)}")

        if not self.weekday.is_wildcard:
            weekdays = sorted(self.weekday.values)
            day_names = [
                list(WEEKDAY_NAMES.keys())[list(WEEKDAY_NAMES.values()).index(d)][:3].title()
                for d in weekdays
                if d in WEEKDAY_NAMES.values()
            ]
            if day_names:
                parts.append(f"on {', '.join(day_names)}")

        return " ".join(parts) if parts else self.original


class CronExpressionParser:
    """Parser for cron expressions with validation."""

    @classmethod
    def parse(cls, expression: str) -> ParsedCronExpression:
        """Parse a cron expression.

        Args:
            expression: The cron expression (5 or 6 parts).

        Returns:
            Parsed expression.

        Raises:
            ValueError: If expression is invalid.
        """
        expression = expression.strip()

        if expression.startswith("@"):
            expression = CRON_ALIASES.get(expression.lower(), expression)
            if expression.startswith("@"):
                raise ValueError(f"Unknown cron alias: {expression}")

        parts = expression.split()

        if len(parts) == 6:
            parts = parts[1:]
        elif len(parts) != 5:
            raise ValueError(
                f"Invalid cron expression: expected 5 parts, got {len(parts)}"
            )

        return ParsedCronExpression(
            original=expression,
            minute=cls._parse_field("minute", parts[0]),
            hour=cls._parse_field("hour", parts[1]),
            day=cls._parse_field("day", parts[2]),
            month=cls._parse_field("month", parts[3]),
            weekday=cls._parse_field("weekday", parts[4]),
        )

    @classmethod
    def _parse_field(cls, name: str, expr: str) -> CronField:
        """Parse a single cron field.

        Args:
            name: Field name.
            expr: Field expression.

        Returns:
            Parsed field.
        """
        field_range = CRON_FIELD_RANGES[name]
        values: set[int] = set()
        is_wildcard = False
        step: int | None = None

        expr = cls._replace_names(expr, name)

        for part in expr.split(","):
            part = part.strip()

            if "/" in part:
                base, step_str = part.split("/", 1)
                step = int(step_str)
                part = base

            if part == "*":
                is_wildcard = True
                if step:
                    values.update(range(field_range[0], field_range[1] + 1, step))
                else:
                    values.update(range(field_range[0], field_range[1] + 1))

            elif "-" in part:
                start, end = part.split("-", 1)
                start_val = int(start)
                end_val = int(end)

                if not (field_range[0] <= start_val <= field_range[1]):
                    raise ValueError(f"Invalid {name} value: {start_val}")
                if not (field_range[0] <= end_val <= field_range[1]):
                    raise ValueError(f"Invalid {name} value: {end_val}")

                values.update(range(start_val, end_val + 1, step or 1))

            else:
                val = int(part)
                if not (field_range[0] <= val <= field_range[1]):
                    raise ValueError(f"Invalid {name} value: {val}")
                values.add(val)

        return CronField(
            name=name,
            expression=expr,
            values=values,
            is_wildcard=is_wildcard,
            step=step,
        )

    @classmethod
    def _replace_names(cls, expr: str, field_name: str) -> str:
        """Replace weekday/month names with numbers."""
        if field_name == "weekday":
            for name, num in WEEKDAY_NAMES.items():
                expr = re.sub(rf"\b{name}\b", str(num), expr, flags=re.IGNORECASE)
        elif field_name == "month":
            for name, num in MONTH_NAMES.items():
                expr = re.sub(rf"\b{name}\b", str(num), expr, flags=re.IGNORECASE)
        return expr

    @classmethod
    def validate(cls, expression: str) -> tuple[bool, str | None]:
        """Validate a cron expression.

        Args:
            expression: The expression to validate.

        Returns:
            Tuple of (is_valid, error_message).
        """
        try:
            cls.parse(expression)
            return True, None
        except Exception as e:
            return False, str(e)


class CronScheduler:
    """Enhanced scheduler with next run calculation and timezone support."""

    def __init__(self, default_timezone: str = "UTC"):
        """Initialize the scheduler.

        Args:
            default_timezone: Default timezone for calculations.
        """
        self.default_timezone = ZoneInfo(default_timezone)
        self._parser = CronExpressionParser()

    def get_next_run(
        self,
        expression: str,
        after: datetime | None = None,
        timezone: str | None = None,
        count: int = 1,
    ) -> list[datetime]:
        """Calculate next run time(s) for a cron expression.

        Args:
            expression: The cron expression.
            after: Calculate runs after this time (default: now).
            timezone: Timezone for calculation.
            count: Number of next runs to calculate.

        Returns:
            List of next run datetimes.
        """
        tz = ZoneInfo(timezone) if timezone else self.default_timezone

        if after is None:
            after = datetime.now(tz)
        elif after.tzinfo is None:
            after = after.replace(tzinfo=tz)

        expression = CRON_ALIASES.get(expression.lower(), expression)

        cron = croniter(expression, after)

        runs = []
        for _ in range(count):
            next_time = cron.get_next(datetime)
            runs.append(next_time.replace(tzinfo=None))

        return runs

    def get_previous_run(
        self,
        expression: str,
        before: datetime | None = None,
        timezone: str | None = None,
    ) -> datetime:
        """Calculate the previous run time for a cron expression.

        Args:
            expression: The cron expression.
            before: Calculate run before this time (default: now).
            timezone: Timezone for calculation.

        Returns:
            Previous run datetime.
        """
        tz = ZoneInfo(timezone) if timezone else self.default_timezone

        if before is None:
            before = datetime.now(tz)
        elif before.tzinfo is None:
            before = before.replace(tzinfo=tz)

        expression = CRON_ALIASES.get(expression.lower(), expression)

        cron = croniter(expression, before)
        prev_time = cron.get_prev(datetime)

        return prev_time.replace(tzinfo=None)

    def is_due(
        self,
        expression: str,
        at: datetime | None = None,
        timezone: str | None = None,
        tolerance_sec: int = 60,
    ) -> bool:
        """Check if a cron expression is due to run.

        Args:
            expression: The cron expression.
            at: Time to check (default: now).
            timezone: Timezone for calculation.
            tolerance_sec: Tolerance window in seconds.

        Returns:
            True if the expression is due.
        """
        tz = ZoneInfo(timezone) if timezone else self.default_timezone

        if at is None:
            at = datetime.now(tz)

        prev_run = self.get_previous_run(expression, at, timezone)
        diff = (at.replace(tzinfo=None) - prev_run).total_seconds()

        return abs(diff) <= tolerance_sec

    def time_until_next(
        self,
        expression: str,
        timezone: str | None = None,
    ) -> timedelta:
        """Calculate time until next run.

        Args:
            expression: The cron expression.
            timezone: Timezone for calculation.

        Returns:
            Timedelta until next run.
        """
        now = datetime.now(ZoneInfo(timezone) if timezone else self.default_timezone)
        next_runs = self.get_next_run(expression, now, timezone, count=1)

        if next_runs:
            return timedelta(seconds=(next_runs[0] - now.replace(tzinfo=None)).total_seconds())

        return timedelta(0)

    def describe(self, expression: str) -> str:
        """Get human-readable description of a cron expression.

        Args:
            expression: The cron expression.

        Returns:
            Human-readable description.
        """
        try:
            parsed = self._parser.parse(expression)
            return parsed.describe()
        except Exception:
            return expression


@dataclass
class RateLimitBucket:
    """Token bucket for rate limiting."""

    capacity: int
    tokens: float
    refill_rate: float
    last_update: datetime = field(default_factory=datetime.utcnow)

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens.

        Args:
            tokens: Number of tokens to consume.

        Returns:
            True if tokens were consumed.
        """
        self._refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True

        return False

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = datetime.utcnow()
        elapsed = (now - self.last_update).total_seconds()

        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_update = now


class RateLimiter:
    """Rate limiter for cron job execution.

    Prevents too many executions within a time window.
    """

    def __init__(
        self,
        default_rate: float = 10.0,
        default_burst: int = 20,
    ):
        """Initialize the rate limiter.

        Args:
            default_rate: Default tokens per second.
            default_burst: Default bucket capacity.
        """
        self.default_rate = default_rate
        self.default_burst = default_burst
        self._buckets: dict[str, RateLimitBucket] = {}
        self._lock = asyncio.Lock()

    async def acquire(
        self,
        key: str,
        tokens: int = 1,
        rate: float | None = None,
        burst: int | None = None,
    ) -> bool:
        """Try to acquire tokens for a key.

        Args:
            key: Rate limit key.
            tokens: Tokens to acquire.
            rate: Custom rate (tokens/sec).
            burst: Custom burst capacity.

        Returns:
            True if tokens were acquired.
        """
        async with self._lock:
            if key not in self._buckets:
                self._buckets[key] = RateLimitBucket(
                    capacity=burst or self.default_burst,
                    tokens=float(burst or self.default_burst),
                    refill_rate=rate or self.default_rate,
                )

            return self._buckets[key].consume(tokens)

    async def wait_for(
        self,
        key: str,
        tokens: int = 1,
        timeout: float = 30.0,
    ) -> bool:
        """Wait to acquire tokens.

        Args:
            key: Rate limit key.
            tokens: Tokens to acquire.
            timeout: Maximum wait time.

        Returns:
            True if tokens were acquired.
        """
        deadline = datetime.utcnow() + timedelta(seconds=timeout)

        while datetime.utcnow() < deadline:
            if await self.acquire(key, tokens):
                return True
            await asyncio.sleep(0.1)

        return False

    def get_status(self, key: str) -> dict[str, Any]:
        """Get rate limit status for a key.

        Args:
            key: Rate limit key.

        Returns:
            Status dictionary.
        """
        bucket = self._buckets.get(key)

        if not bucket:
            return {
                "key": key,
                "exists": False,
            }

        return {
            "key": key,
            "exists": True,
            "tokens": bucket.tokens,
            "capacity": bucket.capacity,
            "refill_rate": bucket.refill_rate,
        }

    def reset(self, key: str) -> None:
        """Reset rate limit for a key.

        Args:
            key: Rate limit key.
        """
        self._buckets.pop(key, None)
