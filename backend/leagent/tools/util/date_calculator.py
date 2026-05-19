"""Date Calculator Tool - Date and time calculations.

Provides operations for date arithmetic, business days calculation,
timezone conversion, and date formatting.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, available_timezones

import structlog

from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)

COMMON_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%m-%d-%Y",
    "%m/%d/%Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%d %b %Y",
    "%d %B %Y",
    "%B %d, %Y",
    "%b %d, %Y",
]


class DateCalculatorTool(SyncTool):
    """Perform date and time calculations.

    Features:
    - Add/subtract days, weeks, months, years
    - Calculate business days between dates
    - Add/subtract business days
    - Format dates in various formats
    - Convert between timezones
    - Calculate date differences
    - Parse dates from various formats
    """

    name = "date_calculator"
    description = (
        "Perform date calculations including arithmetic (add/subtract days, months, years), "
        "business days calculation, timezone conversion, and date formatting."
    )
    category = ToolCategory.UTIL
    version = "1.0.0"
    timeout_sec = 30
    aliases = ["date", "date_calc", "time_calc"]
    search_hint = "date calculate add subtract business days timezone format convert"
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 50_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        op = (params or {}).get("operation", "calculate")
        return f"Calculating date ({op})"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "add",
                        "subtract",
                        "difference",
                        "business_days",
                        "add_business_days",
                        "format",
                        "convert_timezone",
                        "parse",
                        "now",
                        "compare",
                    ],
                    "description": "Date operation to perform.",
                },
                "date": {
                    "type": "string",
                    "description": "Input date (ISO format YYYY-MM-DD or datetime).",
                },
                "date2": {
                    "type": "string",
                    "description": "Second date for difference/compare operations.",
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days to add/subtract.",
                },
                "weeks": {
                    "type": "integer",
                    "description": "Number of weeks to add/subtract.",
                },
                "months": {
                    "type": "integer",
                    "description": "Number of months to add/subtract.",
                },
                "years": {
                    "type": "integer",
                    "description": "Number of years to add/subtract.",
                },
                "hours": {
                    "type": "integer",
                    "description": "Number of hours to add/subtract.",
                },
                "minutes": {
                    "type": "integer",
                    "description": "Number of minutes to add/subtract.",
                },
                "format": {
                    "type": "string",
                    "description": "Output date format (strftime format string).",
                    "default": "%Y-%m-%d",
                },
                "input_format": {
                    "type": "string",
                    "description": "Input date format for parsing.",
                },
                "from_timezone": {
                    "type": "string",
                    "description": "Source timezone (e.g., 'America/New_York', 'UTC').",
                },
                "to_timezone": {
                    "type": "string",
                    "description": "Target timezone for conversion.",
                },
                "holidays": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of holiday dates (YYYY-MM-DD) to exclude from business days.",
                },
                "weekend_days": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0, "maximum": 6},
                    "description": "Days considered weekend (0=Monday, 6=Sunday). Default: [5, 6].",
                    "default": [5, 6],
                },
                "include_end": {
                    "type": "boolean",
                    "description": "Include end date in business days count.",
                    "default": False,
                },
            },
            "required": ["operation"],
            "additionalProperties": False,
        }

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Execute date operation.

        Args:
            params: Tool parameters including operation and date values.
            context: Execution context.

        Returns:
            Dictionary containing operation result.

        Raises:
            ValueError: If parameters are invalid.
        """
        operation = params["operation"]

        logger.info("Executing date operation", operation=operation)

        operations = {
            "add": self._add_duration,
            "subtract": self._subtract_duration,
            "difference": self._calculate_difference,
            "business_days": self._count_business_days,
            "add_business_days": self._add_business_days,
            "format": self._format_date,
            "convert_timezone": self._convert_timezone,
            "parse": self._parse_date,
            "now": self._get_now,
            "compare": self._compare_dates,
        }

        if operation not in operations:
            raise ValueError(f"Unknown operation: {operation}")

        result = operations[operation](params)

        logger.info("Date operation complete", operation=operation)
        return result

    def _parse_input_date(self, date_str: str, input_format: str | None = None) -> datetime:
        """Parse date string to datetime object."""
        if input_format:
            return datetime.strptime(date_str, input_format)

        for fmt in COMMON_DATE_FORMATS:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        raise ValueError(f"Could not parse date: {date_str}. Please provide input_format.")

    def _add_duration(self, params: dict[str, Any]) -> dict[str, Any]:
        """Add duration to a date."""
        date_str = params.get("date")
        if not date_str:
            raise ValueError("Date is required for add operation")

        input_format = params.get("input_format")
        dt = self._parse_input_date(date_str, input_format)

        days = params.get("days", 0)
        weeks = params.get("weeks", 0)
        hours = params.get("hours", 0)
        minutes = params.get("minutes", 0)
        months = params.get("months", 0)
        years = params.get("years", 0)

        result_dt = dt + timedelta(days=days, weeks=weeks, hours=hours, minutes=minutes)

        if months or years:
            result_dt = self._add_months(result_dt, months + years * 12)

        output_format = params.get("format", "%Y-%m-%d")
        if dt.hour or dt.minute or dt.second or hours or minutes:
            output_format = params.get("format", "%Y-%m-%dT%H:%M:%S")

        return {
            "original": date_str,
            "result": result_dt.strftime(output_format),
            "result_iso": result_dt.isoformat(),
            "added": {
                "days": days,
                "weeks": weeks,
                "months": months,
                "years": years,
                "hours": hours,
                "minutes": minutes,
            },
        }

    def _subtract_duration(self, params: dict[str, Any]) -> dict[str, Any]:
        """Subtract duration from a date."""
        negated_params = params.copy()
        for key in ["days", "weeks", "months", "years", "hours", "minutes"]:
            if key in params and params[key]:
                negated_params[key] = -params[key]

        result = self._add_duration(negated_params)
        result["subtracted"] = result.pop("added")
        for key in result["subtracted"]:
            result["subtracted"][key] = abs(result["subtracted"][key])

        return result

    def _add_months(self, dt: datetime, months: int) -> datetime:
        """Add months to datetime, handling month boundaries."""
        month = dt.month - 1 + months
        year = dt.year + month // 12
        month = month % 12 + 1

        max_day = self._days_in_month(year, month)
        day = min(dt.day, max_day)

        return dt.replace(year=year, month=month, day=day)

    def _days_in_month(self, year: int, month: int) -> int:
        """Get number of days in a month."""
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        return (next_month - date(year, month, 1)).days

    def _calculate_difference(self, params: dict[str, Any]) -> dict[str, Any]:
        """Calculate difference between two dates."""
        date1_str = params.get("date")
        date2_str = params.get("date2")

        if not date1_str or not date2_str:
            raise ValueError("Both date and date2 are required for difference operation")

        input_format = params.get("input_format")
        dt1 = self._parse_input_date(date1_str, input_format)
        dt2 = self._parse_input_date(date2_str, input_format)

        delta = dt2 - dt1
        total_seconds = delta.total_seconds()

        return {
            "date1": date1_str,
            "date2": date2_str,
            "difference": {
                "days": delta.days,
                "total_seconds": total_seconds,
                "weeks": delta.days // 7,
                "hours": total_seconds / 3600,
                "minutes": total_seconds / 60,
            },
            "is_positive": delta.days >= 0,
        }

    def _count_business_days(self, params: dict[str, Any]) -> dict[str, Any]:
        """Count business days between two dates."""
        date1_str = params.get("date")
        date2_str = params.get("date2")

        if not date1_str or not date2_str:
            raise ValueError("Both date and date2 are required for business_days operation")

        input_format = params.get("input_format")
        dt1 = self._parse_input_date(date1_str, input_format).date()
        dt2 = self._parse_input_date(date2_str, input_format).date()

        holidays = set()
        for h in params.get("holidays", []):
            try:
                holidays.add(self._parse_input_date(h, input_format).date())
            except ValueError:
                logger.warning("Invalid holiday date", date=h)

        weekend_days = set(params.get("weekend_days", [5, 6]))
        include_end = params.get("include_end", False)

        if dt1 > dt2:
            dt1, dt2 = dt2, dt1

        business_days = 0
        current = dt1
        while current < dt2 or (include_end and current <= dt2):
            if current.weekday() not in weekend_days and current not in holidays:
                business_days += 1
            current += timedelta(days=1)

        return {
            "start_date": str(dt1),
            "end_date": str(dt2),
            "business_days": business_days,
            "calendar_days": (dt2 - dt1).days + (1 if include_end else 0),
            "holidays_excluded": len([h for h in holidays if dt1 <= h <= dt2]),
        }

    def _add_business_days(self, params: dict[str, Any]) -> dict[str, Any]:
        """Add business days to a date."""
        date_str = params.get("date")
        days = params.get("days", 0)

        if not date_str:
            raise ValueError("Date is required for add_business_days operation")
        if days == 0:
            raise ValueError("Days is required for add_business_days operation")

        input_format = params.get("input_format")
        dt = self._parse_input_date(date_str, input_format).date()

        holidays = set()
        for h in params.get("holidays", []):
            try:
                holidays.add(self._parse_input_date(h, input_format).date())
            except ValueError:
                logger.warning("Invalid holiday date", date=h)

        weekend_days = set(params.get("weekend_days", [5, 6]))

        direction = 1 if days > 0 else -1
        remaining = abs(days)
        current = dt

        while remaining > 0:
            current += timedelta(days=direction)
            if current.weekday() not in weekend_days and current not in holidays:
                remaining -= 1

        output_format = params.get("format", "%Y-%m-%d")
        return {
            "original": date_str,
            "result": current.strftime(output_format),
            "business_days_added": days,
            "calendar_days_elapsed": (current - dt).days,
        }

    def _format_date(self, params: dict[str, Any]) -> dict[str, Any]:
        """Format a date string."""
        date_str = params.get("date")
        if not date_str:
            raise ValueError("Date is required for format operation")

        input_format = params.get("input_format")
        output_format = params.get("format", "%Y-%m-%d")

        dt = self._parse_input_date(date_str, input_format)

        common_formats = {
            "iso": dt.isoformat(),
            "date": dt.strftime("%Y-%m-%d"),
            "datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
            "human": dt.strftime("%B %d, %Y"),
            "short": dt.strftime("%m/%d/%Y"),
            "unix": int(dt.timestamp()) if dt.tzinfo or dt.year >= 1970 else None,
        }

        return {
            "original": date_str,
            "formatted": dt.strftime(output_format),
            "common_formats": common_formats,
            "components": {
                "year": dt.year,
                "month": dt.month,
                "day": dt.day,
                "hour": dt.hour,
                "minute": dt.minute,
                "second": dt.second,
                "weekday": dt.weekday(),
                "weekday_name": dt.strftime("%A"),
                "month_name": dt.strftime("%B"),
                "day_of_year": dt.timetuple().tm_yday,
                "week_of_year": dt.isocalendar()[1],
            },
        }

    def _convert_timezone(self, params: dict[str, Any]) -> dict[str, Any]:
        """Convert datetime between timezones."""
        date_str = params.get("date")
        from_tz = params.get("from_timezone")
        to_tz = params.get("to_timezone")

        if not date_str:
            raise ValueError("Date is required for timezone conversion")
        if not to_tz:
            raise ValueError("to_timezone is required for timezone conversion")

        input_format = params.get("input_format")
        dt = self._parse_input_date(date_str, input_format)

        available_tz = available_timezones()

        if from_tz:
            if from_tz not in available_tz:
                raise ValueError(f"Invalid source timezone: {from_tz}")
            dt = dt.replace(tzinfo=ZoneInfo(from_tz))
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))

        if to_tz not in available_tz:
            raise ValueError(f"Invalid target timezone: {to_tz}")

        converted = dt.astimezone(ZoneInfo(to_tz))
        output_format = params.get("format", "%Y-%m-%dT%H:%M:%S%z")

        return {
            "original": date_str,
            "from_timezone": from_tz or "UTC",
            "to_timezone": to_tz,
            "result": converted.strftime(output_format),
            "result_iso": converted.isoformat(),
            "offset": converted.strftime("%z"),
            "offset_hours": converted.utcoffset().total_seconds() / 3600 if converted.utcoffset() else 0,
        }

    def _parse_date(self, params: dict[str, Any]) -> dict[str, Any]:
        """Parse date from string and return components."""
        date_str = params.get("date")
        if not date_str:
            raise ValueError("Date is required for parse operation")

        input_format = params.get("input_format")
        dt = self._parse_input_date(date_str, input_format)

        return self._format_date({"date": date_str, "input_format": input_format})

    def _get_now(self, params: dict[str, Any]) -> dict[str, Any]:
        """Get current date and time."""
        timezone = params.get("to_timezone", "UTC")

        try:
            tz = ZoneInfo(timezone)
        except Exception:
            tz = ZoneInfo("UTC")
            timezone = "UTC"

        now = datetime.now(tz)
        output_format = params.get("format", "%Y-%m-%dT%H:%M:%S%z")

        return {
            "timezone": timezone,
            "datetime": now.strftime(output_format),
            "iso": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "unix_timestamp": int(now.timestamp()),
            "components": {
                "year": now.year,
                "month": now.month,
                "day": now.day,
                "hour": now.hour,
                "minute": now.minute,
                "second": now.second,
                "weekday": now.weekday(),
                "weekday_name": now.strftime("%A"),
            },
        }

    def _compare_dates(self, params: dict[str, Any]) -> dict[str, Any]:
        """Compare two dates."""
        date1_str = params.get("date")
        date2_str = params.get("date2")

        if not date1_str or not date2_str:
            raise ValueError("Both date and date2 are required for compare operation")

        input_format = params.get("input_format")
        dt1 = self._parse_input_date(date1_str, input_format)
        dt2 = self._parse_input_date(date2_str, input_format)

        if dt1 < dt2:
            comparison = "before"
        elif dt1 > dt2:
            comparison = "after"
        else:
            comparison = "equal"

        return {
            "date1": date1_str,
            "date2": date2_str,
            "comparison": comparison,
            "date1_is_before": dt1 < dt2,
            "date1_is_after": dt1 > dt2,
            "dates_are_equal": dt1 == dt2,
            "same_day": dt1.date() == dt2.date(),
            "same_month": dt1.year == dt2.year and dt1.month == dt2.month,
            "same_year": dt1.year == dt2.year,
        }
