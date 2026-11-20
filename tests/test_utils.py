import os
import sys
import unittest
from datetime import datetime, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import (billable_hours, calculate_fee, next_slot_numbers,
                   normalise_vehicle_no, parse_ticket_ref, valid_vehicle_no)

T0 = datetime(2026, 11, 13, 10, 0, 0)


class BillingTests(unittest.TestCase):
    def test_TC01_under_one_hour_is_one_hour(self):
        self.assertEqual(calculate_fee(T0, T0 + timedelta(minutes=20), 20, 10), (1, Decimal("20.00")))

    def test_TC02_exactly_one_hour(self):
        self.assertEqual(billable_hours(T0, T0 + timedelta(hours=1)), 1)

    def test_TC03_one_hour_one_minute_rounds_up(self):
        self.assertEqual(calculate_fee(T0, T0 + timedelta(hours=1, minutes=1), 20, 10), (2, Decimal("30.00")))

    def test_TC04_overnight_stay(self):
        self.assertEqual(calculate_fee(T0, T0 + timedelta(hours=26), 10, 5), (26, Decimal("135.00")))

    def test_TC05_zero_or_negative_duration_charges_minimum(self):
        self.assertEqual(billable_hours(T0, T0), 1)
        self.assertEqual(billable_hours(T0, T0 - timedelta(minutes=5)), 1)

    def test_TC06_decimal_rates(self):
        self.assertEqual(calculate_fee(T0, T0 + timedelta(hours=3), "12.50", "7.25"), (3, Decimal("27.00")))


class InputTests(unittest.TestCase):
    def test_TC07_vehicle_number_is_normalised(self):
        self.assertEqual(normalise_vehicle_no(" dl 01-ab 1234 "), "DL01AB1234")

    def test_TC08_vehicle_number_validation(self):
        self.assertTrue(valid_vehicle_no("DL01AB1234"))
        self.assertFalse(valid_vehicle_no("AB"))
        self.assertFalse(valid_vehicle_no("DL01@B1234"))

    def test_TC09_slot_numbers_continue_after_highest(self):
        self.assertEqual(next_slot_numbers(["G-2W-01", "G-2W-02", "G-4W-09"], "G", "2W", 2), ["G-2W-03", "G-2W-04"])
        self.assertEqual(next_slot_numbers([], "1", "4W", 1), ["1-4W-01"])

    def test_TC10_ticket_reference_parsing(self):
        self.assertEqual(parse_ticket_ref("T00012"), ("ticket", 12))
        self.assertEqual(parse_ticket_ref("12"), ("ticket", 12))
        self.assertEqual(parse_ticket_ref("dl 01 ab 1234"), ("vehicle", "DL01AB1234"))


if __name__ == "__main__":
    unittest.main()
