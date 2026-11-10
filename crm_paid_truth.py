"""Truthful, ledger-first IBROWS CRM display and unpaid pipeline values.

This module alters only authenticated administrative Jinja displays and the
sales pipeline summary's OPEN/unpaid field. It never creates receipts,
edits chat messages or makes a service appear completed.
"""
from decimal import Decimal
import re

TEMPLATE_MARKER = "<!-- ibrows-paid-crm-ledger-truth:20261111 -->"


def current_paid_summary(value, payment_status):
    text = str(value or "No summary available.")
    if payment_status != "PAID":
        return text
    # Retain the historical request, but don't display a pre-payment status
    # from an AI-generated note as if it were the live payment state.
    text = re.sub(
        r",?\s*but\s+the\s+ledger\s+currently\s+shows\s+[^.]*?\bNOT_PAID\b\.?",
        ".",
        text,
        flags=re.I,
    )
    return re.sub(r"\.{2,}", ".", text).strip()


def current_paid_reason(value, payment_status, service):
    reason = str(value or "")
    if payment_status != "PAID":
        return reason
    if (service == "Scholarship Eligibility Check"
            and re.search(r"payment\s+verification\s+requires\s+confirmation", reason, re.I)):
        return ("Payment verified. Next: obtain the customer's academic details "
                "and complete the one-off eligibility assessment.")
    return reason


def _replace_one(template, old, new):
    if template.count(old) != 1:
        raise ValueError("CRM paid display anchor missing or ambiguous")
    return template.replace(old, new, 1)


def improve_paid_leads_template(template):
    if TEMPLATE_MARKER in template:
        return template
    template = _replace_one(
        template,
        '<h2>Sales pipeline</h2>',
        TEMPLATE_MARKER + '\n<h2>Sales pipeline</h2>'
    )
    template = _replace_one(
        template,
        '<div class="pipe-title">Open estimated value</div>',
        '<div class="pipe-title">Unpaid value on open enquiries</div>'
    )
    template = _replace_one(
        template,
        '<div class="summary">{{ lead.summary or \'No summary available.\' }}</div>',
        '<div class="summary">{{ (lead.summary or \'No summary available.\')'
        '|ibrows_current_paid_summary(lead.payment_status) }}</div>',
    )
    template = _replace_one(
        template,
        '{% if lead.handover_reason %}<div class="reason"><strong>Human follow-up:</strong> {{ lead.handover_reason }}</div>{% endif %}',
        '{% if lead.handover_reason %}<div class="reason"><strong>Next step:</strong> '
        '{{ lead.handover_reason|ibrows_current_paid_reason(lead.payment_status, lead.service) }}'
        '</div>{% endif %}',
    )
    template = _replace_one(
        template,
        '<div class="summary">{{ (lead.summary or \'No summary available.\')'
        '|ibrows_current_paid_summary(lead.payment_status) }}</div>',
        '{% if lead.service == \'Scholarship Eligibility Check\' and lead.payment_status == \'PAID\' and lead.status != \'CLOSED\' %}'
        '<div class="completed-service" style="background:#ecfdf3;color:#067647;margin:9px 0">'
        'Payment confirmed — eligibility assessment awaiting completion. '
        'No quotation or second payment required for this MK5,000 package.'
        '</div>'
        '<a class="quick" href="{{ url_for(\'admin_eligibility_case\',lead_id=lead.id) }}">'
        'Open Paid Eligibility Work Queue</a>'
        '{% endif %}'
        '<div class="summary">{{ (lead.summary or \'No summary available.\')'
        '|ibrows_current_paid_summary(lead.payment_status) }}</div>',
    )
    return template


