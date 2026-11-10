"""Admin-only CRM usability and payment-safety improvements.

This module changes the existing Jinja template, not the database or the
authoritative ledger. Payment can only be recorded through the existing
authenticated, CSRF-protected, idempotent admin workflow after verification.
"""
import re
from decimal import Decimal

MARKER = "<!-- ibrows-crm-quality:20261110 -->"


def _replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError("CRM template layout changed; patch not applied")
    return source.replace(old, new, 1)


def improve_crm_template(source):
    """Make customer history actionable without changing a service entitlement."""
    if MARKER in source:
        return source

    source = _replace_once(
        source,
        '<div class="hero">\n<h1>{{ customer_name }}</h1>',
        MARKER + '\n<div class="hero">\n<h1>{{ customer_name }}</h1>'
    )
    source = _replace_once(source, "<span>Current leads</span>", "<span>Current enquiries</span>")
    source = _replace_once(source, "<span>Open leads</span>", "<span>Open enquiries</span>")
    source = _replace_once(source, "<span>Services used</span>", "<span>Service types requested</span>")

    source = _replace_once(
        source,
        '<div class="metrics">\n',
        '<p class="crm-intro">An enquiry is not necessarily a completed or paid service. '
        'Payments below come only from IBROWS verified records.</p>\n'
        '<div class="metrics">\n'
    )

    old_services_start = '<div class="card services">\n<h2>Service history</h2>'
    old_services_end = '\n{% if payments %}'
    if source.count(old_services_start) != 1:
        raise ValueError("Customer service history section not found")
    start = source.index(old_services_start)
    end = source.index(old_services_end, start)
    updated_services = """<section class="card services">
<h2>Customer enquiries <span class="crm-count">({{ leads|length }})</span></h2>
<p class="crm-hint">Open a request to read the full details. Payment screenshots and transaction claims must be independently checked before the ledger is updated.</p>
{% for lead in leads %}
<article class="crm-enquiry" id="crm-lead-{{ lead.id }}">
<div class="lead-head">
  <div class="service">{{ lead.service }}</div>
  <div class="badges"><span class="badge">{{ lead.status }}</span><span class="badge">{{ lead.priority }}</span></div>
</div>
{% if lead.estimated_value_label or lead.paid_label or lead.service == 'Scholarship Search' %}
<div class="crm-payment" aria-label="Payment record">
  <span>Verified ledger:</span>
  <strong>{% if lead.payment_status == 'NOT_PAID' %}No verified payment recorded{% else %}{{ lead.payment_status_label }}{% endif %}</strong>
  {% if lead.paid_label %}<span>Recorded: {{ lead.paid_label }}</span>{% endif %}
  {% if lead.estimated_value_label %}<span>Agreed estimate: {{ lead.estimated_value_label }}</span>{% endif %}
  {% if lead.balance is not none and lead.balance > 0 and lead.estimated_value_label %}
    <span>Balance: {{ lead.balance_label }}</span>
  {% endif %}
</div>
{% endif %}
{% if lead.service == 'Scholarship Search' %}
<div class="crm-scope"><strong>Confirm the selected scholarship package first.</strong>
The MK5,000 Eligibility Check is one-off screening. It is not the MK60,000/month Scholarship Assist plan.
Do not record payment against the wrong service or treat a payment screenshot as a verified transfer.</div>
{% if lead.payment_status == 'NOT_PAID' and not lead.paid_label and not lead.estimated_value_label %}
<details class="crm-actions-panel">
<summary>Set MK5,000 one-off Eligibility Check package</summary>
<p class="crm-hint">Only do this after confirming directly with the customer that they selected the one-off screening package. This does NOT record payment.</p>
<form method="POST" action="{{ url_for('crm_convert_scholarship_eligibility', lead_id=lead.id) }}">
<input type="hidden" name="csrf_token" value="{{ csrf_token }}">
<input type="hidden" name="return_to" value="{{ crm_return }}">
<input type="hidden" name="confirm_scope" value="ELIGIBILITY">
<label><input type="checkbox" name="acknowledge_price" value="1" required> Customer agreed to the one-off MK5,000 eligibility check, not a monthly scholarship subscription.</label>
<button type="submit">Set one-off package — payment remains unverified</button>
</form>
</details>
{% endif %}
{% elif lead.service == 'Scholarship Eligibility Check' %}
<div class="crm-scope"><strong>One-off screening package · MK5,000.</strong>
The customer's profile can be screened after a real payment is independently verified and recorded.
This does not authorize a monthly scholarship search or ongoing applications.</div>
{% endif %}
<p class="crm-preview">{{ (lead.summary or 'No summary available.')|truncate(165, True) }}</p>
<details class="crm-details">
  <summary>Full request and history</summary>
  <div class="summary">{{ lead.summary or 'No summary available.' }}</div>
  {% if lead.quote_status != 'NOT_STARTED' %}
  <div class="commercial">Quote: {{ lead.quote_status_label }}{% if lead.quote_reference %} · {{ lead.quote_reference }}{% endif %}</div>
  {% endif %}
  <div class="meta">Created {{ lead.created_label }} · Updated {{ lead.updated_label }}</div>
</details>
<div class="crm-actions">
  <a href="{{ url_for('admin_inbox_chat', customer_number=customer_number) }}">Reply in IBROWS inbox</a>
  <a href="{{ url_for('admin_leads', q=customer_number) }}">Review pricing &amp; record verified payment</a>
</div>
<details class="crm-actions-panel">
  <summary>Update enquiry or add note</summary>
  <p class="crm-hint">A status update does not confirm payment or indicate the service was delivered.</p>
  {% if lead.status == 'NEW' %}
  <form method="POST" action="{{ url_for('admin_lead_status', lead_id=lead.id) }}">
    <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
    <input type="hidden" name="return_to" value="{{ crm_return }}">
    <input type="hidden" name="status" value="CONTACTED">
    <button type="submit">Mark contacted</button>
  </form>
  {% endif %}
  <form method="POST" action="{{ url_for('admin_lead_operations', lead_id=lead.id) }}">
    <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
    <input type="hidden" name="return_to" value="{{ crm_return }}">
    <input type="hidden" name="action" value="note">
    <label for="crm-note-{{ lead.id }}">Private staff note</label>
    <textarea id="crm-note-{{ lead.id }}" name="note" maxlength="2000" required placeholder="Add next step, agreed package or payment verification follow-up"></textarea>
    <button type="submit">Save note</button>
  </form>
  {% if lead.status in ('NEW', 'CONTACTED') %}
  <details class="crm-close">
    <summary>Close enquiry</summary>
    <form method="POST" action="{{ url_for('admin_lead_status', lead_id=lead.id) }}">
      <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
      <input type="hidden" name="return_to" value="{{ crm_return }}">
      <input type="hidden" name="status" value="CLOSED">
      <label><input type="checkbox" required name="close_ack" value="1"> I have finished or cancelled this enquiry; closing does not indicate payment or service completion.</label>
      <button type="submit">Close enquiry</button>
    </form>
  </details>
  {% endif %}
</details>
</article>
{% else %}
<p class="muted">No active enquiries. Older merged records remain in the audit history.</p>
{% endfor %}
</section>
"""
    source = source[:start] + updated_services + source[end:]
    source = _replace_once(
        source,
        ':where(button,input,select,textarea){font-family:inherit;}</style>',
        """.crm-intro,.crm-hint{font-size:12px;color:#667085;line-height:1.5}
.crm-count{font-size:13px;color:#667085;font-weight:600}
.crm-enquiry{border-top:1px solid #eaecf0;padding:15px 0}
.crm-enquiry:first-of-type{border-top:0}
.crm-payment{display:flex;gap:7px;flex-wrap:wrap;align-items:center;background:#f3f7fb;padding:9px 10px;margin-top:9px;border-radius:9px;font-size:12px;line-height:1.4}
.crm-payment strong{color:#101828}
.crm-payment>span:not(:first-child){border-left:1px solid #d0d5dd;padding-left:8px}
.crm-scope{margin-top:9px;border-left:3px solid #b54708;background:#fff8ec;border-radius:6px;padding:10px;font-size:12px;line-height:1.5}
.crm-preview{font-size:13px;line-height:1.5;color:#344054;overflow-wrap:anywhere;margin:10px 0}
.crm-details,.crm-actions-panel{border:1px solid #eaecf0;border-radius:9px;margin-top:9px;padding:9px 11px}
.crm-details summary,.crm-actions-panel summary,.crm-close summary{cursor:pointer;font-size:13px;font-weight:750}
.crm-details .summary{overflow-wrap:anywhere}
.crm-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:11px 0}
.crm-actions a{min-width:0;display:flex;text-align:center;align-items:center;justify-content:center;border:1px solid #d0d5dd;border-radius:8px;padding:10px 7px;font-size:12px;font-weight:800;text-decoration:none;color:#101828}
.crm-actions a:first-child{background:#157347;color:#fff;border-color:#157347}
.crm-actions-panel form{margin-top:10px;display:grid;gap:7px}
.crm-actions-panel label{font-size:12px;line-height:1.45}
.crm-actions-panel textarea{width:100%;min-height:73px;border:1px solid #d0d5dd;border-radius:8px;padding:10px;font:inherit;font-size:13px}
.crm-actions-panel button{min-height:42px;border:0;border-radius:8px;background:#101828;color:white;font-weight:800;cursor:pointer}
.crm-close{padding:10px 0}
.crm-close label{display:flex;gap:9px;align-items:flex-start}
@media(max-width:620px){.crm-actions{grid-template-columns:1fr}.crm-enquiry .lead-head{flex-wrap:wrap}.crm-enquiry .badges{justify-content:flex-start}}
:where(button,input,select,textarea){font-family:inherit;}</style>"""
    )
    return source


