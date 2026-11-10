"""One-time 2026-11-10 IBROWS production data clean slate.

User explicitly confirmed the only real transactions/projects are the
Agriculture Marketplace and Martha's verified MWK 5,000 Eligibility Check.
Remove *old* demonstration operational data only; preserve public assets,
service configuration, the agricultural supply chain, and the paid customer.

Financial test data is first copied into a private non-operational audit
table, never summed as sales. Do not archive old chat content: delete it.

Runs transactionally on a specific known database state, fails closed if any
guard fails, and is idempotent via an event marker. No external API calls.
"""
from decimal import Decimal
from datetime import datetime, timezone
import sys

EVENT_KEY = "IBROWS_REAL_ONLY_AGRICULTURE_AND_MARTHA_20261110"
# Snapshot boundary: new business activity after this time must be retained.
CUTOFF = datetime(2026, 11, 10, 20, 1, 0, tzinfo=timezone.utc)
MARTHA_CHAT_START = datetime(2026, 11, 10, 16, 32, 0, tzinfo=timezone.utc)
LOCK_ID = 81420261110

REAL_LEAD_ID = 19
DEMO_LEAD_IDS = tuple(range(1, 19))
DEMO_WEBSITE_IDS = (1, 2, 3, 4, 5)
AGRO_WEBSITE_IDS = (8, 9, 10, 11)
DEMO_PROJECT_IDS = (2, 7)
AGRO_LISTING_IDS = (1, 436, 437)
AGRO_RICE_SOURCE_IDS = (436, 437)

# Only tables explicitly enumerated here can be archived or cleaned.
# Public product catalogs, seller submissions and site media are NEVER targets.
ARCHIVE_TABLES = (
    ("leads", "l.id = ANY(%s) AND l.created_at < %s",
        (list(DEMO_LEAD_IDS), CUTOFF), "DEMO_CRM_LEAD"),
    ("lead_payments", "l.lead_id = ANY(%s)",
        (list(DEMO_LEAD_IDS),), "DEMO_PAYMENT_NOT_REVENUE"),
    ("payment_void_audit", "l.lead_id = ANY(%s)",
        (list(DEMO_LEAD_IDS),), "HISTORICAL_DEMO_PAYMENT_VOID"),
    ("business_documents", "l.lead_id = ANY(%s)",
        (list(DEMO_LEAD_IDS),), "DEMO_DOCUMENT_NOT_RECEIVABLE"),
    ("project_assessments", "l.id = ANY(%s) AND l.created_at < %s",
        (list(DEMO_PROJECT_IDS), CUTOFF), "DEMO_PROJECT"),
    ("project_costing", "l.project_id = ANY(%s)",
        (list(DEMO_PROJECT_IDS),), "DEMO_PROJECT_COSTING"),
    ("project_quotations", "l.project_id = ANY(%s)",
        (list(DEMO_PROJECT_IDS),), "DEMO_QUOTATION"),
    ("project_invoices", "l.project_id = ANY(%s)",
        (list(DEMO_PROJECT_IDS),), "DEMO_UNPAID_INVOICE_NOT_RECEIVABLE"),
    ("project_sandbox_payments", "l.project_id = ANY(%s)",
        (list(DEMO_PROJECT_IDS),), "SANDBOX_NOT_REVENUE"),
    ("project_sandbox_state", "l.project_id = ANY(%s)",
        (list(DEMO_PROJECT_IDS),), "DEMO_SANDBOX_STATE"),
    ("project_quotation_events", "l.quotation_id IN "
        "(SELECT id FROM project_quotations WHERE project_id = ANY(%s))",
        (list(DEMO_PROJECT_IDS),), "DEMO_QUOTATION_HISTORY"),
    ("website_service_requests", "l.id = ANY(%s) AND l.service_key <> 'AGRICULTURE' "
        "AND l.created_at < %s",
        (list(DEMO_WEBSITE_IDS), CUTOFF), "DEMO_WEBSITE_REQUEST"),
    ("website_service_request_files", "l.request_id = ANY(%s)",
        (list(DEMO_WEBSITE_IDS),), "DEMO_ATTACHMENT_METADATA_ONLY"),
    ("business_expense_budgets", "l.id=1 AND l.amount=1000 "
        "AND l.budget_year=2026 AND l.budget_month=9", (),
        "DEMO_BUDGET_NOT_REAL"),
)