def improve_paid_customer_template(template):
    marker = "<!-- ibrows-paid-customer-ledger-truth:20261111 -->"
    if marker in template:
        return template
    original_preview = "<p class=\"crm-preview\">{{ (lead.summary or 'No summary available.')|truncate(165, True) }}</p>"
    improved_preview = (
        marker + "\n<p class=\"crm-preview\">{{ "
        "((lead.summary or 'No summary available.')"
        "|ibrows_current_paid_summary(lead.payment_status))|truncate(165, True) }}</p>"
    )
    template = _replace_one(template, original_preview, improved_preview)
    template = _replace_one(
        template,
        '<div class="summary">{{ lead.summary or \'No summary available.\' }}</div>',
        '<div class="summary">{{ (lead.summary or \'No summary available.\')'
        '|ibrows_current_paid_summary(lead.payment_status) }}</div>',
    )
    return template


def unpaid_open_value(original_pipeline, db_factory, amount_formatter):
    """Preserve the preexisting received/accepted metrics; correct OPEN only.

    Prices and payments must match in currency. Payments in any other
    currency cannot silently cancel a local-currency balance.
    """
    summary = original_pipeline()
    buckets = {}
    with db_factory() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT l.id, COALESCE(l.value_currency,'MWK'), l.estimated_value,
                       COALESCE(SUM(
                           CASE WHEN p.currency=COALESCE(l.value_currency,'MWK')
                           THEN p.amount ELSE 0 END
                       ),0)
                FROM leads l
                LEFT JOIN lead_payments p ON p.lead_id=l.id
                WHERE l.status <> 'CLOSED'
                  AND COALESCE(l.quote_status,'NOT_STARTED') <> 'DECLINED'
                  AND l.merged_into_lead_id IS NULL
                  AND l.privacy_deleted_at IS NULL
                  AND l.estimated_value IS NOT NULL
                GROUP BY l.id, l.value_currency, l.estimated_value
            """)
            rows = cur.fetchall()
    for lead_id, currency, value, paid in rows:
        residual = max(Decimal("0"), Decimal(str(value)) - Decimal(str(paid or 0)))
        if residual:
            buckets[currency] = buckets.get(currency, Decimal("0")) + residual
    return {**summary, "open": amount_formatter(buckets)}


def install_paid_crm_truth(flask_app):
    """Wire safe UI improvements into the already-authenticated admin routes."""
    view = getattr(flask_app, "view_functions", {}).get("admin_leads")
    if view is None:
        return False
    ns = view.__globals__
    template = ns.get("DASHBOARD_TEMPLATE")
    if not isinstance(template, str):
        return False
    try:
        improved = improve_paid_leads_template(template)
        customer_template = ns.get("CUSTOMER_CRM_TEMPLATE")
        improved_customer = (
            improve_paid_customer_template(customer_template)
            if isinstance(customer_template, str) and "ibrows-crm-quality:20261110" in customer_template
            else customer_template
        )
    except ValueError:
        print("IBROWS PAID CRM: template changed; existing display safely retained", flush=True)
        return False

    flask_app.add_template_filter(current_paid_summary, "ibrows_current_paid_summary")
    flask_app.add_template_filter(current_paid_reason, "ibrows_current_paid_reason")
    ns["DASHBOARD_TEMPLATE"] = improved
    if isinstance(improved_customer, str):
        ns["CUSTOMER_CRM_TEMPLATE"] = improved_customer

    original = ns.get("get_pipeline_summary")
    if callable(original) and not getattr(original, "_ibrows_paid_unpaid_summary", False):
        def corrected_summary():
            try:
                return unpaid_open_value(
                    original, ns["get_db"], ns["_crm_amount_lines"]
                )
            except Exception as exc:
                # Never break the CRM on an unexpected payment query failure.
                print("IBROWS PAID CRM: unpaid-value query unavailable "
                      f"({type(exc).__name__}); retaining old pipeline summary", flush=True)
                return original()
        corrected_summary._ibrows_paid_unpaid_summary = True
        ns["get_pipeline_summary"] = corrected_summary
    print("IBROWS PAID CRM: truthful verified-payment and unpaid-balance display active",flush=True)
    return True
