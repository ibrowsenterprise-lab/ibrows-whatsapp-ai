"""Narrow verified WhatsApp owner-alert patch for the production webhook.

No customer/payment data is modified by this patch. Two exact application
anchors must match or the build refuses to change app.py.
"""
from pathlib import Path

p=Path("app.py")
old=p.read_text("utf-8")
email_anchor='''        send_human_handover_alert_email(
            lead_id=lead_id,
            customer_name=customer_name,
            customer_number=customer_number,
            service=handover_service,
            handover_reason=handover_reason,
        )
'''
alert_hook='''        # In addition to email, route human-takeover notifications to the
        # explicitly designated old IBROWS WhatsApp Business App number.
        # Free-form requires that recipient's own 24h inbound service window;
        # outside it only an explicitly configured, approved template is used.
        from handover_business_alerts import (
            BUSINESS_ALERT_NUMBER,
            configured_template,
            configured_template_language,
            deliver_handover_alert,
            save_alert_audit,
        )
        try:
            business_alert_window_open, _ = is_whatsapp_service_window_open(
                BUSINESS_ALERT_NUMBER
            )
            alert_status, alert_channel = deliver_handover_alert(
                customer_name, customer_number, handover_service,
                window_open=business_alert_window_open,
                send_text=send_whatsapp_message,
                token=WHATSAPP_TOKEN, phone_number_id=PHONE_NUMBER_ID,
                http_post=requests.post,
                template_name=configured_template(),
                template_language=configured_template_language(),
            )
            save_alert_audit(get_db, lead_id, alert_status, alert_channel)
            print(
                "IBROWS HANDOVER WHATSAPP ALERT: " + alert_status
                + " via " + alert_channel + " to 0882 242 594",
                flush=True,
            )
        except Exception as alert_error:
            print(
                "IBROWS HANDOVER WHATSAPP ALERT UNAVAILABLE: "
                + type(alert_error).__name__,
                flush=True,
            )
'''
if old.count(email_anchor)!=1:
    raise SystemExit(f"Unexpected send_human_handover_alert_email anchor: {old.count(email_anchor)}")
new=old.replace(email_anchor,email_anchor+alert_hook,1)
owner_anchor='''        # Only explicit customer requests resume the AI after human takeover.
'''
owner_branch='''        # IBROWS's old WhatsApp Business App number can open its own 24-hour
        # messaging window with a simple opt-in command. This is an internal
        # alert subscription, not a paid customer lead or human handover.
        if message_type == "text":
            from handover_business_alerts import (
                is_owner_activation, owner_activation_reply,
            )
            if is_owner_activation(customer_number, customer_message):
                save_message(customer_number, "user", customer_message)
                owner_reply = owner_activation_reply()
                save_message(customer_number, "assistant", owner_reply)
                store_pending_reply(message_id, owner_reply)
                owner_sent = send_whatsapp_message(customer_number, owner_reply)
                finish_whatsapp_message(message_id, owner_sent)
                print("IBROWS BUSINESS ALERT RECEIVER WINDOW ACTIVATION", flush=True)
                return "EVENT_RECEIVED", 200

'''
if new.count(owner_anchor)!=1:
    raise SystemExit(f"Unexpected WhatsApp paused-gate anchor: {new.count(owner_anchor)}")
new=new.replace(owner_anchor,owner_branch+owner_anchor,1)
compile(new,"app.py","exec")
p.write_text(new,"utf-8")
print("WHATSAPP HANDOVER ALERT ROUTING PATCHED: 0882 242 594 only; no funds or customer updates")
