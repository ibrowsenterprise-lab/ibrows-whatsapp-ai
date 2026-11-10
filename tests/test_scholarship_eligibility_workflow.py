"""Paid eligibility workflow tests: offline, no real DB, credentials or WhatsApp."""
import ast
import unittest
from decimal import Decimal
from pathlib import Path

from scholarship_eligibility_intake import (
    SERVICE, COMMANDS, is_explicit_eligibility_intake_request,
    is_verified_one_off, paid_eligibility_intake_message,
)
from scholarship_eligibility_backend import (
    DEFAULT_STAGE, NEXT_STAGES, PAGE, can_move_stage,
    install_eligibility_work_queue,
)

SOURCE=Path(__file__).resolve().parents[1]/"app.py"
GOOD={
    "lead_id":19,"service":SERVICE,"status":"PAID",
    "currency":"MWK","required":Decimal("5000"),"paid":Decimal("5000"),
}

def build_webhook(stubs):
    tree=ast.parse(SOURCE.read_text("utf-8"))
    fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=="receive_webhook")
    fn.decorator_list=[]
    ns=stubs.copy()
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(SOURCE),"exec"),ns)
    return ns["receive_webhook"]

class FakeRequest:
    def __init__(self,message):self.message=message
    def get_json(self,silent=True):
        return {"entry":[{"changes":[{"value":{
            "messages":[{"from":"265999001234","id":"eligibility-command-123",
                         "type":"text","text":{"body":self.message}}],
            "contacts":[{"profile":{"name":"Client"}}],
        }}]}]}

class EligibilityIntakeTests(unittest.TestCase):
    def test_exact_commands_and_no_accidental_capture(self):
        self.assertTrue(is_explicit_eligibility_intake_request("  START  my Eligibility check  "))
        self.assertTrue(is_explicit_eligibility_intake_request("continue eligibility"))
        for q in ["0","1","show me your menu","Hello","Can I start university?",
                  "I need a bank loan eligibility check","Please submit my application"]:
            with self.subTest(q=q):
                self.assertFalse(is_explicit_eligibility_intake_request(q))

    def test_verified_scope_requires_exact_service_price_and_currency(self):
        self.assertTrue(is_verified_one_off(GOOD))
        for key,wrong in [
            ("status","NOT_PAID"),("service","Scholarship Search"),
            ("currency","USD"),("required",Decimal("60000")),
            ("paid",Decimal("1000")),("lead_id",None)
        ]:
            with self.subTest(key=key):
                broken=GOOD.copy();broken[key]=wrong
                self.assertFalse(is_verified_one_off(broken))
        self.assertFalse(is_verified_one_off(None))

    def test_intake_message_does_not_promise_admission_or_ask_otp(self):
        msg=paid_eligibility_intake_message()
        self.assertIn("payment is confirmed",msg)
        self.assertIn("Bachelor",msg)
        self.assertIn("economics",msg)
        self.assertIn("English",msg)
        self.assertIn("0",msg)
        self.assertIn("no additional payment is due",msg)
        self.assertNotIn("You are eligible",msg)
        self.assertNotIn("guaranteed",msg)
        self.assertNotIn("Please send your PIN",msg)
        self.assertNotIn("Europe for September",msg)

    def run_webhook(self,message,paid=GOOD,lookup_raises=False):
        events=[]
        def lookup(num,service):
            events.append(("lookup",service))
            if lookup_raises: raise RuntimeError("temporary outage")
            return paid
        ns={
            "request":FakeRequest(message),
            "cleanup_expired_data":lambda:None,
            "claim_whatsapp_message":lambda *a:("NEW",None),
            "is_ai_paused":lambda num:False,
            "get_verified_service_payment_state":lookup,
            "save_message":lambda num,role,msg:events.append(("save",role)),
            "store_pending_reply":lambda msgid,reply:events.append(("pending",reply)),
            "send_whatsapp_message":lambda num,reply:events.append(("send",reply)) or True,
            "finish_whatsapp_message":lambda msgid,sent:events.append(("finish",sent)),
        }
        result=build_webhook(ns)()
        return result,events

    def test_paid_command_replies_and_no_further_payment(self):
        result,events=self.run_webhook("Start eligibility")
        self.assertEqual(result,("EVENT_RECEIVED",200))
        self.assertIn(("lookup",SERVICE),events)
        replies=[e[1] for e in events if e[0]=="send"]
        self.assertEqual(len(replies),1)
        self.assertIn("no additional payment is due",replies[0])
        self.assertIn("academic",replies[0].lower())
        self.assertEqual(events[-1],("finish",True))

    def test_unpaid_command_does_not_claim_received(self):
        bad={**GOOD,"status":"NOT_PAID","paid":Decimal("0")}
        result,events=self.run_webhook("eligibility intake",paid=bad)
        self.assertEqual(result,("EVENT_RECEIVED",200))
        msg=[e[1] for e in events if e[0]=="send"][0]
        self.assertIn("cannot yet verify",msg)
        self.assertNotIn("payment is confirmed",msg)

    def test_db_outage_never_asks_for_extra_funds(self):
        result,events=self.run_webhook("continue eligibility",lookup_raises=True)
        self.assertEqual(result,("EVENT_RECEIVED",200))
        msg=[e[1] for e in events if e[0]=="send"][0]
        self.assertIn("cannot check",msg)
        self.assertIn("Do not make another payment",msg)

class AdminCaseTests(unittest.TestCase):
    def test_strict_sequence_requires_ledger(self):
        current=DEFAULT_STAGE
        for next_stage in ["AWAITING_INFORMATION","REVIEWING","READY_FOR_DELIVERY","DELIVERED"]:
            self.assertEqual(NEXT_STAGES[current],next_stage)
            self.assertTrue(can_move_stage(current,next_stage,GOOD))
            self.assertFalse(can_move_stage(current,next_stage,{
                **GOOD,"status":"NOT_PAID"}))
            current=next_stage
        self.assertFalse(can_move_stage("AWAITING_INFORMATION","DELIVERED",GOOD))
        self.assertFalse(can_move_stage("DELIVERED","AWAITING_INFORMATION",GOOD))

    def test_admin_page_has_csrf_confirmation_and_no_auto_send(self):
        from flask import Flask
        app=Flask("ibrows-eligibility-offline")
        ns={
            "get_db":lambda:None,
            "admin_required":lambda fn:fn,
            "validate_csrf":lambda:None,
            "get_verified_service_payment_state":lambda *args:GOOD,
            "get_csrf_token":lambda:"TEST_CSRF_TOKEN",
        }
        exec("def admin_leads():\n    return 'ok'\n",ns)
        app.add_url_rule("/admin/leads",endpoint="admin_leads",view_func=ns["admin_leads"])
        self.assertTrue(install_eligibility_work_queue(app))
        rule=next(r for r in app.url_map.iter_rules() if r.endpoint=="admin_eligibility_case")
        self.assertEqual(rule.rule,"/admin/eligibility/<int:lead_id>")
        self.assertIn("POST",rule.methods)
        self.assertIn("csrf_token",PAGE)
        self.assertIn('name="confirm_action"',PAGE)
        self.assertIn("Open IBROWS WhatsApp Inbox",PAGE)
        self.assertIn("does not send anything automatically",PAGE)
        self.assertNotIn("send_whatsapp_message(",PAGE)
        app.jinja_env.parse(PAGE)

if __name__=="__main__":
    unittest.main()
