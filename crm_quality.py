"""Admin-only CRM usability and payment-safety improvements.

This module changes the existing Jinja template, not the database or the
authoritative ledger. Payment can only be recorded through the existing
authenticated, CSRF-protected, idempotent admin workflow after verification.
"""
import re

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
<div class="crm-scope"><strong>Check scholarship package before recording payment.</strong>
The MK5,000 Eligibility Check is a one-off screening service; it does not activate
the MK60,000/month Scholarship Assist plan. Set and confirm the correct package
amount in the lead manager after checking the actual mobile-money or bank record.</div>
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
