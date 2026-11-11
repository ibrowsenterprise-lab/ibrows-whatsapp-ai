"""Admin-only, paid-service work tracking for scholarship eligibility checks.

The enquiry status and the ledger are separate from service-delivery progress.
Nothing is sent or marked delivered automatically. All transitions are
administrator-initiated, CSRF-protected, recorded and conditional on an
existing verified payment. No academic documents are stored here.
"""
from decimal import Decimal
from scholarship_eligibility_intake import (
    SERVICE, REQUIRED_MWK, is_verified_one_off, paid_eligibility_intake_message,
)

DEFAULT_STAGE = "PAID_AWAITING_INTAKE"
STAGES = {
    DEFAULT_STAGE: "Paid — intake not yet requested",
    "AWAITING_INFORMATION": "Intake sent — waiting for academic details",
    "REVIEWING": "Academic details received — assessing eligibility",
    "READY_FOR_DELIVERY": "Assessment reviewed — ready to deliver",
    "DELIVERED": "Eligibility assessment delivered",
}
# Only the exact next transition is permitted; this prevents accidentally
# marking a case delivered without prior review.
NEXT_STAGES = {
    DEFAULT_STAGE: "AWAITING_INFORMATION",
    "AWAITING_INFORMATION": "REVIEWING",
    "REVIEWING": "READY_FOR_DELIVERY",
    "READY_FOR_DELIVERY": "DELIVERED",
}
ACTION_LABELS = {
    "AWAITING_INFORMATION": "Mark intake message actually sent",
    "REVIEWING": "Confirm academic details received — start assessment",
    "READY_FOR_DELIVERY": "Confirm assessment reviewed and ready",
    "DELIVERED": "Confirm assessment delivered to the customer",
}
ACTION_NOTES = {
    "AWAITING_INFORMATION": "Staff confirmed one-off eligibility intake message was sent to customer.",
    "REVIEWING": "Staff confirmed relevant academic details received and began eligibility review.",
    "READY_FOR_DELIVERY": "Staff confirmed one-off eligibility report reviewed for delivery.",
    "DELIVERED": "Staff confirmed one-off eligibility report delivered to customer.",
}



def academic_reply_evidence(messages):
    """Describe topics present in saved user replies without inventing credentials.

    This is a routing hint only, not proof of qualifications, transcript receipt,
    graduation, or scholarship eligibility. Never send message content to logs.
    """
    import re
    combined = "\n".join(str(message or "") for message in messages)[-18000:].casefold()
    patterns = {
        "degree": r"\b(bachelor(?:'s|s)?|bsc|b\.?a\.?|undergraduate|degree)\b",
        "grade": r"\b(gpa|cgpa|classification|first class|second class|third class|honou?rs)\b",
        "experience": r"\b(experience|banking|manager|worked|working|years? in)\b",
        "location": r"\b(malawi|malawian|resident|nationality|citizenship)\b",
        "language": r"\b(english|ielts|toefl|duolingo|medium of instruction)\b",
        "destination": r"\b(finland|uk|united kingdom|europe|sweden|germany|norway|netherlands|country|countries)\b",
    }
    return tuple(label for label, pattern in patterns.items()
                 if re.search(pattern, combined))


def classify_customer_reply(last_intake, last_inbound, evidence=()):
    """Conservatively separate payment, intake, review and delivery.

    Intake metadata can flag work for a reviewer; it must never mark an
    eligibility assessment finished, produce an academic verdict, or charge.
    """
    if last_intake is None:
        return (
            "No saved academic intake request found",
            "Check the secure IBROWS Inbox before asking the customer for details. "
            "Only a real saved intake message counts as sent.",
            False, False,
        )
    if last_inbound is not None and last_inbound > last_intake:
        ready = all(item in evidence for item in ("degree", "grade", "experience")) and len(evidence) >= 4
        if ready:
            return (
                "Academic answers already received — assessment review required",
                "Saved replies include degree, grading and experience topics. "
                "Review the actual client answers in the Inbox, verify missing "
                "evidence where needed, and perform the paid assessment. "
                "Do not resend the full intake or mark a report delivered.",
                True, True,
            )
        return (
            "Customer replied — review their existing answers",
            "Open the Inbox and check what was provided. Ask only for missing "
            "academic details; do not send the entire intake form again.",
            True, False,
        )
    return (
        "Awaiting response to recorded academic intake",
        "The request was saved to the conversation. Handset delivery is not "
        "independently proved by this timestamp alone.",
        False, False,
    )