# Content, configuration, compliance history, portfolios and online store
# are protected regardless of the user's historic demonstration projects.
PROTECTED_TABLES = (
    "agro_marketplace_listings",
    "agro_marketplace_listing_sources",
    "agro_marketplace_buyer_enquiries",
    "msj_merch_designs",
    "msj_merch_orders",
    "website_service_portfolio_assets",
    "construction_portfolio_assets",
    "business_document_sequences",
    "ibrows_task_health",
    "ibrows_qa_cleanup_archive",
    "ibrows_verified_record_correction_archive",
    "system_incidents",
)


def validate_clean_slate_snapshot(state):
    """Pure, strict validation that avoids an incorrect production reset."""
    if state["real_lead"] != (
        19, "Martha", "Scholarship Eligibility Check",
        Decimal("5000"), "MWK",
    ):
        return False
    if state["real_payment"] != (1, Decimal("5000"), "MWK"):
        return False
    if state["demo_lead_ids"] != list(DEMO_LEAD_IDS):
        return False
    if not set(state["demo_lead_names"]).issubset({
        "Jones #ibrows", "Martha", "Ibrows Enterprise"
    }):
        return False
    if state["demo_payment"] != (5, Decimal("62000")):
        return False
    if state["project_ids"] != list(DEMO_PROJECT_IDS):
        return False
    if state["project_finance"] != (
        2, Decimal("3425000"), 2, Decimal("3000000")
    ):
        return False
    if state["website_demo_ids"] != list(DEMO_WEBSITE_IDS):
        return False
    if state["agro_request_ids"] != list(AGRO_WEBSITE_IDS):
        return False
    if state["agro_listing_ids"] != list(AGRO_LISTING_IDS):
        return False
    if state["agro_rice_source_count"] != 2:
        return False
    if state["unanticipated_recent_demo_payment"] != 0:
        return False
    return True


