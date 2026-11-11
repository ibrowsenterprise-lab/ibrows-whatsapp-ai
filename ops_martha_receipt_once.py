"""Explicit, one-time receipt delivery authorised for existing paid client.

Authorisation: user asked IBROWS to send Martha her receipt on 11 Nov 2026.
This is NOT an automatic historical backfill. Every safeguard is tied to
the exact real lead #19 and existing payment #10.

Run once on app startup after automatic_verified_receipts is installed.
A unique payment_id delivery claim prevents multiple workers sending twice.
"""
from decimal import Decimal

LEAD_ID = 19
PAYMENT_ID = 10
AMOUNT = Decimal("5000")
CURRENCY = "MWK"
SERVICE = "Scholarship Eligibility Check"
METHOD = "MOBILE_MONEY"


def matches_authorised_payment(record):
    """Verify actual ledger payment, selected package, price and no prior send."""
    if not record or len(record) != 12:
        return False
    (lead_id,payment_id,service,amount,currency,payment_method,
     estimate,value_currency,merged,deleted,receipt_send_count,receipt_count)=record
    try:
        return (
            lead_id == LEAD_ID
            and payment_id == PAYMENT_ID
            and service == SERVICE
            and Decimal(str(amount)) == AMOUNT
            and currency == CURRENCY
            and payment_method == METHOD
            and Decimal(str(estimate)) == AMOUNT
            and value_currency == CURRENCY
            and merged is None and deleted is None
            and int(receipt_send_count)==0
            and int(receipt_count)==1
        )
    except (ValueError,TypeError,ArithmeticError):
        return False


def authorised_receipt_record(db_factory):
    """Read-only check of exactly one existing verified payment and no sent receipt."""
    with db_factory() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT l.id,p.id,l.service,p.amount,p.currency,p.payment_method,
                       l.estimated_value,COALESCE(l.value_currency,'MWK'),
                       l.merged_into_lead_id,l.privacy_deleted_at,
                       (SELECT COUNT(*) FROM business_documents d
                          WHERE d.payment_id=p.id AND d.doc_type='receipt'
                          AND (d.last_sent_at IS NOT NULL OR
                               COALESCE(d.send_count,0)>0)),
                       (SELECT COUNT(*) FROM lead_payments p2 WHERE p2.lead_id=l.id)
                FROM leads l JOIN lead_payments p ON p.lead_id=l.id
                WHERE l.id=%s AND p.id=%s LIMIT 1
            """,(LEAD_ID,PAYMENT_ID))
            record=cur.fetchone()
    return matches_authorised_payment(record)


def send_one_off_martha_receipt(flask_app):
    """Creates no payments, does not touch any other lead, skips old sent receipts."""
    from automatic_verified_receipts import _queue_new_payment,_attempt_delivery
    view=flask_app.view_functions.get("admin_leads")
    if not view:
        return "ADMIN_ROUTE_UNAVAILABLE"
    ns=view.__globals__
    db=ns.get("get_db")
    if not callable(db):
        return "DB_UNAVAILABLE"
    try:
        if not authorised_receipt_record(db):
            print("IBROWS MARTHA RECEIPT: verified-payment guard not met; no action",
                  flush=True)
            return "SAFE_SKIP"
        # Unique payment_id claim is atomic across multiple gunicorn workers.
        # It is not a new payment in the financial ledger.
        if not _queue_new_payment(db, LEAD_ID, PAYMENT_ID):
            print("IBROWS MARTHA RECEIPT: already claimed, no duplicate",flush=True)
            return "ALREADY_CLAIMED"
        result=_attempt_delivery(ns,PAYMENT_ID)
        print("IBROWS MARTHA RECEIPT one-time result="+str(result),flush=True)
        return result
    except Exception as exc:
        print("IBROWS MARTHA RECEIPT safe failure: "
              +type(exc).__name__,flush=True)
        return "ERROR"
