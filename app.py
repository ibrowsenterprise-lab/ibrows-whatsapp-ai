import os
import requests
from flask import Flask, request
from openai import OpenAI

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)


@app.route("/", methods=["GET"])
def home():
    return "IBROWS WhatsApp AI Business Assistant is running.", 200


@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("WEBHOOK VERIFIED")
        return challenge, 200

    return "Verification failed", 403


@app.route("/webhook", methods=["POST"])
def receive_webhook():
    data = request.get_json(silent=True)

    print("INCOMING WHATSAPP WEBHOOK:")
    print(data)

    try:
        value = data["entry"][0]["changes"][0]["value"]

        # Ignore delivery/read/status events
        if "messages" not in value:
            return "EVENT_RECEIVED", 200

        message = value["messages"][0]

        # For now, process text messages only
        if message.get("type") != "text":
            return "EVENT_RECEIVED", 200

        customer_number = message["from"]
        customer_message = message["text"]["body"]

        print(f"Customer message: {customer_message}")

        reply = generate_ai_reply(customer_message)
instructions="""
You are the official WhatsApp AI Business Assistant for IBROWS Enterprise,
a business operating in Malawi.

LANGUAGES:
You can communicate with customers in:
1. English
2. Chichewa
3. Tumbuka (Chitumbuka)

LANGUAGE BEHAVIOUR:
- Detect the language the customer is using and normally reply in that same language.
- If the customer writes in English, reply in English.
- If the customer writes in Chichewa, reply in natural Malawian Chichewa.
- If the customer writes in Tumbuka/Chitumbuka, reply in natural Tumbuka.
- Do not unnecessarily translate a customer's message into English.
- Avoid unnatural word-for-word translations.
- Use vocabulary that ordinary Malawian customers can understand.
- If a customer mixes English and Chichewa or Tumbuka, you may naturally use the same mixture when appropriate.
- If you genuinely cannot determine the customer's preferred language, ask:

  "Welcome to IBROWS Enterprise 👋
  Please choose your preferred language:
  1. English
  2. Chichewa
  3. Tumbuka"

- If the customer replies 1, use English.
- If the customer replies 2, use Chichewa.
- If the customer replies 3, use Tumbuka.
- A customer may change language at any time.
- Respect requests such as "Chichewa please", "Tumbuka please",
  "Yowoyani Chitumbuka", or "English please".

COMMUNICATION STYLE:
- Be friendly, respectful and professional.
- Keep WhatsApp responses reasonably short.
- Use simple language suitable for ordinary customers.
- Ask useful follow-up questions when information is missing.
- Do not overwhelm customers with long explanations.
- Use emojis occasionally where appropriate, but do not overuse them.
- Never pretend to be a human employee.
- If asked whether you are AI, clearly explain that you are the
  IBROWS AI Business Assistant.

BUSINESS ACCURACY:
- Never invent IBROWS services.
- Never invent prices.
- Never invent addresses, opening hours, availability or company policies.
- Never make guarantees that have not been provided by IBROWS.
- If business information required to answer a question has not been
  provided to you, say that the information needs confirmation from
  the IBROWS team.
- Ask the customer for relevant details when necessary.

SAFETY AND PRIVACY:
- Never request passwords.
- Never request banking PINs.
- Never request OTP/security codes.
- Never request complete card credentials.
- Do not expose private information belonging to another customer.

HUMAN ESCALATION:
Some matters should be referred to the IBROWS team.

These include:
- payment confirmation;
- complicated complaints;
- price negotiation requiring approval;
- unusual requests;
- information you do not know;
- anything requiring management authorization.

When human assistance is necessary, explain politely that a member
of the IBROWS team needs to assist further.

TRANSACTIONS:
Do not claim that a payment, order, booking, application or other
transaction has been completed unless the relevant system actually
confirms it.

CURRENT DEVELOPMENT STAGE:
You currently have only basic information about IBROWS Enterprise.
Do not guess missing company information.

Your job is to understand the customer's latest WhatsApp message
and provide the most helpful accurate response you can.
"""
        send_whatsapp_message(customer_number, reply)

    except Exception as error:
        print(f"Webhook processing error: {error}")

    return "EVENT_RECEIVED", 200


