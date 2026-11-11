"""Offline regression to ensure AI uses correct paid-package ledger status."""
import ast
import unittest
from decimal import Decimal
from pathlib import Path
from scholarship_payment_context import scholarship_payment_context_lines

APP=Path(__file__).resolve().parents[1]/"app.py"

class ContextTests(unittest.TestCase):
    def test_verified_one_off_context_fetches_correct_service(self):
        source=APP.read_text("utf-8")
        tree=ast.parse(source)
        func=next(n for n in tree.body if isinstance(n,ast.FunctionDef)
                  and n.name=="build_verified_payment_context")
        ns={"CAREER_SERVICE_DEFAULT_PRICES_MWK":{},
            "expire_career_assist_entitlements":lambda n:None,
            "get_career_assist_lifecycle_state":lambda n:{"state":"NOT_PAID"},
            "get_career_assist_standing_consent":lambda n:{},
           }
        seen=[]
        def getter(number,service,*rest):
            seen.append((number,service,rest))
            return {"lead_id":19,"status":"PAID","service":service,
                    "currency":"MWK","required":Decimal("5000"),
                    "paid":Decimal("5000"),"balance":Decimal("0")}
        ns["get_verified_service_payment_state"]=getter
        exec(compile(ast.Module(body=[func],type_ignores=[]),str(APP),"exec"),ns)
        out=ns["build_verified_payment_context"]("265999001234")
        msg=out[0]["content"]
        self.assertEqual(seen,[("265999001234","Scholarship Eligibility Check",(5000,))])
        self.assertIn("SCHOLARSHIP SERVICE PAYMENT VERIFIED",msg)
        self.assertIn("Scholarship Eligibility Check",msg)
        self.assertNotIn("Scholarship Search (this customer's open lead)",msg)

    def test_no_false_paid_claims_for_wrong_scope_or_ledger(self):
        for state in [
            None,
            {"lead_id":None,"status":"NOT_VERIFIED"},
            {"lead_id":19,"service":"Scholarship Eligibility Check",
             "status":"NOT_PAID","currency":"MWK",
             "required":Decimal("5000"),"paid":Decimal("0")},
        ]:
            msg="\n".join(scholarship_payment_context_lines(state))
            self.assertNotIn("SCHOLARSHIP SERVICE PAYMENT VERIFIED",msg)

if __name__=="__main__":unittest.main()
