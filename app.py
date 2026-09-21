import os
import json
import secrets
import smtplib
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
from email.message import EmailMessage
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

SMTP_EMAIL = os.environ.get("SMTP_EMAIL")
SMTP_APP_PASSWORD = os.environ.get("SMTP_APP_PASSWORD")
NOTIFICATION_EMAIL = os.environ.get("NOTIFICATION_EMAIL")
LEAD_DASHBOARD_URL = "https://ibrows-whatsapp-ai-1.onrender.com/admin/leads"

app.secret_key = FLASK_SECRET_KEY

app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

client = OpenAI(api_key=OPENAI_API_KEY)


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


def create_or_update_lead(
    customer_number,
    customer_name,
    service,
    summary,
    handover_reason
):
    with get_db() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT id
                FROM leads
                WHERE customer_number = %s
                  AND status = 'NEW'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (customer_number,)
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
                    f"LEAD UPDATED: {lead_id} "
                    f"for {customer_number}",
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
                    f"NEW LEAD CREATED: {lead_id} "
                    f"for {customer_number}",
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
    if not SMTP_EMAIL or not SMTP_APP_PASSWORD or not NOTIFICATION_EMAIL:
        print(
            "Lead email skipped: SMTP settings are not fully configured.",
            flush=True
        )
        return False

    try:
        message = EmailMessage()
        message["Subject"] = f"New IBROWS Lead #{lead_id}: {service}"
        message["From"] = SMTP_EMAIL
        message["To"] = NOTIFICATION_EMAIL

        display_name = customer_name or "Not provided"
        message.set_content(
            f"""A new qualified lead has been captured by the IBROWS AI Business Assistant.

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
Opportunity Without Borders.
"""
        )

        with smtplib.SMTP_SSL(
            "smtp.gmail.com",
            465,
            timeout=20
        ) as smtp:
            smtp.login(SMTP_EMAIL, SMTP_APP_PASSWORD)
            smtp.send_message(message)

        print(
            f"NEW LEAD EMAIL SENT: {lead_id}",
            flush=True
        )
        return True

    except Exception as error:
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

def admin_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin_login"))

        return function(*args, **kwargs)

    return wrapper


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
Opportunity Without Borders.
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
            session.clear()
            session["admin_authenticated"] = True
            session["csrf_token"] = secrets.token_urlsafe(32)

            return redirect(url_for("admin_leads"))

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

<meta
    name="viewport"
    content="width=device-width, initial-scale=1"
>

<title>IBROWS Lead Dashboard</title>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background: #f4f6f8;
    font-family: Arial, Helvetica, sans-serif;
    color: #17202a;
}

header {
    background: #111827;
    color: white;
    padding: 18px 24px;
}

.header-inner {
    max-width: 1250px;
    margin: auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 15px;
}

.brand {
    font-size: 22px;
    font-weight: 800;
}

.tagline {
    font-size: 12px;
    opacity: .7;
    margin-top: 3px;
}

.logout {
    background: transparent;
    border: 1px solid rgba(255,255,255,.4);
    color: white;
    border-radius: 7px;
    padding: 8px 12px;
    cursor: pointer;
}

.container {
    max-width: 1250px;
    margin: 25px auto;
    padding: 0 18px 40px;
}

h1 {
    margin-bottom: 5px;
}

.description {
    color: #667085;
    margin-top: 0;
}

.stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;
    margin: 24px 0;
}

.stat {
    background: white;
    padding: 20px;
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,.05);
}

.stat-number {
    font-size: 30px;
    font-weight: 800;
}

.stat-label {
    color: #667085;
    margin-top: 4px;
}

.lead {
    background: white;
    border-radius: 14px;
    margin-bottom: 16px;
    padding: 20px;
    box-shadow: 0 2px 8px rgba(0,0,0,.05);
}

.lead-top {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: flex-start;
}

.customer {
    font-size: 20px;
    font-weight: 800;
}

.number {
    margin-top: 4px;
}

.number a {
    color: #175cd3;
    text-decoration: none;
}

.service {
    margin-top: 12px;
    font-weight: 700;
}

.summary {
    margin-top: 10px;
    line-height: 1.5;
}

.reason {
    margin-top: 10px;
    color: #667085;
    line-height: 1.5;
}

.meta {
    margin-top: 13px;
    color: #98a2b3;
    font-size: 13px;
}

.status {
    font-weight: 800;
    font-size: 12px;
    padding: 7px 10px;
    border-radius: 20px;
    background: #eef2f6;
    white-space: nowrap;
}

.actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 18px;
}

.actions form {
    margin: 0;
}

.actions button {
    border: 1px solid #d0d5dd;
    background: white;
    border-radius: 8px;
    padding: 8px 11px;
    cursor: pointer;
    font-weight: 700;
}

.actions button:hover {
    background: #f2f4f7;
}

.empty {
    background: white;
    padding: 30px;
    border-radius: 12px;
    text-align: center;
    color: #667085;
}

@media (max-width: 700px) {

    .stats {
        grid-template-columns: repeat(2, 1fr);
    }

    .lead-top {
        flex-direction: column;
    }

}

</style>
</head>

<body>

<header>
<div class="header-inner">

<div>
<div class="brand">IBROWS Lead Dashboard</div>
<div class="tagline">Opportunity Without Borders.</div>
</div>

