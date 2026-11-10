"""Ledger-backed WhatsApp AI payment context for Scholarship Search packages.

No screenshots, chat messages, references, or estimates can mark a payment
verified. This formatter receives only the CRM's authenticated-payment snapshot.
"""
from decimal import Decimal


def scholarship_payment_context_lines(state):
    if not state or state.get("lead_id") is None:
        return []

    status = str(state.get("status") or "NOT_VERIFIED")
    currency = str(state.get("currency") or "MWK")
    paid = Decimal(str(state.get("paid") or 0))
    required_raw = state.get("required")
    required = Decimal(str(required_raw)) if required_raw is not None else None
    received_text = f"{currency} {paid:,.0f}"
    required_text = f"{currency} {required:,.0f}" if required is not None else "not set in the ledger"
    lines = [
        f"- Scholarship Search (this customer's open lead): {status}; "
        f"verified ledger receipts {received_text}; recorded package price {required_text}."
    ]

    if status == "PAID" and required is not None and required > 0 and paid >= required:
        lines.append(
            "- SCHOLARSHIP SERVICE PAYMENT VERIFIED for the recorded lead and its "
            "specific selected package only. Do not ask the customer to repay for "
            "that package. Use the customer's stated selection and agreed scope; "
            "do not treat an Eligibility Check as payment for a wider scholarship "
            "search, application service, or ongoing monthly support."
        )
        lines.append(
            "- For a paid Eligibility Check, collect any missing highest qualification, "
            "academic result/classification, country of citizenship/residence, work "
            "experience, intended degree/subject, target countries and intake. "
            "Check official eligibility requirements and explain findings accurately. "
            "Do not promise admission, scholarship awards, or completed work, and "
            "do not request extra payment for this already-verified scope."
        )
    else:
        lines.append(
            "- Scholarship payment is NOT confirmed as fully paid for the selected "
            "package. Do not claim verified paid status or unlock a paid service "
            "based on a receipt screenshot or a chat message. Human administrator "
            "must verify and record money against this exact lead."
        )
    return lines
