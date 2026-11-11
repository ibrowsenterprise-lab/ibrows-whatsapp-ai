"""Request-scoped optimization of verified payment lookups for WhatsApp AI.

The existing source checks every service by reopening PostgreSQL and rerunning
the same 'all active leads for this customer' query. This adapter fetches
those same ledger rows once per inbound WhatsApp request, then applies the
same per-service calculations. It is not a persistent cache.

Safety:
- Read-only SELECT with payment currency and entitlement gates unchanged.
- No cached records shared across requests or customers.
- No changes to receipts, payments, entitlement activation or public routes.
- If a read fails, use the original ledger function; never guess a paid state.
- Only active inside the model's /webhook payment-context construction.
"""
from decimal import Decimal

SQL_ACTIVE_LEADS = """
    SELECT
        l.id, l.service, l.estimated_value, COALESCE(l.value_currency, 'MWK'),
        l.quote_status, l.status, l.updated_at,
        COALESCE(SUM(CASE WHEN p.currency = COALESCE(l.value_currency, 'MWK')
                          THEN p.amount ELSE 0 END), 0) AS paid_total
    FROM leads l
    LEFT JOIN lead_payments p ON p.lead_id = l.id
    WHERE l.customer_number = %s
      AND l.status IN ('NEW', 'CONTACTED')
      AND l.merged_into_lead_id IS NULL
      AND l.privacy_deleted_at IS NULL
      AND l.entitlement_consumed_at IS NULL
    GROUP BY l.id, l.service, l.estimated_value, l.value_currency,
             l.quote_status, l.status, l.updated_at
    ORDER BY l.updated_at DESC, l.id DESC
"""


def fetch_ledger_rows(db_factory, customer_number):
    """One database read, with the same SQL filtering as the original helper."""
    with db_factory() as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_ACTIVE_LEADS, (customer_number,))
            return cur.fetchall()


def state_from_ledger_rows(rows, service, fallback_required_mwk, canonicalize):
    """Reconstruct the original verified-only per-service state exactly."""
    wanted = canonicalize(service)
    row = next((r for r in rows if canonicalize(r[1]) == wanted), None)
    if not row:
        required = (Decimal(str(fallback_required_mwk))
                    if fallback_required_mwk is not None else None)
        return {
            "lead_id": None, "service": wanted, "currency": "MWK",
            "required": required, "paid": Decimal("0"), "balance": required,
            "status": "NOT_VERIFIED", "quote_status": "NOT_STARTED",
        }

    lead_id, _service, estimated, currency, quote_status, _status, _updated, paid_total = row
    paid = Decimal(paid_total or 0)
    required = Decimal(estimated) if estimated is not None else None
    if required is None and currency == "MWK" and fallback_required_mwk is not None:
        required = Decimal(str(fallback_required_mwk))

    balance = None if required is None else max(required - paid, Decimal("0"))
    if paid <= 0:
        status = "NOT_PAID"
    elif required is None:
        status = "RECEIVED_UNPRICED"
    elif paid < required:
        status = "PART_PAID"
    else:
        status = "PAID"

    return {
        "lead_id": lead_id, "service": wanted, "currency": currency,
        "required": required, "paid": paid, "balance": balance,
        "status": status, "quote_status": quote_status or "NOT_STARTED",
    }


def install_payment_query_batch(flask_app):
    """Integrate after Flask core startup; never mutate any stored data."""
    view = getattr(flask_app, "view_functions", {}).get("admin_leads")
    if view is None:
        return False
    ns = view.__globals__
    required = (
        "get_db", "get_verified_service_payment_state",
        "build_verified_payment_context", "canonicalize_service"
    )
    if not all(callable(ns.get(name)) for name in required):
        return False
    original_lookup = ns["get_verified_service_payment_state"]
    original_context = ns["build_verified_payment_context"]
    if getattr(original_context, "_ibrows_batch_ledger_context", False):
        return True

    def request_lookup(customer_number, service, fallback_required_mwk=None):
        from flask import g, has_request_context
        if (not has_request_context()
                or getattr(g, "_ibrows_payment_batch_customer", None) != customer_number):
            return original_lookup(customer_number, service, fallback_required_mwk)
        # A failed batched read must never grant payment; reuse authoritative
        # original lookup and let its own outage handling decide what to do.
        if getattr(g, "_ibrows_payment_batch_failed", False):
            return original_lookup(customer_number, service, fallback_required_mwk)
        try:
            rows = getattr(g, "_ibrows_payment_batch_rows", None)
            if rows is None:
                rows = fetch_ledger_rows(ns["get_db"], customer_number)
                g._ibrows_payment_batch_rows = rows
            return state_from_ledger_rows(
                rows, service, fallback_required_mwk, ns["canonicalize_service"]
            )
        except Exception as error:
            g._ibrows_payment_batch_failed = True
            print("IBROWS PAYMENT BATCH: reverting to original lookup ("
                  + type(error).__name__ + ")", flush=True)
            return original_lookup(customer_number, service, fallback_required_mwk)

    def request_context(customer_number):
        from flask import g, request, has_request_context
        if (not has_request_context() or request.path != "/webhook"
                or request.method != "POST"):
            return original_context(customer_number)
        # Flask.g is isolated to the request; no global cross-customer cache.
        previously = (
            getattr(g, "_ibrows_payment_batch_customer", None),
            getattr(g, "_ibrows_payment_batch_rows", None),
            getattr(g, "_ibrows_payment_batch_failed", False),
        )
        g._ibrows_payment_batch_customer = customer_number
        g._ibrows_payment_batch_rows = None
        g._ibrows_payment_batch_failed = False
        try:
            return original_context(customer_number)
        finally:
            (g._ibrows_payment_batch_customer,
             g._ibrows_payment_batch_rows,
             g._ibrows_payment_batch_failed) = previously

    request_context._ibrows_batch_ledger_context = True
    ns["get_verified_service_payment_state"] = request_lookup
    ns["build_verified_payment_context"] = request_context
    print("IBROWS PAYMENT EFFICIENCY: request-scoped, verified-only ledger batch ready",flush=True)
    return True
