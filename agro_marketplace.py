"""IBROWS-managed agro marketplace. Opt-in registration; no production migration on import."""
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from agro_marketplace_ui import CATALOGUE, ENQUIRY, SUCCESS, MODERATION, IMPORT, SELL_WITH_PHOTOS, SELL_WITH_PHOTOS_SUCCESS
from agro_photo_persistence import save_seller_photos
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


def positive_number(value, limit, places):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or not 0 < number < Decimal(limit) or number != number.quantize(Decimal(places)):
            raise ValueError()
        return number
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Enter a positive quantity (up to 3 decimals) and price (up to 2 decimals).')


def parse_variants(form):
    """Validate the complete batch before any insert; never invent stock allocations."""
    keys = ('variant_name', 'variant_quantity', 'variant_unit', 'variant_price', 'variant_price_unit')
    columns = [form.getlist(k) for k in keys]
    if not columns[0] or len(columns[0]) > 20 or len({len(c) for c in columns}) != 1:
        raise ValueError('Add between 1 and 20 complete varieties.')
    result, names = [], set()
    for row in zip(*columns):
        name, qty, unit, price, per = [v.strip() for v in row]
        if not name or len(name)>150 or not unit or len(unit)>80 or not per or len(per)>80:
            raise ValueError('Each variety needs a name, quantity, quantity unit, price and price unit.')
        if name.casefold() in names:
            raise ValueError('Use a different name for each variety or pack size.')
        names.add(name.casefold())
        qty = positive_number(qty, '10000000000000', '0.001')
        price = positive_number(price, '100000000000000', '0.01')
        result.append(dict(name=name, quantity=str(qty), unit=unit, price=str(price), price_unit=per))
    return result


def money(value):
    number = Decimal(str(value))
    return format(number, ',.0f') if number == number.to_integral_value() else format(number, ',.2f')


