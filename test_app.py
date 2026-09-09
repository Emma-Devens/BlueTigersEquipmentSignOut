import unittest

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
        }

        self.assertEqual(app.status_for(record), "waiting-pickup")

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


if __name__ == "__main__":
    unittest.main()
