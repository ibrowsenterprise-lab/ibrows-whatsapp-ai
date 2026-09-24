import os
import re
import json
import secrets
import time
import threading
from datetime import timedelta

import requests
import psycopg

from functools import wraps
from flask import (
    Flask,
    request,
    session,
    redirect,
    url_for,
    render_template_string,
    abort,
)
from openai import OpenAI


# =========================================================
# IBROWS WHATSAPP AI BUSINESS ASSISTANT
# =========================================================

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")

BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
NOTIFICATION_EMAIL = os.environ.get("NOTIFICATION_EMAIL") or "ibrowsenterprise@gmail.com"
BREVO_SENDER_EMAIL = os.environ.get("BREVO_SENDER_EMAIL") or "ibrowsenterprise@gmail.com"
BREVO_SENDER_NAME = os.environ.get("BREVO_SENDER_NAME") or "IBROWS Enterprise"
LEAD_DASHBOARD_URL = "https://ibrows-whatsapp-ai-1.onrender.com/admin/leads"

app.secret_key = FLASK_SECRET_KEY

app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
)

# Admin login throttling is intentionally lightweight and in-memory.
# It protects this single-worker Render service without storing passwords or attempts in the database.
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_LOCKOUT_SECONDS = 15 * 60
_login_attempts = {}
_login_attempts_lock = threading.Lock()

client = OpenAI(
    api_key=OPENAI_API_KEY,
    timeout=12.0,
    max_retries=0,
)


# =========================================================
# PRIVACY RETENTION
# =========================================================
CONVERSATION_RETENTION_DAYS = 90
WHATSAPP_RETRY_RETENTION_DAYS = 30
LEAD_RETENTION_DAYS = 365
PRIVACY_CLEANUP_INTERVAL_SECONDS = 6 * 60 * 60
_last_privacy_cleanup = 0.0

# =========================================================
# DATABASE
# =========================================================

def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured.")

    return psycopg.connect(DATABASE_URL)


def init_database():
    with get_db() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id BIGSERIAL PRIMARY KEY,
                    customer_number TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS
                idx_conversations_customer
                ON conversations(customer_number, created_at DESC)
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS leads (
                    id BIGSERIAL PRIMARY KEY,
                    customer_number TEXT NOT NULL,
                    customer_name TEXT,
                    service TEXT,
                    summary TEXT,
                    handover_reason TEXT,
                    status TEXT NOT NULL DEFAULT 'NEW',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # Upgrade older leads table without deleting existing leads.
            cur.execute("""
                ALTER TABLE leads
                ADD COLUMN IF NOT EXISTS customer_name TEXT
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS
                idx_leads_customer
                ON leads(customer_number, created_at DESC)
            """)

            # Prevent Meta webhook retries from processing the same
            # incoming WhatsApp message more than once.
            cur.execute("""
                CREATE TABLE IF NOT EXISTS processed_whatsapp_messages (
                    message_id TEXT PRIMARY KEY,
                    customer_number TEXT,
                    status TEXT NOT NULL DEFAULT 'PROCESSING',
                    reply_text TEXT,
                    attempts INTEGER NOT NULL DEFAULT 1,
                    processed_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            cur.execute("""
                ALTER TABLE processed_whatsapp_messages
                ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'COMPLETED'
            """)
            cur.execute("""
                ALTER TABLE processed_whatsapp_messages
                ADD COLUMN IF NOT EXISTS reply_text TEXT
            """)
            cur.execute("""
                ALTER TABLE processed_whatsapp_messages
                ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 1
            """)
            cur.execute("""
                ALTER TABLE processed_whatsapp_messages
                ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS lead_notification_status (
                    lead_id BIGINT PRIMARY KEY REFERENCES leads(id) ON DELETE CASCADE,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # Persistent service-health incidents for admin monitoring.
            cur.execute("""
                CREATE TABLE IF NOT EXISTS system_incidents (
                    incident_key TEXT PRIMARY KEY,
                    component TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    occurrence_count INTEGER NOT NULL DEFAULT 1,
                    last_error_class TEXT,
                    alert_sent_at TIMESTAMPTZ,
                    recovered_at TIMESTAMPTZ
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_system_incidents_status
                ON system_incidents(status, last_seen DESC)
            """)

            # Human takeover state. When paused, incoming customer messages
            # are stored for context but the AI does not reply.
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ai_takeover_state (
                    customer_number TEXT PRIMARY KEY,
                    ai_paused BOOLEAN NOT NULL DEFAULT FALSE,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

        conn.commit()

    print("DATABASE READY", flush=True)



def cleanup_expired_data(force=False):
    global _last_privacy_cleanup
    now = time.monotonic()
    if not force and now - _last_privacy_cleanup < PRIVACY_CLEANUP_INTERVAL_SECONDS:
        return
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM conversations WHERE created_at < NOW() - (%s * INTERVAL '1 day')",
                            (CONVERSATION_RETENTION_DAYS,))
                cur.execute("DELETE FROM processed_whatsapp_messages WHERE updated_at < NOW() - (%s * INTERVAL '1 day')",
                            (WHATSAPP_RETRY_RETENTION_DAYS,))
                cur.execute("DELETE FROM leads WHERE updated_at < NOW() - (%s * INTERVAL '1 day')",
                            (LEAD_RETENTION_DAYS,))
                cur.execute("""
                    DELETE FROM ai_takeover_state a
                    WHERE NOT EXISTS (SELECT 1 FROM leads l WHERE l.customer_number=a.customer_number)
                      AND NOT EXISTS (SELECT 1 FROM conversations c WHERE c.customer_number=a.customer_number)
                """)
            conn.commit()
        _last_privacy_cleanup = now
        print("PRIVACY RETENTION CLEANUP COMPLETED", flush=True)
    except Exception as error:
        print(f"Privacy cleanup error: {type(error).__name__}", flush=True)


def delete_customer_data(customer_number):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE customer_number=%s", (customer_number,))
            cur.execute("DELETE FROM processed_whatsapp_messages WHERE customer_number=%s", (customer_number,))
            cur.execute("DELETE FROM leads WHERE customer_number=%s", (customer_number,))
            cur.execute("DELETE FROM ai_takeover_state WHERE customer_number=%s", (customer_number,))
        conn.commit()
    print("CUSTOMER DATA DELETION COMPLETED", flush=True)



def redact_sensitive_credentials_for_storage(content):
    """
    Redact clearly labelled authentication/payment credentials before
    conversation text is written to PostgreSQL.

    This is deliberately conservative: it targets values attached to explicit
    credential labels and does not redact ordinary phone numbers, prices,
    dates, quantities, room counts, dimensions, or quotation amounts.
    """
    text = str(content or "")

    patterns = (
        # PIN / OTP / one-time-password / verification/security codes.
        r"(?i)\b(pin|otp|one[\s-]?time(?:\s+password|\s+pin|\s+code)?|verification\s+code|security\s+code)\b"
        r"(\s*(?:is|=|:|-)?\s*)([A-Za-z0-9][A-Za-z0-9._\-]{2,31})",

        # Passwords / passcodes / passphrases.
        r"(?i)\b(password|passcode|passphrase)\b"
        r"(\s*(?:is|=|:|-)?\s*)(\S{3,128})",

        # CVV/CVC/CID card security values.
        r"(?i)\b(cvv2?|cvc2?|card\s+security\s+code|card\s+verification\s+code)\b"
        r"(\s*(?:is|=|:|-)?\s*)([0-9]{3,4})",
    )

    for pattern in patterns:
        text = re.sub(
            pattern,
            lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]",
            text
        )

    return text



def save_message(customer_number, role, content):
    safe_content = redact_sensitive_credentials_for_storage(content)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversations
                    (customer_number, role, content)
                VALUES (%s, %s, %s)
                """,
                (customer_number, role, safe_content)
            )

        conn.commit()


def get_recent_conversation(customer_number, limit=12):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content
                FROM conversations
                WHERE customer_number = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (customer_number, limit)
            )

            rows = cur.fetchall()

    rows.reverse()

    return [
        {
            "role": role,
            "content": content
        }
        for role, content in rows
    ]


def claim_whatsapp_message(message_id, customer_number):
    """Return (action, saved_reply). action is PROCESS, RETRY_REPLY, or IGNORE."""
    if not message_id:
        return "PROCESS", None

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO processed_whatsapp_messages (
                    message_id, customer_number, status, attempts, updated_at
                )
                VALUES (%s, %s, 'PROCESSING', 1, NOW())
                ON CONFLICT (message_id) DO NOTHING
                RETURNING message_id
                """,
                (message_id, customer_number)
            )
            if cur.fetchone() is not None:
                conn.commit()
                return "PROCESS", None

            cur.execute(
                """
                SELECT status, reply_text, updated_at
                FROM processed_whatsapp_messages
                WHERE message_id = %s
                FOR UPDATE
                """,
                (message_id,)
            )
            row = cur.fetchone()
            if not row:
                conn.commit()
                return "IGNORE", None

            status, reply_text, updated_at = row
            if status == "COMPLETED":
                conn.commit()
                return "IGNORE", None

            if status == "FAILED" and reply_text:
                cur.execute(
                    """
                    UPDATE processed_whatsapp_messages
                    SET status='PROCESSING', attempts=attempts+1, updated_at=NOW()
                    WHERE message_id=%s
                    """,
                    (message_id,)
                )
                conn.commit()
                return "RETRY_REPLY", reply_text

            # A worker may have died mid-processing. Reclaim only after 90 seconds.
            cur.execute(
                """
                UPDATE processed_whatsapp_messages
                SET status='PROCESSING', attempts=attempts+1, updated_at=NOW()
                WHERE message_id=%s
                  AND status IN ('PROCESSING','FAILED')
                  AND updated_at < NOW() - INTERVAL '90 seconds'
                RETURNING message_id
                """,
                (message_id,)
            )
            reclaimed = cur.fetchone() is not None
            conn.commit()
            return ("PROCESS", None) if reclaimed else ("IGNORE", None)


def store_pending_reply(message_id, reply_text):
    if not message_id:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE processed_whatsapp_messages
                SET reply_text=%s, updated_at=NOW()
                WHERE message_id=%s
                """,
                (reply_text, message_id)
            )
        conn.commit()


def finish_whatsapp_message(message_id, success):
    if not message_id:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE processed_whatsapp_messages
                SET status=%s, updated_at=NOW()
                WHERE message_id=%s
                """,
                ("COMPLETED" if success else "FAILED", message_id)
            )
        conn.commit()

