"""Business-line WhatsApp alerts when a customer requests human takeover.

The notification destination is the explicitly authorized IBROWS legacy
business WhatsApp number, NOT the owner's personal number.

Free-form alerts require the recipient's own inbound 24-hour WhatsApp window.
Outside it, only a configured, Meta-approved utility template is attempted.
Email fallback is intentionally implemented by the existing app code.

Nothing here modifies lead status, AI pause state, payments or customer chats.
"""
import os
import re
from urllib.parse import quote

BUSINESS_ALERT_NUMBER = "265882242594"
DISPLAY_ALERT_NUMBER = "0882 242 594"
OWNER_ENABLE_COMMAND = "ibrows alerts on"
MAX_FIELD_LENGTH = 72


def is_owner_activation(number, text):
    return (str(number or "").strip() == BUSINESS_ALERT_NUMBER
            and " ".join(str(text or "").casefold().split()) == OWNER_ENABLE_COMMAND)


def owner_activation_reply():
    return (
        "IBROWS human-takeover WhatsApp alerts: enabled for 0882 242 594. "
        "For the next 24 hours after this message, free-form takeover alerts "
        "can be sent here. Sending another 'IBROWS ALERTS ON' renews the window. "
        "For reliable alerts after 24 hours, a Meta-approved WhatsApp utility "
        "template must be enabled. Email alerts remain the backup."
    )


def _safe_field(value, default):
    clean = " ".join(str(value or "").split())
    return clean[:MAX_FIELD_LENGTH] if clean else default


def _inbox_url(customer_number):
    digits = re.sub(r"[^0-9]", "", str(customer_number or ""))
    if not 7 <= len(digits) <= 20:
        return "https://www.ibrowsenterprise.com/admin/inbox"
    return "https://www.ibrowsenterprise.com/admin/inbox/" + digits


def freeform_alert(customer_name, service, customer_number):
    name = _safe_field(customer_name, "WhatsApp customer")
    category = _safe_field(service, "General Enquiry")
    return (
        "IBROWS HUMAN TAKEOVER ALERT\n"
        f"Customer: {name}\n"
        f"Service: {category}\n"
        "AI paused for this conversation. Please respond inside the secure "
        "IBROWS Inbox:\n"
        f"{_inbox_url(customer_number)}\n\n"
        "Reply to the CUSTOMER from the IBROWS Inbox, not from this notification chat."
    )


def template_payload(customer_name, service, *, template_name, language="en_US"):
    """Approved template must have 2 BODY variables: customer name and service."""
    if not re.fullmatch(r"[a-z0-9_]{1,256}", str(template_name or "")):
        raise ValueError("Unsafe/absent approved template name")
    if not re.fullmatch(r"[a-z]{2}(?:_[A-Z]{2})?", str(language or "")):
        raise ValueError("Unsafe template language")
    return {
        "messaging_product": "whatsapp",
        "to": BUSINESS_ALERT_NUMBER,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
            "components": [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": _safe_field(customer_name, "Customer")},
                    {"type": "text", "text": _safe_field(service, "General Enquiry")},
                ],
            }],
        },
    }


def deliver_handover_alert(
    customer_name, customer_number, service, *,
    window_open, send_text, token, phone_number_id, http_post,
    template_name="", template_language="en_US",
):
    """Return (status, channel), with no claim of device delivery.

    The WhatsApp API success status means accepted for processing; it is not
    an end-to-end handset delivery receipt.
    """
    if bool(window_open):
        try:
            accepted = bool(send_text(
                BUSINESS_ALERT_NUMBER,
                freeform_alert(customer_name, service, customer_number),
            ))
            return ("ACCEPTED" if accepted else "FAILED", "whatsapp_24h")
        except Exception as exc:
            print("IBROWS HANDOVER WHATSAPP TEXT FAILED: "
                  + type(exc).__name__, flush=True)
            return "FAILED", "whatsapp_24h"

    # No free-form business-initiated message outside recipient's 24h window.
    if not template_name:
        return "TEMPLATE_REQUIRED", "whatsapp_template"
    if not token or not phone_number_id:
        return "MISSING_API_CONFIG", "whatsapp_template"

    try:
        payload = template_payload(
            customer_name, service, template_name=template_name,
            language=template_language,
        )
    except ValueError:
        return "BAD_TEMPLATE_CONFIG", "whatsapp_template"

    try:
        response = http_post(
            f"https://graph.facebook.com/v25.0/{phone_number_id}/messages",
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=8,
        )
        ok = 200 <= response.status_code < 300
        # Do not log request content, phone numbers, bearer token, or Graph
        # response text; a failure may contain sensitive account information.
        if not ok:
            print(f"IBROWS HANDOVER WHATSAPP TEMPLATE HTTP {response.status_code}",
                  flush=True)
        return ("ACCEPTED" if ok else "FAILED", "whatsapp_template")
    except Exception as exc:
        print("IBROWS HANDOVER WHATSAPP TEMPLATE ERROR: "
              + type(exc).__name__, flush=True)
        return "FAILED", "whatsapp_template"


def save_alert_audit(db_factory, lead_id, status, channel):
    """Record only the route and API outcome, not the client's private message."""
    if lead_id is None:
        return False
    try:
        with db_factory() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS ibrows_handover_whatsapp_alerts (
                        id BIGSERIAL PRIMARY KEY,
                        lead_id BIGINT NOT NULL,
                        recipient_last4 TEXT NOT NULL,
                        channel TEXT NOT NULL,
                        delivery_status TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    INSERT INTO ibrows_handover_whatsapp_alerts(
                        lead_id,recipient_last4,channel,delivery_status
                    ) VALUES(%s,%s,%s,%s)
                """, (lead_id, BUSINESS_ALERT_NUMBER[-4:], channel, status))
            conn.commit()
        return True
    except Exception as exc:
        print("IBROWS HANDOVER WHATSAPP AUDIT UNAVAILABLE: "
              + type(exc).__name__, flush=True)
        return False


def configured_template():
    """Set only after its exact name/language is approved in WhatsApp Manager."""
    return (os.environ.get("IBROWS_HANDOVER_WHATSAPP_TEMPLATE") or "").strip()


def configured_template_language():
    return (os.environ.get("IBROWS_HANDOVER_WHATSAPP_TEMPLATE_LANGUAGE")
            or "en_US").strip()
