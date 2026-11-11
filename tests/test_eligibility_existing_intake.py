"""Regression checks for paid eligibility intake already submitted by a customer.

All records are fabricated. No live WhatsApp, payments, or database writes.
"""
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from scholarship_eligibility_backend import (
    DEFAULT_STAGE, PAGE, academic_reply_evidence, classify_customer_reply,
    get_customer_reply_status, can_move_stage,
)
from scholarship_eligibility_intake import SERVICE

PAID = {
    "lead_id": 17, "service": SERVICE, "status": "PAID",
    "currency": "MWK", "required": Decimal("5000"), "paid": Decimal("5000"),
}

ACADEMIC_REPLIES = [
    "My bachelors degree in Business Management was completed in 2022 in Malawi.",
    "My GPA is 3.1, with 14 years experience in banking as a branch manager.",
    "The course was taught in English. My choices are Finland and the UK.",
]


class FakeCursor:
    def __init__(self, replies):
        self.replies = replies
        self.calls = []
        self.time = datetime(2026, 11, 11, 7, 0, tzinfo=timezone.utc)
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def execute(self, sql, params):
        self.calls.append((sql, params))
        assert sql.strip().startswith("SELECT"), "A status check must never write"
        assert params[0] == "FAKE_CUSTOMER"
    def fetchone(self):
        return self.time, self.time + timedelta(hours=1)
    def fetchall(self):
        return [(m,) for m in self.replies]


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_ = cursor
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def cursor(self):
        return self.cursor_


class ExistingIntakeTests(unittest.TestCase):
    def test_substantive_reply_is_ready_for_human_assessment(self):
        evidence = academic_reply_evidence(ACADEMIC_REPLIES)
        self.assertTrue({"degree", "grade", "experience", "language", "destination"} <= set(evidence))
        t = datetime(2026, 11, 11, tzinfo=timezone.utc)
        title, description, new_reply, ready = classify_customer_reply(
            t, t + timedelta(hours=1), evidence
        )
        self.assertTrue(new_reply)
        self.assertTrue(ready)
        self.assertIn("assessment review required", title)
        self.assertIn("Do not resend", description)
        self.assertNotIn("scholarship is awarded", title.lower())

    def test_existing_paid_answers_are_loaded_without_writes(self):
        cursor = FakeCursor(ACADEMIC_REPLIES)
        title, description, replied, ready = get_customer_reply_status(
            lambda: FakeConnection(cursor), "FAKE_CUSTOMER"
        )
        self.assertTrue(replied)
        self.assertTrue(ready)
        self.assertEqual(len(cursor.calls), 2)
        self.assertIn("created_at>%s", cursor.calls[1][0])
        self.assertIn("assessment review", title)

    def test_a_short_acknowledgment_is_not_intake_completion(self):
        evidence = academic_reply_evidence(["OK", "Thank you"])
        self.assertEqual(evidence, ())
        t = datetime(2026, 11, 11, tzinfo=timezone.utc)
        _, description, replied, ready = classify_customer_reply(t, t + timedelta(seconds=10), evidence)
        self.assertTrue(replied)
        self.assertFalse(ready)
        self.assertIn("Ask only for missing", description)

    def test_no_intake_request_does_not_make_fictitious_progress(self):
        t = datetime(2026, 11, 11, tzinfo=timezone.utc)
        _, _, replied, ready = classify_customer_reply(None, t, ("degree","grade","experience","location"))
        self.assertFalse(replied)
        self.assertFalse(ready)

    def test_one_confirmed_shortcut_to_review_not_delivered(self):
        self.assertTrue(can_move_stage(DEFAULT_STAGE, "REVIEWING", PAID, intake_ready=True))
        self.assertFalse(can_move_stage(DEFAULT_STAGE, "REVIEWING", PAID, intake_ready=False))
        self.assertFalse(can_move_stage(DEFAULT_STAGE, "DELIVERED", PAID, intake_ready=True))
        self.assertFalse(can_move_stage(DEFAULT_STAGE, "REVIEWING", {**PAID, "status":"NOT_PAID"}, intake_ready=True))
        self.assertFalse(can_move_stage("AWAITING_INFORMATION", "DELIVERED", PAID, intake_ready=True))

    def test_admin_page_does_not_send_intake_or_pretend_work_finished(self):
        self.assertIn("{% if intake_ready %}", PAGE)
        self.assertIn("Do not send a second intake questionnaire", PAGE)
        self.assertIn("Confirm this step actually happened", PAGE.replace(
            "I confirm this step actually happened", "Confirm this step actually happened"
        ))
        self.assertNotIn("send_whatsapp_message(", PAGE)


if __name__ == "__main__":
    unittest.main()
