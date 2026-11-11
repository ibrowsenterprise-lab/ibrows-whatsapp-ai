"""Automatic, ledger-gated PDF receipts for newly confirmed IBROWS CRM payments.

- Only the existing authenticated admin payment-confirmation workflow is a trigger.
- Each new immutable lead_payments.id gets exactly one automatic delivery claim.
- The existing permanent IBROWS receipt number and PDF builder are reused.
- A PDF is sent only inside the recipient's own 24-hour WhatsApp window.
- Outside the window the receipt waits for the customer's next inbound message.
- A failed/uncertain send is not retried automatically: human review prevents
  duplicate financial documents on ambiguous network acknowledgements.
- Payments and old receipts are never modified or backfilled.
"""
from functools import wraps
import re

ALLOWED_SEND_STATES = ("PENDING", "WAITING_WINDOW")
FINAL_SEND_STATES = ("ACCEPTED", "FAILED", "DOCUMENT_ERROR", "MANUALLY_SENT", "VOID")
CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS ibrows_auto_receipt_deliveries (
    payment_id BIGINT PRIMARY KEY,
    lead_id BIGINT NOT NULL,
    receipt_number TEXT,
    delivery_status TEXT NOT NULL DEFAULT 'PENDING'
      CHECK(delivery_status IN ('PENDING','WAITING_WINDOW','SENDING',
          'ACCEPTED','FAILED','DOCUMENT_ERROR','MANUALLY_SENT','VOID')),
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    attempted_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


def _payment_by_token(db_factory, lead_id, token):
    """An exact, already-confirmed ledger row, never screenshot interpretation."""
    with db_factory() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT p.id FROM lead_payments p
                   JOIN leads l ON l.id=p.lead_id
                   WHERE p.lead_id=%s AND p.request_token=%s
                     AND l.merged_into_lead_id IS NULL
                     AND l.privacy_deleted_at IS NULL LIMIT 1""",
                (lead_id, token),
            )
            row=cur.fetchone()
    return row[0] if row else None


def _queue_new_payment(db_factory, lead_id, payment_id):
    with db_factory() as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE)
            cur.execute(
                """INSERT INTO ibrows_auto_receipt_deliveries(payment_id,lead_id)
                   SELECT p.id,p.lead_id FROM lead_payments p
                   JOIN leads l ON l.id=p.lead_id
                   WHERE p.id=%s AND p.lead_id=%s
                     AND l.merged_into_lead_id IS NULL
                     AND l.privacy_deleted_at IS NULL
                   ON CONFLICT(payment_id) DO NOTHING
                   RETURNING payment_id""",
                (payment_id,lead_id),
            )
            was_queued=cur.fetchone() is not None
        conn.commit()
    return was_queued


def _row_by_payment(db_factory, payment_id):
    with db_factory() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT r.payment_id,r.lead_id,r.delivery_status,
                          l.customer_number
                   FROM ibrows_auto_receipt_deliveries r
                   JOIN lead_payments p ON p.id=r.payment_id
                   JOIN leads l ON l.id=p.lead_id AND l.id=r.lead_id
                   WHERE r.payment_id=%s AND l.merged_into_lead_id IS NULL
                     AND l.privacy_deleted_at IS NULL""",
                (payment_id,),
            )
            return cur.fetchone()


def _change_state(db_factory, payment_id, old, new, reference=None):
    if new not in FINAL_SEND_STATES+("WAITING_WINDOW","SENDING"):
        raise ValueError("Unknown receipt state")
    with db_factory() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE ibrows_auto_receipt_deliveries
                   SET delivery_status=%s,
                       receipt_number=COALESCE(%s,receipt_number),
                       updated_at=NOW(),
                       attempted_at=CASE WHEN %s='SENDING' THEN NOW()
                                         ELSE attempted_at END,
                       attempts=attempts+CASE WHEN %s='SENDING' THEN 1 ELSE 0 END
                   WHERE payment_id=%s AND delivery_status=%s
                   RETURNING payment_id""",
                (new,reference,new,new,payment_id,old),
            )
            changed=cur.fetchone() is not None
        conn.commit()
    return changed


def _record_reference(db_factory, payment_id, ref):
    with db_factory() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE ibrows_auto_receipt_deliveries
                   SET receipt_number=%s,updated_at=NOW()
                   WHERE payment_id=%s AND delivery_status IN ('PENDING','WAITING_WINDOW')""",
                (ref,payment_id),
            )
        conn.commit()


