"""Production-safe, limited resilience around the main IBROWS WhatsApp AI call.

Installs at Gunicorn worker startup. Does not alter customer data or other AI
workflows (career application, scholarship, document generation). It normalizes
the sole business-assistant structured response and makes one bounded retry
for malformed structured output only.
"""
import json
import re
from types import SimpleNamespace
from whatsapp_ai_json_resilience import (
    call_business_ai_resilient, safe_automation_interest_reply,
)

FALLBACK_SIGNATURE = (
    "Our AI assistant is temporarily unavailable. "
    "Please try again shortly"
)
ASSISTANT_INSTRUCTIONS_MARKER = "You are the official WhatsApp AI Business Assistant"


NAVIGATION_FOOTERS = {
    "english": "Reply 0 to talk to Jones. Reply MENU to return to the main menu.",
    "chichewa": "Tumizani 0 kuti mulankhule ndi Jones. Tumizani MENU kuti mubwerere ku menyu yayikulu.",
    "tumbuka": "Tumizgani 0 kuti muyowoye na Jones. Tumizgani MENU kuti muwelere ku menyu yikuru.",
}
TUMBUKA_REPLY_WORDS = re.compile(r"\b(tingamovwirani|tingamovwira|mungatuma|mukukhumba|yowoyani|tumizgani|malonda ghinu)\b")
CHICHEWA_REPLY_WORDS = re.compile(r"\b(zabwino|zikumveka|kukuthandizeni|kuthandiza|kukupangirani|kukupangilani|bizinesi yanu|mukufuna|muli ndi|tumizani|mulankhule|mpunga)\b")


def add_navigation_footer(reply):
    """Add stable shortcuts to the outgoing reply in its detected language."""
    if not isinstance(reply, str) or not reply.strip():
        return reply
    reply = reply.rstrip()
    if any(reply.endswith(footer) for footer in NAVIGATION_FOOTERS.values()):
        return reply
    normalized = reply.casefold()
    if TUMBUKA_REPLY_WORDS.search(normalized):
        language = "tumbuka"
    elif CHICHEWA_REPLY_WORDS.search(normalized):
        language = "chichewa"
    else:
        language = "english"
    with_footer = f"{reply}\n\n{NAVIGATION_FOOTERS[language]}"
    return with_footer if len(with_footer) <= 4096 else reply


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
    import sys
    print("IBROWS AI JSON RESILIENCE: startup installer invoked",flush=True)
    view = getattr(flask_app, "view_functions", {}).get("receive_webhook")
    ns = getattr(view, "__globals__", {}) if view is not None else {}
    def has_primitives(mapping):
        return bool(
            mapping.get("client") is not None
            and callable(mapping.get("generate_ai_reply"))
            and callable(mapping.get("validate_ai_structured_output"))
        )
    if not has_primitives(ns):
        # Some production Flask setups wrap the webhook view and its globals.
        # The actual WSGI app is already imported under the same 'app' module
        # as the multilingual-menu startup integration.
        core = sys.modules.get("app")
        ns = vars(core) if core is not None else {}
    if not has_primitives(ns):
        print("IBROWS AI JSON RESILIENCE: application primitives unavailable",flush=True)
        return False
    core_client = ns["client"]
    original_generate = ns["generate_ai_reply"]
    validator = ns["validate_ai_structured_output"]
    endpoint = getattr(core_client, "responses", None)
    original_create = getattr(endpoint, "create", None)
    if endpoint is None or not callable(original_create):
        print("IBROWS AI JSON RESILIENCE: model endpoint unavailable",flush=True)
        return False
    if getattr(original_create, "_ibrows_safe_ai_json", False):
        print("IBROWS AI JSON RESILIENCE: already installed",flush=True)
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
        reply = result.get("reply")
        if isinstance(reply, str) and FALLBACK_SIGNATURE in reply:
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
        reply = add_navigation_footer(result.get("reply"))
        if reply != result.get("reply"):
            return {**result, "reply": reply}
        return result

    guarded_generate._ibrows_safe_ai_json = True
    ns["generate_ai_reply"] = guarded_generate
    print("IBROWS AI JSON RESILIENCE: validated once, max one malformed-output retry",flush=True)
    return True
