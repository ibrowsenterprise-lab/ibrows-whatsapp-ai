"""Offline AI JSON recovery regression; never calls OpenAI, WhatsApp or database."""
import json
import unittest
from types import SimpleNamespace
from whatsapp_ai_json_resilience import (
    decode_model_json, call_business_ai_resilient, safe_automation_interest_reply
)


def validate(value):
    required={"reply","lead_required","service","lead_summary",
              "handover_reason","attachment_memory","detected_urls"}
    if not isinstance(value,dict) or set(value)!=required:
        raise ValueError("wrong fields")
    if type(value["lead_required"]) is not bool:
        raise ValueError("wrong boolean type")
    if not value["reply"] or not isinstance(value["reply"],str):
        raise ValueError("empty/nonstring reply")
    return value

GOOD={"reply":"How can we help?","lead_required":False,"service":"",
      "lead_summary":"","handover_reason":"","attachment_memory":"",
      "detected_urls":[]}


class ResilientWhatsAppAI(unittest.TestCase):
    def test_plain_and_fenced_json(self):
        self.assertEqual(decode_model_json(json.dumps(GOOD)),GOOD)
        self.assertEqual(decode_model_json("```json\n"+json.dumps(GOOD)+"\n```"),GOOD)
        for bad in ["", "not json", "{", "[]", "```json\n{", json.dumps(GOOD)+" extra"]:
            with self.subTest(bad=bad):
                with self.assertRaises((ValueError,json.JSONDecodeError)):
                    decode_model_json(bad)

    def test_valid_model_output_uses_only_one_request(self):
        calls=[]
        def fake_create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(output_text=json.dumps(GOOD))
        self.assertEqual(call_business_ai_resilient(
            fake_create,model="test-model",instructions="JSON",input_payload=[],
            validator=validate), GOOD)
        self.assertEqual(len(calls),1)
        self.assertFalse(calls[0]["store"])

    def test_bad_json_gets_one_bounded_retry(self):
        payloads=["This is not JSON",json.dumps(GOOD)]
        calls=[]
        def fake_create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(output_text=payloads.pop(0))
        answer=call_business_ai_resilient(
            fake_create,model="test-model",instructions="Original instructions",
            input_payload=[{"role":"user","content":"sample"}],validator=validate)
        self.assertEqual(answer["reply"],GOOD["reply"])
        self.assertEqual(len(calls),2)
        self.assertIn("Original instructions",calls[1]["instructions"])
        self.assertIn("FINAL OUTPUT VALIDATION",calls[1]["instructions"])
        self.assertEqual(calls[0]["input"],calls[1]["input"])
        self.assertFalse(calls[1]["store"])

    def test_invalid_schema_gets_one_retry_then_fails_closed(self):
        calls=[]
        def fake_create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(output_text='{"reply":"Hi"}')
        with self.assertRaises(ValueError):
            call_business_ai_resilient(
                fake_create,model="test",instructions="I",input_payload=[],
                validator=validate)
        self.assertEqual(len(calls),2)

    def test_api_failure_does_not_retry_or_masquerade_as_bad_json(self):
        count=[0]
        def fake_create(**kwargs):
            count[0]+=1
            raise RuntimeError("Simulated provider unavailability")
        with self.assertRaises(RuntimeError):
            call_business_ai_resilient(
                fake_create,model="test",instructions="I",input_payload=[],
                validator=validate)
        self.assertEqual(count[0],1)

    def test_chichewa_sales_fallback_and_no_false_handover(self):
        msg="Ndikufunako mutandipangila zoti whatsapp azindiyankhila ma customer olo ndikugona"
        reply=safe_automation_interest_reply(msg)
        self.assertIn("IBROWS",reply)
        self.assertIn("bizinesi",reply)
        self.assertNotIn("yaikidwa",reply)
        self.assertNotIn("walipira",reply)
        self.assertNotIn("Jones adziwitsidwa",reply)

    def test_unrelated_messages_do_not_trigger_selling(self):
        for msg in ("Muli bwanji","How much is a CV?","I need scholarship help",
                    "WhatsApp my friend","Send a WhatsApp receipt"):
            with self.subTest(msg=msg):
                self.assertIsNone(safe_automation_interest_reply(msg))


if __name__=="__main__":
    unittest.main()
