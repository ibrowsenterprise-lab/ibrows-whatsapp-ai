"""Paid-service query efficiency tests. Offline: no credentials, customer data or writes."""
import unittest
from decimal import Decimal

from payment_query_efficiency import (
    SQL_ACTIVE_LEADS, fetch_ledger_rows, state_from_ledger_rows,
    install_payment_query_batch,
)

def canon(value):
    return str(value or "").strip().casefold()

ROWS = [
    (19, "Scholarship Eligibility Check", Decimal("5000"), "MWK", "NOT_STARTED",
     "NEW", None, Decimal("5000")),
    (20, "CV & Cover Letter", Decimal("7500"), "MWK", None, "NEW", None, Decimal("7500")),
    (21, "Single Job Application", Decimal("3000"), "MWK", "DRAFT", "NEW", None, Decimal("1000")),
    (22, "Other USD Service", None, "USD", "NOT_STARTED", "NEW", None, Decimal("15")),
]
class FakeCursor:
    def __init__(self, tracker):
        self.tracker = tracker
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def execute(self, sql, args):
        self.tracker["sql_calls"] += 1
        self.tracker["sql"].append((sql, args))
        assert sql.strip().startswith("SELECT")
        assert args == (self.tracker["active_customer"],)
    def fetchall(self):
        return self.tracker["rows"]

class FakeConn:
    def __init__(self, tracker):
        self.tracker = tracker
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def cursor(self):
        return FakeCursor(self.tracker)

class PaymentBatchTests(unittest.TestCase):
    def test_exact_payment_semantics_are_preserved(self):
        paid = state_from_ledger_rows(ROWS,"Scholarship Eligibility Check",5000,canon)
        self.assertEqual(paid["status"],"PAID")
        self.assertEqual(paid["lead_id"],19)
        self.assertEqual(paid["paid"],Decimal("5000"))
        self.assertEqual(paid["balance"],Decimal("0"))
        self.assertEqual(state_from_ledger_rows(
            ROWS,"Single Job Application",3000,canon)["status"],"PART_PAID")
        self.assertEqual(state_from_ledger_rows(
            ROWS,"Single Job Application",3000,canon)["balance"],Decimal("2000"))
        unpaid = state_from_ledger_rows(ROWS,"Career Assist",60000,canon)
        self.assertEqual(unpaid["status"],"NOT_VERIFIED")
        self.assertIsNone(unpaid["lead_id"])
        self.assertEqual(unpaid["required"],Decimal("60000"))
        self.assertEqual(unpaid["paid"],Decimal("0"))
        self.assertEqual(state_from_ledger_rows(
            ROWS,"Other USD Service",5000,canon)["status"],"RECEIVED_UNPRICED")
        self.assertIsNone(state_from_ledger_rows(
            ROWS,"Other USD Service",5000,canon)["required"])

    def test_query_only_reads_active_ledgers_with_currency_gating(self):
        self.assertIn("p.currency = COALESCE(l.value_currency, 'MWK')", SQL_ACTIVE_LEADS)
        self.assertIn("l.entitlement_consumed_at IS NULL", SQL_ACTIVE_LEADS)
        self.assertIn("l.privacy_deleted_at IS NULL", SQL_ACTIVE_LEADS)
        self.assertIn("l.merged_into_lead_id IS NULL", SQL_ACTIVE_LEADS)
        self.assertIn("l.status IN ('NEW', 'CONTACTED')", SQL_ACTIVE_LEADS)
        self.assertNotIn("UPDATE ",SQL_ACTIVE_LEADS.upper())
        self.assertNotIn("INSERT ",SQL_ACTIVE_LEADS.upper())
        self.assertNotIn("DELETE ",SQL_ACTIVE_LEADS.upper())

    def test_one_read_for_multiple_payment_checks_and_no_cross_customer_cache(self):
        from flask import Flask
        app=Flask("offline-batch-test")
        tracker={"active_customer":"client-one", "rows":ROWS,
                 "sql_calls":0, "sql":[], "fallback_calls":[]}
        def db_factory():
            return FakeConn(tracker)
        def original_lookup(number, service, amount=None):
            tracker["fallback_calls"].append((number,service))
            return {"status":"NOT_VERIFIED","lead_id":None}
        ns={
            "get_db":db_factory,
            "canonicalize_service":canon,
            "get_verified_service_payment_state":original_lookup,
        }
        exec(
            "def build_verified_payment_context(number):\n"
            "  return [get_verified_service_payment_state(number, name, price) for name,price in [\n"
            "    ('Scholarship Eligibility Check',5000),\n"
            "    ('Single Job Application',3000),('CV & Cover Letter',7500),\n"
            "    ('Career Assist',60000),('Other USD Service',5000)]]\n"
            "def admin_leads(): return 'ok'\n",
            ns
        )
        app.add_url_rule("/admin/leads",endpoint="admin_leads",view_func=ns["admin_leads"])
        self.assertTrue(install_payment_query_batch(app))
        self.assertTrue(install_payment_query_batch(app))
        with app.test_request_context("/webhook",method="POST"):
            result=ns["build_verified_payment_context"]("client-one")
            self.assertEqual(tracker["sql_calls"],1)
            self.assertEqual([x["status"] for x in result],[
                "PAID","PART_PAID","PAID","NOT_VERIFIED","RECEIVED_UNPRICED"
            ])
            # Separate invocations must not share a stale snapshot.
            ns["build_verified_payment_context"]("client-one")
            self.assertEqual(tracker["sql_calls"],2)
        self.assertEqual(tracker["fallback_calls"],[])
        tracker["active_customer"]="client-two"
        tracker["rows"]=[]
        with app.test_request_context("/webhook",method="POST"):
            result=ns["build_verified_payment_context"]("client-two")
            self.assertEqual(tracker["sql_calls"],3)
            self.assertTrue(all(x["status"]=="NOT_VERIFIED" for x in result))
        with app.test_request_context("/admin/leads",method="GET"):
            ns["build_verified_payment_context"]("client-two")
        self.assertEqual(len(tracker["fallback_calls"]),5)
        self.assertEqual(tracker["sql_calls"],3)

    def test_invalid_context_does_not_start_a_cache(self):
        from flask import Flask
        app=Flask("inactive-batch-test")
        ns={
            "get_db":lambda: None, "canonicalize_service":canon,
            "get_verified_service_payment_state":lambda n,s,p=None: {"status":"NOT_VERIFIED"}
        }
        exec("def build_verified_payment_context(number):\n"
             "  return get_verified_service_payment_state(number,'CV & Cover Letter',7500)\n"
             "def admin_leads(): return 'ok'\n",ns)
        app.add_url_rule("/admin/leads",endpoint="admin_leads",view_func=ns["admin_leads"])
        self.assertTrue(install_payment_query_batch(app))
        with app.test_request_context("/webhook",method="GET"):
            self.assertEqual(ns["build_verified_payment_context"]("a")["status"],"NOT_VERIFIED")

if __name__=="__main__":
    unittest.main()
