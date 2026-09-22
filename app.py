import os
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
                    processed_at TIMESTAMPTZ DEFAULT NOW()
                )
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


def save_message(customer_number, role, content):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversations
                    (customer_number, role, content)
                VALUES (%s, %s, %s)
                """,
                (customer_number, role, content)
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
    """Return True only for the first delivery of a WhatsApp message ID."""
    if not message_id:
        return True

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO processed_whatsapp_messages (
                    message_id,
                    customer_number
                )
                VALUES (%s, %s)
                ON CONFLICT (message_id) DO NOTHING
                RETURNING message_id
                """,
                (message_id, customer_number)
            )
            claimed = cur.fetchone() is not None
        conn.commit()

    return claimed


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
            print(
                f"NEW LEAD EMAIL SENT: {lead_id}",
                flush=True
            )
            return True

        safe_error = response.text[:500]
        print(
            f"Lead email error for lead {lead_id}: "
            f"Brevo HTTP {response.status_code} - {safe_error}",
            flush=True
        )
        return False

    except requests.RequestException as error:
        print(
            f"Lead email error for lead {lead_id}: {error}",
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
        print(f"Health check error: {error}", flush=True)

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
.lead{background:white;border-radius:14px;margin-bottom:14px;padding:17px;box-shadow:0 2px 8px rgba(0,0,0,.05)}.lead-top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.customer{font-size:19px;font-weight:800}.number{margin-top:4px}.number a{color:#175cd3;text-decoration:none}.status{font-weight:800;font-size:11px;padding:7px 10px;border-radius:20px;background:#eef2f6;white-space:nowrap}.service{margin-top:12px;font-weight:800}.summary,.reason{margin-top:9px;line-height:1.5}.reason{color:#667085}.meta{margin-top:12px;color:#98a2b3;font-size:12px;line-height:1.5}.quick{display:block;text-align:center;text-decoration:none;background:#157347;color:white;border-radius:9px;padding:11px 12px;margin-top:15px;font-weight:800}.takeover{margin-top:8px}.takeover button{width:100%;border:1px solid #d0d5dd;background:#fff;border-radius:9px;padding:11px 12px;font-weight:800}.takeover .resume{background:#101828;color:#fff;border-color:#101828}.ai-state{margin-top:8px;font-size:12px;font-weight:800;color:#667085}.actions{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:8px}.actions form{margin:0}.actions button{width:100%;height:100%;border:1px solid #d0d5dd;background:white;border-radius:8px;padding:9px 6px;font-weight:700;font-size:12px}.empty{background:white;padding:28px;border-radius:12px;text-align:center;color:#667085}.clear{display:inline-block;margin-top:10px;color:#175cd3;text-decoration:none;font-weight:700}
@media(max-width:700px){.stats{grid-template-columns:repeat(2,1fr)}.lead-top{align-items:flex-start}.container{padding:0 12px}.header-inner{padding:0 12px}.search-row button{padding:0 12px}.actions{grid-template-columns:1fr 1fr 1fr}}
</style>
</head>
<body>
<header><div class="header-inner"><div><div class="brand">IBROWS Lead Dashboard</div><div class="tagline">Kupanga zofanana, mosiyana</div></div><form method="POST" action="{{ url_for('admin_logout') }}"><input type="hidden" name="csrf_token" value="{{ csrf_token }}"><button class="logout" type="submit">Logout</button></form></div></header>
<div class="container">
<h1>Business Leads</h1><p class="description">Qualified enquiries captured by the IBROWS AI Business Assistant.</p>
<div class="stats"><div class="stat"><div class="stat-number">{{ counts.ALL }}</div><div class="stat-label">All Leads</div></div><div class="stat"><div class="stat-number">{{ counts.NEW }}</div><div class="stat-label">New</div></div><div class="stat"><div class="stat-number">{{ counts.CONTACTED }}</div><div class="stat-label">Contacted</div></div><div class="stat"><div class="stat-number">{{ counts.CLOSED }}</div><div class="stat-label">Closed</div></div></div>
<div class="tools"><form class="search-row" method="GET" action="{{ url_for('admin_leads') }}"><input name="q" value="{{ search_query }}" placeholder="Search name, number, service or enquiry"><input type="hidden" name="status" value="{{ status_filter }}"><button type="submit">Search</button></form><div class="filters">{% for item in ['ALL','NEW','CONTACTED','CLOSED'] %}<a class="filter {% if status_filter == item %}active{% endif %}" href="{{ url_for('admin_leads', status=item, q=search_query) }}">{{ item.title() }}</a>{% endfor %}</div></div>
<div class="result-note">Showing {{ leads|length }} lead{% if leads|length != 1 %}s{% endif %}{% if search_query %} matching “{{ search_query }}”{% endif %}.</div>
{% if leads %}{% for lead in leads %}<div class="lead"><div class="lead-top"><div><div class="customer">{{ lead.customer_name or 'WhatsApp Customer' }}</div><div class="number"><a href="https://wa.me/{{ lead.customer_number }}" target="_blank" rel="noopener noreferrer">+{{ lead.customer_number }}</a></div></div><div class="status">{{ lead.status }}</div></div><div class="service">{{ lead.service or 'General Enquiry' }}</div><div class="summary">{{ lead.summary or 'No summary available.' }}</div>{% if lead.handover_reason %}<div class="reason"><strong>Human follow-up:</strong> {{ lead.handover_reason }}</div>{% endif %}<div class="meta">Created: {{ lead.created_at.strftime('%d %b %Y %H:%M') }} &nbsp;|&nbsp; Updated: {{ lead.updated_at.strftime('%d %b %Y %H:%M') }}</div><a class="quick" href="https://wa.me/{{ lead.customer_number }}" target="_blank" rel="noopener noreferrer">Open WhatsApp Customer</a><div class="ai-state">AI: {% if lead.ai_paused %}PAUSED — human takeover active{% else %}ACTIVE{% endif %}</div><form class="takeover" method="POST" action="{{ url_for('admin_ai_takeover', customer_number=lead.customer_number) }}"><input type="hidden" name="csrf_token" value="{{ csrf_token }}"><input type="hidden" name="paused" value="{% if lead.ai_paused %}0{% else %}1{% endif %}"><button class="{% if lead.ai_paused %}resume{% endif %}" type="submit">{% if lead.ai_paused %}Resume AI Assistant{% else %}Pause AI — Human Takeover{% endif %}</button></form><div class="actions">{% for target,label in [('NEW','Mark New'),('CONTACTED','Contacted'),('CLOSED','Close Lead')] %}{% if lead.status != target %}<form method="POST" action="{{ url_for('admin_lead_status', lead_id=lead.id) }}"><input type="hidden" name="csrf_token" value="{{ csrf_token }}"><input type="hidden" name="status" value="{{ target }}"><button type="submit">{{ label }}</button></form>{% else %}<button type="button" disabled>{{ label }}</button>{% endif %}{% endfor %}</div></div>{% endfor %}{% else %}<div class="empty">No leads match this view.<br><a class="clear" href="{{ url_for('admin_leads') }}">Clear search and filters</a></div>{% endif %}
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

        if not claim_whatsapp_message(message_id, customer_number):
            print(
                f"DUPLICATE WHATSAPP MESSAGE IGNORED: {message_id}",
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
            print("AI PAUSED FOR CUSTOMER — HUMAN TAKEOVER ACTIVE", flush=True)
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
                    f"Lead creation error: {lead_error}",
                    flush=True
                )

                reply = (
                    "Thank you. Your enquiry needs assistance "
                    "from the IBROWS team. Please contact us on "
                    "+265 882 242 594 or email "
                    "ibrowsenterprise@gmail.com for further "
                    "assistance."
                )

        send_whatsapp_message(
            customer_number,
            reply
        )

    except Exception as error:

        print(
            f"Webhook processing error: {error}",
            flush=True
        )

    return "EVENT_RECEIVED", 200


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

Set lead_required to TRUE when:

- The customer asks for a quotation.
- The customer asks how to pay.
- The customer wants to proceed with purchasing a service.
- The customer asks to speak with a person.
- Management or staff assistance is requested.
- Price negotiation is required.
- Enough information has been supplied for staff to continue.
- A complaint requires human attention.
- A custom project needs assessment.
- Product availability requires human confirmation.

Do not create a lead merely because someone says hello or
asks a general question.

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

You may say the enquiry will be referred to the IBROWS team
when lead_required is true.

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

        result = json.loads(raw_output)

        print(
            "AI STRUCTURED OUTPUT OK: "
            f"lead_required={bool(result.get('lead_required', False))}, "
            f"service={canonicalize_service(result.get('service', ''))}",
            flush=True
        )

        reply = str(
            result.get(
                "reply",
                "Thank you for contacting IBROWS Enterprise."
            )
        ).strip()

        final_result = {
            "reply": reply,
            "lead_required": bool(
                result.get("lead_required", False)
            ),
            "service": str(
                result.get("service", "")
            ).strip(),
            "lead_summary": str(
                result.get("lead_summary", "")
            ).strip(),
            "handover_reason": str(
                result.get("handover_reason", "")
            ).strip()
        }

        save_message(
            customer_number,
            "assistant",
            reply
        )

        return final_result

    except Exception as error:

        print(
            f"OpenAI/database error: {error}",
            flush=True
        )

        return {
            "reply": (
                "Thank you for contacting IBROWS Enterprise. "
                "Our AI assistant is temporarily unable to "
                "process your request. Please try again shortly."
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
        print(
            "WhatsApp credentials not configured.",
            flush=True
        )
        return

    url = (
        f"https://graph.facebook.com/v25.0/"
        f"{PHONE_NUMBER_ID}/messages"
    )

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "text",
        "text": {
            "body": message
        },
    }

    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=8,
        )

        print(
            f"WhatsApp send status: {response.status_code}",
            flush=True
        )


    except requests.RequestException as error:

        print(
            f"WhatsApp send error: {error}",
            flush=True
        )


# =========================================================
# PRIVACY POLICY
# =========================================================

@app.route("/privacy", methods=["GET"])
def privacy_policy():

    return """
    <html>
    <head>
        <title>
        IBROWS AI Business Assistant - Privacy Policy
        </title>
    </head>

    <body>

        <h1>Privacy Policy</h1>

        <p>
        <strong>IBROWS AI Business Assistant</strong>
        </p>

        <p>
        IBROWS Enterprise uses this WhatsApp Business service
        to communicate with customers, respond to enquiries,
        and provide information about our services.
        </p>

        <p>
        When you communicate with us through WhatsApp, we may
        process information you provide voluntarily, including
        your WhatsApp phone number, profile information made
        available by WhatsApp, and the contents of messages
        you send to us.
        </p>

        <p>
        This information may be used to respond to enquiries,
        provide requested services, maintain conversation
        context, improve customer support, and manage
        legitimate business enquiries.
        </p>

        <p>
        Some responses may be generated or assisted by
        artificial intelligence.
        </p>

        <p>
        Customers should not send passwords, banking PINs,
        OTP codes, or other highly sensitive information
        through the assistant.
        </p>

        <p>
        We do not sell customer personal information.
        </p>

        <p>
        Customers may request access to or deletion of
        information associated with their interactions with
        IBROWS Enterprise by contacting:
        ibrowsenterprise@gmail.com
        </p>

        <p>
        Last updated: 21 September 2026.
        </p>

    </body>
    </html>
    """, 200


# =========================================================
# DATA DELETION PAGE
# =========================================================

@app.route("/data-deletion", methods=["GET"])
def data_deletion():

    return """
    <html>

    <head>
        <title>IBROWS - Data Deletion</title>
    </head>

    <body>

        <h1>User Data Deletion</h1>

        <p>
        You may request deletion of personal information
        associated with your interactions with the IBROWS
        AI Business Assistant.
        </p>

        <p>
        Send your request to
        <strong>ibrowsenterprise@gmail.com</strong>
        and state that you are requesting deletion of your
        IBROWS WhatsApp Assistant data.
        </p>

        <p>
        We may ask for reasonable information necessary to
        identify the relevant records before completing the
        request.
        </p>

    </body>

    </html>
    """, 200


# =========================================================
# INITIALIZE DATABASE
# =========================================================

try:
    init_database()

except Exception as error:

    print(
        f"DATABASE INITIALIZATION ERROR: {error}",
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
