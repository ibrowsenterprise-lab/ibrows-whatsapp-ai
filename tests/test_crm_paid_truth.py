"""Regression tests: paid CRM display derives from verified ledger, not AI notes."""
import re
import unittest
from decimal import Decimal
from pathlib import Path
from jinja2 import Environment
from crm_paid_truth import (
    current_paid_summary,current_paid_reason,improve_paid_leads_template,
    improve_paid_customer_template,unpaid_open_value,
)
from crm_paid_note_cleanup import (
    OLD_PAYMENT_CLAUSE,OLD_REASON,NEW_PAYMENT_CLAUSE,correction_is_safe
)
from crm_quality import improve_crm_template

SOURCE=Path(__file__).resolve().parents[1].joinpath("app.py").read_text("utf-8")
def get_template(name):
    match=re.search(r'^'+re.escape(name)+r'\s*=\s*"""(.*?)"""',SOURCE,re.S|re.M)
    assert match, "source template not found "+name
    return match.group(1)

class PaymentTruthTests(unittest.TestCase):
    def test_stale_not_paid_phrase_suppressed_only_for_ledger_paid(self):
        old="Study in Europe. "+OLD_PAYMENT_CLAUSE
        self.assertEqual(current_paid_summary(old,"NOT_PAID"),old)
        self.assertEqual(current_paid_summary(old,"PART_PAID"),old)
        new=current_paid_summary(old,"PAID")
        self.assertNotIn("NOT_PAID",new)
        self.assertIn("Study in Europe",new)
        self.assertIn("They sent an Airtel payment screenshot",new)
        self.assertEqual(current_paid_summary("No issue", "PAID"),"No issue")

    def test_payment_verification_reason_replaced_with_real_next_step(self):
        self.assertEqual(current_paid_reason(OLD_REASON,"NOT_PAID","Scholarship Eligibility Check"),OLD_REASON)
        self.assertIn("Payment verified", current_paid_reason(OLD_REASON,"PAID","Scholarship Eligibility Check"))
        self.assertIn("eligibility assessment", current_paid_reason(OLD_REASON,"PAID","Scholarship Eligibility Check"))
        self.assertEqual(current_paid_reason("Customer expects a callback","PAID","Scholarship Eligibility Check"),
                         "Customer expects a callback")
        self.assertEqual(current_paid_reason(OLD_REASON,"PAID","Website development"),OLD_REASON)

    def test_leads_template_shows_paid_workflow_and_unpaid_balance_correctly(self):
        original=get_template("DASHBOARD_TEMPLATE")
        updated=improve_paid_leads_template(original)
        self.assertEqual(improve_paid_leads_template(updated),updated)
        self.assertIn("Unpaid value on open enquiries",updated)
        self.assertIn("Payment confirmed — eligibility assessment awaiting completion",updated)
        self.assertIn("No quotation or second payment required",updated)
        self.assertIn("ibrows_current_paid_summary",updated)
        self.assertIn("ibrows_current_paid_reason",updated)
        self.assertIn("csrf_token",updated)
        self.assertNotIn("<div class=\"pipe-title\">Open estimated value</div>",updated)
        env=Environment(autoescape=True)
        env.filters["ibrows_current_paid_summary"]=current_paid_summary
        env.filters["ibrows_current_paid_reason"]=current_paid_reason
        env.parse(updated)

    def test_customer_history_shows_current_paid_note(self):
        original=improve_crm_template(get_template("CUSTOMER_CRM_TEMPLATE"))
        updated=improve_paid_customer_template(original)
        self.assertEqual(improve_paid_customer_template(updated),updated)
        self.assertIn("ibrows_current_paid_summary",updated)
        env=Environment(autoescape=True)
        env.filters["ibrows_current_paid_summary"]=current_paid_summary
        env.parse(updated)

    def test_unpaid_open_balances_are_net_of_same_currency_receipts(self):
        class FakeCur:
            def __enter__(self):return self
            def __exit__(self,*a):return False
            def execute(self,q):
                self.query=q
            def fetchall(self):
                return [
                    (19,"MWK",Decimal("5000"),Decimal("5000")),
                    (21,"MWK",Decimal("15000"),Decimal("10000")),
                    (22,"USD",Decimal("100"),Decimal("25")),
                    (23,"MWK",Decimal("4000"),Decimal("6000")),
                ]
        class FakeConn:
            def __enter__(self):return self
            def __exit__(self,*a):return False
            def cursor(self):return FakeCur()
        result=unpaid_open_value(
            lambda:{"open":[{"label":"OLD"}],"received":[{"label":"MWK 21,000"}],
                    "accepted":[],"sent":[],"outstanding":[]},
            lambda:FakeConn(),
            lambda b:[{"currency":k,"amount":v} for k,v in sorted(b.items())],
        )
        self.assertEqual(result["open"],[
            {"currency":"MWK","amount":Decimal("5000")},
            {"currency":"USD","amount":Decimal("75")},
        ])
        self.assertEqual(result["received"],[{"label":"MWK 21,000"}])

    def test_one_time_repair_requires_exact_ledger_receipt_and_note(self):
        lead=(
            19,"Scholarship Eligibility Check",
            "Customer wishes to study in Europe. "+OLD_PAYMENT_CLAUSE,
            OLD_REASON,Decimal("5000"),"MWK","NEW",None,None,
        )
        receipt=(1,Decimal("5000"),"MWK")
        self.assertTrue(correction_is_safe(lead,receipt))
        for bad_receipt in [
            (0,Decimal("0"),"MWK"),(2,Decimal("5000"),"MWK"),
            (1,Decimal("5000"),"USD"),(1,Decimal("6000"),"MWK")
        ]:
            self.assertFalse(correction_is_safe(lead,bad_receipt))
        bad=list(lead);bad[3]="Service already handled"
        self.assertFalse(correction_is_safe(tuple(bad),receipt))
        bad=list(lead);bad[0]=18
        self.assertFalse(correction_is_safe(tuple(bad),receipt))
        self.assertIn("corresponding MK5,000 payment",NEW_PAYMENT_CLAUSE)
        self.assertFalse(correction_is_safe(None,receipt))

if __name__=="__main__":unittest.main()
