"""Offline privacy and integrity tests for paid-work monitoring dashboard.

No external service, real customer data, credential or production DB call.
"""
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from functools import wraps
import unittest

from backend_operations_health import (
    PAGE, has_new_reply, paid_case_row, read_health,
    install_backend_operations,
)


class FakeCursor:
    def __init__(self,metrics,customers,stages=None,media=(125*1048576,19*1048576),failure=False):
        self.metrics=metrics
        self.customers=customers
        self.stages=stages
        self.media=media
        self.failure=failure
        self.current=""
        self.sql=[]
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,query,params=None):
        if self.failure:
            raise RuntimeError("Simulated read-only DB failure")
        cleaned=" ".join(query.split())
        assert cleaned.startswith("SELECT"),"Dangerous SQL in read-only monitor"
        self.sql.append((cleaned,params))
        self.current=cleaned
    def fetchone(self):
        if self.current.startswith("SELECT (SELECT COUNT(*) FROM leads"):
            return self.metrics
        if self.current.startswith("SELECT to_regclass"):
            return ("scholarship_eligibility_cases",) if self.stages is not None else (None,)
        if self.current.startswith("SELECT pg_total_relation_size"):
            return self.media
        raise AssertionError("Unknown read-one SQL: "+self.current[:120])
    def fetchall(self):
        if self.current.startswith("SELECT l.id,l.customer_name"):
            return self.customers
        if self.current.startswith("SELECT lead_id,stage"):
            return list(self.stages.items())
        raise AssertionError("Unknown read-all SQL: "+self.current[:120])


class FakeConn:
    def __init__(self,cursor):self.cur=cursor
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def cursor(self):return self.cur


METRICS=(1,1,Decimal("5000"),3,4,0,0,0,0,0,0,0)
UTC=timezone.utc
DAY=datetime(2026,11,11,6,0,tzinfo=UTC)
CLIENT_ROW=(
    19,"Example Paid Customer","Scholarship Eligibility Check","NEW",
    Decimal("5000"),Decimal("5000"),DAY,DAY+timedelta(hours=1),
)


class ReadOnlyHealthTests(unittest.TestCase):
    def test_tri_state_does_not_invent_a_reply(self):
        self.assertIsNone(has_new_reply(None,DAY))
        self.assertFalse(has_new_reply(DAY,None))
        self.assertFalse(has_new_reply(DAY,DAY))
        self.assertFalse(has_new_reply(DAY,DAY-timedelta(seconds=1)))
        self.assertTrue(has_new_reply(DAY,DAY+timedelta(seconds=1)))

    def test_paid_case_status_does_not_mark_work_completed(self):
        case=paid_case_row(CLIENT_ROW,None)
        self.assertTrue(case["needs_review"])
        self.assertFalse(case["waiting"])
        self.assertEqual(case["stage"],"Not yet recorded")
        self.assertEqual(case["enquiry_status"],"NEW")
        self.assertEqual(case["paid_mwk"],Decimal("5000"))
        case=paid_case_row(CLIENT_ROW,"REVIEWING")
        self.assertEqual(case["stage"],"REVIEWING")
        self.assertTrue(case["needs_review"])

    def test_complete_dashboard_uses_only_selects_and_is_private(self):
        cur=FakeCursor(METRICS,[CLIENT_ROW])
        result=read_health(lambda:FakeConn(cur))
        self.assertEqual(result["totals"]["verified_mwk"],Decimal("5000"))
        self.assertEqual(result["totals"]["agro_approved"],3)
        self.assertEqual(result["totals"]["receipt_issues"],0)
        self.assertEqual(result["media"]["website_mb"],125)
        self.assertEqual(result["media"]["construction_mb"],19)
        self.assertTrue(result["paid_cases"][0]["needs_review"])
        self.assertEqual(result["paid_cases"][0]["stage"],"Not yet recorded")
        self.assertTrue(all(sql.startswith("SELECT") for sql,params in cur.sql))
        self.assertEqual(len(cur.sql),4)
        self.assertNotIn("UPDATE leads",str(cur.sql))
        self.assertIn("processed_whatsapp_messages",cur.sql[0][0])
        self.assertIn("agro_marketplace_listings",cur.sql[0][0])
        self.assertIn("lead_payments",cur.sql[0][0])

    def test_existing_stage_displayed_but_not_changed(self):
        cur=FakeCursor(METRICS,[CLIENT_ROW],stages={19:"AWAITING_INFORMATION"})
        res=read_health(lambda:FakeConn(cur))
        self.assertEqual(res["paid_cases"][0]["stage"],"AWAITING_INFORMATION")
        self.assertEqual(len(cur.sql),5)
        self.assertEqual(cur.sql[-2][1],([19],))

    def test_null_intake_never_falsely_says_waiting(self):
        row=list(CLIENT_ROW);row[6]=None
        c=paid_case_row(tuple(row))
        self.assertFalse(c["needs_review"])
        self.assertFalse(c["waiting"])

    def test_503_for_unavailable_db_and_no_false_healthy_claim(self):
        from flask import Flask,abort,request
        app=Flask("private-backend-audit")
        def admin_required(fn):
            @wraps(fn)
            def wrapped(*args,**kwargs):
                if request.headers.get("X-TEST-ADMIN")!="yes":
                    abort(403)
                return fn(*args,**kwargs)
            return wrapped
        ns={"get_db":lambda:FakeConn(FakeCursor(METRICS,[],failure=True)),
            "admin_required":admin_required,
            "DASHBOARD_TEMPLATE":"<h2>Sales pipeline</h2>"}
        exec("def admin_leads():\n    return 'ok'\n",ns)
        app.add_url_rule("/admin/leads",endpoint="admin_leads",view_func=ns["admin_leads"])
        app.add_url_rule("/admin/inbox",endpoint="admin_inbox",view_func=lambda:"inbox")
        app.add_url_rule("/admin/eligibility/<int:lead_id>",endpoint="admin_eligibility_case",view_func=lambda lead_id:"eligibility")
        app.add_url_rule("/admin/receipts",endpoint="admin_auto_receipts",view_func=lambda:"receipts")
        self.assertTrue(install_backend_operations(app))
        self.assertTrue(install_backend_operations(app))
        with app.test_client() as client:
            unauth=client.get("/admin/backend-health")
            self.assertEqual(unauth.status_code,403)
            auth=client.get("/admin/backend-health",headers={"X-TEST-ADMIN":"yes"})
            self.assertEqual(auth.status_code,503)
            self.assertNotIn(b"All healthy",auth.data)
            self.assertEqual(auth.headers["Cache-Control"],"private, no-store, max-age=0")
            self.assertEqual(auth.headers["X-Robots-Tag"],"noindex, nofollow")
        self.assertIn("ibrows-backend-health-nav",ns["DASHBOARD_TEMPLATE"])
        self.assertNotIn("pay customer",ns["DASHBOARD_TEMPLATE"])

    def test_private_admin_page_renders_only_safe_metadata(self):
        from jinja2 import Environment
        Environment(autoescape=True).parse(PAGE)
        self.assertIn("Customer reply needs review",PAGE.replace("New customer reply needs review","Customer reply needs review"))
        self.assertIn("Read-only system checks",PAGE)
        self.assertIn("No records are changed",PAGE)
        self.assertNotIn("customer_number",PAGE)
        self.assertNotIn("api_key",PAGE)
        self.assertNotIn("DELETE FROM",PAGE)


if __name__=="__main__":
    unittest.main()
