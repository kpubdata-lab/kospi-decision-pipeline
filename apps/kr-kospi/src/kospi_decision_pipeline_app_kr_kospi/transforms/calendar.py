from __future__ import annotations

from datetime import date
from typing import final


KRX_HOLIDAYS = {
    2024: frozenset(
        {
            date(2024, 1, 1),
            date(2024, 2, 9),
            date(2024, 2, 10),
            date(2024, 2, 12),
            date(2024, 3, 1),
            date(2024, 4, 10),
            date(2024, 5, 1),
            date(2024, 5, 6),
            date(2024, 5, 15),
            date(2024, 6, 6),
            date(2024, 8, 15),
            date(2024, 9, 16),
            date(2024, 9, 17),
            date(2024, 9, 18),
            date(2024, 10, 1),
            date(2024, 10, 3),
            date(2024, 10, 9),
            date(2024, 12, 25),
            date(2024, 12, 31),
        }
    ),
    2025: frozenset(
        {
            date(2025, 1, 1),
            date(2025, 1, 28),
            date(2025, 1, 29),
            date(2025, 1, 30),
            date(2025, 3, 3),
            date(2025, 5, 1),
            date(2025, 5, 5),
            date(2025, 5, 6),
            date(2025, 6, 3),
            date(2025, 6, 6),
            date(2025, 8, 15),
            date(2025, 10, 3),
            date(2025, 10, 6),
            date(2025, 10, 7),
            date(2025, 10, 8),
            date(2025, 10, 9),
            date(2025, 12, 25),
            date(2025, 12, 31),
        }
    ),
    2026: frozenset(
        {
            date(2026, 1, 1),
            date(2026, 2, 16),
            date(2026, 2, 17),
            date(2026, 2, 18),
            date(2026, 3, 2),
            date(2026, 5, 1),
            date(2026, 5, 5),
            date(2026, 5, 25),
            date(2026, 8, 17),
            date(2026, 9, 24),
            date(2026, 9, 25),
            date(2026, 10, 5),
            date(2026, 10, 9),
            date(2026, 12, 25),
            date(2026, 12, 31),
        }
    ),
    2027: frozenset(
        {
            date(2027, 1, 1),
            date(2027, 2, 8),
            date(2027, 2, 9),
            date(2027, 2, 10),
            date(2027, 3, 1),
            date(2027, 5, 5),
            date(2027, 5, 12),
            date(2027, 6, 6),
            date(2027, 8, 16),
            date(2027, 9, 15),
            date(2027, 9, 16),
            date(2027, 9, 17),
            date(2027, 10, 4),
            date(2027, 10, 11),
            date(2027, 12, 31),
        }
    ),
}


@final
class TradingCalendar:
    def is_trading_day(self, value: date) -> bool:
        holidays = KRX_HOLIDAYS.get(value.year)
        if holidays is None:
            raise ValueError(f"unsupported KRX calendar year: {value.year}")
        return value.weekday() < 5 and value not in holidays
