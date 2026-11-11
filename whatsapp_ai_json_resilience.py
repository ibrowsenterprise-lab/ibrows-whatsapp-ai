"""Bounded, fail-closed JSON recovery for the IBROWS customer-facing AI.

Only malformed *model output* is retried, once. No response body or user data is
logged. Parsed objects still pass the original strict business validator.
"""
import json
import re


def decode_model_json(raw_text):
    text = str(raw_text or "").strip()
    # Occasionally a model encloses otherwise valid JSON in a single fence.
    if text.startswith("```"):
        match = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if not match:
            raise ValueError("Incomplete or invalid fenced JSON")
        text = match.group(1).strip()
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError("Expected a structured JSON object")
    return result


def call_business_ai_resilient(create_response, *, model, instructions,
                               input_payload, validator):
    """At most two model requests; retry only if the model's output is invalid.

    API/network/database failures are NOT retried here. No partial result
    is returned: every candidate must pass the existing strict validator.
    """
    response = create_response(model=model, store=False,
                               instructions=instructions, input=input_payload)
    try:
        return validator(decode_model_json(response.output_text))
    except ValueError as first_error:
        print("IBROWS AI STRUCTURED OUTPUT RETRY: "
              + type(first_error).__name__, flush=True)
    retry_instructions = (
        instructions
        + "\nFINAL OUTPUT VALIDATION: Your previous output could not be parsed "
          "or did not satisfy the required JSON schema. Retry the SAME user "
          "request. Return a complete concise JSON object with exactly the "
          "specified keys and field types. No markdown, leading text or "
          "trailing commentary. Do not fabricate customer payment, staff "
          "contact, service completion or human handover."
    )
    retry_response = create_response(model=model, store=False,
                                    instructions=retry_instructions,
                                    input=input_payload)
    return validator(decode_model_json(retry_response.output_text))


def safe_automation_interest_reply(customer_message):
    """A concise sales acknowledgement only for unambiguous automation intent.

    Does not state that a bot has been provisioned, guarantee uptime, quote a
    price, accept payment or claim human contact has taken place.
    """
    text = " ".join(str(customer_message or "").casefold().split())
    if "whatsapp" not in text:
        return None
    intent = (
        "azindiyankhila", "azindiyankha", "azindiyankhira",
        "ayankhe", "amayankha", "automatic reply", "automatically reply",
        "auto reply", "reply to customers", "reply customers",
        "answer customers", "answer my customers", "chatbot",
        "ai assistant", "automate", "automation",
    )
    customers = ("customer", "makasitomala", "makasitoma", "ma customer",
                 "business", "bizinesi", "kugona", "asleep", "sleeping")
    if not any(term in text for term in intent) or not any(term in text for term in customers):
        return None
    chichewa = any(term in text for term in (
        "ndikufun", "mutandipang", "azindiyankh", "ayankhe",
        "makasitoma", "ndikugona", "olo", "kuti"
    ))
    if chichewa:
        return (
            "Inde, IBROWS imathandiza kukhazikitsa WhatsApp AI Assistant "
            "yoyankha mafunso a makasitomala ngakhale mukugona kapena foni "
            "yanu ili yozimitsa, bola intaneti ndi makina a AI zikugwira ntchito. "
            "Kodi muli ndi bizinesi yanji, ndipo mumalandira mafunso ati kwambiri?"
        )
    return (
        "Yes, IBROWS can help set up a WhatsApp AI assistant to respond to "
        "routine customer enquiries even while you sleep or your phone is off, "
        "provided the online service is running. What type of business do you "
        "operate, and what questions do customers ask most often?"
    )
