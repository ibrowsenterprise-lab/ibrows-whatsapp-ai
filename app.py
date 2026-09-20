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