def is_ai_paused(customer_number):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ai_paused
                FROM ai_takeover_state
                WHERE customer_number = %s
                """,
                (customer_number,)
            )
            row = cur.fetchone()
    return bool(row and row[0])


def set_ai_paused(customer_number, paused):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ai_takeover_state (customer_number, ai_paused, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (customer_number)
                DO UPDATE SET ai_paused = EXCLUDED.ai_paused, updated_at = NOW()
                """,
                (customer_number, bool(paused))
            )
        conn.commit()



def detect_explicit_human_handover(customer_message):
    """
    Detect only clear requests to stop AI or speak to a human.
    This deliberately uses local rules so handover still works when OpenAI
    is unavailable or out of credits.
    """
    text = " ".join(str(customer_message or "").lower().split())

    strong_phrases = (
        "speak to a manager",
        "talk to a manager",
        "speak with a manager",
        "talk with a manager",
        "speak to a person",
        "talk to a person",
        "speak with a person",
        "talk with a person",
        "speak to a human",
        "talk to a human",
        "speak with a human",
        "talk with a human",
        "human please",
        "human agent",
        "real person",
        "customer service agent",
        "customer care agent",
        "stop ai",
        "stop the ai",
        "pause ai",
        "turn off ai",
        "no more ai",
        "don't want to talk to ai",
        "do not want to talk to ai",
        "dont want to talk to ai",
        "don't want ai",
        "do not want ai",
        "dont want ai",
        "ndikufuna kulankhula ndi munthu",
        "ndikufuna munthu",
        "ndilumikizeni ndi munthu",
        "ndilumikizeni ndi manager",
        "ndikufuna manager",
        "sindikufuna kulankhula ndi ai",
        "sindikufuna ai",
    )

    return any(phrase in text for phrase in strong_phrases)


def handle_local_human_handover(
    customer_number,
    customer_name,
    customer_message,
):
    """
    Pause AI and create/update a handover lead without calling OpenAI.
    Returns the fixed customer acknowledgement.
    """
    save_message(customer_number, "user", customer_message)

    reply = (
        "Thank you for letting us know. I have paused the AI assistant "
        "for this conversation and recorded your request for human assistance. "
        "The IBROWS team will need to assist you from here."
    )

    # Pause first so the customer's explicit preference is respected even
    # if email notification later fails.
    set_ai_paused(customer_number, True)

    try:
        lead_id, is_new_lead = create_or_update_lead(
            customer_number=customer_number,
            customer_name=customer_name,
            service="Human Handover",
            summary="Customer explicitly requested human assistance and asked to stop AI interaction.",
            handover_reason="Explicit request to speak with a human/manager or stop AI."
        )

        if is_new_lead:
            send_new_lead_email(
                lead_id=lead_id,
                customer_name=customer_name,
                customer_number=customer_number,
                service="Human Handover",
                summary="Customer explicitly requested human assistance and asked to stop AI interaction.",
                handover_reason="Explicit request to speak with a human/manager or stop AI."
            )
    except Exception as handover_error:
        print(
            f"Local handover lead/notification error: {type(handover_error).__name__}",
            flush=True
        )

    save_message(customer_number, "assistant", reply)
    return reply


def get_paused_customers():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT customer_number
                FROM ai_takeover_state
                WHERE ai_paused = TRUE
                """
            )
            return {row[0] for row in cur.fetchall()}


def canonicalize_service(service):
    """Normalize AI service labels so one enquiry updates the right open lead."""
    value = " ".join(str(service or "General Enquiry").strip().lower().split())

    aliases = {
        "landscaping": "Landscaping",
        "landscaping service": "Landscaping",
        "landscaping services": "Landscaping",
        "fumigation": "Fumigation",
        "fumigation service": "Fumigation",
        "fumigation services": "Fumigation",
        "cleaning": "Cleaning Services",
        "cleaning service": "Cleaning Services",
        "cleaning services": "Cleaning Services",
        "car wash": "Car Wash",
        "carwash": "Car Wash",
        "construction": "Construction",
        "construction services": "Construction",
        "agro": "Agro Services",
        "agro services": "Agro Services",
        "agriculture": "Agro Services",
        "website": "Website Development",
        "website development": "Website Development",
        "web development": "Website Development",
        "whatsapp ai assistant": "WhatsApp AI Assistant",
        "ai business assistant": "WhatsApp AI Assistant",
        "career assist": "Career Assist",
        "scholarship search": "Scholarship Search",
        "cv and cover letter": "CV & Cover Letter",
        "cv & cover letter": "CV & Cover Letter",
        "business services": "Business Services",
        "business registration": "Business Registration",
        "graphic design": "Graphic Design",
        "branding": "Branding",
        "social media": "Social Media Management",
        "social media management": "Social Media Management",
        "photo restoration": "Photo Restoration",
    }

    return aliases.get(value, str(service or "General Enquiry").strip() or "General Enquiry")


def create_or_update_lead(
    customer_number,
    customer_name,
    service,
    summary,
    handover_reason
):
    service = canonicalize_service(service)

    with get_db() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT id
                FROM leads
                WHERE customer_number = %s
                  AND status = 'NEW'
                  AND LOWER(COALESCE(service, '')) = LOWER(%s)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (customer_number, service)
            )

            existing = cur.fetchone()

            if existing:
                lead_id = existing[0]

                cur.execute(
                    """
                    UPDATE leads
                    SET customer_name = COALESCE(
                            NULLIF(%s, ''),
                            customer_name
                        ),
                        service = %s,
                        summary = %s,
                        handover_reason = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        customer_name,
                        service,
                        summary,
                        handover_reason,
                        lead_id
                    )
                )

                print(
                    f"LEAD UPDATED: {lead_id}",
                    flush=True
                )

            else:
                cur.execute(
                    """
                    INSERT INTO leads (
                        customer_number,
                        customer_name,
                        service,
                        summary,
                        handover_reason
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        customer_number,
                        customer_name,
                        service,
                        summary,
                        handover_reason
                    )
                )

                lead_id = cur.fetchone()[0]

                print(
                    f"NEW LEAD CREATED: {lead_id}",
                    flush=True
                )

        conn.commit()

    return lead_id, existing is None


def record_lead_notification(lead_id, status, error=None):
    """Persist notification delivery state without storing API secrets."""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO lead_notification_status
                        (lead_id, status, attempts, last_error, updated_at)
                    VALUES (%s, %s, 1, %s, NOW())
                    ON CONFLICT (lead_id) DO UPDATE SET
                        status=EXCLUDED.status,
                        attempts=lead_notification_status.attempts + 1,
                        last_error=EXCLUDED.last_error,
                        updated_at=NOW()
                    """,
                    (lead_id, status, error)
                )
            conn.commit()
    except Exception as tracking_error:
        print(
            f"Lead notification tracking error: {type(tracking_error).__name__}",
            flush=True
        )



