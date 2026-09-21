import os
import json
import requests
import psycopg
from flask import Flask, request
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
                    service TEXT,
                    summary TEXT,
                    handover_reason TEXT,
                    status TEXT NOT NULL DEFAULT 'NEW',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
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


def create_lead(
    customer_number,
    service,
    summary,
    handover_reason
):
    """
    Avoid creating multiple NEW leads for the same customer
    in a short period. If a NEW lead already exists, update it.
    """

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
                    SET service = %s,
                        summary = %s,
                        handover_reason = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (
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
                        service,
                        summary,
                        handover_reason
                    )
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        customer_number,
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


# =========================================================
# HOME PAGE
# =========================================================

@app.route("/", methods=["GET"])
def home():
    return "IBROWS WhatsApp AI Business Assistant is running.", 200


# =========================================================
# HEALTH CHECK
# =========================================================

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

        print(
            f"Customer message: {customer_message}",
            flush=True
        )

        result = generate_ai_reply(
            customer_number,
            customer_message
        )

        reply = result["reply"]

        print(f"AI reply: {reply}", flush=True)

        if result.get("lead_required"):
            try:
                create_lead(
                    customer_number=customer_number,
                    service=result.get(
                        "service",
                        "General Enquiry"
                    ),
                    summary=result.get(
                        "lead_summary",
                        customer_message
                    ),
                    handover_reason=result.get(
                        "handover_reason",
                        "Human assistance required"
                    )
                )

            except Exception as lead_error:
                # We do NOT tell the customer a lead was
                # successfully created if the DB operation failed.
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

def generate_ai_reply(customer_number, customer_message):

    try:
        # Store incoming customer message permanently.
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

Your job is to:
1. Help customers understand IBROWS services.
2. Understand what they need.
3. Ask useful follow-up questions.
4. Provide accurate approved information.
5. Identify genuine business leads.
6. Determine when human assistance is required.

You are an AI assistant.
Never pretend to be a human employee.


============================================================
OUTPUT FORMAT - VERY IMPORTANT
============================================================

Return ONLY a valid JSON object.

Never place the JSON inside markdown code fences.

Use exactly these fields:

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
- The customer requests management or staff assistance.
- Price negotiation is required.
- The customer has provided enough information for IBROWS
  staff to continue the enquiry.
- A complaint needs human attention.
- A custom project needs assessment.
- Product availability requires human confirmation.

Do NOT create a lead merely because somebody says hello,
asks a general question, or is still casually exploring.

When lead_required is true:

service:
Give the most appropriate IBROWS service category.

lead_summary:
Briefly summarize what the customer wants and important
information already collected from the conversation.

handover_reason:
Briefly explain why human follow-up is required.

IMPORTANT:
When lead_required is true, you may tell the customer that
their enquiry is being referred to the IBROWS team because
the system is configured to create a lead.

Do not claim payment, booking, registration, purchase,
application or any other transaction has been completed.


============================================================
CONVERSATION CONTEXT
============================================================

You receive recent messages from the same WhatsApp customer.

Use the conversation history to understand follow-up answers.

Do not unnecessarily ask for information the customer has
already supplied.

The conversation history may contain only recent messages.
Do not invent older conversation details.


============================================================
LANGUAGES
============================================================

You communicate in:

1. English
2. Chichewa
3. Tumbuka / Chitumbuka

Normally respond in the language being used by the customer.

Use natural Malawian Chichewa where Chichewa is appropriate.

Use natural Malawian Tumbuka/Chitumbuka where Tumbuka is
appropriate.

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

Do not ask all questions at once.

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

If somebody simply says hello, greet them naturally and ask
how IBROWS can assist.

Ask only one or two useful follow-up questions at a time.

Do not pressure customers.

Do not make false promises.


============================================================
PRICING
============================================================

Only quote prices explicitly approved above.

For services without approved prices, explain that pricing
depends on requirements and needs confirmation from the
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
SAFETY & PRIVACY
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

Help the customer move toward the correct next step while
remaining accurate.

Respond to the customer's latest message in the context of
their recent conversation.

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

        lead_required = bool(
            result.get("lead_required", False)
        )

        final_result = {
            "reply": reply,
            "lead_required": lead_required,
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

        # Save only the customer-facing reply in conversation history.
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
                "Our AI assistant is temporarily unable to process "
                "your request. Please try again shortly."
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
    print(response.text, flush=True)


# =========================================================
# PRIVACY POLICY
# =========================================================

@app.route("/privacy", methods=["GET"])
def privacy_policy():
    return """
    <html>
    <head>
        <title>IBROWS AI Business Assistant - Privacy Policy</title>
    </head>
    <body>
        <h1>Privacy Policy</h1>

        <p><strong>IBROWS AI Business Assistant</strong></p>

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
        context, improve customer support, and manage legitimate
        business enquiries.
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
    port = int(os.environ.get("PORT", 10000))
    app.run(
        host="0.0.0.0",
        port=port
    )