def install_crm_improvements(flask_app):
    """Patch only the existing authenticated customer-CRM view's Jinja template."""
    view = getattr(flask_app, "view_functions", {}).get("admin_customer_history")
    if view is None:
        return False
    namespace = view.__globals__
    current = namespace.get("CUSTOMER_CRM_TEMPLATE")
    if not isinstance(current, str):
        return False
    try:
        upgraded = improve_crm_template(current)
    except ValueError:
        # Fail open rather than take down the production web worker.
        print("IBROWS CRM: template shape changed; safely kept original view", flush=True)
        return False

    namespace["CUSTOMER_CRM_TEMPLATE"] = upgraded
    install_eligibility_package_support(flask_app, namespace)

    @flask_app.after_request
    def _crm_sensitive_response_headers(response):
        from flask import request
        # Include unauthenticated redirects and errors for the private profile route.
        if re.fullmatch(r"/admin/customers/[0-9]{1,20}", request.path):
            response.headers["Cache-Control"] = "private, no-store, no-cache, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    print("IBROWS CRM: admin-only customer improvements active", flush=True)
    return True



def _can_convert_to_eligibility(lead, paid, another_active_package):
    """Refuse conversion of any already-commercially-active or settled lead."""
    if not lead or paid or another_active_package:
        return False
    (_number, service, status, merged, privacy_deleted, consumed,
     estimated, currency, quote_status) = lead
    if service != "Scholarship Search" or status not in ("NEW", "CONTACTED"):
        return False
    if merged is not None or privacy_deleted is not None or consumed is not None:
        return False
    if quote_status != "NOT_STARTED":
        return False
    if currency != "MWK":
        return False
    if estimated is not None and Decimal(str(estimated)) != Decimal("5000"):
        return False
    return True


