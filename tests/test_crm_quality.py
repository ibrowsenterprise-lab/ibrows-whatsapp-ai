"""Offline regression coverage for the private IBROWS customer CRM.

No app import, production database, tokens, network or customer messages.
"""
import re
import unittest
from pathlib import Path
from jinja2 import Environment
from decimal import Decimal
from crm_quality import (MARKER, improve_crm_template, install_crm_improvements,
                         _can_convert_to_eligibility, install_eligibility_package_support)

APP_SOURCE = Path(__file__).resolve().parents[1].joinpath("app.py").read_text(encoding="utf-8")
match = re.search(r'CUSTOMER_CRM_TEMPLATE = """(.*?)"""', APP_SOURCE, re.S)
assert match, "Existing customer CRM template not found"
ORIGINAL = match.group(1)


class TestCustomerCRM(unittest.TestCase):
    def test_original_admin_route_stays_authenticated(self):
        self.assertRegex(
            APP_SOURCE,
            r'@app\.route\("/admin/customers/<customer_number>", methods=\["GET"\]\)\s*@admin_required\s*def admin_customer_history'
        )
        self.assertIn("validate_csrf()", APP_SOURCE)
        self.assertIn("ON CONFLICT (request_token) DO NOTHING", APP_SOURCE)

    def test_improved_template_is_idempotent_and_parses(self):
        upgraded = improve_crm_template(ORIGINAL)
        self.assertEqual(improve_crm_template(upgraded), upgraded)
        self.assertIn(MARKER, upgraded)
        self.assertIn("Current enquiries", upgraded)
        self.assertIn("Open enquiries", upgraded)
        self.assertIn("Service types requested", upgraded)
        self.assertNotIn("Services used", upgraded)
        self.assertIn("No verified payment recorded", upgraded)
        self.assertIn("MK5,000 Eligibility Check", upgraded)
        self.assertIn("MK60,000/month Scholarship Assist", upgraded)
        self.assertIn("crm_return", upgraded)
        self.assertIn("csrf_token", upgraded)
        self.assertNotIn('name="payment_confirmed"', upgraded)
        self.assertNotIn('name="payment_amount"', upgraded)
        Environment(autoescape=True).parse(upgraded)

    def test_customer_name_and_summary_are_escaped(self):
        upgraded = improve_crm_template(ORIGINAL)
        env = Environment(autoescape=True)
        html = env.from_string(upgraded).render(
            url_for=lambda endpoint, **kwargs: "/admin/" + endpoint,
            customer_name="<script>alert('unsafe')</script>",
            customer_number="265999000111",
            leads=[{
                "id": 1, "service": "Scholarship Search", "status": "NEW",
                "priority": "NORMAL", "summary": "<img src=x onerror=alert(1)>",
                "estimated_value_label": "", "paid_label": "", "payment_status": "NOT_PAID",
                "payment_status_label": "Not paid", "quote_status": "NOT_STARTED",
                "quote_status_label": "Not started", "quote_reference": "",
                "created_label": "10 Nov 2026", "updated_label": "10 Nov 2026",
                "balance": None,
            }],
            open_count=1, services_count=1, archived_merged_count=0,
            duplicate_groups=[], customer_values={}, timeline=[], payments=[],
            documents=[], csrf_token="TEST_CSRF_NOT_A_REAL_SECRET",
            return_to="/admin/leads", crm_return="/admin/customers/265999000111",
        )
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("No verified payment recorded", html)
        self.assertIn("MK5,000 Eligibility Check", html)
        self.assertIn("Reply in IBROWS inbox", html)
        self.assertIn("TEST_CSRF_NOT_A_REAL_SECRET", html)
        self.assertNotIn('name="payment_confirmed"', html)

    def test_one_off_conversion_refuses_existing_payments_and_monthly_quotes(self):
        clean = ("265999000111", "Scholarship Search", "NEW", None, None, None,
                 None, "MWK", "NOT_STARTED")
        self.assertTrue(_can_convert_to_eligibility(clean, False, False))
        self.assertFalse(_can_convert_to_eligibility(clean, True, False))
        self.assertFalse(_can_convert_to_eligibility(clean, False, True))
        self.assertFalse(_can_convert_to_eligibility(
            clean[:1] + ("Scholarship Eligibility Check",) + clean[2:], False, False))
        self.assertFalse(_can_convert_to_eligibility(
            clean[:6] + (Decimal("60000"),) + clean[7:], False, False))
        self.assertFalse(_can_convert_to_eligibility(
            clean[:8] + ("ACCEPTED",), False, False))
        self.assertFalse(_can_convert_to_eligibility(
            clean[:2] + ("CLOSED",) + clean[3:], False, False))

    def test_eligibility_package_price_and_ai_context_are_separate(self):
        from flask import Flask
        app = Flask("ibrows-oneoff-service-test")
        prices = {"Scholarship Search": Decimal("60000")}
        context = lambda number: [{"role": "user",
            "content": "- Scholarship Eligibility Check: PAID; verified received MWK 5,000; required MWK 5,000."}]
        def old_canonical(service):
            return {"scholarship search":"Scholarship Search"}.get(
                str(service).lower(), service)
        fake_ns = {
            "CAREER_SERVICE_DEFAULT_PRICES_MWK": prices,
            "get_db": lambda: None,
            "admin_required": lambda fn: fn,
            "validate_csrf": lambda: None,
            "_safe_admin_return_path": lambda p: p or "/admin/leads",
            "_activity_insert": lambda *args: None,
            "canonicalize_service": old_canonical,
            "build_verified_payment_context": context,
        }
        self.assertTrue(install_eligibility_package_support(app, fake_ns))
        self.assertEqual(prices["Scholarship Search"], Decimal("60000"))
        self.assertEqual(prices["Scholarship Eligibility Check"], Decimal("5000"))
        self.assertEqual(fake_ns["canonicalize_service"]("scholarship eligibility check"),
                         "Scholarship Eligibility Check")
        self.assertEqual(fake_ns["canonicalize_service"]("scholarship search"),
                         "Scholarship Search")
        text = fake_ns["build_verified_payment_context"]("265999000111")[0]["content"]
        self.assertIn("one-off", text.lower())
        self.assertIn("NOT the MK60,000/month", text)
        self.assertIn("crm_convert_scholarship_eligibility", app.view_functions)
        rules = [r for r in app.url_map.iter_rules()
                 if r.endpoint == "crm_convert_scholarship_eligibility"]
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].methods - {"OPTIONS"}, {"POST"})

    def test_unexpected_template_fails_safely(self):
        with self.assertRaises(ValueError):
            improve_crm_template("<div>unknown template</div>")

    def test_install_isolated_to_customer_view_and_private_headers(self):
        from flask import Flask
        app = Flask("ibrows-crm-offline-test")
        @app.get("/admin/customers/<customer_number>", endpoint="admin_customer_history")
        def private_history(customer_number):
            return "TEST PRIVATE PAGE"
        @app.get("/public-test")
        def public_test():
            return "PUBLIC"
        ns = private_history.__globals__
        original_value = ns.get("CUSTOMER_CRM_TEMPLATE", None)
        ns["CUSTOMER_CRM_TEMPLATE"] = ORIGINAL
        try:
            self.assertTrue(install_crm_improvements(app))
            self.assertIn(MARKER, ns["CUSTOMER_CRM_TEMPLATE"])
            with app.test_client() as client:
                res = client.get("/admin/customers/265999000111")
                self.assertEqual(res.status_code, 200)
                self.assertIn("no-store", res.headers["Cache-Control"])
                self.assertEqual(res.headers["X-Robots-Tag"], "noindex, nofollow")
                public = client.get("/public-test")
                self.assertNotIn("no-store", public.headers.get("Cache-Control", ""))
                self.assertNotIn("X-Robots-Tag", public.headers)
        finally:
            if original_value is None:
                ns.pop("CUSTOMER_CRM_TEMPLATE", None)
            else:
                ns["CUSTOMER_CRM_TEMPLATE"] = original_value


if __name__ == "__main__":
    unittest.main()