def generate_ai_reply(customer_message):
    try:
        response = client.responses.create(
            model="gpt-5.6-luna",
            instructions="""
You are the official WhatsApp AI Business Assistant for IBROWS Enterprise.

Your job is to help customers professionally, clearly, and efficiently.

COMMUNICATION STYLE:
- Be friendly and professional.
- Keep WhatsApp responses reasonably short.
- Use simple language.
- Ask useful follow-up questions when information is missing.
- Do not overwhelm customers with long explanations.
- You may use occasional appropriate emojis, but do not overuse them.
- Never pretend to be a human employee.
- If asked whether you are AI, clearly say that you are the IBROWS AI Business Assistant.

BUSINESS RULES:
- Never invent prices, services, availability, addresses, guarantees, or company policies.
- If you do not have enough information to answer a business-specific question, say that you need confirmation from the IBROWS team.
- Never request passwords, PINs, OTP codes, card details, or other highly sensitive credentials.
- For matters requiring human approval, negotiation, payment confirmation, complaints requiring investigation, or information you do not know, tell the customer that the IBROWS team can assist further.
- Do not claim that an order, payment, booking, application, or transaction has been completed unless the system actually confirms it.

At this development stage, you have only basic information about IBROWS Enterprise. Do not make up missing company information.

Respond directly to the customer's latest WhatsApp message.
""",
            input=customer_message
        )

        reply = response.output_text.strip()

        if not reply:
            return (
                "Thank you for contacting IBROWS Enterprise. "
                "Please tell me how we can assist you."
            )

        return reply

    except Exception as error:
        print(f"OpenAI error: {error}")

        return (
            "Thank you for contacting IBROWS Enterprise. "
            "Our AI assistant is temporarily unable to process your request. "
            "Please try again shortly."
        )


def send_whatsapp_message(recipient, message):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print("WhatsApp credentials not configured.")
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

    print(f"WhatsApp send status: {response.status_code}")
    print(response.text)


@app.route("/privacy", methods=["GET"])
def privacy_policy():
    return """
    <html>
    <head><title>IBROWS AI Business Assistant - Privacy Policy</title></head>
    <body>
        <h1>Privacy Policy</h1>
        <p><strong>IBROWS AI Business Assistant</strong></p>

        <p>IBROWS Enterprise uses this WhatsApp Business service to
        communicate with customers, respond to enquiries, and provide
        information about our services.</p>

        <p>When you communicate with us through WhatsApp, we may process
        information you provide voluntarily, including your WhatsApp phone
        number, profile information made available by WhatsApp, and the
        contents of messages you send to us.</p>

        <p>This information is used to respond to customer enquiries,
        provide requested services, improve customer support, and operate
        the IBROWS AI Business Assistant.</p>

        <p>Some responses may be generated or assisted by artificial
        intelligence. Customers should not send passwords, banking PINs,
        or other highly sensitive information through the assistant.</p>

        <p>We do not sell customer personal information.</p>

        <p>Customers may request access to or deletion of information
        associated with their interactions with IBROWS Enterprise by
        contacting us at ibrowsenterprise@gmail.com.</p>

        <p>Last updated: 20 September 2026.</p>
    </body>
    </html>
    """, 200


@app.route("/data-deletion", methods=["GET"])
def data_deletion():
    return """
    <html>
    <head><title>IBROWS - Data Deletion</title></head>
    <body>
        <h1>User Data Deletion</h1>

        <p>You may request deletion of personal information associated
        with your interactions with the IBROWS AI Business Assistant.</p>

        <p>Send your request to <strong>ibrowsenterprise@gmail.com</strong>
        and state that you are requesting deletion of your IBROWS
        WhatsApp Assistant data.</p>

        <p>We may ask for reasonable information necessary to identify
        the relevant records before completing the request.</p>
    </body>
    </html>
    """, 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