<form method="POST" action="{{ url_for('admin_logout') }}">

<input
    type="hidden"
    name="csrf_token"
    value="{{ csrf_token }}"
>

<button class="logout" type="submit">
Logout
</button>

</form>

</div>
</header>


<div class="container">

<h1>Business Leads</h1>

<p class="description">
Qualified enquiries captured by the IBROWS AI Business Assistant.
</p>


<div class="stats">

<div class="stat">
<div class="stat-number">{{ counts.ALL }}</div>
<div class="stat-label">All Leads</div>
</div>

<div class="stat">
<div class="stat-number">{{ counts.NEW }}</div>
<div class="stat-label">New</div>
</div>

<div class="stat">
<div class="stat-number">{{ counts.CONTACTED }}</div>
<div class="stat-label">Contacted</div>
</div>

<div class="stat">
<div class="stat-number">{{ counts.CLOSED }}</div>
<div class="stat-label">Closed</div>
</div>

</div>


{% if leads %}

{% for lead in leads %}

<div class="lead">

<div class="lead-top">

<div>

<div class="customer">
{{ lead.customer_name or "WhatsApp Customer" }}
</div>

<div class="number">

<a
href="https://wa.me/{{ lead.customer_number }}"
target="_blank"
rel="noopener noreferrer"
>
+{{ lead.customer_number }}
</a>

</div>

</div>

<div class="status">
{{ lead.status }}
</div>

</div>


<div class="service">
{{ lead.service or "General Enquiry" }}
</div>


<div class="summary">
{{ lead.summary or "No summary available." }}
</div>


{% if lead.handover_reason %}

<div class="reason">
<strong>Human follow-up:</strong>
{{ lead.handover_reason }}
</div>

{% endif %}


<div class="meta">

Created:
{{ lead.created_at.strftime("%d %b %Y %H:%M") }}

&nbsp; | &nbsp;

Updated:
{{ lead.updated_at.strftime("%d %b %Y %H:%M") }}

</div>


<div class="actions">

{% if lead.status != "NEW" %}

<form
method="POST"
action="{{ url_for('admin_lead_status', lead_id=lead.id) }}"
>

<input
type="hidden"
name="csrf_token"
value="{{ csrf_token }}"
>

<input
type="hidden"
name="status"
value="NEW"
>

<button type="submit">
Mark New
</button>

</form>

{% endif %}


{% if lead.status != "CONTACTED" %}

<form
method="POST"
action="{{ url_for('admin_lead_status', lead_id=lead.id) }}"
>

<input
type="hidden"
name="csrf_token"
value="{{ csrf_token }}"
>

<input
type="hidden"
name="status"
value="CONTACTED"
>

<button type="submit">
Mark Contacted
</button>

</form>

{% endif %}


{% if lead.status != "CLOSED" %}

<form
method="POST"
action="{{ url_for('admin_lead_status', lead_id=lead.id) }}"
>

<input
type="hidden"
name="csrf_token"
value="{{ csrf_token }}"
>

<input
type="hidden"
name="status"
value="CLOSED"
>

<button type="submit">
Close Lead
</button>

</form>

{% endif %}

</div>

</div>

{% endfor %}

{% else %}

<div class="empty">
No business leads have been captured yet.
</div>

{% endif %}

</div>

</body>
</html>
"""


@app.route("/admin/leads", methods=["GET"])
@admin_required
def admin_leads():

    rows = get_all_leads()

    leads = []

    for row in rows:
        leads.append({
            "id": row[0],
            "customer_number": row[1],
            "customer_name": row[2],
            "service": row[3],
            "summary": row[4],
            "handover_reason": row[5],
            "status": row[6],
            "created_at": row[7],
            "updated_at": row[8]
        })

    counts = get_lead_counts()

    return render_template_string(
        DASHBOARD_TEMPLATE,
        leads=leads,
        counts=counts,
        csrf_token=get_csrf_token()
    )


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

    print("INCOMING WHATSAPP WEBHOOK:", flush=True)
    print(data, flush=True)

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

        customer_name = ""

        contacts = value.get("contacts", [])

        if contacts:
            customer_name = (
                contacts[0]
                .get("profile", {})
                .get("name", "")
            )

        print(
            f"Customer: {customer_name} "
            f"({customer_number})",
            flush=True
        )

        print(
            f"Customer message: {customer_message}",
            flush=True
        )

        result = generate_ai_reply(
            customer_number,
            customer_message
        )

        reply = result["reply"]

        print(
            f"AI reply: {reply}",
            flush=True
        )

        if result.get("lead_required"):

            try:

                service = result.get(
                    "service",
                    "General Enquiry"
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
Give the appropriate IBROWS service category.

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

IBROWS Enterprise is a multi-service business operating
in Malawi.

Location:
Lilongwe, Malawi

WhatsApp:
+265 882 242 594

Email:
ibrowsenterprise@gmail.com

Business line:
"Opportunity Without Borders."


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
- General location
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
- General location
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
- General location
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
- General location
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

        print(
            f"AI structured output: {raw_output}",
            flush=True
        )

        result = json.loads(raw_output)

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
            timeout=20,
        )

        print(
            f"WhatsApp send status: {response.status_code}",
            flush=True
        )

        print(
            response.text,
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
