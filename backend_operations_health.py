"""Read-only operational health for IBROWS's first genuine paid clients.

This is intentionally an administrative dashboard, NOT an autonomous cleanup
daemon. It cannot update leads, payments, receipts, agricultural listings, or
customer chats. It surfaces evidence-backed action items while preserving
client privacy, backed by one authenticated route.
"""
from decimal import Decimal
from datetime import datetime, timedelta, timezone

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>IBROWS Backend Operations</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#f3f5f9;color:#101828;font:15px/1.55 system-ui,Arial,sans-serif}
header{padding:17px 15px;background:#101828;color:#fff}
header a{color:#fff;text-decoration:none;font-weight:600}
main{max-width:850px;margin:auto;padding:13px}
h1{font-size:24px;margin:3px 0 8px}
h2{font-size:18px;margin:2px 0 13px}
.card{background:#fff;border-radius:12px;padding:15px;margin:12px 0;box-shadow:0 1px 5px #0001}
.kpis{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.kpi{border:1px solid #e5e7eb;border-radius:10px;padding:11px}
.kpi strong{display:block;font-size:22px;color:#101828;overflow-wrap:anywhere}
.small{font-size:13px;color:#667085}
.action{display:block;border:1px solid #ccd2da;padding:11px;text-align:center;text-decoration:none;border-radius:9px;color:#101828;font-weight:700;margin:9px 0;min-height:44px}
.warning{background:#fff7ed;border-left:4px solid #d97706;padding:11px;border-radius:7px}
.good{background:#effdf3;border-left:4px solid #059669;padding:11px;border-radius:7px}
.case{border-top:1px solid #e5e7eb;padding:13px 0}
.case:first-child{border-top:0}
.tag{display:inline-block;font-size:12px;font-weight:700;border-radius:20px;background:#f1f5f9;padding:4px 10px;margin:3px 0}
code{overflow-wrap:anywhere}
</style></head><body>
<header><a href="{{ url_for('admin_leads') }}">← Customers &amp; Enquiries</a></header>
<main>
<div class="card">
<p class="small">IBROWS Enterprise · Administrator only · Read-only system checks</p>
<h1>Backend Operations</h1>
<p class="small">Last checked: {{ checked_at }} (Malawi). Refresh to check again. No records are changed by this page.</p>
<div class="kpis">
<div class="kpi"><span class="small">Active CRM leads</span><strong>{{ totals.leads }}</strong></div>
<div class="kpi"><span class="small">Recorded payments</span><strong>{{ totals.payments }}</strong></div>
<div class="kpi"><span class="small">Verified MWK receipts</span><strong>{{ "{:,.0f}".format(totals.verified_mwk) }}</strong></div>
<div class="kpi"><span class="small">Approved agricultural listings</span><strong>{{ totals.agro_approved }}</strong></div>
</div>
<p class="small">Customer payment status comes only from the verified ledger, never a screenshot or an AI-generated note.</p>
</div>

<section class="card">
<h2>Priority actions before serving more clients</h2>
{% if pending_paid %}
<div class="warning"><strong>{{ pending_paid }} verified paid service case(s) still not marked delivered.</strong>
<p>Open each paid case below, check the customer's existing information, and complete the promised service. A paid receipt does not mean work was completed.</p></div>
{% else %}
<div class="good">No unfinished paid scholarship eligibility cases were found in the monitored service.</div>
{% endif %}
{% if reminder_health.attention %}
<div class="warning"><strong>Reminder scheduler needs verification.</strong>
<p>{{ reminder_health.description }}</p></div>
{% else %}
<div class="good">{{ reminder_health.description }}</div>
{% endif %}
{% if paused_handoffs %}
<div class="warning"><strong>{{ paused_handoffs }} conversation(s) currently paused for human assistance.</strong>
<p>Review the secure Inbox and ensure each customer has an actual response. Paused state alone does not prove a customer is waiting.</p></div>
{% else %}
<p class="small">No current AI-paused human handovers recorded.</p>
{% endif %}
<a class="action" href="{{ url_for('admin_inbox') }}">Check secure Inbox and human handovers</a>
<p class="small">These are read-only advisory checks. They do not send messages, create reminders, or alter payments. The 48-hour monitoring threshold is an operational warning, not a customer service deadline.</p>
</section>

<section class="card">
<h2>Paid service — customer replies</h2>
{% for item in paid_cases %}
<div class="case">
<strong>{{ item.name }} · {{ item.service }}</strong>
<p class="small">Enquiry: {{ item.enquiry_status }} · Work stage: {{ item.stage }} · Paid: MWK {{ "{:,.0f}".format(item.paid_mwk) }}</p>
{% if item.needs_review %}
<div class="warning"><strong>New customer reply needs review</strong>
<p>Customer messaged after the saved intake request. Check what was supplied; this alone does not mean an eligibility report is ready.</p></div>
{% elif item.waiting %}
<div class="good"><strong>Awaiting customer response</strong><p>No newer inbound message appears after the saved intake.</p></div>
{% else %}
<div class="warning"><strong>Review intake status</strong><p>No matching saved intake request was found, so the system cannot determine whether the customer has replied.</p></div>
{% endif %}
<a class="action" href="{{ url_for('admin_eligibility_case',lead_id=item.id) }}">Open eligibility work queue</a>
</div>
{% else %}
<p>No active verified one-off scholarship eligibility cases require review.</p>
{% endfor %}
</section>

<section class="card">
<h2>Payments and receipts</h2>
<p><strong>{{ totals.receipt_issues }}</strong> receipt deliveries require attention.</p>
<p class="small">Failed, document-error, or long-running attempts are counted. An API-accepted receipt is not proof of handset delivery.</p>
<p><strong>{{ totals.orphaned_receipts }}</strong> orphaned receipt delivery pointers.</p>
<p><strong>{{ totals.duplicate_payment_tokens }}</strong> duplicated non-empty ledger request tokens.</p>
{% if totals.receipt_issues or totals.orphaned_receipts or totals.duplicate_payment_tokens %}
<div class="warning">Review these accounting integrity flags before entering any new payment.</div>
{% endif %}
<a class="action" href="{{ url_for('admin_auto_receipts') }}">Review receipt deliveries</a>
</section>

<section class="card">
<h2>WhatsApp processing</h2>
<p><strong>{{ totals.webhook_unfinished }}</strong> webhook jobs not marked completed.</p>
<p><strong>{{ totals.outbox_attention }}</strong> unsent, failed or in-flight outbox items.</p>
{% if totals.webhook_unfinished or totals.outbox_attention %}
<div class="warning">Inspect the pending records and Render logs; do not blindly replay potentially sent messages.</div>
{% else %}
<div class="good">No incomplete message processing or outbox items detected.</div>
{% endif %}
<a class="action" href="{{ url_for('admin_inbox') }}">Open IBROWS WhatsApp Inbox</a>
</section>

<section class="card">
<h2>Agriculture data integrity</h2>
<p><strong>{{ totals.agro_approved }}</strong> approved product listings; <strong>{{ totals.agro_requests }}</strong> seller submissions.</p>
<p><strong>{{ totals.agro_invalid }}</strong> approved listings missing a valid positive price, quantity or seller contact.</p>
<p><strong>{{ totals.agro_orphaned_sources }}</strong> listing-source links without an existing listing.</p>
{% if totals.agro_invalid or totals.agro_orphaned_sources %}
<div class="warning">Agriculture needs a data review. No listing has been changed automatically.</div>
{% else %}
<div class="good">No invalid approved listing or orphaned listing-source references detected.</div>
{% endif %}
</section>

<section class="card">
<h2>Backend storage</h2>
<p>Published website-gallery media: <strong>{{ media.website_mb }} MB</strong></p>
<p>Construction portfolio media: <strong>{{ media.construction_mb }} MB</strong></p>
<p class="small">These are legitimate public website assets, not dummy client payments. Large media stored in Postgres may justify a future managed object-storage migration with backups and a rollback plan. Nothing is deleted here.</p>
</section>

<p class="small">Data is private to administrators. No customer chat text, account number, identity documents or API tokens are shown.</p>
</main></body></html>"""


def classify_reminder_health(last_run_at, last_ok, has_error, now_utc=None):
    """Advisory freshness indicator, not proof that reminders were delivered."""
    now = now_utc or datetime.now(timezone.utc)
    if last_run_at is None:
        return {
            "attention": True,
            "description": "No recorded reminder-run evidence is available. "
                           "Check the scheduled job before relying on follow-up alerts.",
        }
    if last_run_at.tzinfo is None:
        # Unknown timezone must not produce a falsely reassuring healthy result.
        return {
            "attention": True,
            "description": "Reminder run timezone is unknown; verify the scheduler.",
        }
    if has_error or last_ok is not True:
        return {
            "attention": True,
            "description": "The latest recorded reminder run did not report success. "
                           "Check the scheduler and delivery channel.",
        }
    if last_run_at > now + timedelta(minutes=5):
        return {
            "attention": True,
            "description": "The reminder run timestamp is unexpectedly in the future. "
                           "Check server clock and scheduler records.",
        }
    if now - last_run_at > timedelta(hours=48):
        return {
            "attention": True,
            "description": "The last recorded successful reminder run is older than "
                           "48 hours. This does not prove reminders failed, but the "
                           "scheduler needs an independent check.",
        }
    return {
        "attention": False,
        "description": "A recent successful reminder run is recorded. "
                       "Individual WhatsApp/email delivery is not proven by this check.",
    }


def has_new_reply(intake_at, inbound_at):
    """Return tri-state: True, False, or None when no saved intake exists."""
    if intake_at is None:
        return None
    return inbound_at is not None and inbound_at > intake_at


def paid_case_row(row, stage=None):
    lead_id, name, service, status, estimated, paid, intake_at, inbound_at = row
    comparison=has_new_reply(intake_at,inbound_at)
    return {
        "id":lead_id,
        "name":name or "Customer",
        "service":service,
        "enquiry_status":status,
        "stage":stage or "Not yet recorded",
        "paid_mwk":Decimal(str(paid or 0)),
        "needs_review":comparison is True,
        "waiting":comparison is False,
    }


def read_health(db_factory):
    """Read only. Errors must never be reported as a clean/healthy status."""
    with db_factory() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                (SELECT COUNT(*) FROM leads WHERE privacy_deleted_at IS NULL
                    AND merged_into_lead_id IS NULL),
                (SELECT COUNT(*) FROM lead_payments),
                (SELECT COALESCE(SUM(amount),0) FROM lead_payments WHERE currency='MWK'),
                (SELECT COUNT(*) FROM agro_marketplace_listings WHERE status='APPROVED'),
                (SELECT COUNT(*) FROM website_service_requests WHERE service_key='AGRICULTURE'),
                (SELECT COUNT(*) FROM ibrows_auto_receipt_deliveries
                    WHERE delivery_status IN ('FAILED','DOCUMENT_ERROR')
                    OR (delivery_status='SENDING' AND attempted_at< NOW()-INTERVAL '15 minutes')),
                (SELECT COUNT(*) FROM ibrows_auto_receipt_deliveries r
                    LEFT JOIN lead_payments p ON p.id=r.payment_id WHERE p.id IS NULL),
                (SELECT COUNT(*) FROM
                    (SELECT request_token FROM lead_payments
                     WHERE request_token IS NOT NULL AND BTRIM(request_token) <> ''
                     GROUP BY request_token HAVING COUNT(*) > 1) x),
                (SELECT COUNT(*) FROM processed_whatsapp_messages WHERE status IS DISTINCT FROM 'COMPLETED'),
                (SELECT COUNT(*) FROM whatsapp_delivery_outbox WHERE status IS DISTINCT FROM 'SENT'),
                (SELECT COUNT(*) FROM agro_marketplace_listings WHERE status='APPROVED'
                    AND (quantity<=0 OR COALESCE(price_mwk,0)<=0
                    OR NULLIF(BTRIM(seller_phone),'') IS NULL)),
                (SELECT COUNT(*) FROM agro_marketplace_listing_sources s
                    LEFT JOIN agro_marketplace_listings l ON l.id=s.listing_id
                    WHERE l.id IS NULL)
            """)
            metric=cur.fetchone()
            if metric is None or len(metric)!=12:
                raise ValueError("Incomplete operations metrics")
            labels=(
                "leads","payments","verified_mwk","agro_approved","agro_requests",
                "receipt_issues","orphaned_receipts","duplicate_payment_tokens",
                "webhook_unfinished","outbox_attention","agro_invalid","agro_orphaned_sources"
            )
            totals=dict(zip(labels,metric))

            cur.execute("""
                SELECT l.id,l.customer_name,l.service,l.status,
                       l.estimated_value,
                       (SELECT COALESCE(SUM(p.amount),0) FROM lead_payments p
                         WHERE p.lead_id=l.id AND p.currency='MWK') AS paid_mwk,
                       (SELECT MAX(c.created_at) FROM conversations c
                         WHERE c.customer_number=l.customer_number
                           AND c.role='assistant'
                           AND (POSITION('Your MK5,000 Scholarship Eligibility Check payment is confirmed' IN c.content)>0
                             OR POSITION('IBROWS Enterprise 🎓 | Scholarship Eligibility Check' IN c.content)>0)
                       ) AS latest_intake,
                       (SELECT MAX(c.created_at) FROM conversations c
                         WHERE c.customer_number=l.customer_number
                           AND c.role='user'
                       ) AS latest_inbound
                FROM leads l
                WHERE l.service='Scholarship Eligibility Check'
                  AND l.status <> 'CLOSED'
                  AND l.privacy_deleted_at IS NULL
                  AND l.merged_into_lead_id IS NULL
                  AND EXISTS (
                    SELECT 1 FROM lead_payments p WHERE p.lead_id=l.id AND p.currency='MWK'
                    GROUP BY p.lead_id
                    HAVING SUM(p.amount)>=COALESCE(l.estimated_value,5000)
                  )
                ORDER BY l.created_at DESC LIMIT 50
            """)
            candidate_rows=cur.fetchall()

            cur.execute("SELECT to_regclass('public.scholarship_eligibility_cases')")
            has_table=cur.fetchone()[0] is not None
            stages={}
            if has_table and candidate_rows:
                cur.execute("""
                    SELECT lead_id,stage FROM scholarship_eligibility_cases
                    WHERE lead_id=ANY(%s)
                """, ([row[0] for row in candidate_rows],))
                stages=dict(cur.fetchall())

            cur.execute("""
                SELECT
                  pg_total_relation_size('public.website_service_portfolio_assets'::regclass),
                  pg_total_relation_size('public.construction_portfolio_assets'::regclass)
            """)
            sizes=cur.fetchone()
            if not sizes:
                raise ValueError("Missing media size figures")

            # A monitoring record can be stale even while there are no due
            # reminders. A private warning is safer than claiming the job ran.
            cur.execute("""
                SELECT t.last_run_at,t.last_ok,
                       COALESCE(NULLIF(BTRIM(t.last_error),''),NULL) IS NOT NULL AS has_error,
                       (SELECT COUNT(*) FROM ai_takeover_state WHERE ai_paused=TRUE)
                FROM (SELECT 1) one
                LEFT JOIN LATERAL (
                    SELECT last_run_at,last_ok,last_error
                    FROM ibrows_task_health
                    WHERE task_key='FOLLOWUP_REMINDERS'
                    ORDER BY last_run_at DESC NULLS LAST
                    LIMIT 1
                ) t ON TRUE
            """)
            operational = cur.fetchone()
            if operational is None or len(operational)!=4:
                raise ValueError("Missing follow-up monitor evidence")
    cases=[paid_case_row(row,stages.get(row[0])) for row in candidate_rows]
    reminder_health=classify_reminder_health(
        operational[0],operational[1],operational[2]
    )
    return {
        "totals":totals,
        "paid_cases":cases,
        "pending_paid":sum(case["stage"]!="DELIVERED" for case in cases),
        "reminder_health":reminder_health,
        "paused_handoffs":operational[3],
        "media":{
            "website_mb":round(sizes[0]/1048576,1),
            "construction_mb":round(sizes[1]/1048576,1),
        }
    }


def install_backend_operations(flask_app):
    """Private route and navigation link, no data migration or background tasks."""
    if "admin_backend_health" in flask_app.view_functions:
        return True
    view=flask_app.view_functions.get("admin_leads")
    if view is None:
        return False
    ns=view.__globals__
    if not callable(ns.get("get_db")) or not callable(ns.get("admin_required")):
        return False

    def admin_backend_health():
        from flask import render_template_string,make_response
        try:
            result=read_health(ns["get_db"])
            from datetime import datetime
            from zoneinfo import ZoneInfo
            local=datetime.now(ZoneInfo("Africa/Blantyre")).strftime("%d %b %Y, %H:%M")
            html=render_template_string(PAGE,**result,checked_at=local)
            response=make_response(html,200)
        except Exception as exc:
            # Fail closed: cannot report "all healthy" if the DB is unavailable.
            print("IBROWS BACKEND HEALTH READ FAILED: "+type(exc).__name__,flush=True)
            response=make_response(
                "Backend health temporarily unavailable. "
                "Open the authenticated CRM or inspect Render logs.",503
            )
        response.headers["Cache-Control"]="private, no-store, max-age=0"
        response.headers["X-Robots-Tag"]="noindex, nofollow"
        return response

    flask_app.add_url_rule(
        "/admin/backend-health",
        endpoint="admin_backend_health",
        methods=["GET"],
        view_func=ns["admin_required"](admin_backend_health),
    )

    template=ns.get("DASHBOARD_TEMPLATE")
    anchor="<h2>Sales pipeline</h2>"
    if (isinstance(template,str)
            and "ibrows-backend-health-nav" not in template
            and template.count(anchor)==1):
        link=(
            '<!-- ibrows-backend-health-nav -->'
            '<p style="margin:8px 0 12px;font-size:13px">'
            '<a href="{{ url_for(\'admin_backend_health\') }}">'
            'Backend Operations · paid replies, receipts, WhatsApp & agriculture'
            '</a></p>'
        )
        ns["DASHBOARD_TEMPLATE"]=template.replace(anchor,anchor+"\n"+link,1)
    print("IBROWS BACKEND HEALTH: private read-only operations dashboard enabled",flush=True)
    return True