def _snapshot(cur):
    """Lock old CRM roots; read preflight conditions inside one transaction."""
    cur.execute(
        "SELECT id FROM leads WHERE id=ANY(%s) ORDER BY id FOR UPDATE",
        (list(DEMO_LEAD_IDS),),
    )
    lead_ids = [x[0] for x in cur.fetchall()]

    cur.execute(
        """SELECT id,customer_name,service,estimated_value,
                  COALESCE(value_currency,'MWK')
           FROM leads WHERE id=%s FOR SHARE""",
        (REAL_LEAD_ID,),
    )
    row = cur.fetchone()
    real_lead = None if not row else (
        row[0], row[1], row[2], Decimal(str(row[3])), row[4]
    ) if row[3] is not None else None

    cur.execute(
        """SELECT COUNT(*),COALESCE(SUM(amount),0),
                  MIN(currency)
           FROM lead_payments WHERE lead_id=%s""",
        (REAL_LEAD_ID,),
    )
    n, amount, currency = cur.fetchone()
    real_payment = (int(n), Decimal(str(amount)), currency)

    cur.execute(
        "SELECT DISTINCT customer_name FROM leads WHERE id=ANY(%s) ORDER BY customer_name",
        (list(DEMO_LEAD_IDS),),
    )
    demo_names = [x[0] for x in cur.fetchall()]

    cur.execute(
        """SELECT COUNT(*),COALESCE(SUM(amount),0)
           FROM lead_payments WHERE lead_id=ANY(%s)""",
        (list(DEMO_LEAD_IDS),),
    )
    n, amount = cur.fetchone()
    demo_payment = (int(n), Decimal(str(amount)))

    cur.execute(
        "SELECT id FROM project_assessments WHERE id=ANY(%s) ORDER BY id FOR UPDATE",
        (list(DEMO_PROJECT_IDS),),
    )
    project_ids = [x[0] for x in cur.fetchall()]

    cur.execute(
        "SELECT COUNT(*),COALESCE(SUM(amount),0) FROM project_invoices WHERE project_id=ANY(%s)",
        (list(DEMO_PROJECT_IDS),),
    )
    in_n, in_sum = cur.fetchone()
    cur.execute(
        "SELECT COUNT(*),COALESCE(SUM(amount),0) FROM project_sandbox_payments WHERE project_id=ANY(%s)",
        (list(DEMO_PROJECT_IDS),),
    )
    sb_n, sb_sum = cur.fetchone()
    project_finance = (int(in_n), Decimal(str(in_sum)), int(sb_n), Decimal(str(sb_sum)))

    cur.execute(
        """SELECT id FROM website_service_requests
           WHERE id=ANY(%s) AND service_key <> 'AGRICULTURE'
           ORDER BY id FOR UPDATE""",
        (list(DEMO_WEBSITE_IDS),),
    )
    website_demo_ids = [x[0] for x in cur.fetchall()]
    cur.execute(
        "SELECT id FROM website_service_requests WHERE service_key='AGRICULTURE' ORDER BY id",
    )
    agro_request_ids = [x[0] for x in cur.fetchall()]
    cur.execute(
        "SELECT id FROM agro_marketplace_listings WHERE status='APPROVED' ORDER BY id",
    )
    agro_listing_ids = [x[0] for x in cur.fetchall()]
    cur.execute(
        "SELECT COUNT(*) FROM agro_marketplace_listing_sources WHERE listing_id=ANY(%s)",
        (list(AGRO_RICE_SOURCE_IDS),),
    )
    agro_rice_source_count = int(cur.fetchone()[0])

    cur.execute(
        "SELECT COUNT(*) FROM lead_payments WHERE lead_id=ANY(%s) AND received_at>=%s",
        (list(DEMO_LEAD_IDS), CUTOFF),
    )
    unanticipated = int(cur.fetchone()[0])

    return {
        "real_lead": real_lead,
        "real_payment": real_payment,
        "demo_lead_ids": lead_ids,
        "demo_lead_names": demo_names,
        "demo_payment": demo_payment,
        "project_ids": project_ids,
        "project_finance": project_finance,
        "website_demo_ids": website_demo_ids,
        "agro_request_ids": agro_request_ids,
        "agro_listing_ids": agro_listing_ids,
        "agro_rice_source_count": agro_rice_source_count,
        "unanticipated_recent_demo_payment": unanticipated,
    }


def _archive(cur, table, where_clause, params, classification):
    """Copy compact metadata and all finance/legal records before deleting."""
    # Binary attachment bytes are deliberately excluded from archive; this
    # permanently removes the old 7MB demo upload rather than duplicating it.
    snapshot = ("to_jsonb(l) - 'file_bytes'"
                if table == "website_service_request_files"
                else "to_jsonb(l)")
    sql = f"""
        INSERT INTO ibrows_clean_slate_audit
            (source_table, source_pk, original_snapshot, classification)
        SELECT %s, l.id::text, {snapshot}, %s
        FROM {table} l WHERE {where_clause}
        ON CONFLICT (source_table,source_pk) DO NOTHING
    """
    cur.execute(sql, (table, classification, *params))
    return cur.rowcount


def _delete(cur, table, where_clause, params=()):
    cur.execute(f"DELETE FROM {table} WHERE {where_clause}", params)
    return int(cur.rowcount)


