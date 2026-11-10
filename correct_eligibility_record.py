"""One-time correction of one verified one-off scholarship eligibility lead.

Never records or alters a payment. Uses a locked row, exact customer/lead,
selected scope, one real matching ledger receipt, and an archive-first
transaction to correct a mismatched generic service label.
"""
import sys
from decimal import Decimal

TARGET_LEAD_ID = 19
OLD_SERVICE = "Scholarship Search"
NEW_SERVICE = "Scholarship Eligibility Check"
PRICE = Decimal("5000")
SELECTED_SCOPE = "Customer selected the Eligibility Check package (MK5,000)"


def should_relabel_verified_eligibility(lead, payment):
    if not lead or not payment:
        return False
    (
        lead_id, name, service, summary, estimated, currency, status,
        quote_status, merged, privacy_deleted, consumed,
    ) = lead
    count, amount, mwk_only, mobile_only = payment
    return bool(
        lead_id == TARGET_LEAD_ID
        and name == "Martha"
        and service == OLD_SERVICE
        and SELECTED_SCOPE in (summary or "")
        and estimated is None
        and currency == "MWK"
        and status == "NEW"
        and quote_status == "NOT_STARTED"
        and merged is None
        and privacy_deleted is None
        and consumed is None
        and count == 1
        and Decimal(str(amount or 0)) == PRICE
        and mwk_only is True
        and mobile_only is True
    )


def correct_verified_eligibility_once(flask_app):
    core = sys.modules.get("app")
    if core is None or not callable(getattr(core, "get_db", None)):
        print("IBROWS ELIGIBILITY CORRECTION: app not ready; skipped", flush=True)
        return False
    try:
        with core.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (919620261110,))
                cur.execute(
                    """SELECT id, customer_name, service, summary, estimated_value,
                              COALESCE(value_currency,'MWK'),status,
                              COALESCE(quote_status,'NOT_STARTED'),
                              merged_into_lead_id,privacy_deleted_at,
                              entitlement_consumed_at
                       FROM leads WHERE id=%s FOR UPDATE""",
                    (TARGET_LEAD_ID,),
                )
                lead = cur.fetchone()
                cur.execute(
                    """SELECT COUNT(*), COALESCE(SUM(amount),0),
                              BOOL_AND(currency='MWK'),
                              BOOL_AND(payment_method='MOBILE_MONEY')
                       FROM lead_payments WHERE lead_id=%s""",
                    (TARGET_LEAD_ID,),
                )
                payment = cur.fetchone()
                if not should_relabel_verified_eligibility(lead, payment):
                    print("IBROWS ELIGIBILITY CORRECTION: guard not met, no change",flush=True)
                    return False

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS ibrows_verified_record_correction_archive (
                        source_table TEXT NOT NULL,
                        source_id BIGINT NOT NULL,
                        original_snapshot JSONB NOT NULL,
                        correction_reason TEXT NOT NULL,
                        archived_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (source_table,source_id)
                    )
                """)
                cur.execute(
                    """INSERT INTO ibrows_verified_record_correction_archive
                       (source_table,source_id,original_snapshot,correction_reason)
                       SELECT 'leads',id,to_jsonb(l),
                              'Verified single-payment eligibility package relabel'
                       FROM leads l WHERE id=%s
                       ON CONFLICT (source_table,source_id) DO NOTHING""",
                    (TARGET_LEAD_ID,),
                )
                cur.execute(
                    """UPDATE leads
                       SET service=%s, estimated_value=%s,
                           value_currency='MWK',updated_at=NOW()
                       WHERE id=%s AND service=%s
                         AND estimated_value IS NULL""",
                    (NEW_SERVICE, PRICE, TARGET_LEAD_ID, OLD_SERVICE),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("Expected exactly one eligibility lead; rollback")
                cur.execute(
                    """INSERT INTO lead_activity (lead_id,activity_type,description)
                       VALUES (%s,'LEAD_UPDATED',%s)""",
                    (
                        TARGET_LEAD_ID,
                        "One-off Scholarship Eligibility Check MK5,000 scope corrected "
                        "following existing verified mobile-money receipt; no new "
                        "payment entered or changed.",
                    ),
                )
            conn.commit()
    except Exception as exc:
        print("IBROWS ELIGIBILITY CORRECTION: rollback or skip "
              f"({type(exc).__name__})",flush=True)
        return False
    print("IBROWS ELIGIBILITY CORRECTION COMPLETE: one scope corrected, payment unchanged",flush=True)
    return True
