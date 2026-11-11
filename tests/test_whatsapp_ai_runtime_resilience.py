"""Offline integration checks: no real OpenAI, Meta, payments or databases."""
import json
import unittest
from types import SimpleNamespace
from whatsapp_ai_runtime_resilience import (
    install_whatsapp_ai_resilience, is_business_assistant_request
)


def fake_validator(result):
    fields={"reply","lead_required","service","lead_summary","handover_reason",
            "attachment_memory","detected_urls"}
    if not isinstance(result,dict) or set(result.keys())!=fields:
        raise ValueError("invalid structure")
    if type(result["lead_required"]) is not bool or not isinstance(result["reply"],str):
        raise ValueError("invalid type")
    return result


VALID={"reply":"We can help with WhatsApp AI.","lead_required":False,"service":"",
       "lead_summary":"","handover_reason":"","attachment_memory":"",
       "detected_urls":[]}
GENERIC=("Thank you for contacting IBROWS Enterprise. Our AI assistant is temporarily "
         "unavailable. Please try again shortly, or ask to speak to a human "
         "if you need assistance from the IBROWS team.")


def fixture(outputs):
    requests=[]
    def fake_create(*args,**kwargs):
        requests.append((args,kwargs))
        if kwargs.get("model")=="gpt-5.6-luna":
            return SimpleNamespace(output_text=outputs.pop(0))
        return SimpleNamespace(output_text="UNRELATED_OK")
    endpoint=SimpleNamespace(create=fake_create)
    client=SimpleNamespace(responses=endpoint)
    ns={"client":client,"validate_ai_structured_output":fake_validator,"generic":GENERIC}
    exec("def generate_ai_reply(customer_number,customer_message,**kwargs):\n"
         "    return {'reply': generic, 'lead_required':False,'service':'',"
         "'lead_summary':'','handover_reason':'','attachment_memory':'',"
         "'detected_urls':[]}\n"
         "def receive_webhook():\n    return None\n",
         ns)
    app=SimpleNamespace(view_functions={"receive_webhook":ns["receive_webhook"]})
    return app,ns,endpoint,requests


class RuntimeResilienceTests(unittest.TestCase):
    def test_route_match_limited_to_business_assistant(self):
        self.assertTrue(is_business_assistant_request((),{
            "model":"gpt-5.6-luna","store":False,
            "instructions":"You are the official WhatsApp AI Business Assistant",
            "input":[]}))
        for kwargs in [
            {"model":"gpt-5.6-luna","store":True,"instructions":"You are the official WhatsApp AI Business Assistant","input":[]},
            {"model":"gpt-5.6-luna","store":False,"instructions":"A job application assistant","input":[]},
            {"model":"another-model","store":False,"instructions":"You are the official WhatsApp AI Business Assistant","input":[]}
        ]:
            self.assertFalse(is_business_assistant_request((),kwargs))

    def test_recover_invalid_json_without_changing_unrelated_api_calls(self):
        app,ns,endpoint,calls=fixture(["not json",json.dumps(VALID)])
        self.assertTrue(install_whatsapp_ai_resilience(app))
        self.assertTrue(install_whatsapp_ai_resilience(app))
        output=endpoint.create(
            model="gpt-5.6-luna",store=False,
            instructions="You are the official WhatsApp AI Business Assistant",
            input=[{"role":"user","content":"hello"}])
        self.assertEqual(json.loads(output.output_text),VALID)
        self.assertEqual(len(calls),2)
        self.assertIn("FINAL OUTPUT VALIDATION",calls[1][1]["instructions"])
        other=endpoint.create(model="other-model",store=False,instructions="other",input=[])
        self.assertEqual(other.output_text,"UNRELATED_OK")
        self.assertEqual(len(calls),3)

    def test_when_model_fails_customer_receives_specific_chichewa_sales_support(self):
        app,ns,endpoint,calls=fixture([])
        self.assertTrue(install_whatsapp_ai_resilience(app))
        msg="Ndikufunako mutandipangila zoti whatsapp azindiyankhila ma customer olo ndikugona"
        result=ns["generate_ai_reply"]("TEST_NUMBER",msg)
        self.assertIn("IBROWS",result["reply"])
        self.assertIn("bizinesi",result["reply"])
        self.assertNotIn("temporarily unavailable",result["reply"])
        self.assertFalse(result["lead_required"])
        self.assertEqual(len(calls),0)

    def test_unrelated_fallback_does_not_fabricate_response(self):
        app,ns,endpoint,calls=fixture([])
        self.assertTrue(install_whatsapp_ai_resilience(app))
        result=ns["generate_ai_reply"]("TEST_NUMBER","Do I qualify for a scholarship?")
        self.assertEqual(result["reply"],GENERIC)
        self.assertFalse(result["lead_required"])


if __name__=="__main__":
    unittest.main()
