"""``remnawave.reminder.first_connection`` config: delay parsing and normalization."""

import pytest
from pydantic import ValidationError

from src.config.schema import FirstConnectionReminderSettings, parse_delay


@pytest.mark.parametrize('text, minutes', [
    ('3d 5h', 3 * 24 * 60 + 5 * 60),
    ('1h 3m', 63),
    ('5m', 5),
    ('2d', 2880),
    ('  10m   1d ', 24 * 60 + 10),  # any order, extra whitespace
    ('0d 1m', 1),
])
def test_parse_delay(text, minutes):
    assert parse_delay(text) == minutes


@pytest.mark.parametrize('text', ['', '   ', '0m', '5x', '5', '1h 1h', '-1h', '1.5h', '1h3m', 'h'])
def test_parse_delay_rejects_malformed(text):
    with pytest.raises(ValueError):
        parse_delay(text)


def test_default_is_one_reminder_after_two_days():
    settings = FirstConnectionReminderSettings()

    assert settings.enabled is True
    assert settings.delay_minutes == [2880]


def test_delay_minutes_are_sorted_and_deduplicated():
    settings = FirstConnectionReminderSettings(delay=['3d 5h', '1h 3m', '5m', '63m'])

    assert settings.delay_minutes == [5, 63, 4620]


@pytest.mark.parametrize('delay', [[], ['5m', 'soon']])
def test_invalid_delay_list_is_rejected(delay):
    with pytest.raises(ValidationError):
        FirstConnectionReminderSettings(delay=delay)