def install_eligibility_package_support(flask_app, namespace):
    """Register an explicitly admin-selected one-off package.

    No screenshot, message or package selection can produce a ledger payment.
    Only the existing verified-payment admin workflow can do so.
    """
    required = (
        "CAREER_SERVICE_DEFAULT_PRICES_MWK", "get_db", "admin_required",
        "validate_csrf", "_safe_admin_return_path", "_activity_insert",
        "canonicalize_service", "build_verified_payment_context",
    )
    if not all(name in namespace for name in required):
        return False

    prices = namespace["CAREER_SERVICE_DEFAULT_PRICES_MWK"]
    if "Scholarship Eligibility Check" not in prices:
        prices["Scholarship Eligibility Check"] = Decimal("5000")

    previous_canonicalize = namespace["canonicalize_service"]
    def canonicalize_with_one_off(value):
        normalized = " ".join(str(value or "").lower().split())
        if normalized in {
            "scholarship eligibility check", "scholarship eligibility screening",
        }:
            return "Scholarship Eligibility Check"
        return previous_canonicalize(value)
    namespace["canonicalize_service"] = canonicalize_with_one_off

    original_context = namespace["build_verified_payment_context"]
    def package_aware_payment_context(customer_number):
        context = original_context(customer_number)
        if not isinstance(context, list):
            return context
        extra = (
            "\nONE-OFF SCHOLARSHIP RULE: 'Scholarship Eligibility Check' is a separate "
            "MK5,000 screening service, NOT the MK60,000/month 'Scholarship Search' "
            "subscription. It only authorizes profile/qualification screening and "
            "identifying requirements for the customer's specific opportunity. "
            "Do not treat its payment as authorizing a shortlist, application "
            "submissions or a recurring term. When its VERIFIED STATUS is PAID, "
            "help with screening, clearly explain missing evidence and remind "
            "the customer that final eligibility decisions belong to funders. "
            "When not PAID, do not claim money received; request verification. "
            "For a one-off customer, use the exact CRM service label "
            "'Scholarship Eligibility Check' for future follow-ups."
        )
        output = []
        for part in context:
            if isinstance(part, dict) and isinstance(part.get("content"), str) and (
                "- Scholarship Eligibility Check:" in part["content"]
            ):
                output.append({**part, "content": part["content"] + extra})
            else:
                output.append(part)
        return output
    namespace["build_verified_payment_context"] = package_aware_payment_context

    if "crm_convert_scholarship_eligibility" not in flask_app.view_functions:
        def convert_scholarship_eligibility(lead_id):
            from flask import abort, request, redirect, url_for
            namespace["validate_csrf"]()
            if (request.form.get("confirm_scope") != "ELIGIBILITY"
                    or request.form.get("acknowledge_price") != "1"):
                abort(400)
            with namespace["get_db"]() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT customer_number, service, status, merged_into_lead_id,
                                  privacy_deleted_at, entitlement_consumed_at,
                                  estimated_value, COALESCE(value_currency,'MWK'),
                                  COALESCE(quote_status,'NOT_STARTED')
                           FROM leads WHERE id=%s FOR UPDATE""",
                        (lead_id,),
                    )
                    lead = cur.fetchone()
                    if not lead:
                        abort(404)
                    cur.execute(
                        "SELECT EXISTS(SELECT 1 FROM lead_payments WHERE lead_id=%s)",
                        (lead_id,),
                    )
                    has_payment = bool(cur.fetchone()[0])
                    cur.execute(
                        """SELECT EXISTS(
                             SELECT 1 FROM leads
                             WHERE customer_number=%s AND id<>%s
                               AND service='Scholarship Eligibility Check'
                               AND status IN ('NEW','CONTACTED')
                               AND merged_into_lead_id IS NULL
                               AND privacy_deleted_at IS NULL
                           )""",
                        (lead[0], lead_id),
                    )
                    already_active = bool(cur.fetchone()[0])
                    if not _can_convert_to_eligibility(lead, has_payment, already_active):
                        abort(409)
                    cur.execute(
                        """UPDATE leads
                           SET service='Scholarship Eligibility Check',
                               estimated_value=5000, value_currency='MWK',
                               updated_at=NOW()
                           WHERE id=%s""",
                        (lead_id,),
                    )
                    namespace["_activity_insert"](
                        cur, lead_id, "LEAD_UPDATED",
                        "Admin confirmed MK5,000 one-off Scholarship Eligibility Check "
                        "package; no payment recorded. Verify actual funds before assistance.",
                    )
                conn.commit()
            return_to = namespace["_safe_admin_return_path"](
                request.form.get("return_to")
            )
            return redirect(
                url_for("admin_customer_history", customer_number=lead[0],
                        return_to=return_to),
                code=303,
            )

        flask_app.add_url_rule(
            "/admin/leads/<int:lead_id>/scholarship-eligibility-package",
            endpoint="crm_convert_scholarship_eligibility",
            view_func=namespace["admin_required"](convert_scholarship_eligibility),
            methods=["POST"],
        )
    return True
