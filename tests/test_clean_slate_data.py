"""Offline production cleanup guard tests. No DB access and no network."""
from decimal import Decimal
import inspect
import unittest

import clean_slate_data as c


def baseline():
    return {
        "real_lead":(19,"Scholarship Eligibility Check",Decimal("5000"),"MWK"),
        "real_payment":(1,Decimal("5000"),"MWK"),
        "demo_lead_ids":list(range(1,19)),
        "demo_lead_names":["old test business","test team"],
        "demo_payment":(5,Decimal("62000")),
        "project_ids":[2,7],
        "project_finance":(2,Decimal("3425000"),2,Decimal("3000000")),
        "website_demo_ids":[1,2,3,4,5],
        "agro_request_ids":[8,9,10,11],
        "agro_listing_ids":[1,436,437],
        "agro_rice_source_count":2,
        "unanticipated_recent_demo_payment":0,
    }


class CleanSlateGuards(unittest.TestCase):
    def test_current_inspected_baseline_is_eligible(self):
        self.assertTrue(c.validate_clean_slate_snapshot(baseline()))

    def test_wrong_real_customer_finance_aborts(self):
        wrong=[
            ("real_lead",(19,"Scholarship Search",Decimal("5000"),"MWK")),
            ("real_lead",(19,"Scholarship Eligibility Check",Decimal("60000"),"MWK")),
            ("real_payment",(0,Decimal("0"),"MWK")),
            ("real_payment",(2,Decimal("5000"),"MWK")),
            ("real_payment",(1,Decimal("5000"),"USD")),
        ]
        for name,value in wrong:
            with self.subTest(name=name,value=value):
                s=baseline();s[name]=value
                self.assertFalse(c.validate_clean_slate_snapshot(s))

    def test_no_cleanup_if_agriculture_supply_chain_mismatches(self):
        for name,val in [
            ("agro_request_ids",[8,9,10]),
            ("agro_listing_ids",[1,436]),
            ("agro_rice_source_count",1),
        ]:
            with self.subTest(name=name):
                s=baseline();s[name]=val
                self.assertFalse(c.validate_clean_slate_snapshot(s))

    def test_wrong_fake_ledger_or_projects_must_abort(self):
        for name,val in [
            ("demo_lead_ids",[1,2,3]),
            ("demo_payment",(5,Decimal("67000"))),
            ("demo_payment",(6,Decimal("62000"))),
            ("project_ids",[2]),
            ("project_finance",(2,Decimal("3425000"),3,Decimal("3000000"))),
            ("website_demo_ids",[1,2,3,4]),
            ("unanticipated_recent_demo_payment",1),
        ]:
            with self.subTest(name=name):
                s=baseline();s[name]=val
                self.assertFalse(c.validate_clean_slate_snapshot(s))

    def test_archive_financial_and_project_proof_before_cascade(self):
        kinds={name:label for name,where,params,label in c.ARCHIVE_TABLES}
        for table in (
            "lead_payments","payment_void_audit","business_documents",
            "project_invoices","project_sandbox_payments",
            "project_quotations","leads","project_assessments"
        ):
            self.assertIn(table,kinds)
        self.assertEqual(kinds["lead_payments"],"DEMO_PAYMENT_NOT_REVENUE")
        self.assertEqual(kinds["project_invoices"],"DEMO_UNPAID_INVOICE_NOT_RECEIVABLE")

    def test_never_clear_site_media_products_or_agriculture(self):
        source=inspect.getsource(c.run_clean_slate_once)
        for table in c.PROTECTED_TABLES:
            self.assertNotIn('DELETE FROM '+table,source)
        self.assertIn("REAL_LEAD_ID",source)
        self.assertIn("MARTHA_CHAT_START" if hasattr(c,"MARTHA_CHAT_START")
                      else "VERIFIED_CUSTOMER_CHAT_START",source)
        self.assertNotIn("TRUNCATE",source)
        self.assertNotIn("DROP TABLE",source)

    def test_sandbox_key_and_upload_payload_do_not_break_archiving(self):
        class FakeCursor:
            rowcount=1
            def execute(self,query,params):
                self.sql=query
                self.params=params
        cur=FakeCursor()
        result=c._archive(cur,"project_sandbox_state",
                         "l.project_id = ANY(%s)",([2,7],),"TEST")
        self.assertEqual(result,1)
        self.assertIn("l.project_id::text",cur.sql)
        c._archive(cur,"website_service_request_files",
                   "l.request_id=ANY(%s)",([1,2],),"TEST")
        self.assertIn("to_jsonb(l) - 'file_bytes'",cur.sql)

    def test_missing_runtime_db_never_mutates(self):
        self.assertFalse(c.run_clean_slate_once(None))

if __name__=="__main__":
    unittest.main()
