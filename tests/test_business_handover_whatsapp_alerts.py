"""IBROWS human takeover alerts must only reach old Business App line.

No real WhatsApp requests, customer data or production DB connections here.
"""
import ast
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from handover_business_alerts import (
    BUSINESS_ALERT_NUMBER, DISPLAY_ALERT_NUMBER,
    is_owner_activation, owner_activation_reply,
    freeform_alert, template_payload, deliver_handover_alert,
)

SOURCE=Path(__file__).resolve().parents[1]/"app.py"


def isolated_handler(name, ns):
    tree=ast.parse(SOURCE.read_text("utf-8"))
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    node.decorator_list=[]
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(SOURCE),"exec"),ns)
    return ns[name]


class WhatsAppBusinessAlertTests(unittest.TestCase):
    def test_receiver_is_exact_old_business_line_not_personal(self):
        self.assertEqual(BUSINESS_ALERT_NUMBER, "265882242594")
        self.assertEqual(DISPLAY_ALERT_NUMBER, "0882 242 594")
        self.assertNotEqual(BUSINESS_ALERT_NUMBER,"265999242594")
        self.assertFalse(is_owner_activation("265999242594","IBROWS ALERTS ON"))
        self.assertTrue(is_owner_activation("265882242594"," ibrows   alerts on " ))
        self.assertFalse(is_owner_activation("265882242594","0"))
        self.assertIn("24 hours",owner_activation_reply())

    def test_session_alert_has_secure_customer_inbox_link(self):
        content=freeform_alert("Example Customer","Construction", "265999001111")
        self.assertIn("https://www.ibrowsenterprise.com/admin/inbox/265999001111",content)
        self.assertIn("Example Customer",content)
        self.assertIn("AI paused",content)
        self.assertNotIn("0999 242 594",content)

    def test_available_session_sends_only_to_0882(self):
        calls=[]
        result=deliver_handover_alert(
            "Example","General Enquiry","265999001111",
            window_open=True,
            send_text=lambda phone,text:calls.append((phone,text)) or True,
            token="dummy",phone_number_id="123",
            http_post=lambda *a,**k:self.fail("template HTTP called inside 24h"),
        )
        self.assertEqual(result,("ACCEPTED","whatsapp_24h"))
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][0],"265882242594")

    def test_no_window_without_approved_template_never_sends_freeform(self):
        calls=[]
        result=deliver_handover_alert(
            "Example","Scholarship","265999001111",
            window_open=False,
            send_text=lambda *a:calls.append("TEXT"),
            token="dummy",phone_number_id="123",
            http_post=lambda *a,**k:calls.append("HTTP"),
        )
        self.assertEqual(result,("TEMPLATE_REQUIRED","whatsapp_template"))
        self.assertEqual(calls,[])

    def test_template_with_two_safe_variables_and_correct_sender(self):
        pay=template_payload(" Customer A ","Landscaping",template_name="ibrows_human_takeover_notice")
        self.assertEqual(pay["to"],"265882242594")
        self.assertEqual(pay["type"],"template")
        self.assertEqual(pay["template"]["name"],"ibrows_human_takeover_notice")
        self.assertEqual(pay["template"]["language"]["code"],"en_US")
        params=pay["template"]["components"][0]["parameters"]
        self.assertEqual([v["text"] for v in params],["Customer A","Landscaping"])
        with self.assertRaises(ValueError):
            template_payload("Customer","Service",template_name="bad<script>")

    def test_template_uses_graph_and_acceptance_not_handset_delivery(self):
        requests=[]
        def http_post(url,**kwargs):
            requests.append((url,kwargs))
            return types.SimpleNamespace(status_code=200)
        result=deliver_handover_alert(
            "Example","General Enquiry","265999001111",
            window_open=False,send_text=lambda *a:self.fail("text outside window"),
            token="FAKE_NOT_SECRET",phone_number_id="sender123",
            http_post=http_post,template_name="ibrows_human_takeover_notice",
        )
        self.assertEqual(result,("ACCEPTED","whatsapp_template"))
        self.assertEqual(len(requests),1)
        self.assertIn("sender123/messages",requests[0][0])
        self.assertEqual(requests[0][1]["json"]["to"],"265882242594")
        self.assertEqual(requests[0][1]["json"]["type"],"template")

    def test_failed_template_never_claims_sent(self):
        result=deliver_handover_alert(
            "Example","General Enquiry","265999001111",
            window_open=False,send_text=lambda *a:self.fail("no open window"),
            token="dummy",phone_number_id="sender123",
            http_post=lambda *a,**k:types.SimpleNamespace(status_code=400),
            template_name="ibrows_human_takeover_notice",
        )
        self.assertEqual(result,("FAILED","whatsapp_template"))

    def test_normal_handover_preserves_email_and_adds_business_whatsapp(self):
        events=[]
        stub_module=types.SimpleNamespace(
            BUSINESS_ALERT_NUMBER=BUSINESS_ALERT_NUMBER,
            configured_template=lambda:"",
            configured_template_language=lambda:"en_US",
            deliver_handover_alert=lambda *a,**kw:events.append(("old_business_whatsapp",kw.get("window_open"))) or ("ACCEPTED","whatsapp_24h"),
            save_alert_audit=lambda *a:events.append(("audit",a[2])) or True,
        )
        stubs={
            "JONES_PERSONAL_WHATSAPP_DISPLAY":"0999 242 594",
            "save_message":lambda num,role,msg:events.append(("saved",role)),
            "set_ai_paused":lambda num,paused:events.append(("paused",paused)),
            "record_human_handover_on_current_lead":lambda **kw:(15,False,"General Enquiry","Original request","Talk to Jones"),
            "send_human_handover_alert_email":lambda **kw:events.append(("email",kw.get("lead_id"))) or True,
            "is_whatsapp_service_window_open":lambda num:(num==BUSINESS_ALERT_NUMBER,None),
            "send_whatsapp_message":lambda *a:True,
            "get_db":lambda:None,"WHATSAPP_TOKEN":"demo","PHONE_NUMBER_ID":"123",
            "requests":types.SimpleNamespace(post=lambda *a:None),
        }
        with patch.dict(sys.modules,{"handover_business_alerts":stub_module}):
            func=isolated_handler("handle_local_human_handover",stubs)
            customer_response=func("265999001111","Customer","0",requested_person="Jones")
        self.assertIn(("paused",True),events)
        self.assertIn(("email",15),events)
        self.assertIn(("old_business_whatsapp",True),events)
        self.assertIn(("audit","ACCEPTED"),events)
        self.assertNotIn("0999 242 594",customer_response)
        self.assertIn("continue replying here",customer_response)
        self.assertLess(events.index(("email",15)),events.index(("old_business_whatsapp",True)))

    def test_owner_opt_in_branch_in_actual_webhook(self):
        source=SOURCE.read_text("utf-8")
        fn=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)
                and n.name=="receive_webhook")
        snippet=ast.get_source_segment(source,fn)
        self.assertIn("is_owner_activation(customer_number, customer_message)",snippet)
        self.assertLess(snippet.index("is_owner_activation(customer_number, customer_message)"),
                        snippet.index("if is_ai_paused(customer_number):"))
        events=[]
        fake_request=types.SimpleNamespace(get_json=lambda silent=True:{
            "entry":[{"changes":[{"value":{
                "messages":[{"from":BUSINESS_ALERT_NUMBER,
                             "id":"owner-activation-test-1",
                             "type":"text","text":{"body":"IBROWS ALERTS ON"}}],
                "contacts":[{"profile":{"name":"IBROWS"}}],
            }}]}]
        })
        stubs={
            "request":fake_request,
            "cleanup_expired_data":lambda:None,
            "claim_whatsapp_message":lambda *a:("NEW",None),
            "save_message":lambda num,role,msg:events.append(("saved",role)),
            "store_pending_reply":lambda id,msg:events.append(("pending",msg)),
            "send_whatsapp_message":lambda num,msg:events.append(("sent_to",num)) or True,
            "finish_whatsapp_message":lambda id,ok:events.append(("finished",ok)),
        }
        handler=isolated_handler("receive_webhook",stubs)
        result=handler()
        self.assertEqual(result,("EVENT_RECEIVED",200))
        self.assertIn(("sent_to",BUSINESS_ALERT_NUMBER),events)
        self.assertIn(("finished",True),events)


if __name__ == "__main__":
    unittest.main()