MONITORED_COMPONENTS = {"OpenAI", "WhatsApp", "Brevo"}

def record_system_failure(component, error_class):
    if component not in MONITORED_COMPONENTS:
        return False
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO system_incidents
                    (incident_key, component, status, first_seen, last_seen,
                     occurrence_count, last_error_class, alert_sent_at, recovered_at)
                    VALUES (%s,%s,'OPEN',NOW(),NOW(),1,%s,NULL,NULL)
                    ON CONFLICT (incident_key) DO UPDATE SET
                      status='OPEN', last_seen=NOW(),
                      occurrence_count=CASE WHEN system_incidents.status='OPEN'
                        THEN system_incidents.occurrence_count+1 ELSE 1 END,
                      first_seen=CASE WHEN system_incidents.status='OPEN'
                        THEN system_incidents.first_seen ELSE NOW() END,
                      last_error_class=EXCLUDED.last_error_class,
                      alert_sent_at=CASE WHEN system_incidents.status='OPEN'
                        THEN system_incidents.alert_sent_at ELSE NULL END,
                      recovered_at=NULL
                """,(component.lower(),component,str(error_class)[:120]))
            conn.commit()
        return True
    except Exception as exc:
        print(f"MONITORING RECORD FAILURE: {type(exc).__name__}",flush=True)
        return False

def mark_system_recovered(component):
    if component not in MONITORED_COMPONENTS:
        return False
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE system_incidents
                    SET status='RECOVERED', recovered_at=NOW(), last_seen=NOW()
                    WHERE incident_key=%s AND status='OPEN'""",(component.lower(),))
                changed=cur.rowcount>0
            conn.commit()
        return changed
    except Exception as exc:
        print(f"MONITORING RECOVERY FAILURE: {type(exc).__name__}",flush=True)
        return False

def get_open_system_incidents():
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT component,first_seen,last_seen,occurrence_count,
                    last_error_class,alert_sent_at FROM system_incidents
                    WHERE status='OPEN' ORDER BY last_seen DESC""")
                return cur.fetchall()
    except Exception as exc:
        print(f"MONITORING READ FAILURE: {type(exc).__name__}",flush=True)
        return []

def send_system_alert_email(component,error_class):
    # Brevo cannot reliably alert us about its own outage.
    if component=="Brevo" or not BREVO_API_KEY or not NOTIFICATION_EMAIL or not BREVO_SENDER_EMAIL:
        return False
    try:
        r=requests.post("https://api.brevo.com/v3/smtp/email",
            headers={"accept":"application/json","api-key":BREVO_API_KEY,
                     "content-type":"application/json"},
            json={"sender":{"name":BREVO_SENDER_NAME,"email":BREVO_SENDER_EMAIL},
                  "to":[{"email":NOTIFICATION_EMAIL}],
                  "subject":f"IBROWS AI System Alert: {component}",
                  "textContent":("The IBROWS AI Business Assistant detected a service failure.\\n\\n"
                    f"Component: {component}\\nError class: {error_class}\\n\\n"
                    "Customer-facing safeguards remain active where available. "
                    "Please review Render and the admin monitoring page.")},
            timeout=8)
        return 200<=r.status_code<300
    except requests.RequestException:
        return False

def maybe_alert_system_failure(component,error_class):
    if not record_system_failure(component,error_class) or component=="Brevo":
        return
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT alert_sent_at FROM system_incidents
                    WHERE incident_key=%s AND status='OPEN'""",(component.lower(),))
                row=cur.fetchone()
                if not row or row[0] is not None:
                    return
            if not send_system_alert_email(component,error_class):
                return
            with conn.cursor() as cur:
                cur.execute("""UPDATE system_incidents SET alert_sent_at=NOW()
                    WHERE incident_key=%s AND status='OPEN' AND alert_sent_at IS NULL""",
                    (component.lower(),))
            conn.commit()
    except Exception as exc:
        print(f"MONITORING ALERT FAILURE: {type(exc).__name__}",flush=True)


def send_new_lead_email(
    lead_id,
    customer_name,
    customer_number,
    service,
    summary,
    handover_reason
):
    if not BREVO_API_KEY or not NOTIFICATION_EMAIL or not BREVO_SENDER_EMAIL:
        print(
            "Lead email skipped: Brevo API settings are not fully configured.",
            flush=True
        )
        record_lead_notification(lead_id, "FAILED", "Brevo configuration incomplete")
        return False

    display_name = customer_name or "Not provided"
    subject = f"New IBROWS Lead #{lead_id}: {service}"
    body = f"""A new qualified lead has been captured by the IBROWS AI Business Assistant.

Lead ID: {lead_id}
Customer: {display_name}
WhatsApp: +{customer_number}
Service: {service}

Lead summary:
{summary}

Human follow-up reason:
{handover_reason}

Lead dashboard:
{LEAD_DASHBOARD_URL}

IBROWS Enterprise
Kupanga zofanana, mosiyana
"""

    payload = {
        "sender": {
            "name": BREVO_SENDER_NAME,
            "email": BREVO_SENDER_EMAIL,
        },
        "to": [
            {"email": NOTIFICATION_EMAIL}
        ],
        "subject": subject,
        "textContent": body,
    }

    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "accept": "application/json",
                "api-key": BREVO_API_KEY,
                "content-type": "application/json",
            },
            json=payload,
            timeout=8,
        )

        if 200 <= response.status_code < 300:
            mark_system_recovered("Brevo")
            record_lead_notification(lead_id, "SENT")
            print(
                f"NEW LEAD EMAIL SENT: {lead_id}",
                flush=True
            )
            return True

        error_label = f"Brevo HTTP {response.status_code}"
        record_system_failure("Brevo", f"HTTP{response.status_code}")
        record_lead_notification(lead_id, "FAILED", error_label)
        print(
            f"Lead email error for lead {lead_id}: {error_label}",
            flush=True
        )
        return False

    except requests.RequestException as error:
        error_label = type(error).__name__
        record_system_failure("Brevo", error_label)
        record_lead_notification(lead_id, "FAILED", error_label)
        print(
            f"Lead email error for lead {lead_id}: {error_label}",
            flush=True
        )
        return False


def get_all_leads():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    customer_number,
                    customer_name,
                    service,
                    summary,
                    handover_reason,
                    status,
                    created_at,
                    updated_at
                FROM leads
                ORDER BY
                    CASE status
                        WHEN 'NEW' THEN 1
                        WHEN 'CONTACTED' THEN 2
                        WHEN 'CLOSED' THEN 3
                        ELSE 4
                    END,
                    updated_at DESC
            """)

            return cur.fetchall()


def get_lead_counts():
    counts = {
        "ALL": 0,
        "NEW": 0,
        "CONTACTED": 0,
        "CLOSED": 0
    }

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT status, COUNT(*)
                FROM leads
                GROUP BY status
            """)

            for status, count in cur.fetchall():
                counts["ALL"] += count

                if status in counts:
                    counts[status] = count

    return counts


def update_lead_status(lead_id, status):
    allowed = {"NEW", "CONTACTED", "CLOSED"}

    if status not in allowed:
        raise ValueError("Invalid lead status.")

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE leads
                SET status = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (status, lead_id)
            )

        conn.commit()


# =========================================================
# HOME / HEALTH
# =========================================================

@app.route("/", methods=["GET"])
def home():
    return "IBROWS WhatsApp AI Business Assistant is running.", 200


@app.route("/health", methods=["GET"])
def health():
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()

        return {
            "status": "ok",
            "database": "connected"
        }, 200

    except Exception as error:
        print(f"Health check error: {type(error).__name__}", flush=True)

        return {
            "status": "error",
            "database": "not connected"
        }, 500


