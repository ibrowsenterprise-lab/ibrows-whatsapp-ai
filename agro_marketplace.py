"""IBROWS-managed agro marketplace. Opt-in registration; no production migration on import."""
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from agro_marketplace_ui import CATALOGUE, ENQUIRY, SUCCESS, MODERATION, IMPORT
import re
from flask import current_app
from flask import Blueprint, abort, redirect, render_template_string, request, url_for


def format_quantity(value):
    """Remove padding zeros while preserving fractional stock and whole-number zeros."""
    text = format(Decimal(str(value)), 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def stock_summary(quantity, unit):
    """Separate stock count from package weight; never infer an unspecified bag size."""
    label = str(unit or '').strip()
    try:
        amount = format_quantity(quantity)
        singular = Decimal(str(quantity)) == 1
    except (InvalidOperation, ValueError, TypeError):
        return {'amount': str(quantity or ''), 'unit': label, 'pack': ''}
    bag = re.fullmatch(r'(\d+(?:\.\d+)?)\s*kg\s*bags?', label, re.IGNORECASE)
    if bag:
        return {'amount': amount, 'unit': 'bag' if singular else 'bags',
                'pack': format_quantity(bag.group(1)) + ' kg per bag'}
    normal = label.lower()
    if normal in ('kg', 'kilogram', 'kilograms'):
        label = 'kg'
    elif normal in ('tonne', 'tonnes'):
        label = 'tonne' if singular else 'tonnes'
    elif normal in ('bag', 'bags', 'other bag size'):
        label = 'bag' if singular else 'bags'
    return {'amount': amount, 'unit': label, 'pack': ''}


def create_agro_marketplace_blueprint(get_db, admin_required, get_csrf_token, validate_csrf, rate_limit=None, client_ip=None, reference_for_id=None, alert=None):
    bp = Blueprint('agro_marketplace', __name__)
    bp.add_app_template_filter(format_quantity, 'agro_quantity')
    bp.add_app_template_filter(stock_summary, 'agro_stock')

    @bp.before_request
    def protect_marketplace():
        if current_app.config.get('AGRO_MARKETPLACE_READY', True) is False:
            abort(503, 'Produce enquiries are temporarily unavailable. Please try again shortly.')
        if request.method == 'POST' and not request.path.startswith('/admin/'):
            if rate_limit and not rate_limit('agro-buy:' + client_ip(), 8, 3600):
                abort(429)
            if request.form.get('fax_number'):
                abort(400)

    @bp.after_request
    def privacy_headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Robots-Tag'] = 'noindex, nofollow' if '/enquire' in request.path or request.path.startswith('/admin/') else 'index, follow'
        return response

    @bp.get('/agriculture/marketplace')
    def catalogue():
        commodity = (request.args.get('commodity') or '').strip()[:80]
        location = (request.args.get('location') or '').strip()[:80]
        with get_db() as conn, conn.cursor() as cur:
            cur.execute('''SELECT id, commodity, variety_grade, quantity, quantity_unit,
                            price_mwk, price_unit, location, description
                            FROM agro_marketplace_listings
                            WHERE status='APPROVED' AND quantity>0
                              AND (%s='' OR commodity ILIKE '%%' || %s || '%%')
                              AND (%s='' OR location ILIKE '%%' || %s || '%%')
                            ORDER BY created_at DESC LIMIT 100''',
                        (commodity, commodity, location, location))
            rows = cur.fetchall()
        return render_template_string(CATALOGUE, page_title='Farm Produce Marketplace', rows=rows, commodity=commodity, location=location)

    @bp.route('/agriculture/marketplace/<int:listing_id>/enquire', methods=['GET','POST'])
    def buyer_enquiry(listing_id):
        with get_db() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, commodity FROM agro_marketplace_listings WHERE id=%s AND status='APPROVED' AND quantity>0", (listing_id,))
            listing = cur.fetchone()
        if not listing:
            abort(404)
        error = ''
        if request.method == 'POST':
            validate_csrf()
            name = (request.form.get('name') or '').strip()[:180]
            phone = (request.form.get('phone') or '').strip()[:80]
            message = (request.form.get('message') or '').strip()[:2000]
            if not name or not (7 <= len(''.join(c for c in phone if c.isdigit())) <= 15) or request.form.get('consent') != '1':
                error = 'Name, phone and consent are required.'
            else:
                with get_db() as conn, conn.cursor() as cur:
                    cur.execute("SELECT id,commodity FROM agro_marketplace_listings WHERE id=%s AND status='APPROVED' AND quantity>0 FOR SHARE", (listing_id,))
                    if not cur.fetchone(): abort(409)
                    service_id = None
                    if reference_for_id:
                        payload = json.dumps({'trade_type':'Buy Farm Produce from IBROWS','marketplace_listing_id':listing_id,'commodity':listing[1],'notes':message,'trade_status':'Buyer enquiry only — IBROWS confirmation required'})
                        cur.execute("INSERT INTO website_service_requests (service_key,full_name,phone,payload,status,notification_status) VALUES ('AGRICULTURE',%s,%s,%s::jsonb,'NEW','PENDING') RETURNING id,created_at", (name,phone,payload))
                        service_id, created_at = cur.fetchone()
                        reference = reference_for_id(service_id, created_at)
                        cur.execute('UPDATE website_service_requests SET reference=%s WHERE id=%s', (reference,service_id))
                    cur.execute('''INSERT INTO agro_marketplace_buyer_enquiries (listing_id,buyer_name,buyer_phone,message,service_request_id)
                        SELECT id,%s,%s,%s,%s FROM agro_marketplace_listings
                        WHERE id=%s AND status='APPROVED' AND quantity>0 RETURNING id''', (name, phone, message, service_id, listing_id))
                    result = cur.fetchone()
                    if not result: abort(409)
                    enquiry_id = result[0]
                if service_id and alert:
                    try:
                        alert(service_id)
                    except Exception:
                        current_app.logger.warning('Agro enquiry saved; admin notification requires retry')
                return render_template_string(SUCCESS, page_title='Enquiry received',id=enquiry_id)
        return render_template_string(ENQUIRY, page_title='Produce enquiry',listing=listing,error=error,csrf=get_csrf_token())

    @bp.route('/admin/agro-marketplace/import-request/<int:request_id>', methods=['GET', 'POST'])
    @admin_required
    def import_request(request_id):
        """Explicit admin conversion: an enquiry is NOT automatically a published listing."""
        with get_db() as conn, conn.cursor() as cur:
            cur.execute("""SELECT id, reference, service_key, payload
                           FROM website_service_requests WHERE id=%s""", (request_id,))
            req = cur.fetchone()
        if not req or req[2] != 'AGRICULTURE':
            abort(404)
        import json
        data = req[3] if isinstance(req[3], dict) else json.loads(req[3] or '{}')
        if data.get('trade_type') not in (None, 'Sell Farm Produce to IBROWS'):
            abort(400, 'Only seller requests can become listings')
        if request.method == 'POST':
            validate_csrf()
            if request.form.get('confirm') != 'yes' or request.form.get('seller_consent') != 'yes':
                abort(400)
            commodity = (data.get('commodity') or '').strip()
            location = (data.get('location') or '').strip()
            quantity_text = str(data.get('quantity') or '').strip()
            unit = (data.get('quantity_unit') or '').strip()
            try:
                qty = Decimal(quantity_text)
            except InvalidOperation:
                abort(400, 'Invalid source quantity')
            if not commodity or not location or not unit or not qty.is_finite() or not 0 < qty < Decimal('10000000000000'):
                abort(400, 'Incomplete source listing')
            price_text = request.form.get('price_mwk', '').strip()
            try:
                price = Decimal(price_text)
            except InvalidOperation:
                abort(400, 'Enter numeric price in MWK')
            if not price.is_finite() or not 0 < price < Decimal('100000000000000'):
                abort(400, 'Price must be positive')
            price_unit = (request.form.get('price_unit') or '').strip()[:80]
            if not price_unit:
                abort(400, 'Price unit required')
            # Avoid accidental publication; moderation approval is a separate step.
            with get_db() as conn, conn.cursor() as cur:
                cur.execute("""INSERT INTO agro_marketplace_listings
                    (source_request_id,seller_name,seller_phone,commodity,variety_grade,
                     quantity,quantity_unit,price_mwk,price_unit,location,
                     availability_note,transport_note,packaging,status)
                    SELECT id,full_name,phone,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDING'
                    FROM website_service_requests WHERE id=%s AND service_key='AGRICULTURE'
                    ON CONFLICT (source_request_id) DO NOTHING RETURNING id""",
                    (commodity,(data.get('variety_grade') or '')[:150],qty,unit,price,
                     price_unit,location,(data.get('timeframe') or '')[:200],
                     (data.get('transport_available') or '')[:200],
                     (data.get('packaging') or '')[:200],request_id))
                created = cur.fetchone()
            if created:
                return redirect(url_for('agro_marketplace.moderation'))
            abort(409, 'This service request already has a marketplace listing')
        return render_template_string(IMPORT, page_title='Prepare a produce listing',
          ref=req[1],commodity=data.get('commodity'),qty=data.get('quantity'),
          unit=data.get('quantity_unit'),location=data.get('location'),csrf=get_csrf_token())

    @bp.route('/admin/agro-marketplace', methods=['GET','POST'])
    @admin_required
    def moderation():
        if request.method == 'POST':
            validate_csrf()
            listing_id = request.form.get('listing_id',type=int)
            status = request.form.get('status','')
            if not listing_id or status not in ('APPROVED','REJECTED','PAUSED','SOLD_OUT'):
                abort(400)
            quantity = request.form.get('quantity', '').strip()
            try:
                quantity = Decimal(quantity) if quantity else None
            except InvalidOperation:
                abort(400)
            if quantity is not None and (not quantity.is_finite() or not 0 <= quantity < Decimal('10000000000000')):
                abort(400)
            if quantity == 0: status = 'SOLD_OUT'
            with get_db() as conn, conn.cursor() as cur:
                cur.execute('''UPDATE agro_marketplace_listings SET quantity=COALESCE(%s,quantity),status=%s,reviewed_at=NOW(),updated_at=NOW()
                    WHERE id=%s RETURNING id''',(quantity,status,listing_id))
                if not cur.fetchone(): abort(404)
            return redirect(url_for('agro_marketplace.moderation'))
        with get_db() as conn, conn.cursor() as cur:
            cur.execute('''SELECT id,commodity,quantity,quantity_unit,location,status,created_at
                           FROM agro_marketplace_listings ORDER BY created_at DESC LIMIT 100''')
            rows=cur.fetchall()
        return render_template_string(MODERATION, page_title='Manage produce listings',rows=rows,csrf=get_csrf_token())
    return bp


def initialize_marketplace(get_db):
    """Atomic, additive migration. Never alters or deletes existing service records.

    Bounded locks and one transaction ensure a failed rollout leaves the old
    application intact. Idempotent seed never republishes moderated stock.
    """
    with get_db() as conn, conn.cursor() as cur:
        cur.execute("SET LOCAL lock_timeout='3s'")
        cur.execute("SET LOCAL statement_timeout='15s'")
        cur.execute("SELECT pg_advisory_xact_lock(20261021, 10)")
        cur.execute((Path(__file__).parent / 'migrations/agro_marketplace_v1.sql').read_text())
        cur.execute("""INSERT INTO agro_marketplace_listings
            (source_request_id,seller_name,seller_phone,commodity,variety_grade,quantity,
             quantity_unit,price_mwk,price_unit,location,status,reviewed_at)
            SELECT id,full_name,phone,'White maize','White',50,'50 kg bags',52000,
              '50 kg bag','Area 25 Sector 4, Lilongwe','APPROVED',NOW()
            FROM website_service_requests WHERE reference='IBR-SR-2026-0010'
              AND service_key='AGRICULTURE' AND lower(payload->>'commodity')='maize'
              AND payload->>'quantity'='50' AND lower(payload->>'variety_grade')='white'
              AND payload->>'quantity_unit'='50 kg bags'
              AND payload->>'trade_type'='Sell Farm Produce to IBROWS'
            ON CONFLICT (source_request_id) DO NOTHING""")
