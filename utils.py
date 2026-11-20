"""Pure helper functions (no database, no Flask) so they are easy to unit-test."""
import math
import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

VEHICLE_TYPES = {"2W": "Two-wheeler", "4W": "Four-wheeler"}
_VNO = re.compile(r"^[A-Z0-9]{4,12}$")


def normalise_vehicle_no(raw):
    """'mh 12-ab 1234' -> 'MH12AB1234'."""
    return re.sub(r"[\s-]+", "", raw or "").upper()


def valid_vehicle_no(vno):
    return bool(_VNO.match(vno))


def to_dt(value):
    """Accept a datetime or an ISO-style string and return a datetime."""
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def billable_hours(entry, exit_):
    """Parking time rounded UP to whole hours, minimum 1 hour."""
    seconds = max((exit_ - entry).total_seconds(), 0)
    return max(1, math.ceil(seconds / 3600))


def calculate_fee(entry, exit_, first_hour, extra_hour):
    """Fee = first-hour charge + extra-hour charge for every hour after the first."""
    hours = billable_hours(entry, exit_)
    first, extra = Decimal(str(first_hour)), Decimal(str(extra_hour))
    amount = (first + extra * (hours - 1)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    return hours, amount


def next_slot_numbers(existing_slot_nos, level, slot_type, count):
    """Create `count` new slot numbers like 'G-2W-04' continuing after the highest existing one."""
    prefix = f"{level}-{slot_type}-"
    highest = 0
    for no in existing_slot_nos:
        if no.startswith(prefix) and no[len(prefix):].isdigit():
            highest = max(highest, int(no[len(prefix):]))
    return [f"{prefix}{n:02d}" for n in range(highest + 1, highest + count + 1)]


def parse_ticket_ref(text):
    """'T00012' / '12' -> ('ticket', 12); anything else is treated as a vehicle number."""
    cleaned = (text or "").strip().upper().replace(" ", "")
    m = re.fullmatch(r"T?(\d+)", cleaned)
    if m:
        return "ticket", int(m.group(1))
    return "vehicle", normalise_vehicle_no(text)