def create_agro_marketplace_blueprint(get_db, admin_required, get_csrf_token, validate_csrf, rate_limit=None, client_ip=None, reference_for_id=None, alert=None):
    bp = Blueprint('agro_marketplace', __name__)
    bp.add_app_template_filter(format_quantity, 'agro_quantity')
    bp.add_app_template_filter(money, 'agro_money')
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

    @bp.route('/agriculture/marketplace/sell', methods=['GET', 'POST'])
    def sell_with_photos():
        """Mobile-friendly direct seller intake, with pending moderation."""
        error = ''
        values = request.form if request.method == 'POST' else {}
        if request.method == 'POST':
            validate_csrf()
            if request.content_length and request.content_length > 25 * 1024 * 1024:
                abort(413, 'Photo upload is too large.')
            name = (request.form.get('name') or '').strip()[:180]
            phone = (request.form.get('phone') or '').strip()[:80]
            commodity = (request.form.get('commodity') or '').strip()[:120]
            variety = (request.form.get('variety') or '').strip()[:150]
            unit = (request.form.get('quantity_unit') or '').strip()[:80]
            price_unit = (request.form.get('price_unit') or '').strip()[:80]
            location = (request.form.get('location') or '').strip()[:220]
            description = (request.form.get('description') or '').strip()[:1000]
            if not all((name, commodity, unit, price_unit, location)) or not 7 <= len(''.join(c for c in phone if c.isdigit())) <= 15 or request.form.get('consent') != '1':
                error = 'Complete the required fields, provide a valid phone number and confirm consent.'
            else:
                try:
                    quantity = positive_number(request.form.get('quantity'), '10000000000000', '0.001')
                    price = positive_number(request.form.get('price_mwk'), '100000000000000', '0.01')
                    from agro_photo_validation import validate_produce_photos
                    photos = validate_produce_photos(request.files.getlist('produce_photos'))
                except ValueError as exc:
                    error = str(exc)
                if not error:
                    payload = json.dumps({
                        'trade_type': 'Sell Farm Produce to IBROWS',
                        'commodity': commodity, 'variety_grade': variety,
                        'quantity': str(quantity), 'quantity_unit': unit,
                        'target_price': str(price), 'price_unit': price_unit,
                        'location': location, 'description': description,
                        'photo_count': len(photos), 'seller_consent': True,
                    })
                    with get_db() as conn, conn.cursor() as cur:
                        cur.execute("""INSERT INTO website_service_requests
                            (service_key,full_name,phone,payload,status,notification_status)
                            VALUES ('AGRICULTURE',%s,%s,%s::jsonb,'NEW','PENDING')
                            RETURNING id,created_at""", (name, phone, payload))
                        request_id, created_at = cur.fetchone()
                        if reference_for_id:
                            reference = reference_for_id(request_id, created_at)
                            cur.execute('UPDATE website_service_requests SET reference=%s WHERE id=%s',
                                        (reference, request_id))
                        cur.execute("""INSERT INTO agro_marketplace_listings
                            (source_request_id,seller_name,seller_phone,commodity,variety_grade,
                             quantity,quantity_unit,price_mwk,price_unit,location,description,status)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDING')
                            RETURNING id""",
                            (request_id,name,phone,commodity,variety,str(quantity),unit,str(price),price_unit,location,description))
                        listing_id = cur.fetchone()[0]
                        save_seller_photos(cur, request_id, request.files.getlist('produce_photos'))
                        if photos:
                            cur.execute('UPDATE agro_produce_photos SET listing_id=%s WHERE seller_request_id=%s',
                                        (listing_id, request_id))
                    if alert:
                        try:
                            alert(request_id)
                        except Exception:
                            current_app.logger.warning('Seller submission saved; notification requires retry')
                    return render_template_string(SELL_WITH_PHOTOS_SUCCESS, page_title='Produce submitted', id=request_id)
        return render_template_string(SELL_WITH_PHOTOS, page_title='Sell your produce',
                                      csrf=get_csrf_token(), values=values, error=error), (400 if error else 200)

    @bp.get('/agriculture/marketplace/photo/<int:photo_id>')
    def approved_produce_photo(photo_id):
        from flask import Response
        from agro_photo_persistence import get_approved_listing_photo
        with get_db() as conn, conn.cursor() as cur:
            result = get_approved_listing_photo(cur, photo_id)
        if not result:
            abort(404)
        return Response(bytes(result[0]), mimetype='image/jpeg',
                        headers={'X-Content-Type-Options':'nosniff',
                                 'Cache-Control':'public, max-age=300'})

    @bp.get('/agriculture/marketplace')
    def catalogue():
        commodity = (request.args.get('commodity') or '').strip()[:80]
        location = (request.args.get('location') or '').strip()[:80]
        with get_db() as conn, conn.cursor() as cur:
            cur.execute('''SELECT id, commodity, variety_grade, quantity, quantity_unit,
                            price_mwk, price_unit, location, description,
                            (SELECT MIN(p.id) FROM agro_produce_photos p
                             WHERE p.listing_id=agro_marketplace_listings.id) AS photo_id
                            FROM agro_marketplace_listings
                            WHERE status='APPROVED' AND quantity>0
                              AND (%s='' OR concat_ws(' ',commodity,variety_grade) ILIKE '%%' || %s || '%%')
                              AND (%s='' OR location ILIKE '%%' || %s || '%%')
                            ORDER BY created_at DESC LIMIT 100''',
                        (commodity, commodity, location, location))
            rows = cur.fetchall()
        return render_template_string(CATALOGUE, page_title='Farm Produce Marketplace', rows=rows, commodity=commodity, location=location)

    @bp.route('/agriculture/marketplace/<int:listing_id>/enquire', methods=['GET','POST'])
    def buyer_enquiry(listing_id):
        with get_db() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, commodity, variety_grade, price_mwk, price_unit FROM agro_marketplace_listings WHERE id=%s AND status='APPROVED' AND quantity>0", (listing_id,))
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
                        payload = json.dumps({'trade_type':'Buy Farm Produce from IBROWS','marketplace_listing_id':listing_id,'commodity':listing[1],'variety_grade':listing[2], 'quoted_price_mwk':str(listing[3]), 'price_unit':listing[4], 'notes':message,'trade_status':'Buyer enquiry only — IBROWS confirmation required'})
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
        error = ''
        source_options = data.get('product_options') or []
        if request.method == 'POST':
            validate_csrf()
            if request.form.get('confirm') != 'yes' or request.form.get('seller_consent') != 'yes':
                abort(400, 'Confirm stock, price and seller permission.')
            try:
                if request.form.getlist('variant_name'):
                    options = parse_variants(request.form)
                else:
                    # Backward compatible single-product import; mixed requests need explicit rows.
                    grade = str(data.get('variety_grade') or '')
                    target = str(data.get('target_price') or '').lower()
                    if source_options or '/' in grade or ('white' in target and 'brown' in target):
                        raise ValueError('Enter each variety and its confirmed quantity separately.')
                    options = [dict(name=grade or str(data.get('commodity') or ''),
                        quantity=str(positive_number(data.get('quantity'), '10000000000000', '0.001')),
                        unit=str(data.get('quantity_unit') or ''),
                        price=str(positive_number(request.form.get('price_mwk'), '100000000000000', '0.01')),
                        price_unit=(request.form.get('price_unit') or '').strip()[:80])]
                    if not options[0]['unit'] or not options[0]['price_unit']:
                        raise ValueError('Quantity and price units are required.')
                commodity = str(data.get('commodity') or '').strip()[:240]
                location = str(data.get('location') or '').strip()[:220]
                if not commodity or not location:
                    raise ValueError('The seller request needs produce and location details.')
            except ValueError as exc:
                error = str(exc)
            if not error:
                with get_db() as conn, conn.cursor() as cur:
                    # Serialize imports of the same source, including simultaneous browser submissions.
                    cur.execute('SELECT id FROM website_service_requests WHERE id=%s FOR UPDATE', (request_id,))
                    cur.execute('SELECT id FROM agro_marketplace_listings WHERE source_request_id=%s', (request_id,))
                    if cur.fetchone():
                        abort(409, 'This request already has listings. Manage the existing stock instead.')
                    for index, option in enumerate(options):
                        cur.execute("""INSERT INTO agro_marketplace_listings
                            (source_request_id,seller_name,seller_phone,commodity,variety_grade,
                             quantity,quantity_unit,price_mwk,price_unit,location,
                             availability_note,transport_note,packaging,status)
                            SELECT %s,full_name,phone,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'PENDING'
                            FROM website_service_requests WHERE id=%s AND service_key='AGRICULTURE'
                            ON CONFLICT (source_request_id) DO NOTHING RETURNING id""",
                            (request_id if index==0 else None,commodity,option['name'],option['quantity'],
                             option['unit'],option['price'],option['price_unit'],location,
                             str(data.get('timeframe') or '')[:200],str(data.get('transport_available') or '')[:200],
                             str(data.get('packaging') or '')[:200],request_id))
                        created = cur.fetchone()
                        if not created: abort(409, 'This request already has a listing.')
                        cur.execute("""INSERT INTO agro_marketplace_listing_sources
                            (listing_id,source_request_id,variant_key) VALUES (%s,%s,%s)""",
                            (created[0],request_id,option['name'].casefold()))
                return redirect(url_for('agro_marketplace.moderation'))
        if request.method == 'POST' and request.form.getlist('variant_name'):
            options = [dict(zip(('name','quantity','unit','price','price_unit'), row)) for row in zip(*[
                request.form.getlist(k) for k in ('variant_name','variant_quantity','variant_unit','variant_price','variant_price_unit')])][:20]
        elif source_options:
            options = source_options
        else:
            mixed = '/' in str(data.get('variety_grade') or '') or ('white' in str(data.get('target_price') or '').lower() and 'brown' in str(data.get('target_price') or '').lower())
            options = [dict(name='' if mixed else data.get('variety_grade') or data.get('commodity'),
                quantity='' if mixed else data.get('quantity'),unit=data.get('quantity_unit'),price='',price_unit='')]
        return render_template_string(IMPORT, page_title='Prepare produce listings',
          ref=req[1],commodity=data.get('commodity'),qty=data.get('quantity'),
          unit=data.get('quantity_unit'),location=data.get('location'),source_grade=data.get('variety_grade'),
          source_price=data.get('target_price'),options=options,error=error,csrf=get_csrf_token()), (400 if error else 200)

    @bp.route('/admin/agro-marketplace', methods=['GET','POST'])
    @admin_required
    def moderation():
        if request.method == 'POST':
            validate_csrf()
            listing_id = request.form.get('listing_id',type=int)
            status = request.form.get('status','')
            if not listing_id or status not in ('PENDING','APPROVED','REJECTED','PAUSED','SOLD_OUT'):
                abort(400)
            quantity = request.form.get('quantity', '').strip()
            try:
                quantity = Decimal(quantity) if quantity else None
            except InvalidOperation:
                abort(400)
            if quantity is not None and (not quantity.is_finite() or not 0 <= quantity < Decimal('10000000000000') or quantity != quantity.quantize(Decimal('0.001'))):
                abort(400)
            price = None
            price_unit = None
            if 'price_mwk' in request.form:
                try:
                    price = positive_number(request.form.get('price_mwk'), '100000000000000', '0.01')
                except ValueError as exc:
                    abort(400, str(exc))
                price_unit = (request.form.get('price_unit') or '').strip()[:80]
                if not price_unit: abort(400, 'Price unit required')
            if quantity == 0: status = 'SOLD_OUT'
            with get_db() as conn, conn.cursor() as cur:
                cur.execute('''UPDATE agro_marketplace_listings SET quantity=COALESCE(%s,quantity),status=%s,price_mwk=COALESCE(%s,price_mwk),price_unit=COALESCE(%s,price_unit),reviewed_at=NOW(),updated_at=NOW()
                    WHERE id=%s RETURNING id''',(quantity,status,price,price_unit,listing_id))
                if not cur.fetchone(): abort(404)
            return redirect(url_for('agro_marketplace.moderation'))
        with get_db() as conn, conn.cursor() as cur:
            cur.execute('''SELECT id,commodity,quantity,quantity_unit,location,status,created_at,variety_grade,price_mwk,price_unit
                           FROM agro_marketplace_listings ORDER BY created_at DESC LIMIT 100''')
            rows=cur.fetchall()
        return render_template_string(MODERATION, page_title='Manage produce listings',rows=rows,csrf=get_csrf_token())
    return bp


def initialize_marketplace(get_db):
    """Atomic setup and authorized corrections; preserves existing service records.

    Bounded locks and one transaction ensure a failed rollout leaves the old
    application intact. Idempotent seed never republishes moderated stock.
    """
    with get_db() as conn, conn.cursor() as cur:
        cur.execute("SET LOCAL lock_timeout='3s'")
        cur.execute("SET LOCAL statement_timeout='15s'")
        cur.execute("SELECT pg_advisory_xact_lock(20261021, 10)")
        cur.execute((Path(__file__).parent / 'migrations/agro_marketplace_v1.sql').read_text())
        cur.execute((Path(__file__).parent / 'migrations/agro_marketplace_varieties.sql').read_text())
        cur.execute((Path(__file__).parent / 'migrations/agro_rice_units_20261105.sql').read_text())
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
