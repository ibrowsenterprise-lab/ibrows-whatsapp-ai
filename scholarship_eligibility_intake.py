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
        "We'll use study goals you already shared in this conversation, "
        "rather than asking you to repeat them. If your intended subject, "
        "country or intake has changed, please tell us.\n\n"
        "To assess academic eligibility, please reply with the following "
        "(you can answer in parts):\n"
        "1. Your exact Bachelor's degree, university, graduation year, "
        "and grade/classification or GPA.\n"
        "2. Did you study economics, statistics, mathematics or econometrics? "
        "If possible, share module names or a transcript.\n"
        "3. How many years of relevant banking/finance/business work experience "
        "do you have, and in what roles?\n"
        "4. What is your nationality and country of residence?\n"
        "5. Do you have an English proficiency test or accepted proof of "
        "English-medium study? (It's okay if not.)\n"
        "6. Preferred study countries, intake month/year and whether you need "
        "full funding or would consider partial funding, *only if you have not "
        "already supplied these details*.\n\n"
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


def required_documents_request_message():
    """Professional follow-up for paid clients whose academic answers are saved.

    Administrator copies into the secure WhatsApp Inbox after checking whether
    documents were previously provided. The function itself never sends.
    """
    return (
        "Hello, and thank you for completing your IBROWS Scholarship "
        "Eligibility Check questionnaire. We have your academic and "
        "professional details on record, so you do not need to answer "
        "those questions again.\n\n"
        "Before we complete your eligibility assessment, please share:\n"
        "1. Your most recent CV/resume (PDF or Word document).\n"
        "2. Your Bachelor's academic transcript showing your modules "
        "and results (clear PDF or readable images).\n\n"
        "If either document has already been sent, please tell us and "
        "we will check your existing record. If you cannot obtain a "
        "transcript yet, let us know so we can explain what can be "
        "assessed provisionally and what remains unverified.\n\n"
        "For your privacy, do not send banking details, passwords, PINs, "
        "national ID numbers or unrelated sensitive information. You may "
        "hide unnecessary personal identifiers from the documents.\n\n"
        "Your MWK 5,000 eligibility-check payment is already confirmed. "
        "No additional payment is required for this service. "
        "We will confirm receipt of the documents and review them "
        "before issuing your written eligibility assessment.\n\n"
        "Thank you for choosing IBROWS Enterprise."
    )