def get_customer_reply_status(db_factory, customer_number):
    """Read saved intake and replies for this exact customer; no writes or sends."""
    try:
        with db_factory() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                      (
                        SELECT MAX(created_at)
                        FROM conversations
                        WHERE customer_number=%s
                          AND role='assistant'
                          AND (
                            POSITION(%s IN content)>0 OR
                            POSITION(%s IN content)>0
                          )
                      ) AS intake_at,
                      (
                        SELECT MAX(created_at)
                        FROM conversations
                        WHERE customer_number=%s
                          AND role='user'
                      ) AS last_customer_at
                """, (
                    customer_number,
                    "Your MK5,000 Scholarship Eligibility Check payment is confirmed",
                    "IBROWS Enterprise 🎓 | Scholarship Eligibility Check",
                    customer_number,
                ))
                row = cur.fetchone()
                if not row:
                    raise ValueError("No conversation activity returned")
                evidence = ()
                if row[0] is not None and row[1] is not None and row[1] > row[0]:
                    cur.execute("""
                        SELECT content FROM conversations
                        WHERE customer_number=%s AND role='user'
                          AND created_at>%s
                        ORDER BY created_at DESC LIMIT 40
                    """, (customer_number, row[0]))
                    evidence = academic_reply_evidence([r[0] for r in cur.fetchall()])
        return classify_customer_reply(row[0], row[1], evidence)
    except Exception as exc:
        print("IBROWS ELIGIBILITY REPLY STATUS UNAVAILABLE: "
              + type(exc).__name__, flush=True)
        return (
            "Saved academic reply check temporarily unavailable",
            "Open the secure IBROWS Inbox to review answers before requesting more.",
            False, False,
        )


def can_move_stage(current, target, payment_state, intake_ready=False):
    return bool(
        is_verified_one_off(payment_state)
        and (
            (current in NEXT_STAGES and NEXT_STAGES[current] == target)
            or (intake_ready and current == DEFAULT_STAGE and target == "REVIEWING")
        )
    )


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>IBROWS Eligibility Work Queue</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f3f5f9;color:#101828;font:15px/1.5 system-ui,Arial}
header{background:#101828;color:white;padding:18px 16px}header a{color:white}
main{max-width:700px;margin:auto;padding:14px}.card{background:white;border-radius:14px;padding:17px;margin:12px 0;box-shadow:0 1px 5px #0001}
h1{font-size:23px;margin:5px 0}h2{font-size:18px;margin:2px 0 10px}
.small{color:#667085;font-size:13px}.chip{display:inline-block;background:#ecfdf3;color:#067647;border-radius:30px;padding:5px 11px;font-weight:700;font-size:13px}
button,a.action{display:block;text-align:center;width:100%;padding:13px 12px;min-height:47px;border-radius:9px;background:#101828;color:white;border:0;text-decoration:none;font-weight:750;font-size:14px;cursor:pointer;margin:9px 0}
button[disabled]{background:#b0b6c4;cursor:not-allowed}a.outline{border:1px solid #ccd2da;background:white;color:#101828}
textarea{display:block;width:100%;height:290px;resize:vertical;padding:12px;border:1px solid #ccd2da;border-radius:9px;font:13px/1.55 system-ui;white-space:pre-wrap}
.warning{background:#fff7eb;border-radius:10px;padding:12px;font-size:13px}.reply{border-left:4px solid #1d4ed8;background:#eff6ff;padding:12px;border-radius:8px}.reply.new{border-left-color:#b45309;background:#fffbeb}
label{display:flex;gap:10px;align-items:flex-start;margin:12px 0}input[type=checkbox]{width:21px;height:21px;flex-shrink:0}
</style></head><body>
<header><a href="{{ url_for('admin_leads') }}">← Customers &amp; Enquiries</a></header>
<main><section class="card">
<p class="small">IBROWS Enterprise · Lead #{{ lead_id }}</p>
<h1>Scholarship Eligibility Check</h1>
<p><strong>{{ customer_name or 'WhatsApp customer' }}</strong></p>
{% if paid %}<span class="chip">Verified paid · MWK 5,000</span>
{% else %}<p class="warning">Payment not verified for this exact one-off package. Do not start the paid assessment or charge again without reviewing the ledger.</p>{% endif %}
<p class="small">Enquiry: {{ enquiry_status }} · Assessment: {{ stage_label }}</p>
</section>
<section class="card">
<h2>Customer reply tracker</h2>
<div class="reply{% if new_reply %} new{% endif %}">
<strong>{{ reply_title }}</strong>
<p class="small">{{ reply_description }}</p>
</div>
<p class="small">This checks only recorded conversation timestamps, not whether a WhatsApp message was delivered or whether academic documents are complete. Refresh this page to check again.</p>
<a class="action outline" href="{{ url_for('admin_inbox_chat',customer_number=customer_number) }}">Read latest customer messages</a>
</section>
<section class="card">
<h2>Step 1 · Review existing academic answers</h2>
{% if intake_ready %}
<div class="reply new"><strong>Intake answers are already saved.</strong>
<p>Read the client's messages in the secure Inbox and assess what they provided. Do not send a second intake questionnaire or request another payment. Transcript and evidence still require verification.</p></div>
{% elif new_reply %}
<div class="reply"><strong>The client has replied.</strong>
<p>Review those messages first. Request only any details still missing. Do not repeat questions already answered.</p></div>
{% else %}
<p class="small">If the client has not provided academic details, copy this intake message to the Inbox and send it. Copying it does not send anything automatically.</p>
<textarea id="intake" readonly>{{ intake_message }}</textarea>
<button type="button" id="copy-intake" onclick="copyIntake()">Copy intake message</button>
<p id="copy-status" class="small" aria-live="polite">Copying does not send anything automatically.</p>
{% endif %}
<a class="action outline" href="{{ url_for('admin_inbox_chat',customer_number=customer_number) }}">Open IBROWS WhatsApp Inbox — read client answers</a>
</section>
<section class="card">
<h2>Step 2 · Track actual work</h2>
<p><strong>{{ stage_label }}</strong></p>
{% if stage == 'DELIVERED' %}
<p class="small">The eligibility assessment is marked delivered. This does not imply scholarship admission or a submitted university application.</p>
{% elif paid %}
<form method="post" action="{{ url_for('admin_eligibility_case',lead_id=lead_id) }}">
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<input type="hidden" name="next_stage" value="{{ next_stage }}">
<label><input type="checkbox" name="confirm_action" value="1" required>
<span>I confirm this step actually happened. The system will record my confirmation, not perform the step for me.</span></label>
<button type="submit">{{ action_label }}</button>
</form>
{% else %}
<p class="small">Workflow cannot advance until the corresponding payment is verified in the authoritative ledger.</p>
{% endif %}
<p class="warning">This is a **one-off screening**, not the separate MK15,000 shortlist,
MK40,000 application-support or monthly scholarship package. Never promise a scholarship award.</p>
</section></main>
<script>
function copyIntake(){
 const el=document.getElementById('intake');if(!el)return;el.focus();el.select();
 const value=el.value;
 if(navigator.clipboard && navigator.clipboard.writeText){
   navigator.clipboard.writeText(value).then(()=>{
     document.getElementById('copy-status').textContent='Copied. Open IBROWS Inbox and paste the message.';
   }).catch(()=>{document.getElementById('copy-status').textContent='Select and copy the highlighted text manually.';});
 }else{
   document.getElementById('copy-status').textContent='Text selected. Choose Copy from your phone menu.';
 }
}
</script></body></html>"""