def run_clean_slate_once(flask_app):
    """Execute guarded 2026-11-10 reset exactly once on production deployment."""
    core = sys.modules.get("app")
    if core is None or not callable(getattr(core, "get_db", None)):
        print("IBROWS REAL DATA RESET: app unavailable; safely skipped", flush=True)
        return False

    rows_deleted = {}
    audit_copied = 0
    try:
        with core.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS ibrows_clean_slate_events (
                        event_key TEXT PRIMARY KEY,
                        completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        deleted_counts JSONB NOT NULL,
                        rationale TEXT NOT NULL
                    )
                """)
                cur.execute(
                    "SELECT EXISTS(SELECT 1 FROM ibrows_clean_slate_events WHERE event_key=%s)",
                    (EVENT_KEY,),
                )
                if cur.fetchone()[0]:
                    print("IBROWS REAL DATA RESET: already completed, no-op", flush=True)
                    return True

                pre = _snapshot(cur)
                if not validate_clean_slate_snapshot(pre):
                    raise RuntimeError("Preflight mismatch: no record changed")

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS ibrows_clean_slate_audit (
                        source_table TEXT NOT NULL,
                        source_pk TEXT NOT NULL,
                        original_snapshot JSONB NOT NULL,
                        classification TEXT NOT NULL,
                        archived_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (source_table, source_pk)
                    )
                """)
                for table, where, params, classification in ARCHIVE_TABLES:
                    audit_copied += _archive(cur, table, where, params, classification)

                # Any genuinely new leads/requests arriving after CUTOFF
                # are protected; this reset is frozen to historic test IDs.
                old_id_list = list(DEMO_LEAD_IDS)
                project_ids = list(DEMO_PROJECT_IDS)
                web_ids = list(DEMO_WEBSITE_IDS)

                # Career assistant test data is not a real paid service.
                for table, ts in (
                    ("application_confirmation_evidence","created_at"),
                    ("application_evidence_corrections","created_at"),
                    ("career_verified_vacancies","first_verified_at"),
                    ("career_assist_applications","started_at"),
                    ("career_assist_application_consent_events","created_at"),
                ):
                    rows_deleted[table] = _delete(
                        cur, table, f"({ts}<%s OR {ts} IS NULL)",
                        (CUTOFF,),
                    )
                rows_deleted["application_pack_state"] = _delete(
                    cur, "application_pack_state",
                    "updated_at<%s AND customer_number<>("
                    "SELECT customer_number FROM leads WHERE id=%s)",
                    (CUTOFF, REAL_LEAD_ID),
                )

                # Fake CRM finance is audit-archived first and deleted only
                # through the old lead roots: real lead #19 is not selected.
                rows_deleted["old_leads"] = _delete(
                    cur, "leads", "id=ANY(%s) AND created_at<%s",
                    (old_id_list, CUTOFF),
                )
                if rows_deleted["old_leads"] != len(DEMO_LEAD_IDS):
                    raise RuntimeError("Old CRM row count changed; rollback")

                # Projects cascade quotes, dummy invoices, demo sandbox
                # payments, project notes/events and other test artifacts.
                rows_deleted["old_projects"] = _delete(
                    cur, "project_assessments", "id=ANY(%s) AND created_at<%s",
                    (project_ids, CUTOFF),
                )
                if rows_deleted["old_projects"] != 2:
                    raise RuntimeError("Old project row count changed; rollback")

                # Preserves ALL agricultural website submissions, buyer
                # enquiries, listing sources and all three approved listings.
                rows_deleted["non_agri_requests"] = _delete(
                    cur, "website_service_requests",
                    "id=ANY(%s) AND service_key<>'AGRICULTURE' AND created_at<%s",
                    (web_ids, CUTOFF),
                )
                if rows_deleted["non_agri_requests"] != len(DEMO_WEBSITE_IDS):
                    raise RuntimeError("Website QA count changed; rollback")

                # Preserve only Martha's current paid-service conversation.
                # All earlier September test chatter, including from Martha's
                # number, is removed so the AI will not confuse service context.
                cur.execute(
                    "SELECT customer_number FROM leads WHERE id=%s",
                    (REAL_LEAD_ID,),
                )
                mnum = cur.fetchone()[0]
                rows_deleted["old_chat_messages"] = _delete(
                    cur, "conversations",
                    "created_at<%s AND NOT (customer_number=%s AND created_at>=%s)",
                    (CUTOFF, mnum, MARTHA_CHAT_START),
                )
                rows_deleted["old_attachment_memories"] = _delete(
                    cur, "attachment_memories",
                    "created_at<%s AND NOT (customer_number=%s AND created_at>=%s)",
                    (CUTOFF, mnum, MARTHA_CHAT_START),
                )
                rows_deleted["old_message_dedupe"] = _delete(
                    cur, "processed_whatsapp_messages",
                    "processed_at<%s AND NOT (customer_number=%s AND processed_at>=%s)",
                    (CUTOFF, mnum, MARTHA_CHAT_START),
                )
                rows_deleted["old_human_handover_states"] = _delete(
                    cur, "ai_takeover_state",
                    "customer_number<>%s AND updated_at<%s", (mnum, CUTOFF)
                )
                rows_deleted["old_menu_states"] = _delete(
                    cur, "customer_menu_state",
                    "customer_number<>%s AND updated_at<%s", (mnum, CUTOFF)
                )
                # Keep unexpired delivery retries: never discard a queued
                # outbound message merely because the conversation was a test.
                rows_deleted["old_outbox"] = 0

                rows_deleted["demo_budget"] = _delete(
                    cur, "business_expense_budgets",
                    "id=1 AND amount=1000 AND budget_year=2026 AND budget_month=9",
                )

                # Double-check no original fake finance remains active,
                # and the genuine one-time paid service survives exactly.
                cur.execute("SELECT COUNT(*) FROM leads WHERE id=ANY(%s)", (old_id_list,))
                if int(cur.fetchone()[0]) != 0:
                    raise RuntimeError("Old leads still active")
                cur.execute(
                    """SELECT l.service,l.estimated_value,COUNT(p.id),
                              COALESCE(SUM(p.amount),0)
                       FROM leads l LEFT JOIN lead_payments p ON p.lead_id=l.id
                       WHERE l.id=%s GROUP BY l.id""",
                    (REAL_LEAD_ID,),
                )
                actual = cur.fetchone()
                if (not actual or actual[0] != "Scholarship Eligibility Check"
                        or Decimal(str(actual[1])) != Decimal("5000")
                        or int(actual[2]) != 1
                        or Decimal(str(actual[3])) != Decimal("5000")):
                    raise RuntimeError("Real MK5,000 payment safeguard failed")

                # Record one audit marker, not a fake revenue transaction.
                from json import dumps
                cur.execute(
                    """INSERT INTO ibrows_clean_slate_events
                       (event_key,deleted_counts,rationale)
                       VALUES (%s,%s::jsonb,%s)""",
                    (
                        EVENT_KEY, dumps(rows_deleted),
                        "User confirmed 10 Nov 2026: only Agriculture Marketplace "
                        "and Martha one-off MWK 5000 scholarship screening are real. "
                        "Prior lead payments and project invoices were demonstrations; "
                        "financial snapshots retained outside active reporting.",
                    ),
                )
            conn.commit()
    except Exception as exc:
        print(
            f"IBROWS REAL DATA RESET: safely rolled back ({type(exc).__name__})",
            flush=True,
        )
        return False

    print(
        "IBROWS REAL DATA RESET COMPLETE: "
        f"old_leads={rows_deleted.get('old_leads')} "
        f"old_projects={rows_deleted.get('old_projects')} "
        f"non_agri_requests={rows_deleted.get('non_agri_requests')} "
        f"old_chat_messages={rows_deleted.get('old_chat_messages')} "
        f"audit_records={audit_copied}",
        flush=True,
    )
    return True