def _already_sent_manually(db_factory, payment_id):
    with db_factory() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT EXISTS(
                    SELECT 1 FROM business_documents d
                    WHERE d.doc_type='receipt' AND d.payment_id=%s
                      AND (d.last_sent_at IS NOT NULL OR d.send_count>0)
                )""",
                (payment_id,),
            )
            return bool(cur.fetchone()[0])


def _document_for_payment(ns, lead_id, payment_id):
    record=ns["get_or_create_business_document_record"](
        "receipt", lead_id, payment_id=payment_id
    )
    if record.get("document_status")=="VOID":
        raise ValueError("Voided receipt document cannot be delivered")
    return record


def _attempt_delivery(ns, payment_id):
    """At-most-one automatic API send; SENDING is never auto-retried."""
    db=ns["get_db"]
    row=_row_by_payment(db,payment_id)
    if not row or row[2] not in ALLOWED_SEND_STATES:
        return "NO_PENDING_RECEIPT"

    _,lead_id,state,customer_number=row
    # Allocate the permanent receipt reference even if the messaging window is
    # closed, so staff can download it without waiting on Meta.
    try:
        document_record=_document_for_payment(ns,lead_id,payment_id)
        ref=document_record["document_number"]
        _record_reference(db,payment_id,ref)
        if _already_sent_manually(db,payment_id):
            _change_state(db,payment_id,state,"MANUALLY_SENT",ref)
            return "MANUALLY_SENT"
    except Exception as exc:
        print("IBROWS AUTO RECEIPT DOCUMENT ERROR: "
              +type(exc).__name__,flush=True)
        _change_state(db,payment_id,state,"DOCUMENT_ERROR")
        return "DOCUMENT_ERROR"

    try:
        window_open,_last=ns["is_whatsapp_service_window_open"](customer_number)
    except Exception as exc:
        print("IBROWS AUTO RECEIPT WINDOW CHECK ERROR: "
              +type(exc).__name__,flush=True)
        # A query failure cannot authorize a WhatsApp business-initiated send.
        return "WINDOW_UNKNOWN"

    if not window_open:
        _change_state(db,payment_id,state,"WAITING_WINDOW",ref)
        return "WAITING_WINDOW"

    if not _change_state(db,payment_id,state,"SENDING",ref):
        return "ALREADY_CLAIMED"

    try:
        context=ns["get_business_document_context"](
            lead_id,payment_id=payment_id
        )
        if not context or context.get("customer_number")!=customer_number:
            raise ValueError("Receipt/customer mismatch")
        doc=ns["_business_pdf_build"](
            "receipt",context,payment_id=payment_id,
            document_record=document_record,
        )
        accepted=bool(ns["send_whatsapp_document"](
            customer_number,
            doc["bytes"],doc["filename"],doc["mime_type"],
            caption="IBROWS Enterprise payment receipt — "+ref,
        ))
    except Exception as exc:
        print("IBROWS AUTO RECEIPT SEND ERROR: "
              +type(exc).__name__,flush=True)
        accepted=False

    outcome="ACCEPTED" if accepted else "FAILED"
    try:
        _change_state(db,payment_id,"SENDING",outcome,ref)
    except Exception as exc:
        # Do not re-send: the API may already have accepted this document.
        print("IBROWS AUTO RECEIPT AUDIT UPDATE UNCERTAIN: "
              +type(exc).__name__,flush=True)
        return "UNCERTAIN_NEEDS_REVIEW"

    if accepted:
        try:
            ns["_record_document_sent_activity"](lead_id,"receipt",ref)
        except Exception as exc:
            print("IBROWS AUTO RECEIPT DOCUMENT HISTORY ERROR: "
                  +type(exc).__name__,flush=True)
    print("IBROWS AUTO RECEIPT payment_id="+str(payment_id)
          +" status="+outcome,flush=True)
    return outcome


def _pending_for_customer(db_factory, customer_number, max_items=3):
    with db_factory() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT r.payment_id
                   FROM ibrows_auto_receipt_deliveries r
                   JOIN lead_payments p ON p.id=r.payment_id
                   JOIN leads l ON l.id=p.lead_id AND l.id=r.lead_id
                   WHERE l.customer_number=%s
                     AND r.delivery_status='WAITING_WINDOW'
                     AND l.merged_into_lead_id IS NULL
                     AND l.privacy_deleted_at IS NULL
                   ORDER BY r.created_at ASC LIMIT %s""",
                (customer_number,max_items),
            )
            return [row[0] for row in cur.fetchall()]