# =========================================================
# ADMIN AUTHENTICATION
# =========================================================

def _login_client_key():
    # request.remote_addr is intentionally used instead of trusting a user-supplied
    # forwarding header. On this small single-worker service it provides a safe,
    # conservative throttle key.
    return request.remote_addr or "unknown"


def _login_is_locked(client_key):
    now = time.monotonic()
    with _login_attempts_lock:
        record = _login_attempts.get(client_key)
        if not record:
            return False
        attempts = [t for t in record.get("attempts", []) if now - t <= LOGIN_WINDOW_SECONDS]
        locked_until = record.get("locked_until", 0)
        if locked_until and now < locked_until:
            record["attempts"] = attempts
            return True
        if locked_until and now >= locked_until:
            _login_attempts.pop(client_key, None)
            return False
        record["attempts"] = attempts
        if not attempts:
            _login_attempts.pop(client_key, None)
        return False


def _record_failed_login(client_key):
    now = time.monotonic()
    with _login_attempts_lock:
        record = _login_attempts.setdefault(client_key, {"attempts": [], "locked_until": 0})
        record["attempts"] = [t for t in record["attempts"] if now - t <= LOGIN_WINDOW_SECONDS]
        record["attempts"].append(now)
        if len(record["attempts"]) >= LOGIN_MAX_ATTEMPTS:
            record["locked_until"] = now + LOGIN_LOCKOUT_SECONDS


def _clear_failed_logins(client_key):
    with _login_attempts_lock:
        _login_attempts.pop(client_key, None)