def install_eligibility_work_queue(flask_app):
    """Register a CSRF-protected administrator view; no startup DB mutation."""
    if "admin_eligibility_case" in flask_app.view_functions:
        return True
    dashboard_view = flask_app.view_functions.get("admin_leads")
    if dashboard_view is None:
        return False
    ns = dashboard_view.__globals__
    required = ("get_db", "admin_required", "validate_csrf",
                "get_verified_service_payment_state", "get_csrf_token")
    if not all(callable(ns.get(key)) for key in required):
        print("IBROWS ELIGIBILITY WORK QUEUE: missing existing admin primitives",flush=True)
        return False

    def admin_eligibility_case(lead_id):
        from flask import abort, request, redirect, url_for, render_template_string
        if request.method == "POST":
            ns["validate_csrf"]()
        # All business actions require the lead to exist and match the exact
        # one-off service; don't allow other paid packages to be mistaken here.
        with ns["get_db"]() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT customer_number, customer_name,service,status,
                           privacy_deleted_at,merged_into_lead_id
                    FROM leads WHERE id=%s""", (lead_id,))
                lead = cur.fetchone()
        if (not lead or lead[2] != SERVICE or lead[4] is not None
                or lead[5] is not None):
            abort(404)
        number, name, service, status, _deleted, _merged = lead
        state = ns["get_verified_service_payment_state"](number, SERVICE)
        paid = is_verified_one_off(state) and state.get("lead_id") == lead_id
        with ns["get_db"]() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public.scholarship_eligibility_cases')")
                exists = cur.fetchone()[0] is not None
                if exists:
                    cur.execute(
                        "SELECT stage FROM scholarship_eligibility_cases WHERE lead_id=%s",
                        (lead_id,),
                    )
                    result = cur.fetchone()
                    stage = result[0] if result else DEFAULT_STAGE
                else:
                    stage = DEFAULT_STAGE

        reply_title, reply_description, new_reply, intake_ready = get_customer_reply_status(
            ns["get_db"], number
        )
        if request.method == "POST":
            if not paid or status == "CLOSED":
                abort(409)
            target = request.form.get("next_stage")
            if (request.form.get("confirm_action") != "1"
                    or not can_move_stage(stage,target,state,intake_ready=intake_ready)):
                abort(409)
            with ns["get_db"]() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_xact_lock(%s)", (lead_id+937000,))
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS scholarship_eligibility_cases (
                            lead_id BIGINT PRIMARY KEY REFERENCES leads(id) ON DELETE CASCADE,
                            stage TEXT NOT NULL DEFAULT 'PAID_AWAITING_INTAKE'
                              CHECK(stage IN ('PAID_AWAITING_INTAKE',
                                             'AWAITING_INFORMATION',
                                             'REVIEWING',
                                             'READY_FOR_DELIVERY',
                                             'DELIVERED')),
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                    """)
                    cur.execute("""
                        INSERT INTO scholarship_eligibility_cases(lead_id)
                        VALUES(%s) ON CONFLICT(lead_id) DO NOTHING
                    """, (lead_id,))
                    cur.execute(
                        "SELECT stage FROM scholarship_eligibility_cases WHERE lead_id=%s FOR UPDATE",
                        (lead_id,),
                    )
                    latest_stage = cur.fetchone()[0]
                    if not can_move_stage(latest_stage,target,state,intake_ready=intake_ready):
                        abort(409)
                    cur.execute("""
                        UPDATE scholarship_eligibility_cases
                        SET stage=%s,updated_at=NOW()
                        WHERE lead_id=%s AND stage=%s
                    """, (target,lead_id,latest_stage))
                    if cur.rowcount != 1:
                        abort(409)
                    cur.execute("""
                        INSERT INTO lead_activity (lead_id,activity_type,description)
                        VALUES(%s,'LEAD_UPDATED',%s)
                    """, (lead_id, ACTION_NOTES[target]))
                conn.commit()
            return redirect(url_for("admin_eligibility_case",lead_id=lead_id),code=303)

        next_stage=("REVIEWING" if stage == DEFAULT_STAGE and intake_ready
                    else NEXT_STAGES.get(stage))
        stage_label=("Intake answers recorded — eligibility assessment awaiting review"
                     if stage == DEFAULT_STAGE and intake_ready
                     else STAGES.get(stage,"Unknown"))
        action_label=("Confirm existing answers reviewed — start assessment"
                      if stage == DEFAULT_STAGE and intake_ready
                      else ACTION_LABELS.get(next_stage))
        resp = render_template_string(
            PAGE, lead_id=lead_id,customer_name=name,customer_number=number,
            enquiry_status=status,paid=paid,stage=stage,
            stage_label=stage_label,next_stage=next_stage,
            reply_title=reply_title,reply_description=reply_description,
            new_reply=new_reply,intake_ready=intake_ready,
            action_label=action_label,
            csrf_token=ns["get_csrf_token"](),
            intake_message=paid_eligibility_intake_message(),
        )
        from flask import make_response
        r=make_response(resp)
        r.headers["Cache-Control"]="private, no-store, no-cache, max-age=0"
        r.headers["X-Robots-Tag"]="noindex, nofollow"
        return r

    flask_app.add_url_rule(
        "/admin/eligibility/<int:lead_id>",
        endpoint="admin_eligibility_case",
        view_func=ns["admin_required"](admin_eligibility_case),
        methods=["GET","POST"],
    )
    print("IBROWS ELIGIBILITY WORK QUEUE: admin-only payment-gated workflow enabled",flush=True)
    return True
