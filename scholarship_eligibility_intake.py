"""Minimal, verified-payment-only client intake for one-off scholarship screening.

The message requests only information relevant to academic eligibility.
It does not claim scholarship availability, admission, guaranteed funding or
completed applications, and never requests sensitive payment credentials.
"""
from decimal import Decimal

SERVICE = "Scholarship Eligibility Check"
REQUIRED_MWK = Decimal("5000")
COMMANDS = frozenset({
    "start eligibility", "start my eligibility check",
    "continue eligibility", "continue my eligibility check",
    "begin eligibility assessment", "eligibility intake",
    "start eligibility check", "eligibility form",
})


def is_explicit_eligibility_intake_request(message):
    return " ".join(str(message or "").casefold().split()) in COMMANDS


def is_verified_one_off(state):
    if not state:
        return False
    try:
        return bool(
            state.get("lead_id") is not None
            and state.get("service") == SERVICE
            and state.get("status") == "PAID"
            and state.get("currency") == "MWK"
            and Decimal(str(state.get("required"))) == REQUIRED_MWK
            and Decimal(str(state.get("paid") or 0)) >= REQUIRED_MWK
        )
    except (TypeError, ValueError, ArithmeticError):
        return False


def paid_eligibility_intake_message():
    return (
        "IBROWS Enterprise 🎓 | Scholarship Eligibility Check\n"
        "✅ Your MK5,000 one-off eligibility-check payment is confirmed.\n\n"
        "We have your interest in a Master's in Banking & Finance, in Europe "
        "for September 2027, with full or partial funding considered.\n\n"
        "Please reply with the following (you can answer in parts):\n"
        "1. Your exact Bachelor's degree, university, graduation year, "
        "and grade/classification or GPA.\n"
        "2. Did you study economics, statistics, mathematics or econometrics? "
        "If possible, share module names or a transcript.\n"
        "3. How many years of relevant banking/finance/business work experience "
        "do you have, and in what roles?\n"
        "4. What is your nationality and country of residence?\n"
        "5. Do you have an English proficiency test or accepted proof of "
        "English-medium study? (It's okay if not.)\n"
        "6. Any specific European countries you prefer or want to avoid?\n\n"
        "Please do not send PINs, passwords, bank account numbers or national-ID "
        "numbers. If sending a transcript, hide unnecessary personal details.\n\n"
        "IBROWS will check official programme requirements and explain which "
        "pathways may suit your qualifications. This check is not a scholarship "
        "award or a paid application service, and no additional payment is due "
        "for the MK5,000 eligibility check.\n"
        "Reply 0 at any time to request human assistance."
    )


def unpaid_eligibility_intake_message():
    return (
        "I can help with the one-off Scholarship Eligibility Check, but I "
        "cannot yet verify that this exact MK5,000 package is fully paid "
        "in the IBROWS ledger. If you have already paid, please ask the "
        "IBROWS team to check the payment; do not pay twice unless the "
        "team confirms a balance is actually outstanding. Reply 0 for "
        "human assistance."
    )