def admin_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin_login"))

        session.permanent = True
        return function(*args, **kwargs)

    return wrapper


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
    )
    if request.path.startswith("/admin"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


def get_csrf_token():
    token = session.get("csrf_token")

    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token

    return token


def validate_csrf():
    supplied = request.form.get("csrf_token", "")
    stored = session.get("csrf_token", "")

    if (
        not supplied
        or not stored
        or not secrets.compare_digest(supplied, stored)
    ):
        abort(403)


# =========================================================
# ADMIN LOGIN
# =========================================================

LOGIN_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1">

<title>IBROWS Admin Login</title>

<style>
* {
    box-sizing: border-box;
}

body {
    margin: 0;
    font-family: Arial, Helvetica, sans-serif;
    background: #f4f6f8;
    color: #17202a;
}

.wrapper {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
}

.card {
    width: 100%;
    max-width: 430px;
    background: white;
    border-radius: 18px;
    padding: 34px;
    box-shadow: 0 12px 40px rgba(0,0,0,.10);
}

.brand {
    font-size: 28px;
    font-weight: 800;
    margin-bottom: 4px;
}

.subtitle {
    color: #667085;
    margin-bottom: 28px;
}

label {
    display: block;
    font-weight: 700;
    margin-top: 16px;
    margin-bottom: 7px;
}

input {
    width: 100%;
    padding: 13px;
    border: 1px solid #d0d5dd;
    border-radius: 9px;
    font-size: 16px;
}

button {
    width: 100%;
    margin-top: 22px;
    padding: 13px;
    border: 0;
    border-radius: 9px;
    background: #111827;
    color: white;
    font-size: 16px;
    font-weight: 700;
    cursor: pointer;
}

.error {
    background: #fee4e2;
    color: #b42318;
    padding: 11px;
    border-radius: 8px;
    margin-bottom: 15px;
}

.footer {
    text-align: center;
    color: #98a2b3;
    margin-top: 24px;
    font-size: 13px;
}
</style>
</head>

<body>
<div class="wrapper">
<div class="card">

<div class="brand">IBROWS</div>
<div class="subtitle">AI Business Assistant — Administration</div>

{% if error %}
<div class="error">{{ error }}</div>
{% endif %}

<form method="POST">

<input
    type="hidden"
    name="csrf_token"
    value="{{ csrf_token }}"
>

<label>Username</label>
<input
    name="username"
    type="text"
    autocomplete="username"
    required
>

<label>Password</label>
<input
    name="password"
    type="password"
    autocomplete="current-password"
    required
>

<button type="submit">Sign in</button>

</form>

<div class="footer">
Kupanga zofanana, mosiyana
</div>

</div>
</div>
</body>
</html>
"""


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if session.get("admin_authenticated"):
        return redirect(url_for("admin_leads"))

    error = None
    csrf_token = get_csrf_token()

    if request.method == "POST":

        validate_csrf()

        client_key = _login_client_key()
        if _login_is_locked(client_key):
            error = "Too many sign-in attempts. Please wait 15 minutes and try again."
            return render_template_string(
                LOGIN_TEMPLATE,
                error=error,
                csrf_token=get_csrf_token()
            ), 429

        username = request.form.get("username", "")
        password = request.form.get("password", "")

        username_ok = (
            ADMIN_USERNAME
            and secrets.compare_digest(
                username,
                ADMIN_USERNAME
            )
        )

        password_ok = (
            ADMIN_PASSWORD
            and secrets.compare_digest(
                password,
                ADMIN_PASSWORD
            )
        )

        if username_ok and password_ok:
            _clear_failed_logins(client_key)
            session.clear()
            session.permanent = True
            session["admin_authenticated"] = True
            session["csrf_token"] = secrets.token_urlsafe(32)

            return redirect(url_for("admin_leads"))

        _record_failed_login(client_key)
        error = "Incorrect username or password."

    return render_template_string(
        LOGIN_TEMPLATE,
        error=error,
        csrf_token=csrf_token
    )


@app.route("/admin/logout", methods=["POST"])
@admin_required
def admin_logout():
    validate_csrf()
    session.clear()

    return redirect(url_for("admin_login"))


# =========================================================
# ADMIN LEAD DASHBOARD
# =========================================================

DASHBOARD_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>IBROWS Lead Dashboard</title>
<style>
*{box-sizing:border-box} body{margin:0;background:#f5f7fa;color:#101828;font-family:Arial,sans-serif}
header{background:#101828;color:white;padding:16px 0;position:sticky;top:0;z-index:10}.header-inner,.container{max-width:980px;margin:auto;padding:0 16px}.header-inner{display:flex;justify-content:space-between;align-items:center;gap:12px}.brand{font-size:19px;font-weight:800}.tagline{font-size:12px;color:#d0d5dd;margin-top:3px}.logout{background:transparent;color:white;border:1px solid #667085;border-radius:8px;padding:8px 11px;font-weight:700}
h1{margin:24px 0 4px;font-size:26px}.description{color:#667085;margin:0 0 18px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:18px 0}.stat{background:white;padding:16px;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,.05)}.stat-number{font-size:26px;font-weight:800}.stat-label{color:#667085;font-size:13px;margin-top:3px}
.tools{background:white;border-radius:12px;padding:12px;margin:0 0 14px;box-shadow:0 2px 8px rgba(0,0,0,.05)}.search-row{display:flex;gap:8px}.search-row input{flex:1;min-width:0;border:1px solid #d0d5dd;border-radius:9px;padding:11px;font-size:15px}.search-row button{border:0;background:#101828;color:white;border-radius:9px;padding:0 16px;font-weight:700}.filters{display:flex;gap:7px;overflow-x:auto;padding-top:10px}.filter{white-space:nowrap;text-decoration:none;color:#344054;border:1px solid #d0d5dd;border-radius:20px;padding:7px 11px;font-size:13px;font-weight:700}.filter.active{background:#101828;color:white;border-color:#101828}.result-note{color:#667085;font-size:13px;margin:4px 2px 12px}
.lead{background:white;border-radius:14px;margin-bottom:14px;padding:17px;box-shadow:0 2px 8px rgba(0,0,0,.05)}.lead-top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.customer{font-size:19px;font-weight:800}.number{margin-top:4px}.number a{color:#175cd3;text-decoration:none}.status{font-weight:800;font-size:11px;padding:7px 10px;border-radius:20px;background:#eef2f6;white-space:nowrap}.service{margin-top:12px;font-weight:800}.summary,.reason{margin-top:9px;line-height:1.5}.reason{color:#667085}.meta{margin-top:12px;color:#98a2b3;font-size:12px;line-height:1.5}.quick{display:block;text-align:center;text-decoration:none;background:#157347;color:white;border-radius:9px;padding:11px 12px;margin-top:15px;font-weight:800}.privacy-link{display:block;text-align:center;text-decoration:none;color:#344054;border:1px solid #d0d5dd;border-radius:9px;padding:10px 12px;margin-top:8px;font-weight:700;font-size:13px}.takeover{margin-top:8px}.takeover button{width:100%;border:1px solid #d0d5dd;background:#fff;border-radius:9px;padding:11px 12px;font-weight:800}.takeover .resume{background:#101828;color:#fff;border-color:#101828}.ai-state{margin-top:8px;font-size:12px;font-weight:800;color:#667085}.actions{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:8px}.actions form{margin:0}.actions button{width:100%;height:100%;border:1px solid #d0d5dd;background:white;border-radius:8px;padding:9px 6px;font-weight:700;font-size:12px}.empty{background:white;padding:28px;border-radius:12px;text-align:center;color:#667085}.clear{display:inline-block;margin-top:10px;color:#175cd3;text-decoration:none;font-weight:700}
@media(max-width:700px){.stats{grid-template-columns:repeat(2,1fr)}.lead-top{align-items:flex-start}.container{padding:0 12px}.header-inner{padding:0 12px}.search-row button{padding:0 12px}.actions{grid-template-columns:1fr 1fr 1fr}}
</style>
</head>
<body>
<header><div class="header-inner"><div><div class="brand">IBROWS Lead Dashboard</div><div class="tagline">Kupanga zofanana, mosiyana</div><div><a href="{{ url_for('admin_monitoring') }}" style="color:white">System Monitoring</a></div></div><form method="POST" action="{{ url_for('admin_logout') }}"><input type="hidden" name="csrf_token" value="{{ csrf_token }}"><button class="logout" type="submit">Logout</button></form></div></header>
<div class="container">
<h1>Business Leads</h1><p class="description">Qualified enquiries captured by the IBROWS AI Business Assistant.</p>
<div class="stats"><div class="stat"><div class="stat-number">{{ counts.ALL }}</div><div class="stat-label">All Leads</div></div><div class="stat"><div class="stat-number">{{ counts.NEW }}</div><div class="stat-label">New</div></div><div class="stat"><div class="stat-number">{{ counts.CONTACTED }}</div><div class="stat-label">Contacted</div></div><div class="stat"><div class="stat-number">{{ counts.CLOSED }}</div><div class="stat-label">Closed</div></div></div>
<div class="tools"><form class="search-row" method="GET" action="{{ url_for('admin_leads') }}"><input name="q" value="{{ search_query }}" placeholder="Search name, number, service or enquiry"><input type="hidden" name="status" value="{{ status_filter }}"><button type="submit">Search</button></form><div class="filters">{% for item in ['ALL','NEW','CONTACTED','CLOSED'] %}<a class="filter {% if status_filter == item %}active{% endif %}" href="{{ url_for('admin_leads', status=item, q=search_query) }}">{{ item.title() }}</a>{% endfor %}</div></div>
<div class="result-note">Showing {{ leads|length }} lead{% if leads|length != 1 %}s{% endif %}{% if search_query %} matching “{{ search_query }}”{% endif %}.</div>
{% if leads %}{% for lead in leads %}<div class="lead"><div class="lead-top"><div><div class="customer">{{ lead.customer_name or 'WhatsApp Customer' }}</div><div class="number"><a href="https://wa.me/{{ lead.customer_number }}" target="_blank" rel="noopener noreferrer">+{{ lead.customer_number }}</a></div></div><div class="status">{{ lead.status }}</div></div><div class="service">{{ lead.service or 'General Enquiry' }}</div><div class="summary">{{ lead.summary or 'No summary available.' }}</div>{% if lead.handover_reason %}<div class="reason"><strong>Human follow-up:</strong> {{ lead.handover_reason }}</div>{% endif %}<div class="meta">Created: {{ lead.created_at.strftime('%d %b %Y %H:%M') }} &nbsp;|&nbsp; Updated: {{ lead.updated_at.strftime('%d %b %Y %H:%M') }}</div><a class="quick" href="https://wa.me/{{ lead.customer_number }}" target="_blank" rel="noopener noreferrer">Open WhatsApp Customer</a><a class="privacy-link" href="{{ url_for('admin_customer_privacy', customer_number=lead.customer_number) }}">Customer Data & Privacy</a><div class="ai-state">AI: {% if lead.ai_paused %}PAUSED — human takeover active{% else %}ACTIVE{% endif %}</div><form class="takeover" method="POST" action="{{ url_for('admin_ai_takeover', customer_number=lead.customer_number) }}"><input type="hidden" name="csrf_token" value="{{ csrf_token }}"><input type="hidden" name="paused" value="{% if lead.ai_paused %}0{% else %}1{% endif %}"><button class="{% if lead.ai_paused %}resume{% endif %}" type="submit">{% if lead.ai_paused %}Resume AI Assistant{% else %}Pause AI — Human Takeover{% endif %}</button></form><div class="actions">{% for target,label in [('NEW','Mark New'),('CONTACTED','Contacted'),('CLOSED','Close Lead')] %}{% if lead.status != target %}<form method="POST" action="{{ url_for('admin_lead_status', lead_id=lead.id) }}"><input type="hidden" name="csrf_token" value="{{ csrf_token }}"><input type="hidden" name="status" value="{{ target }}"><button type="submit">{{ label }}</button></form>{% else %}<button type="button" disabled>{{ label }}</button>{% endif %}{% endfor %}</div></div>{% endfor %}{% else %}<div class="empty">No leads match this view.<br><a class="clear" href="{{ url_for('admin_leads') }}">Clear search and filters</a></div>{% endif %}
</div></body></html>
"""


@app.route("/admin/leads", methods=["GET"])
@admin_required
def admin_leads():
    rows = get_all_leads()
    leads = []
    for row in rows:
        leads.append({
            "id": row[0], "customer_number": row[1], "customer_name": row[2],
            "service": row[3], "summary": row[4], "handover_reason": row[5],
            "status": row[6], "created_at": row[7], "updated_at": row[8]
        })

    paused_customers = get_paused_customers()
    for lead in leads:
        lead["ai_paused"] = lead["customer_number"] in paused_customers

    status_filter = request.args.get("status", "ALL").strip().upper()
    if status_filter not in {"ALL", "NEW", "CONTACTED", "CLOSED"}:
        status_filter = "ALL"
    search_query = request.args.get("q", "").strip()[:100]

    if status_filter != "ALL":
        leads = [lead for lead in leads if lead["status"] == status_filter]

    if search_query:
        needle = search_query.casefold()
        def matches(lead):
            searchable = " ".join(str(lead.get(field) or "") for field in (
                "customer_name", "customer_number", "service", "summary", "handover_reason"
            )).casefold()
            return needle in searchable
        leads = [lead for lead in leads if matches(lead)]

    return render_template_string(
        DASHBOARD_TEMPLATE,
        leads=leads,
        counts=get_lead_counts(),
        csrf_token=get_csrf_token(),
        status_filter=status_filter,
        search_query=search_query
    )



@app.route("/admin/customers/<customer_number>/ai", methods=["POST"])
@admin_required
def admin_ai_takeover(customer_number):
    validate_csrf()
    paused = request.form.get("paused", "")
    if paused not in {"0", "1"}:
        abort(400)
    set_ai_paused(customer_number, paused == "1")
    return redirect(url_for("admin_leads"))




MONITORING_TEMPLATE = """
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>IBROWS System Monitoring</title><style>
body{font-family:Arial,sans-serif;background:#f5f7fa;color:#1f2937;margin:0}.wrap{max-width:900px;margin:auto;padding:20px}
.card{background:#fff;border-radius:12px;padding:18px;margin:14px 0;box-shadow:0 1px 4px rgba(0,0,0,.08)}
.ok{border-left:5px solid #198754}.bad{border-left:5px solid #dc3545}.muted{color:#6b7280}a{color:#0d6efd}
</style></head><body><div class="wrap"><h1>IBROWS System Monitoring</h1>
<p class="muted">Open service incidents recorded by the assistant.</p>
<p><a href="{{ url_for('admin_leads') }}">← Back to Lead Dashboard</a></p>
{% if incidents %}{% for i in incidents %}<div class="card bad"><strong>{{ i[0] }} — OPEN INCIDENT</strong>
<p>Error class: {{ i[4] }}</p><p>Occurrences: {{ i[3] }}</p>
<p>First seen: {{ i[1] }}<br>Last seen: {{ i[2] }}</p>
<p>Alert email: {{ 'Sent' if i[5] else 'Not sent / unavailable' }}</p></div>{% endfor %}
{% else %}<div class="card ok"><strong>No open incidents recorded.</strong>
<p>No unresolved OpenAI, WhatsApp, or Brevo incident is currently recorded.</p></div>{% endif %}
</div></body></html>
"""

@app.route("/admin/monitoring",methods=["GET"])
@admin_required
def admin_monitoring():
    return render_template_string(MONITORING_TEMPLATE,incidents=get_open_system_incidents())


CUSTOMER_PRIVACY_TEMPLATE = """
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>IBROWS Customer Data</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f5f7fa;color:#101828;font-family:Arial,sans-serif}.wrap{max-width:620px;margin:auto;padding:24px 16px}.card{background:white;border-radius:14px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,.06)}.warning{background:#fff4ed;border-radius:10px;padding:13px;margin:16px 0;line-height:1.5}label{display:block;font-weight:700;margin:16px 0 7px}input{width:100%;padding:12px;border:1px solid #d0d5dd;border-radius:9px;font-size:16px}button{width:100%;padding:12px;border:0;border-radius:9px;background:#b42318;color:white;font-weight:800;margin-top:12px}.back{display:block;text-align:center;margin-top:14px;color:#175cd3;text-decoration:none;font-weight:700}.small{color:#667085;font-size:13px;line-height:1.5}</style>
</head><body><div class="wrap"><div class="card">
<h1>Customer Data & Privacy</h1><p><strong>+{{ customer_number }}</strong></p>
<p class="small">Use this only after IBROWS has reasonably verified that the customer is requesting deletion.</p>
<div class="warning"><strong>Permanent action:</strong> deletes this customer's conversations, leads, retry records, linked lead-notification records and AI takeover state. It cannot be undone from the dashboard.</div>
<form method="POST"><input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<label>Type DELETE to confirm</label><input name="confirmation" autocomplete="off" required>
<button type="submit">Permanently Delete Customer Data</button></form>
<a class="back" href="{{ url_for('admin_leads') }}">Cancel</a>
</div></div></body></html>
"""

@app.route("/admin/customers/<customer_number>/privacy", methods=["GET", "POST"])
@admin_required
def admin_customer_privacy(customer_number):
    if not customer_number.isdigit() or len(customer_number) > 20:
        abort(400)
    if request.method == "POST":
        validate_csrf()
        if request.form.get("confirmation", "").strip() != "DELETE":
            return render_template_string(CUSTOMER_PRIVACY_TEMPLATE,
                customer_number=customer_number, csrf_token=get_csrf_token()), 400
        delete_customer_data(customer_number)
        return redirect(url_for("admin_leads"))
    return render_template_string(CUSTOMER_PRIVACY_TEMPLATE,
        customer_number=customer_number, csrf_token=get_csrf_token())


@app.route(
    "/admin/leads/<int:lead_id>/status",
    methods=["POST"]
)
@admin_required
def admin_lead_status(lead_id):

    validate_csrf()

    status = request.form.get("status", "")

    if status not in {
        "NEW",
        "CONTACTED",
        "CLOSED"
    }:
        abort(400)

    update_lead_status(
        lead_id,
        status
    )

    return redirect(url_for("admin_leads"))


# =========================================================
# META WEBHOOK VERIFICATION
# =========================================================

@app.route("/webhook", methods=["GET"])
def verify_webhook():

    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("WEBHOOK VERIFIED", flush=True)
        return challenge, 200

    return "Verification failed", 403


# =========================================================
# RECEIVE WHATSAPP MESSAGES
# =========================================================

@app.route("/webhook", methods=["POST"])
def receive_webhook():

    data = request.get_json(silent=True)

    print("INCOMING WHATSAPP WEBHOOK", flush=True)
    cleanup_expired_data()

    try:

        value = data["entry"][0]["changes"][0]["value"]

        # Ignore sent/read/delivered status events.
        if "messages" not in value:
            return "EVENT_RECEIVED", 200

        message = value["messages"][0]

        # Text only for this version.
        if message.get("type") != "text":
            return "EVENT_RECEIVED", 200

        customer_number = message["from"]
        customer_message = message["text"]["body"]
        message_id = message.get("id", "")

        message_action, saved_reply = claim_whatsapp_message(
            message_id, customer_number
        )

        if message_action == "IGNORE":
            print("DUPLICATE WHATSAPP MESSAGE IGNORED", flush=True)
            return "EVENT_RECEIVED", 200

        if message_action == "RETRY_REPLY":
            sent = send_whatsapp_message(customer_number, saved_reply)
            finish_whatsapp_message(message_id, sent)
            print(
                "RETRIED SAVED WHATSAPP REPLY" if sent
                else "SAVED WHATSAPP REPLY RETRY FAILED",
                flush=True
            )
            return "EVENT_RECEIVED", 200

        customer_name = ""

        contacts = value.get("contacts", [])

        if contacts:
            customer_name = (
                contacts[0]
                .get("profile", {})
                .get("name", "")
            )

        print("TEXT MESSAGE ACCEPTED", flush=True)

        if is_ai_paused(customer_number):
            # Keep the customer's message in conversation history so the AI
            # has context when a human later resumes automation.
            save_message(customer_number, "user", customer_message)
            finish_whatsapp_message(message_id, True)
            print("AI PAUSED FOR CUSTOMER — HUMAN TAKEOVER ACTIVE", flush=True)
            return "EVENT_RECEIVED", 200

        # Critical fail-safe: an explicit request for a human must not depend
        # on OpenAI being available or having API credit.
        if detect_explicit_human_handover(customer_message):
            reply = handle_local_human_handover(
                customer_number=customer_number,
                customer_name=customer_name,
                customer_message=customer_message,
            )
            store_pending_reply(message_id, reply)
            sent = send_whatsapp_message(customer_number, reply)
            finish_whatsapp_message(message_id, sent)
            print("LOCAL HUMAN HANDOVER ACTIVATED", flush=True)
            return "EVENT_RECEIVED", 200

        result = generate_ai_reply(
            customer_number,
            customer_message
        )

        reply = result["reply"]

        print("AI REPLY GENERATED", flush=True)

        if result.get("lead_required"):

            try:

                service = canonicalize_service(
                    result.get("service", "General Enquiry")
                )
                summary = result.get(
                    "lead_summary",
                    customer_message
                )
                handover_reason = result.get(
                    "handover_reason",
                    "Human assistance required"
                )

                lead_id, is_new_lead = create_or_update_lead(
                    customer_number=customer_number,
                    customer_name=customer_name,
                    service=service,
                    summary=summary,
                    handover_reason=handover_reason
                )

                if is_new_lead:
                    send_new_lead_email(
                        lead_id=lead_id,
                        customer_name=customer_name,
                        customer_number=customer_number,
                        service=service,
                        summary=summary,
                        handover_reason=handover_reason
                    )

            except Exception as lead_error:

                print(
                    f"Lead creation error: {type(lead_error).__name__}",
                    flush=True
                )

                reply = (
                    "Thank you. Your enquiry needs assistance "
                    "from the IBROWS team. Please contact us on "
                    "+265 882 242 594 or email "
                    "ibrowsenterprise@gmail.com for further "
                    "assistance."
                )

        store_pending_reply(message_id, reply)
        sent = send_whatsapp_message(
            customer_number,
            reply
        )
        finish_whatsapp_message(message_id, sent)

    except Exception as error:

        print(
            f"Webhook processing error: {error}",
            flush=True
        )

    return "EVENT_RECEIVED", 200



AI_OUTPUT_KEYS = {
    "reply",
    "lead_required",
    "service",
    "lead_summary",
    "handover_reason",
}


def validate_ai_structured_output(result):
    """
    Strictly validate model output before it can affect WhatsApp replies,
    lead creation, or human-handover metadata.
    """
    if not isinstance(result, dict):
        raise ValueError("AI output must be a JSON object")

    if set(result.keys()) != AI_OUTPUT_KEYS:
        raise ValueError("AI output has missing or unexpected fields")

    if not isinstance(result["reply"], str):
        raise ValueError("AI reply must be a string")

    reply = result["reply"].strip()
    if not reply or len(reply) > 4000:
        raise ValueError("AI reply is empty or too long")

    if type(result["lead_required"]) is not bool:
        raise ValueError("lead_required must be a JSON boolean")

    for field in ("service", "lead_summary", "handover_reason"):
        if not isinstance(result[field], str):
            raise ValueError(f"{field} must be a string")

    service = result["service"].strip()
    lead_summary = result["lead_summary"].strip()
    handover_reason = result["handover_reason"].strip()

    if len(service) > 100:
        raise ValueError("service is too long")
    if len(lead_summary) > 1500:
        raise ValueError("lead_summary is too long")
    if len(handover_reason) > 800:
        raise ValueError("handover_reason is too long")

    if result["lead_required"]:
        # A lead must contain useful, explicit handover data. This prevents
        # malformed model output from silently creating low-quality leads.
        if not service or not lead_summary or not handover_reason:
            raise ValueError("qualified lead is missing required handover data")
    else:
        # Non-lead output is not allowed to smuggle lead/handover metadata
        # into downstream processing.
        service = ""
        lead_summary = ""
        handover_reason = ""

    return {
        "reply": reply,
        "lead_required": result["lead_required"],
        "service": service,
        "lead_summary": lead_summary,
        "handover_reason": handover_reason,
    }



# =========================================================
# OPENAI BUSINESS ASSISTANT
# =========================================================

def generate_ai_reply(
    customer_number,
    customer_message
):

    try:

        save_message(
            customer_number,
            "user",
            customer_message
        )

        conversation = get_recent_conversation(
            customer_number,
            limit=12
        )

        response = client.responses.create(

            model="gpt-5.6-luna",

            instructions="""
You are the official WhatsApp AI Business Assistant for
IBROWS Enterprise, a multi-service business operating in Malawi.

You help customers understand IBROWS services, understand
their needs, ask useful follow-up questions, provide accurate
approved information, identify genuine business leads, and
determine when human assistance is required.

You are an AI assistant.
Never pretend to be a human employee.


============================================================
OUTPUT FORMAT
============================================================

Return ONLY a valid JSON object.

Do not place the JSON inside markdown code fences.

Use exactly:

{
  "reply": "WhatsApp response shown to customer",
  "lead_required": false,
  "service": "",
  "lead_summary": "",
  "handover_reason": ""
}

lead_required must be true or false.

Set lead_required to TRUE when the enquiry is ready for useful human follow-up.

A quotation request BY ITSELF is not automatically a qualified lead when essential
scope details are still missing. First ask one or two concise questions needed for
the relevant service. Set lead_required to TRUE once enough information has been
collected for IBROWS staff to assess, quote, confirm availability, negotiate, or
continue the transaction.

Examples of useful qualification:
- Landscaping: location plus approximate property/yard size and the work required.
- Cleaning: location, property type/size or room count, and preferred date/timeframe.
- Fumigation: location, premises type/size, pest/problem, and preferred timeframe.
- Construction: location, project type/stage, and the work or scope requested.
- Car Wash: location, vehicle type/service required, and preferred date when relevant.
- Website/Digital work: what the business/project needs and the requested type of work.
- Agro/product enquiries: product/equipment needed, location, quantity or useful scope
  where relevant, especially when stock or sourcing must be confirmed.

Set lead_required to TRUE immediately when:
- The customer asks to speak with a person or explicitly requests human assistance.
- A complaint requires human attention.
- Payment confirmation, price negotiation, management approval, or another action
  clearly requires staff involvement and asking more AI qualification questions would
  not materially improve the handover.

Also set lead_required to TRUE when:
- The customer wants to proceed and enough practical information is available.
- A custom project has enough scope information for staff assessment.
- Product availability needs human confirmation after useful product/scope details
  have been collected.

Do not create a lead merely because someone says hello, asks a general question,
or asks for a quotation before essential service details have been collected.

When lead_required is true:

service:
Use ONE stable IBROWS service category. Prefer these exact labels when applicable:
Career Assist, Scholarship Search, CV & Cover Letter, Business Registration,
Business Services, Website Development, WhatsApp AI Assistant, Graphic Design,
Branding, Social Media Management, Photo Restoration, Cleaning Services, Car Wash,
Fumigation, Landscaping, Construction, Agro Services, General Enquiry.
Do not add words such as "services" to a label unless they are part of the exact label above.

lead_summary:
Summarize what the customer wants and important information
already collected.

handover_reason:
Explain briefly why human follow-up is appropriate.

Only say that the enquiry will be referred to the IBROWS team when
lead_required is true in the SAME JSON response. If lead_required is false, do not
imply that staff have already been notified or that referral has already happened.
Instead, ask for the missing qualification details.

Never claim that payment, booking, registration, purchase,
application, reservation, or another transaction has been
completed unless the system explicitly confirms it.


============================================================
CONVERSATION CONTEXT
============================================================

You receive recent messages belonging to the same WhatsApp
customer.

Use them to understand follow-up answers.

Do not ask again for information already supplied unless
clarification is genuinely required.

Do not invent conversation history beyond the supplied
messages.


============================================================
LANGUAGES
============================================================

You communicate in:

1. English
2. Chichewa
3. Tumbuka / Chitumbuka

Normally respond in the customer's language.

Use natural Malawian Chichewa when appropriate.

Use natural Malawian Tumbuka/Chitumbuka when appropriate.

Customers may mix languages naturally.

If language preference is genuinely unclear, you may ask:

"Welcome to IBROWS Enterprise 👋

Please choose your preferred language:
1. English
2. Chichewa
3. Tumbuka"


============================================================
IBROWS ENTERPRISE
============================================================

IBROWS Enterprise is a multi-service business based in
Lilongwe and serving clients countrywide across Malawi.

Base:
Lilongwe, Malawi

Service coverage:
Countrywide across Malawi. Never assume a customer must be
in Lilongwe. When location matters, ask for the customer's
town, district, or project location. Continue assisting
customers elsewhere in Malawi normally. For services where
travel, logistics, or availability may affect the quotation,
refer those details to the IBROWS team for confirmation and
do not invent extra charges or restrictions.

WhatsApp:
+265 882 242 594

Email:
ibrowsenterprise@gmail.com

Business line:
"Kupanga zofanana, mosiyana"


============================================================
CAREER ASSIST
============================================================

Services include:

- Job opportunity searches
- Job opportunity alerts
- Scholarship searches
- Scholarship opportunity alerts
- CV preparation
- CV review and improvement
- Tailored cover letters
- Job application assistance
- Application guidance
- Application tracking
- Eligibility screening
- Remote job opportunity searches
- International opportunity searches

APPROVED PRICES:

Opportunity Alerts:
MK20,000 per month

Career Assist:
MK50,000 per month

Career Assist Pro:
MK100,000 per month

Scholarship Search:
MK60,000 per month

One-Off CV + Cover Letter:
MK5,000

Single Job Application:
MK2,000

IBROWS does not sell jobs or scholarships.

IBROWS cannot guarantee employment, interviews,
scholarship awards, admission or selection.


============================================================
BUSINESS SERVICES
============================================================

Services include:

- Business registration assistance
- South Africa business setup assistance
- Business plans
- Accounting-related support
- Tax-related support

Do not invent prices.

Custom requirements may require an IBROWS quotation.


============================================================
DIGITAL & AI SERVICES
============================================================

Services include:

- Website development
- AI solutions
- AI business assistants
- WhatsApp AI business assistants
- Business automation
- Mobile application solutions
- Digital systems
- Technology consulting

For websites and custom technology work, useful information
may include:

- Type of business
- Purpose of the website/system
- Required features
- Whether the customer has content
- Whether the customer has branding
- Languages required
- Existing systems

Ask only one or two useful questions at a time.

Do not invent development prices.


============================================================
MEDIA, BRANDING & CONTENT
============================================================

Services include:

- Graphic design
- Branding
- Printing-related services
- Social media management
- Digital marketing campaigns
- AI-assisted content creation
- Photo restoration
- Photo enhancement

For old-photo restoration, IBROWS aims to improve quality
while preserving the identity and appearance of people in
the original photograph.

Do not invent prices.


============================================================
CLEANING SERVICES
============================================================

Services include:

- Office cleaning
- House cleaning
- Residential cleaning
- Commercial cleaning
- General property cleaning

Useful information may include:

- Property type
- General location (town/district anywhere in Malawi)
- Approximate size
- Cleaning required
- Preferred date
- Once-off or recurring

Ask only one or two questions at a time.

Do not invent prices.


============================================================
CAR WASH
============================================================

IBROWS provides car wash services.

Useful information may include:

- Vehicle type
- Cleaning/service required
- Preferred date
- Relevant location

Do not invent prices or opening hours.


============================================================
FUMIGATION
============================================================

IBROWS provides fumigation services.

Useful information may include:

- Type of premises
- General location (town/district anywhere in Malawi)
- Approximate size
- Pest problem
- Preferred date

Do not provide dangerous pesticide mixing instructions.

Do not invent prices.


============================================================
LANDSCAPING
============================================================

IBROWS provides landscaping services.

Useful information may include:

- Property/site type
- General location (town/district anywhere in Malawi)
- Approximate size
- Work required
- New landscaping or maintenance

Do not invent prices.


============================================================
CONSTRUCTION
============================================================

IBROWS provides construction-related services including:

- New construction
- Renovation
- Property improvement
- Maintenance
- Repairs
- Construction materials/services
- Other construction work

Useful information may include:

- Project type
- Project location (town/district anywhere in Malawi)
- Current stage
- Work required

Do not invent project costs.

Do not guarantee completion dates.

Construction quotations require IBROWS team confirmation.


============================================================
AGRO DEALING / AGRICULTURAL SERVICES
============================================================

IBROWS is involved in:

- Agricultural products
- Agricultural supplies
- Agricultural equipment
- Agricultural hardware
- Agricultural sourcing
- Agro dealing
- Agricultural supply services

Do not claim stock is available unless confirmed.

Do not invent prices.

Large orders and sourcing may require human confirmation.


============================================================
CUSTOMER SERVICE
============================================================

Be:

- Friendly
- Respectful
- Professional
- Helpful
- Conversational
- Concise

WhatsApp replies should normally be short.

Do not send the complete service catalogue unless asked.

If someone simply says hello, greet them naturally and ask
how IBROWS can assist.

Ask only one or two useful follow-up questions at a time.

Do not pressure customers.

Do not make false promises.


============================================================
PRICING
============================================================

Only quote prices explicitly approved above.

For services without approved prices, explain that pricing
depends on requirements and requires confirmation from the
IBROWS team.

Never guess.


============================================================
BUSINESS ACCURACY
============================================================

Never invent:

- Prices
- Discounts
- Addresses
- Opening hours
- Stock availability
- Staff names
- Payment details
- Bank accounts
- Mobile money numbers
- Completion dates
- Company policies
- Qualifications
- Partnerships
- Guarantees

Accuracy is more important than answering everything.


============================================================
SAFETY AND PRIVACY
============================================================

Never request:

- Passwords
- Banking PINs
- OTP codes
- Security codes
- Complete payment-card credentials

Do not expose information belonging to another customer.


============================================================
FINAL RULE
============================================================

Help the customer move toward the appropriate next step
while remaining accurate.

Respond to the latest message in the context of the recent
conversation.

Return ONLY the required JSON object.
""",

            input=conversation
        )

        raw_output = response.output_text.strip()

        parsed_result = json.loads(raw_output)
        final_result = validate_ai_structured_output(parsed_result)
        mark_system_recovered("OpenAI")

        print(
            "AI STRUCTURED OUTPUT VALIDATED: "
            f"lead_required={final_result['lead_required']}, "
            f"service={canonicalize_service(final_result['service'])}",
            flush=True
        )

        reply = final_result["reply"]

        save_message(
            customer_number,
            "assistant",
            reply
        )

        return final_result

    except Exception as error:

        error_class = type(error).__name__
        print(f"OpenAI/database error: {error_class}", flush=True)
        maybe_alert_system_failure("OpenAI", error_class)

        return {
            "reply": (
                "Thank you for contacting IBROWS Enterprise. "
                "Our AI assistant is temporarily unavailable. "
                "Please try again shortly, or ask to speak to a human "
                "if you need assistance from the IBROWS team."
            ),
            "lead_required": False,
            "service": "",
            "lead_summary": "",
            "handover_reason": ""
        }


# =========================================================
# SEND WHATSAPP MESSAGE
# =========================================================

def send_whatsapp_message(recipient, message):

    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print("WhatsApp credentials not configured.", flush=True)
        return False

    url = f"https://graph.facebook.com/v25.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "text",
        "text": {"body": message},
    }

    try:
        response = requests.post(
            url, headers=headers, json=payload, timeout=8
        )
        success = 200 <= response.status_code < 300
        print(f"WhatsApp send status: {response.status_code}", flush=True)
        if success:
            mark_system_recovered("WhatsApp")
            return True
        print("WhatsApp send failed with non-success HTTP status.", flush=True)
        maybe_alert_system_failure("WhatsApp", f"HTTP{response.status_code}")
        return False
    except requests.RequestException as error:
        error_class = type(error).__name__
        print(f"WhatsApp send error: {error_class}", flush=True)
        maybe_alert_system_failure("WhatsApp", error_class)
        return False


