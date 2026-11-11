"""Offline authorisation and idempotency for one-time receipt #10.

Tests contain no customer phone numbers, passwords, real payment methods or
actual WhatsApp message sends.
"""
import unittest
from decimal import Decimal
from unittest.mock import patch
from flask import Flask
from ops_martha_receipt_once import (
    matches_authorised_payment,authorised_receipt_record,
    send_one_off_martha_receipt,LEAD_ID,PAYMENT_ID,
)


GOOD=(
    19,10,"Scholarship Eligibility Check",Decimal("5000"),"MWK",
    "MOBILE_MONEY",Decimal("5000"),"MWK",None,None,0,1
)


class FakeCursor:
    def __init__(self,row):self.row=row;self.query=None;self.params=None
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def execute(self,q,args):self.query=q;self.params=args
    def fetchone(self):return self.row


class FakeConn:
    def __init__(self,row):self.cur=FakeCursor(row)
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def cursor(self):return self.cur


class AuthorisedReceiptTests(unittest.TestCase):
    def test_only_exact_existing_payment_can_be_sent(self):
        self.assertTrue(matches_authorised_payment(GOOD))
        for index,bad in [
            (0,18),(1,11),(2,"Scholarship Search"),
            (3,Decimal("6000")),(4,"USD"),(5,"CASH"),
            (6,Decimal("15000")),(7,"EUR"),(8,19),
            (9,"deleted"),(10,1),(11,2)
        ]:
            with self.subTest(index=index):
                row=list(GOOD);row[index]=bad
                self.assertFalse(matches_authorised_payment(tuple(row)))
        self.assertFalse(matches_authorised_payment(None))
        self.assertFalse(matches_authorised_payment(("bad",)))

    def test_query_is_read_only_and_checks_prior_send(self):
        db=FakeConn(GOOD)
        self.assertTrue(authorised_receipt_record(lambda:db))
        self.assertEqual(db.cur.params,(19,10))
        self.assertIn("business_documents",db.cur.query)
        self.assertIn("d.last_sent_at IS NOT NULL",db.cur.query)
        self.assertIn("lead_payments",db.cur.query)
        self.assertFalse("INSERT " in db.cur.query or "UPDATE " in db.cur.query)

    def make_app(self):
        app=Flask("one-time-send-test")
        ns={"get_db":lambda:FakeConn(GOOD)}
        exec("def admin_leads():\n  return 'ok'\n",ns)
        app.add_url_rule("/admin/leads",endpoint="admin_leads",view_func=ns["admin_leads"])
        return app

    def test_exactly_one_attempt_after_claim(self):
        app=self.make_app()
        with patch("automatic_verified_receipts._queue_new_payment",return_value=True) as claim,\
             patch("automatic_verified_receipts._attempt_delivery",return_value="ACCEPTED") as deliver:
            result=send_one_off_martha_receipt(app)
        self.assertEqual(result,"ACCEPTED")
        claim.assert_called_once()
        self.assertEqual(claim.call_args.args[1:],(LEAD_ID,PAYMENT_ID))
        deliver.assert_called_once()
        self.assertEqual(deliver.call_args.args[1],PAYMENT_ID)

    def test_prior_claim_never_sends_again(self):
        app=self.make_app()
        with patch("automatic_verified_receipts._queue_new_payment",return_value=False) as claim,\
             patch("automatic_verified_receipts._attempt_delivery") as deliver:
            self.assertEqual(send_one_off_martha_receipt(app),"ALREADY_CLAIMED")
        claim.assert_called_once()
        deliver.assert_not_called()

    def test_missing_or_invalid_payment_never_claims_receipt(self):
        app=self.make_app()
        with patch("ops_martha_receipt_once.authorised_receipt_record",return_value=False),\
             patch("automatic_verified_receipts._queue_new_payment") as claim,\
             patch("automatic_verified_receipts._attempt_delivery") as deliver:
            self.assertEqual(send_one_off_martha_receipt(app),"SAFE_SKIP")
        claim.assert_not_called()
        deliver.assert_not_called()

    def test_nonmatching_customer_is_unaffected(self):
        app=self.make_app()
        with patch("ops_martha_receipt_once.authorised_receipt_record",return_value=False),\
             patch("automatic_verified_receipts._queue_new_payment") as claim:
            self.assertEqual(send_one_off_martha_receipt(app),"SAFE_SKIP")
        claim.assert_not_called()


if __name__=="__main__":
    unittest.main()
