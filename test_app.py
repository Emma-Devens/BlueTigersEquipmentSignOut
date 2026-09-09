import unittest
from datetime import datetime
from unittest.mock import patch

import app


class StatusForTests(unittest.TestCase):
    def test_claimed_return_takes_precedence_over_pickup_state(self):
        record = {
            "staff_confirmed": False,
            "return_claimed": True,
            "picked_up": False,
            "return_date": app.today_iso(),
        }

        self.assertEqual(app.status_for(record), "pending-review")

    def test_unclaimed_record_not_picked_up_still_waits_for_pickup(self):
        record = {
            "staff_confirmed": False,
            "return_claimed": False,
            "picked_up": False,
            "return_date": app.today_iso(),
            "pickup_date": "2099-01-01",
        }

        self.assertEqual(app.status_for(record), "waiting-pickup")

    def test_pickup_checkbox_moves_record_to_currently_out(self):
        record = {
            "staff_confirmed": False,
            "return_claimed": False,
            "picked_up": True,
            "pickup_date": "2099-01-01",
            "return_date": "2099-01-02",
        }

        self.assertEqual(app.status_for(record), "checked-out")

    @patch("app.now", return_value=datetime(2026, 9, 9, 8, 0, 0))
    def test_record_moves_to_currently_out_at_pickup_time(self, _mock_now):
        record = {
            "staff_confirmed": False,
            "return_claimed": False,
            "picked_up": False,
            "pickup_date": "2026-09-09",
            "return_date": "2026-09-10",
        }

        self.assertEqual(app.status_for(record), "checked-out")

    def test_google_sheets_false_strings_are_false(self):
        record = {
            "staff_confirmed": "FALSE",
            "return_claimed": "TRUE",
            "picked_up": "TRUE",
            "return_date": app.today_iso(),
        }

        self.assertEqual(app.status_for(record), "pending-review")

    def test_staff_confirmation_moves_pending_return_to_returned(self):
        record = {
            "staff_confirmed": "TRUE",
            "return_claimed": "TRUE",
            "picked_up": "TRUE",
            "return_date": app.today_iso(),
        }

        self.assertEqual(app.status_for(record), "returned")


class AdminPageTests(unittest.TestCase):
    @patch("app.load_records", return_value=[])
    def test_currently_out_appears_before_equipment_returned(self, _mock_load):
        page = app.admin_page().decode("utf-8")

        self.assertLess(
            page.index('<section id="out"'),
            page.index('<section id="returned"'),
        )


if __name__ == "__main__":
    unittest.main()