# =========================================================
# PRIVACY POLICY
# =========================================================

@app.route("/privacy", methods=["GET"])
def privacy_policy():
    return """
    <!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>IBROWS Privacy Policy</title></head>
    <body style="font-family:Arial,sans-serif;max-width:760px;margin:auto;padding:24px;line-height:1.6">
    <h1>Privacy Policy</h1><p><strong>IBROWS AI Business Assistant</strong></p>
    <p>IBROWS Enterprise uses WhatsApp to respond to customer enquiries and provide information about its services. Some responses are generated or assisted by artificial intelligence.</p>
    <h2>Information we process</h2><p>We may process your WhatsApp number, WhatsApp profile name made available to us, message content, enquiry details and information needed to follow up your request.</p>
    <h2>Why we use it</h2><p>We use this information to respond to enquiries, maintain recent conversation context, manage business leads, support human follow-up, prevent duplicate message processing, and operate and secure the service.</p>
    <h2>Service providers</h2><p>WhatsApp/Meta carries the messages. OpenAI may process relevant conversation content to generate AI-assisted responses. Brevo is used to send qualified-lead notifications to IBROWS management. Hosting and database providers process data as necessary to operate the service.</p>
    <h2>Retention</h2><p>Ordinary conversation history is retained for up to 90 days. Technical WhatsApp retry records are retained for up to 30 days. Inactive business leads are retained for up to 12 months, unless longer retention is reasonably required for legal, accounting, dispute-resolution, or other legitimate obligations.</p>
    <h2>Safety</h2><p>Do not send passwords, banking PINs, OTP/security codes or full payment-card credentials through the assistant. IBROWS does not sell customer personal information.</p>
    <h2>Your data</h2><p>You may request access to, correction of, or deletion of information associated with your interactions by contacting <strong>ibrowsenterprise@gmail.com</strong>. We may request reasonable information to verify the request before acting on it.</p>
    <p><strong>Last updated: 22 September 2026.</strong></p></body></html>
    """, 200