def _inbound_numbers(payload):
    """Only message webhooks, never status/delivery events or contact objects."""
    numbers=[]
    for entry in (payload.get("entry") or []):
        if not isinstance(entry,dict):
            continue
        for change in (entry.get("changes") or []):
            value=change.get("value") if isinstance(change,dict) else None
            if not isinstance(value,dict):
                continue
            for msg in (value.get("messages") or []):
                if not isinstance(msg,dict) or msg.get("type") not in (
                    "text","image","document","audio","video","interactive"
                ):
                    continue
                number=str(msg.get("from") or "")
                if re.fullmatch(r"[0-9]{8,20}",number) and number not in numbers:
                    numbers.append(number)
    return numbers[:5]


def _success_response(result):
    from flask import Response
    if isinstance(result,Response):
        return result.status_code<300
    if isinstance(result,tuple) and len(result)>=2:
        return isinstance(result[1],int) and 200<=result[1]<300
    return True


def install_auto_receipts(flask_app):
    """Wire only existing verified payment path; no database write at startup."""
    lead_view=flask_app.view_functions.get("admin_leads")
    if lead_view is None:
        return False
    ns=lead_view.__globals__
    needed=("get_db","update_lead_management",
            "get_business_document_context","get_or_create_business_document_record",
            "_business_pdf_build","send_whatsapp_document",
            "is_whatsapp_service_window_open","_record_document_sent_activity")
    if not all(callable(ns.get(k)) for k in needed):
        print("IBROWS AUTO RECEIPT: existing required services missing",flush=True)
        return False

    original=ns["update_lead_management"]
    if getattr(original,"_ibrows_auto_receipt",False):
        return True

    @wraps(original)
    def confirmed_payment_with_receipt(*args,**kwargs):
        # Existing admin-CSRF-protected route requires its explicit checkbox.
        # A screenshot, incoming WhatsApp text or empty form cannot trigger us.
        eligible=bool(kwargs.get("payment_confirmed")) and (
            kwargs.get("payment_amount") not in (None,"")
        ) and bool(str(kwargs.get("payment_request_token") or "").strip())
        lead_id=kwargs.get("lead_id",args[0] if args else None)
        token=str(kwargs.get("payment_request_token") or "").strip()
        existed=None
        if eligible and lead_id is not None:
            try:
                existed=_payment_by_token(ns["get_db"],lead_id,token)
            except Exception as exc:
                # Fail closed: a ledger lookup outage cannot authorize an
                # automatic receipt; the existing payment route still runs.
                print("IBROWS AUTO RECEIPT PRECHECK ERROR: "
                      +type(exc).__name__,flush=True)
                existed="UNAVAILABLE"
        result=original(*args,**kwargs)
        if not eligible or lead_id is None or existed is not None:
            return result
        try:
            payment_id=_payment_by_token(ns["get_db"],lead_id,token)
            if payment_id and _queue_new_payment(ns["get_db"],lead_id,payment_id):
                _attempt_delivery(ns,payment_id)
        except Exception as exc:
            print("IBROWS AUTO RECEIPT QUEUE ERROR: "
                  +type(exc).__name__,flush=True)
        # Crucial: a WhatsApp failure never rolls back a real confirmed payment.
        return result

    confirmed_payment_with_receipt._ibrows_auto_receipt=True
    ns["update_lead_management"]=confirmed_payment_with_receipt

    webhook=flask_app.view_functions.get("receive_webhook")
    if callable(webhook) and not getattr(webhook,"_ibrows_receipt_inbound",False):
        @wraps(webhook)
        def whatsapp_inbound_receipt_flush(*args,**kwargs):
            from flask import request
            original_result=webhook(*args,**kwargs)
            if request.method!="POST" or not _success_response(original_result):
                return original_result
            data=request.get_json(silent=True) or {}
            if not isinstance(data,dict):
                return original_result
            for number in _inbound_numbers(data):
                try:
                    for payment_id in _pending_for_customer(ns["get_db"],number):
                        _attempt_delivery(ns,payment_id)
                except Exception as exc:
                    print("IBROWS AUTO RECEIPT INBOUND FLUSH ERROR: "
                          +type(exc).__name__,flush=True)
            return original_result
        whatsapp_inbound_receipt_flush._ibrows_receipt_inbound=True
        flask_app.view_functions["receive_webhook"]=whatsapp_inbound_receipt_flush

    # A read-only admin view of receipt delivery status; no customer secrets
    # in URL and no public registration.
    if "admin_auto_receipts" not in flask_app.view_functions:
        from flask import render_template_string
        def admin_auto_receipts():
            try:
                with ns["get_db"]() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT to_regclass('public.ibrows_auto_receipt_deliveries')")
                        if not cur.fetchone()[0]:
                            rows=[]
                        else:
                            cur.execute("""
                              SELECT r.payment_id,r.lead_id,l.customer_name,
                                     l.service,p.amount,p.currency,
                                     r.receipt_number,r.delivery_status,
                                     r.updated_at
                              FROM ibrows_auto_receipt_deliveries r
                              JOIN lead_payments p ON p.id=r.payment_id
                              JOIN leads l ON l.id=p.lead_id
                              ORDER BY r.created_at DESC LIMIT 100
                            """)
                            rows=cur.fetchall()
            except Exception as exc:
                print("IBROWS AUTO RECEIPT ADMIN VIEW ERROR: "
                      +type(exc).__name__,flush=True)
                rows=[]
            html=render_template_string(ADMIN_TEMPLATE,rows=rows)
            from flask import make_response
            out=make_response(html)
            out.headers["Cache-Control"]="private, no-store"
            out.headers["X-Robots-Tag"]="noindex, nofollow"
            return out
        flask_app.add_url_rule(
            "/admin/receipts",endpoint="admin_auto_receipts",
            view_func=ns["admin_required"](admin_auto_receipts),
            methods=["GET"],
        )
    # Surface the audit view on the existing authenticated CRM dashboard.
    # No new public information or financial state is created.
    original_dashboard=ns.get("DASHBOARD_TEMPLATE")
    dashboard_anchor="<h2>Sales pipeline</h2>"
    display_link=(
        '<!-- ibrows-auto-receipt-delivery-link -->'
        '<p style="margin:8px 0 14px;font-size:13px">'
        '<a href="{{ url_for(\'admin_auto_receipts\') }}">'
        'View automatic receipt deliveries</a></p>'
    )
    if (isinstance(original_dashboard,str)
            and "ibrows-auto-receipt-delivery-link" not in original_dashboard
            and original_dashboard.count(dashboard_anchor)==1):
        ns["DASHBOARD_TEMPLATE"]=original_dashboard.replace(
            dashboard_anchor,dashboard_anchor+"\n"+display_link,1
        )
    print("IBROWS AUTO RECEIPT: verified-only PDF receipt delivery enabled",flush=True)
    return True


