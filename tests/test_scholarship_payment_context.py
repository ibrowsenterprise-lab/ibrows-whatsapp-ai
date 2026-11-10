"""Scholarship payment context must be based solely on authenticated ledger."""
import ast
import unittest
from decimal import Decimal
from pathlib import Path
from scholarship_payment_context import scholarship_payment_context_lines

SOURCE = Path(__file__).resolve().parents[1] / "app.py"


class ScholarshipPaymentTests(unittest.TestCase):
    def test_paid_eligibility_includes_verification_and_correct_scope(self):
        lines = scholarship_payment_context_lines({
            "lead_id": 19, "status": "PAID", "currency": "MWK",
            "paid": Decimal("5000"), "required": Decimal("5000"),
        })
        text = "\n".join(lines)
        self.assertIn("SCHOLARSHIP SERVICE PAYMENT VERIFIED", text)
        self.assertIn("Eligibility Check", text)
        self.assertIn("specific selected package", text)
        self.assertIn("MWK 5,000", text)

    def test_screenshot_or_unpaid_never_treated_as_verified(self):
        for status, paid, required in [
            ("NOT_PAID", 0, 5000),
            ("NOT_VERIFIED", 0, 5000),
            ("PART_PAID", 2000, 5000),
            ("RECEIVED_UNPRICED", 5000, None),
        ]:
            with self.subTest(status=status):
                text = "\n".join(scholarship_payment_context_lines({
                    "lead_id": 19, "status": status, "paid": paid,
                    "currency": "MWK", "required": required,
                }))
                self.assertIn("NOT confirmed as fully paid", text)
                self.assertNotIn("SCHOLARSHIP SERVICE PAYMENT VERIFIED", text)

    def test_no_record_no_client_payment_claim(self):
        self.assertEqual(scholarship_payment_context_lines({"lead_id": None}), [])

    def test_ai_payment_context_uses_real_ledger_lookup(self):
        source = SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        func = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef)
                    and node.name == "build_verified_payment_context")
        funcs = ast.Module(body=[func], type_ignores=[])
        seen=[]
        def lookup(number, service, *other):
            seen.append((number,service))
            return ({
                "lead_id": 19, "status": "PAID", "paid": Decimal("5000"),
                "currency": "MWK", "required": Decimal("5000"),
            } if service == "Scholarship Search" else {"lead_id": None})
        ns = {
            "CAREER_SERVICE_DEFAULT_PRICES_MWK":{},
            "expire_career_assist_entitlements":lambda number:None,
            "get_verified_service_payment_state":lookup,
            "get_career_assist_lifecycle_state":lambda number:{"state":"NOT_PAID"},
            "get_career_assist_standing_consent":lambda number:{},
        }
        exec(compile(funcs,str(SOURCE),"exec"),ns)
        result=ns["build_verified_payment_context"]("265999000111")[0]["content"]
        self.assertIn("SCHOLARSHIP SERVICE PAYMENT VERIFIED",result)
        self.assertIn(("265999000111","Scholarship Search"),seen)

if __name__ == "__main__":
    unittest.main()
