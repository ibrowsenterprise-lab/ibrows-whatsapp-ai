"""Production-safe, limited resilience around the main IBROWS WhatsApp AI call.

Installs at Gunicorn worker startup. Does not alter customer data or other AI
workflows (career application, scholarship, document generation). It normalizes
the sole business-assistant structured response and makes one bounded retry
for malformed structured output only.
"""
import json
from types import SimpleNamespace
from whatsapp_ai_json_resilience import (
    call_business_ai_resilient, safe_automation_interest_reply,
)

FALLBACK_SIGNATURE = (
    "Our AI assistant is temporarily unavailable. "
    "Please try again shortly"
)
ASSISTANT_INSTRUCTIONS_MARKER = "You are the official WhatsApp AI Business Assistant"


def is_business_assistant_request(args, kwargs):
    """Fail closed if the model/instructions are different or ambiguous."""
    return (
        not args
        and kwargs.get("model") == "gpt-5.6-luna"
        and kwargs.get("store") is False
        and isinstance(kwargs.get("instructions"), str)
        and ASSISTANT_INSTRUCTIONS_MARKER in kwargs["instructions"]
        and "input" in kwargs
    )


def install_whatsapp_ai_resilience(flask_app):
    """Keep all unrelated OpenAI calls, webhook routing and ledgers unchanged."""
    view = getattr(flask_app, "view_functions", {}).get("receive_webhook")
    if view is None:
        return False
    ns = view.__globals__
    core_client = ns.get("client")
    original_generate = ns.get("generate_ai_reply")
    validator = ns.get("validate_ai_structured_output")
    if not core_client or not original_generate or not callable(validator):
        return False
    endpoint = getattr(core_client, "responses", None)
    original_create = getattr(endpoint, "create", None)
    if endpoint is None or not callable(original_create):
        return False
    if getattr(original_create, "_ibrows_safe_ai_json", False):
        return True

    def guarded_create(*args, **kwargs):
        if not is_business_assistant_request(args, kwargs):
            return original_create(*args, **kwargs)
        # Validation is identical to the main app; only this LLM call is
        # intercepted. A second LLM call happens only if the first JSON fails.
        validated = call_business_ai_resilient(
            original_create,
            model=kwargs["model"],
            instructions=kwargs["instructions"],
            input_payload=kwargs["input"],
            validator=validator,
        )
        return SimpleNamespace(
            output_text=json.dumps(validated, ensure_ascii=False)
        )
    guarded_create._ibrows_safe_ai_json = True

    try:
        endpoint.create = guarded_create
    except (AttributeError, TypeError):
        print("IBROWS AI JSON RESILIENCE: endpoint wrapping unavailable", flush=True)
        return False

    def guarded_generate(customer_number, customer_message, *args, **kwargs):
        result = original_generate(customer_number, customer_message, *args, **kwargs)
        if not isinstance(result, dict):
            return result
        reply = str(result.get("reply") or "")
        if FALLBACK_SIGNATURE not in reply:
            return result
        # Only a narrow, well-known business AI sales question receives a
        # deterministic response; no fabricated human alert or qualified lead.
        service_reply = safe_automation_interest_reply(customer_message)
        if service_reply:
            result = dict(result)
            result["reply"] = service_reply
            result["lead_required"] = False
            for key in ("service", "lead_summary", "handover_reason",
                        "attachment_memory"):
                result[key] = ""
            result["detected_urls"] = []
            print("IBROWS AI SALES CONTINUITY: safe fallback served", flush=True)
        return result

    guarded_generate._ibrows_safe_ai_json = True
    ns["generate_ai_reply"] = guarded_generate
    print("IBROWS AI JSON RESILIENCE: validated once, max one malformed-output retry",flush=True)
    return True
