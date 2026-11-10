"""Exact one-time patch to the WhatsApp webhook, applied in CI only.

The patch adds an explicit, service-specific *paid* eligibility intake command,
before the general AI or menus, after the human-handover pause gate.
"""
from pathlib import Path
p=Path("app.py")
old=p.read_text("utf-8")
anchor="""        # Deterministic numbered/text service navigation. This runs before OpenAI so
"""
insert='''        # A paid one-off eligibility customer can request an intake without
        # involving OpenAI. The official verified ledger is the only payment
        # source. The command must never auto-mark work completed or charge.
        if message_type == "text":
            from scholarship_eligibility_intake import (
                SERVICE as ELIGIBILITY_ONE_OFF_SERVICE,
                is_explicit_eligibility_intake_request,
                is_verified_one_off,
                paid_eligibility_intake_message,
                unpaid_eligibility_intake_message,
            )
            if is_explicit_eligibility_intake_request(customer_message):
                try:
                    payment_state = get_verified_service_payment_state(
                        customer_number, ELIGIBILITY_ONE_OFF_SERVICE
                    )
                except Exception as eligibility_lookup_error:
                    print(
                        "SCHOLARSHIP ELIGIBILITY LEDGER LOOKUP ERROR: "
                        + type(eligibility_lookup_error).__name__,
                        flush=True,
                    )
                    reply = (
                        "I cannot check your payment record just now. "
                        "Please try again or reply 0 for IBROWS assistance. "
                        "Do not make another payment while verification is unavailable."
                    )
                else:
                    reply = (
                        paid_eligibility_intake_message()
                        if is_verified_one_off(payment_state)
                        else unpaid_eligibility_intake_message()
                    )
                save_message(customer_number, "user", customer_message)
                save_message(customer_number, "assistant", reply)
                store_pending_reply(message_id, reply)
                sent = send_whatsapp_message(customer_number, reply)
                finish_whatsapp_message(message_id, sent)
                print("SCHOLARSHIP ELIGIBILITY INTAKE ROUTE HANDLED", flush=True)
                return "EVENT_RECEIVED", 200

'''
if old.count(anchor)!=1:
    raise SystemExit("Refusing webhook patch: exact verified anchor missing")
new=old.replace(anchor,insert+anchor,1)
compile(new,"app.py","exec")
p.write_text(new,encoding="utf-8")
print("WHATSAPP ELIGIBILITY COMMAND ADDED BEFORE GENERAL AI/NUMBERED MENU")
