import os
import requests
from flask import Flask, request

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")


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

        if "messages" not in value:
            return "EVENT_RECEIVED", 200

        message = value["messages"][0]

        # For now, respond only to text messages
        if message.get("type") != "text":
            return "EVENT_RECEIVED", 200

        customer_number = message["from"]
        customer_message = message["text"]["body"]

        print(f"Customer message: {customer_message}")

        reply = (
            "Hello! 👋 Welcome to IBROWS Enterprise.\n\n"
            "Our AI Business Assistant is now online. "
            "How can we assist you today?"
        )

        send_whatsapp_message(customer_number, reply)

    except Exception as error:
        print(f"Webhook processing error: {error}")

    return "EVENT_RECEIVED", 200


def send_whatsapp_message(recipient, message):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print("WhatsApp credentials not configured yet.")
        return

    url = (
        f"https://graph.facebook.com/v24.0/"
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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
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
