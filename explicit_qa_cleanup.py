"""One-time, strictly scoped cleanup of three confirmed internal QA records.

Only two website requests that explicitly label themselves as internal tests and
one noncommercial "Test" project may be removed. Their complete row snapshots
(including related project activity) are archived first in the same transaction.
Never touches CRM leads, conversations, payments, invoices, real listings, or
existing approved products. An identifier and exact label must both match.
"""
import sys

WEBSITE_TEST_REQUESTS = (
    (6, "IBROWS QA TEST - DO NOT SERVICE"),
    (7, "IBROWS INTERNAL TEST — Media enquiry"),
)
PROJECT_TEST_ID = 1
PROJECT_TEST_NAME = "Test"
ADVISORY_LOCK_ID = 719620261110


def run_exact_qa_cleanup(flask_app):
    """No-op on missing core DB; errors rollback and must not prevent boot."""
    core = sys.modules.get("app")
    if core is None or not callable(getattr(core, "get_db", None)):
        print("IBROWS QA CLEANUP: core app not ready; skipped", flush=True)
        return False

    removed_requests = 0
    removed_projects = 0
    archive_rows = 0
    try:
        with core.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (ADVISORY_LOCK_ID,))
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS ibrows_qa_cleanup_archive (
                        source_table TEXT NOT NULL,
                        source_id BIGINT NOT NULL,
                        source_snapshot JSONB NOT NULL,
                        archived_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (source_table,source_id)
                    )
                """)

                for request_id, exact_name in WEBSITE_TEST_REQUESTS:
                    cur.execute(
                        """SELECT id FROM website_service_requests
                           WHERE id=%s AND full_name=%s FOR UPDATE""",
                        (request_id, exact_name),
                    )
                    if cur.fetchone() is None:
                        continue
                    # No product listing, photo, customer or downstream enquiry
                    # is permitted to depend on this row.
                    cur.execute(
                        """SELECT
                           EXISTS(SELECT 1 FROM website_service_request_files
                                  WHERE request_id=%s)
                           OR EXISTS(SELECT 1 FROM agro_marketplace_listings
                                     WHERE source_request_id=%s)
                           OR EXISTS(SELECT 1 FROM agro_marketplace_listing_sources
                                     WHERE source_request_id=%s)
                           OR EXISTS(SELECT 1 FROM agro_marketplace_buyer_enquiries
                                     WHERE service_request_id=%s)""",
                        (request_id,)*4,
                    )
                    if cur.fetchone()[0]:
                        print("IBROWS QA CLEANUP: website record has dependencies; skipped",flush=True)
                        continue
                    cur.execute(
                        """INSERT INTO ibrows_qa_cleanup_archive
                           (source_table,source_id,source_snapshot)
                           SELECT 'website_service_requests',id,to_jsonb(r)
                           FROM website_service_requests r
                           WHERE id=%s AND full_name=%s
                           ON CONFLICT (source_table,source_id) DO NOTHING""",
                        (request_id, exact_name),
                    )
                    archive_rows += cur.rowcount
                    cur.execute(
                        "DELETE FROM website_service_requests WHERE id=%s AND full_name=%s",
                        (request_id, exact_name),
                    )
                    if cur.rowcount != 1:
                        raise RuntimeError("Expected one website QA row; transaction rolled back")
                    removed_requests += 1

                cur.execute(
                    """SELECT id FROM project_assessments
                       WHERE id=%s AND contact_name=%s AND status='NEW'
                       FOR UPDATE""",
                    (PROJECT_TEST_ID, PROJECT_TEST_NAME),
                )
                if cur.fetchone() is not None:
                    # Commercial records or sandbox revenue must never be removed
                    # through this automatic QA cleanup.
                    blockers = (
                        "project_quotations", "project_payments", "project_invoices",
                        "project_execution", "project_sandbox_payments",
                        "project_sandbox_state", "project_costing",
                        "project_tasks", "project_milestones", "project_stage_invoices",
                        "project_client_updates", "project_cost_import_staging",
                    )
                    blocked = False
                    for table in blockers:
                        cur.execute(
                            f"SELECT EXISTS(SELECT 1 FROM {table} WHERE project_id=%s)",
                            (PROJECT_TEST_ID,),
                        )
                        if cur.fetchone()[0]:
                            blocked = True
                            break
                    if not blocked:
                        cur.execute(
                            """INSERT INTO ibrows_qa_cleanup_archive
                               (source_table,source_id,source_snapshot)
                               SELECT 'project_assessments',id,to_jsonb(p)
                               FROM project_assessments p
                               WHERE id=%s AND contact_name=%s AND status='NEW'
                               ON CONFLICT (source_table,source_id) DO NOTHING""",
                            (PROJECT_TEST_ID, PROJECT_TEST_NAME),
                        )
                        archive_rows += cur.rowcount
                        cur.execute(
                            """INSERT INTO ibrows_qa_cleanup_archive
                               (source_table,source_id,source_snapshot)
                               SELECT 'project_activity',id,to_jsonb(a)
                               FROM project_activity a WHERE project_id=%s
                               ON CONFLICT (source_table,source_id) DO NOTHING""",
                            (PROJECT_TEST_ID,),
                        )
                        archive_rows += cur.rowcount
                        # FK cascade removes only the already-archived activity.
                        cur.execute(
                            """DELETE FROM project_assessments
                               WHERE id=%s AND contact_name=%s AND status='NEW'""",
                            (PROJECT_TEST_ID, PROJECT_TEST_NAME),
                        )
                        if cur.rowcount != 1:
                            raise RuntimeError("Expected one project QA row; transaction rolled back")
                        removed_projects = 1
                    else:
                        print("IBROWS QA CLEANUP: project has commercial dependencies; skipped",flush=True)
            conn.commit()
    except Exception as error:
        # psycopg connection context handles rollback on errors.
        print(f"IBROWS QA CLEANUP: safely rolled back ({type(error).__name__})",flush=True)
        return False

    print(
        "IBROWS QA CLEANUP COMPLETE: "
        f"requests={removed_requests} projects={removed_projects} "
        f"new_archived_rows={archive_rows}",
        flush=True,
    )
    return True