# =========================================================
# DATA DELETION PAGE
# =========================================================

@app.route("/data-deletion", methods=["GET"])
def data_deletion():
    return """
    <!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>IBROWS Data Deletion</title></head>
    <body style="font-family:Arial,sans-serif;max-width:760px;margin:auto;padding:24px;line-height:1.6">
    <h1>User Data Deletion</h1>
    <p>You may request deletion of personal information associated with your interactions with the IBROWS AI Business Assistant.</p>
    <p>Email <strong>ibrowsenterprise@gmail.com</strong> and state that you are requesting deletion of your IBROWS WhatsApp Assistant data. Include the WhatsApp number concerned, but never send passwords, PINs, OTPs or payment-card credentials.</p>
    <p>IBROWS may request reasonable information to verify the request. After verification, applicable assistant records can be deleted. Information that must be retained for a legal, accounting, dispute-resolution, or other legitimate obligation may be retained only as necessary.</p>
    <p>Standard retention: conversations up to 90 days; technical retry records up to 30 days; inactive business leads up to 12 months.</p>
    </body></html>
    """, 200


# =========================================================
# INITIALIZE DATABASE
# =========================================================

try:
    init_database()
    cleanup_expired_data(force=True)

except Exception as error:

    print(
        f"DATABASE INITIALIZATION ERROR: {type(error).__name__}",
        flush=True
    )


# =========================================================
# START APPLICATION
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
