"""Offline customer-reply detection for paid eligibility cases.

No real customer messages, external APIs, or production DB access used.
"""
from datetime import datetime, timezone, timedelta
import unittest
from scholarship_eligibility_backend import (
    classify_customer_reply, get_customer_reply_status, PAGE,
)

UTC=timezone.utc
def moment(day,hour):return datetime(2026,11,day,hour,0,tzinfo=UTC)


class FakeCursor:
    def __init__(self,row,raises=False):
        self.row=row
        self.raises=raises
        self.sql=""
        self.args=None
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def execute(self,sql,args):
        if self.raises:raise RuntimeError("DB error")
        self.sql=sql;self.args=args
    def fetchone(self):return self.row


class FakeConn:
    def __init__(self,cursor):self.cur=cursor
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def cursor(self):return self.cur


class PaidCustomerReplyTests(unittest.TestCase):
    def test_no_claim_that_existing_outbound_has_been_delivered(self):
        title,description,new=classify_customer_reply(moment(11,1),moment(10,19))
        self.assertEqual(title,"Waiting for the customer's response")
        self.assertFalse(new)
        self.assertIn("not independently confirmed",description)

    def test_new_reply_is_not_misclassified_as_academic_documents(self):
        title,description,new=classify_customer_reply(moment(11,1),moment(11,4))
        self.assertTrue(new)
        self.assertIn("New customer reply",title)
        self.assertIn("read the reply",description)
        self.assertIn("Only mark details received",description)

    def test_no_intake_record_never_means_no_customer_reply(self):
        title,description,new=classify_customer_reply(None,moment(11,5))
        self.assertFalse(new)
        self.assertIn("No academic intake",title)
        self.assertIn("Copying a message is not the same as sending",description)

    def test_reply_at_same_time_not_a_new_one(self):
        self.assertFalse(classify_customer_reply(moment(11,3),moment(11,3))[2])

    def test_reader_keys_both_queries_to_matching_customer(self):
        c=FakeCursor((moment(11,1),moment(11,5)))
        title,desc,needs_review=get_customer_reply_status(lambda:FakeConn(c),"265999000111")
        self.assertTrue(needs_review)
        self.assertEqual(c.args[0],"265999000111")
        self.assertEqual(c.args[3],"265999000111")
        self.assertIn("role='assistant'",c.sql)
        self.assertIn("role='user'",c.sql)
        self.assertIn("MAX(created_at)",c.sql)
        self.assertIn("Your MK5,000 Scholarship Eligibility Check payment is confirmed",c.args)
        self.assertIn("IBROWS Enterprise 🎓 | Scholarship Eligibility Check",c.args)

    def test_database_outage_is_unknown_never_false_no_reply(self):
        c=FakeCursor(None,raises=True)
        title,desc,needs_review=get_customer_reply_status(lambda:FakeConn(c),"265999000111")
        self.assertEqual(title,"Reply status temporarily unavailable")
        self.assertFalse(needs_review)
        self.assertIn("Inbox",desc)

    def test_mobile_admin_only_panel_and_no_auto_completion(self):
        from jinja2 import Environment
        Environment(autoescape=True).parse(PAGE)
        self.assertIn("Customer reply tracker",PAGE)
        self.assertIn("Read latest customer messages",PAGE)
        self.assertIn("Refresh this page",PAGE)
        self.assertIn("confirm_action",PAGE)
        self.assertNotIn("send_whatsapp_message(",PAGE)

if __name__=="__main__":
    unittest.main()
