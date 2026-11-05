"""Variety batches preserve sources and independently priced stock."""
from decimal import Decimal
import pytest
from werkzeug.datastructures import MultiDict
from agro_marketplace import parse_variants, money, initialize_marketplace
from test_agro_postgres import application, live, admin


def variant_form(**overrides):
    data = dict(variant_name=['White rice','Brown rice'],variant_quantity=['3000','2000'],
        variant_unit=['kg','kg'],variant_price=['5000','7000'],variant_price_unit=['kg','kg'])
    data.update(overrides)
    return MultiDict(data)


def source(a, options=None):
    import json
    data = dict(commodity='Rice',variety_grade='White / Brown',quantity='5000',quantity_unit='kg',
        location='Lilongwe',target_price='White MK5000/kg, Brown MK7000/kg',trade_type='Sell Farm Produce to IBROWS')
    if options is not None: data['product_options']=options
    with a.get_db() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO website_service_requests(reference,service_key,full_name,phone,payload) VALUES ('IBR-SR-TEST-RICE','AGRICULTURE','PRIVATE RICE SELLER','+265999987654',%s::jsonb) RETURNING id",(json.dumps(data),))
        return cur.fetchone()[0],data


@pytest.mark.parametrize('changes',[
    {'variant_quantity':['NaN','2000']}, {'variant_quantity':['3000','']},
    {'variant_quantity':['3000','0']}, {'variant_price':['5000','Infinity']},
    {'variant_price':['5000','7000.001']}, {'variant_name':['Rice','rice']},
    {'variant_unit':['kg']}, {'variant_name':['A']*21},
])
def test_reject_incomplete_or_invalid_batches(changes):
    with pytest.raises(ValueError): parse_variants(variant_form(**changes))


def test_money_retains_cents():
    assert money(Decimal('5000'))=='5,000'
    assert money(Decimal('5000.25'))=='5,000.25'


def test_separate_prices_pending_then_approval(live):
    a,c=live;rid,original=source(a); form=admin(c)
    data=variant_form();data.update({**form,'confirm':'yes','seller_consent':'yes'})
    assert c.post(f'/admin/agro-marketplace/import-request/{rid}',data=data).status_code==302
    with a.get_db() as conn,conn.cursor() as cur:
        cur.execute('SELECT payload FROM website_service_requests WHERE id=%s',(rid,));assert cur.fetchone()[0]==original
        cur.execute("SELECT l.id,l.variety_grade,l.quantity,l.price_mwk,l.status FROM agro_marketplace_listings l JOIN agro_marketplace_listing_sources s ON s.listing_id=l.id WHERE s.source_request_id=%s ORDER BY l.id",(rid,))
        rows=cur.fetchall()
    assert [(r[1],r[2],r[3],r[4]) for r in rows]==[('White rice',3000,5000,'PENDING'),('Brown rice',2000,7000,'PENDING')]
    assert b'Brown rice' not in c.get('/agriculture/marketplace').data
    assert c.post(f'/admin/agro-marketplace/import-request/{rid}',data=data).status_code==409
    for row in rows:
        assert c.post('/admin/agro-marketplace',data={**form,'listing_id':row[0],'quantity':str(row[2]),'price_mwk':str(row[3]),'price_unit':'kg','status':'APPROVED'}).status_code==302
    page=c.get('/agriculture/marketplace?commodity=brown').data
    assert b'Brown rice' in page and b'MK 7,000' in page and b'White rice' not in page
    assert b'PRIVATE RICE SELLER' not in page and b'999987654' not in page
    detail=c.get(f'/agriculture/marketplace/{rows[1][0]}/enquire').data
    assert b'Brown rice' in detail and b'MK 7,000' in detail
    # Re-running migrations preserves all moderated stock and every original request.
    initialize_marketplace(a.get_db)
    with a.get_db() as conn,conn.cursor() as cur:
        cur.execute('SELECT count(*) FROM agro_marketplace_listing_sources WHERE source_request_id=%s',(rid,));assert cur.fetchone()[0]==2


def test_mixed_request_needs_explicit_stock_and_atomic_validation(live):
    a,c=live;rid,_=source(a);form=admin(c)
    before=c.get(f'/admin/agro-marketplace/import-request/{rid}')
    assert b'value="5000"' not in before.data # Combined source stock is not prefilled as variety stock.
    legacy={**form,'confirm':'yes','seller_consent':'yes','price_mwk':'5000','price_unit':'kg'}
    assert c.post(f'/admin/agro-marketplace/import-request/{rid}',data=legacy).status_code==400
    data=variant_form(variant_quantity=['3000','NaN']);data.update({**form,'confirm':'yes','seller_consent':'yes'})
    assert c.post(f'/admin/agro-marketplace/import-request/{rid}',data=data).status_code==400
    with a.get_db() as conn,conn.cursor() as cur:
        cur.execute('SELECT count(*) FROM agro_marketplace_listings WHERE source_request_id=%s',(rid,));assert cur.fetchone()[0]==0


def test_seller_form_saves_options_without_publishing(live,monkeypatch):
    a,c=live; captured=[]
    monkeypatch.setattr(a,'_create_website_service_request',lambda *args: captured.append(args) or 'TEST-REF')
    c.get('/agriculture?sell=1')
    with c.session_transaction() as sess: token=sess.get('public_service_csrf_AGRICULTURE')
    # Use the same token extractor a real visitor receives.
    import re
    token=re.search(r'name="csrf_token" value="([^"]+)"',c.get('/agriculture?sell=1').get_data(as_text=True)).group(1)
    data=variant_form();data.update(dict(csrf_token=token,full_name='Seller',phone='+265888000111',consent='1',trade_type='SELL_TO_IBROWS',commodity='Rice',quantity='5000',quantity_unit='KG',location='Lilongwe'))
    response=c.post('/agriculture',data=data)
    assert response.status_code==302
    assert len(captured)==1 and captured[0][4]['product_options'][1]['price']=='7000'
    assert 'Varieties supplied:' in captured[0][4]['notes']
