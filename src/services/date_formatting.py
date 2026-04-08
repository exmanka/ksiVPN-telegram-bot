"""Locale-aware datetime and timedelta formatting helpers.

The bot previously relied on PostgreSQL `TO_CHAR(..., 'FMDD TMMonth YYYY в HH24:MI')`
which required the `ru_RU.UTF-8` OS locale to be pre-generated in the postgres
container. To get rid of the custom postgres image we moved locale-dependent
formatting into Python via Babel. All formatting respects
`settings.localization.language` (ru/en), matching the rest of the i18n layer.
"""
from datetime import datetime, timedelta

from babel.dates import format_datetime, format_timedelta

from src.config import settings


# Babel datetime skeletons/patterns per language. Matches the visual output:
#   ru: "1 апреля 2026 в 14:30"
#   en: "1 April 2026 at 14:30"
_LONG_DATETIME_PATTERNS: dict[str, str] = {
    'ru': "d MMMM y 'в' HH:mm",
    'en': "d MMMM y 'at' HH:mm",
}


def _current_locale() -> str:
    """Return the Babel locale code corresponding to the bot's configured language."""
    return settings.localization.language


def format_localized_datetime(dt: datetime | None) -> str:
    """Format a datetime in the bot's configured language (long form with month name).

    Returns an empty string for ``None`` so callers that interpolate the result into
    messages don't have to special-case missing values.
    """
    if dt is None:
        return ''
    locale = _current_locale()
    pattern = _LONG_DATETIME_PATTERNS.get(locale, _LONG_DATETIME_PATTERNS['en'])
    return format_datetime(dt, pattern, locale=locale)


def format_localized_bonus_days(td: timedelta | None) -> str:
    """Format a bonus-time interval as a localized, properly pluralized day count.

    Examples:
        ru: 1 → "1 день", 2 → "2 дня", 5 → "5 дней"
        en: 1 → "1 day",  5 → "5 days"

    Returns ``'0'`` for ``None``/zero to preserve the previous ``TO_CHAR(..., 'FMDDD')``
    behaviour of never yielding an empty string.
    """
    if td is None or td.total_seconds() == 0:
        # Babel would return "0 days" / "0 дней" for zero, which matches previous
        # TO_CHAR behaviour of "0". Keep explicit handling for None → "0".
        td = timedelta(0)
    return format_timedelta(td, granularity='day', locale=_current_locale())
