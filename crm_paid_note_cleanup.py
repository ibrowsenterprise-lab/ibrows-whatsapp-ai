"""Correct a single stale historical payment note after ledger verification.

Only lead #19 can be touched, and only if the exact known pre-payment wording
is still present and there is exactly one MWK 5,000 verified receipt.
An original snapshot is archived before any change in the same transaction.
No payment record or service status is altered.
"""
from decimal import Decimal
import sys

LEAD_ID = 19
OLD_PAYMENT_CLAUSE = (
    "They sent an Airtel payment screenshot, but the ledger currently "
    "shows Scholarship Search as NOT_PAID."
)
OLD_REASON = "Payment verification requires confirmation by the IBROWS team."
NEW_PAYMENT_CLAUSE = (
    "The customer supplied an Airtel payment screenshot. "
    "The corresponding MK5,000 payment was later verified and recorded "
    "in the IBROWS ledger on 10 November 2026."
)
NEW_REASON = (
    "Payment verified for the one-off MK5,000 Eligibility Check. "
    "Collect academic qualifications and supporting details; complete "
    "the eligibility assessment. No second payment is due for this package."
)


def correction_is_safe(lead, payment):
    if not lead or not payment:
        return False
    lead_id, service, summary, reason, amount, currency, status, deleted, merged = lead
    count, total, payment_currency = payment
    return bool(
        lead_id == LEAD_ID
        and service == "Scholarship Eligibility Check"
        and isinstance(summary, str) and OLD_PAYMENT_CLAUSE in summary
        and reason == OLD_REASON
        and Decimal(str(amount or 0)) == Decimal("5000")
        and currency == "MWK"
        and status in ("NEW", "CONTACTED")
        and deleted is None and merged is None
        and int(count) == 1
        and Decimal(str(total or 0)) == Decimal("5000")
        and payment_currency == "MWK"
    )


def correct_paid_eligibility_note_once(flask_app):
    core = sys.modules.get("app")
    if core is None or not callable(getattr(core, "get_db", None)):
        return False
    try:
        with core.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (11920261111,))
                cur.execute("""
                    SELECT id,service,summary,handover_reason,estimated_value,
                           COALESCE(value_currency,'MWK'),status,
                           privacy_deleted_at,merged_into_lead_id
                    FROM leads WHERE id=%s FOR UPDATE
                """, (LEAD_ID,))
                lead = cur.fetchone()
                cur.execute("""
                    SELECT COUNT(*),COALESCE(SUM(amount),0),MIN(currency)
                    FROM lead_payments WHERE lead_id=%s
                """, (LEAD_ID,))
                payment = cur.fetchone()
                if not correction_is_safe(lead, payment):
                    print("IBROWS PAID NOTE: guards not met; no change", flush=True)
                    return False
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS ibrows_paid_note_archive (
                        source_lead_id BIGINT PRIMARY KEY,
                        original_snapshot JSONB NOT NULL,
                        correction_reason TEXT NOT NULL,
                        archived_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    INSERT INTO ibrows_paid_note_archive
                        (source_lead_id,original_snapshot,correction_reason)
                    SELECT id,to_jsonb(l),
                           'Post-payment correction of stale AI NOT_PAID claim'
                    FROM leads l WHERE id=%s
                    ON CONFLICT (source_lead_id) DO NOTHING
                """, (LEAD_ID,))
                updated = lead[2].replace(OLD_PAYMENT_CLAUSE, NEW_PAYMENT_CLAUSE, 1)
                cur.execute("""
                    UPDATE leads
                    SET summary=%s,handover_reason=%s,updated_at=NOW()
                    WHERE id=%s AND service='Scholarship Eligibility Check'
                      AND summary=%s AND handover_reason=%s
                """,(updated, NEW_REASON, LEAD_ID, lead[2], OLD_REASON))
                if cur.rowcount != 1:
                    raise RuntimeError("Paid CRM note changed during correction; rollback")
                cur.execute("""
                    INSERT INTO lead_activity(lead_id,activity_type,description)
                    VALUES(%s,'LEAD_UPDATED',%s)
                """,(
                    LEAD_ID,
                    "Updated pre-payment AI summary after independently verified "
                    "MK5,000 ledger receipt. Historical snapshot archived; "
                    "payment amount and service status unchanged.",
                ))
            conn.commit()
    except Exception as exc:
        print("IBROWS PAID NOTE: rollback or safe skip "
              f"({type(exc).__name__})",flush=True)
        return False
    print("IBROWS PAID NOTE CORRECTED: stale payment warning replaced",flush=True)
    return True
