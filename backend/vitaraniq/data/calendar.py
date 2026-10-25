"""
Synthetic Calendar generation for VitaranIQ.
Covers days 1 to 740 starting from 2024-11-01.
Includes 12 festival windows per year and official public holidays.
"""

from datetime import date, timedelta
from typing import Dict, List, Tuple


START_DATE = date(2024, 11, 1)  # Day 1

# Fixed festival definitions per year (month, day, duration_days, name)
FESTIVALS = [
    (1, 14, 3, "Makar Sankranti"),
    (3, 18, 3, "Holi"),
    (4, 2, 2, "Gudi Padwa"),
    (4, 20, 3, "Eid"),
    (8, 19, 2, "Raksha Bandhan"),
    (8, 28, 5, "Ganesh Chaturthi"),
    (10, 10, 4, "Navratri"),
    (10, 22, 2, "Dussehra"),
    (11, 1, 5, "Diwali"),
    (12, 24, 3, "Christmas"),
    (12, 31, 2, "New Year"),
]

PUBLIC_HOLIDAYS = [
    (1, 26, "Republic Day"),
    (8, 15, "Independence Day"),
    (10, 2, "Gandhi Jayanti"),
    (12, 25, "Christmas Day"),
]


def generate_calendar_days(n_days: int = 740) -> List[Dict]:
    """Generate calendar records for days 1 to n_days."""
    records = []
    
    # Precompute holiday & festival lookup
    for day_idx in range(1, n_days + 1):
        cur_date = START_DATE + timedelta(days=day_idx - 1)
        m = cur_date.month
        d = cur_date.day
        dow = cur_date.weekday()  # 0 = Monday, 6 = Sunday

        is_holiday = 0
        is_festival = 0
        festival_name = None

        # Check public holidays
        for h_m, h_d, h_name in PUBLIC_HOLIDAYS:
            if m == h_m and d == h_d:
                is_holiday = 1
                festival_name = h_name
                break

        # Check festival windows
        for f_m, f_d, f_dur, f_name in FESTIVALS:
            # Check if cur_date falls in [f_date, f_date + f_dur - 1]
            try:
                f_start = date(cur_date.year, f_m, f_d)
                f_end = f_start + timedelta(days=f_dur - 1)
                if f_start <= cur_date <= f_end:
                    is_festival = 1
                    festival_name = f_name
                    break
            except ValueError:
                pass

        records.append({
            "day": day_idx,
            "date": cur_date.isoformat(),
            "dow": dow,
            "month": m,
            "is_holiday": is_holiday,
            "is_festival": is_festival,
            "festival_name": festival_name,
        })

    return records