ADMIN_TEMPLATE="""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>IBROWS Automatic Receipts</title>
<style>body{font:15px/1.5 system-ui;background:#f4f6fa;color:#182230;margin:0}
main{max-width:800px;margin:auto;padding:16px}h1{font-size:24px}
article{background:#fff;border-radius:12px;padding:14px;margin:12px 0;box-shadow:0 1px 4px #0001}
small{color:#667085}a{color:#155eef}code{font-size:12px}
strong{display:block;margin:8px 0}.status{font-weight:750}
</style></head><body><main>
<p><a href="{{ url_for('admin_leads') }}">← IBROWS CRM</a></p>
<h1>Automated receipts</h1>
<p>Only newly confirmed ledger payments appear here. Each receipt has a unique permanent number. A WhatsApp API acceptance is not proof of handset delivery.</p>
{% for r in rows %}
<article><strong>{{ r[2] or 'Customer' }} — {{ r[3] }}</strong>
<div>Payment: {{ r[5] }} {{ "{:,.2f}".format(r[4]) }}</div>
<div>Receipt: {{ r[6] or 'Not generated yet' }}</div>
<div class="status">Delivery: {{ r[7]|replace('_',' ')|title }}</div>
<small>Payment #{{ r[0] }} · Updated {{ r[8] }}</small>
<p><a href="{{ url_for('admin_business_document_download', lead_id=r[1], doc_type='receipt', payment_id=r[0]) }}">Download receipt PDF</a>
· <a href="{{ url_for('admin_leads', q='') }}">Open CRM to send manually</a></p>
</article>
{% else %}
<article>No new automated receipt records yet. Earlier payments can still have their receipts generated and sent manually from the CRM.</article>
{% endfor %}
</main></body></html>"""
