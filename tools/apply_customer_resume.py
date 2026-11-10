"""Narrow patch of WhatsApp resume behavior, safe for CI on checked-out code."""
from pathlib import Path
p=Path("app.py")
original=p.read_text(encoding="utf-8")
anchor1="""        if is_ai_paused(customer_number):
            # Keep a text-only record so the AI has context if automation resumes.
"""
block='''        # Only explicit customer requests resume the AI after human takeover.
        # This branch must appear before the paused-conversation gate.
        if message_type == "text" and " ".join(customer_message.lower().split()) in {
            "resume ai", "restart ai", "start ai", "enable ai", "resume bot",
        }:
            set_ai_paused(customer_number, False)
            clear_customer_menu_state(customer_number)
            reply = (
                "IBROWS AI Assistant is active again. You can now ask a question "
                'or send "Show me your menu" to explore services.\n\n'
                "To speak with Jones again, reply 0."
            )
            save_message(customer_number, "user", customer_message)
            save_message(customer_number, "assistant", reply)
            store_pending_reply(message_id, reply)
            sent = send_whatsapp_message(customer_number, reply)
            finish_whatsapp_message(message_id, sent)
            print("CUSTOMER SELF-SERVICE AI RESUMED", flush=True)
            return "EVENT_RECEIVED", 200

'''
anchor2="""    # Pause first so the customer's explicit preference is respected even
    # if lead recording or notification later fails.
"""
replacement2='''    # Tell customers how to return to the assistant when they are ready.
    reply += "\n\nTo return to AI support later, send: Resume AI"

'''+anchor2
assert original.count(anchor1)==1, f"Unexpected paused guard anchor count {original.count(anchor1)}"
assert original.count(anchor2)==1, f"Unexpected handover anchor count {original.count(anchor2)}"
new=original.replace(anchor1,block+anchor1,1).replace(anchor2,replacement2,1)
assert len(new)-len(original)<2400
compile(new,"app.py","exec")
p.write_text(new,encoding="utf-8")
print("PATCH APPLIED AND COMPILED: explicit Resume AI and handover help message")
