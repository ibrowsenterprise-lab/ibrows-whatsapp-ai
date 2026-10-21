"""Runs only against a disposable PostgreSQL database provisioned by CI."""
import os
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

@pytest.fixture(scope='module')
def application():
    assert os.environ['DATABASE_URL'].endswith('/ibrows_marketplace_test'), 'Disposable test database required'
    import app as production
    production.app.config.update(TESTING=True)
    return production

@pytest.fixture
def live(application, monkeypatch):
    a=application
    # Any accidental external notification fails this test; only the IBROWS admin alert is stubbed.
    import requests
    def no_network(*args, **kwargs): raise AssertionError('External network in tests')
    monkeypatch.setattr(requests.sessions.Session, 'request', no_network)
    from agro_marketplace import initialize_marketplace
    with a.get_db() as conn, conn.cursor() as c:
        c.execute('DELETE FROM public_rate_limits')
        c.execute('DELETE FROM agro_marketplace_buyer_enquiries')
        c.execute('DELETE FROM agro_marketplace_listings')
        c.execute('DELETE FROM website_service_requests')
        c.execute("""INSERT INTO website_service_requests(id,reference,service_key,full_name,phone,payload)
         VALUES (10,'IBR-SR-2026-0010','AGRICULTURE','PRIVATE SELLER','+265999123456',
         '{"commodity":"maize","variety_grade":"white","quantity":"50","quantity_unit":"50 kg bags","location":"Area 25 sector 4","trade_type":"Sell Farm Produce to IBROWS"}')""")
        c.execute("SELECT setval(pg_get_serial_sequence('website_service_requests','id'),10,true)")
    initialize_marketplace(a.get_db)
    return a,a.app.test_client()

def admin(c):
    with c.session_transaction() as s:
        s['admin_authenticated']=True
        s['csrf_token']='real-test-token'
    return {'csrf_token':'real-test-token'}

def listing(a):
    with a.get_db() as conn, conn.cursor() as cur:
        cur.execute('SELECT id FROM agro_marketplace_listings');return cur.fetchone()[0]

def test_seed_privacy_filter_and_html_escape(live):
    a,c=live
    r=c.get('/agriculture/marketplace')
    assert r.status_code==200
    assert b'MK 52,000' in r.data and b'White maize' in r.data
    assert b'Area 25 Sector 4, Lilongwe' in r.data
    for secret in (b'PRIVATE SELLER',b'999123456',b'seller_phone',b'seller_name'):
        assert secret not in r.data
    assert b'White maize' not in c.get('/agriculture/marketplace?commodity=soya').data
    r=c.get('/agriculture/marketplace?commodity=<script>alert(1)</script>')
    assert b'<script>' not in r.data
    assert r.headers['Cache-Control']=='no-store'

@pytest.mark.parametrize('status',['PENDING','REJECTED','PAUSED','SOLD_OUT'])
def test_hidden_stock_cannot_receive_enquiries(live,status):
    a,c=live; id=listing(a)
    with a.get_db() as conn, conn.cursor() as cur:
        cur.execute('UPDATE agro_marketplace_listings SET status=%s WHERE id=%s',(status,id))
    assert b'White maize' not in c.get('/agriculture/marketplace').data
    assert c.get(f'/agriculture/marketplace/{id}/enquire').status_code==404
    assert c.post(f'/agriculture/marketplace/{id}/enquire', data={}).status_code==404

def test_real_buyer_transaction_and_admin_visibility(live,monkeypatch):
    a,c=live; id=listing(a);called=[]
    # Blueprint captures alert at registration. Replace globals of captured function so no email can leave.
    monkeypatch.setattr(a,'BREVO_API_KEY','')
    c.get(f'/agriculture/marketplace/{id}/enquire')
    with c.session_transaction() as s: token=s['csrf_token']
    payload={'csrf_token':token,'name':'Test buyer','phone':'+265888000111','message':'Please arrange 3 bags','consent':'1'}
    assert c.post(f'/agriculture/marketplace/{id}/enquire',data={**payload,'csrf_token':'wrong'}).status_code==403
    response=c.post(f'/agriculture/marketplace/{id}/enquire',data=payload)
    assert response.status_code==200 and b'Enquiry received' in response.data
    with a.get_db() as conn, conn.cursor() as cur:
        cur.execute('SELECT e.listing_id,r.service_key,r.payload,r.full_name FROM agro_marketplace_buyer_enquiries e JOIN website_service_requests r ON r.id=e.service_request_id')
        row=cur.fetchone()
        assert row[0]==id and row[1]=='AGRICULTURE' and row[2]['marketplace_listing_id']==id and row[3]=='Test buyer'
        assert 'PRIVATE SELLER' not in str(row[2])
    admin(c)
    r=c.get('/admin/service-requests?service=AGRICULTURE')
    assert r.status_code==200 and b'Test buyer' in r.data

def test_admin_csrf_stock_and_seed_does_not_republish(live):
    from agro_marketplace import initialize_marketplace
    a,c=live; id=listing(a)
    assert c.get('/admin/agro-marketplace').status_code==302
    assert c.post('/admin/agro-marketplace',data={'listing_id':id,'status':'APPROVED'}).status_code==302
    form=admin(c)
    assert c.post('/admin/agro-marketplace',data={'listing_id':id,'status':'APPROVED'}).status_code==403
    response=c.post('/admin/agro-marketplace',data={**form,'listing_id':id,'quantity':'0','status':'APPROVED'})
    assert response.status_code==302
    initialize_marketplace(a.get_db)
    with a.get_db() as conn, conn.cursor() as cur:
        cur.execute('SELECT status,quantity,count(*) OVER() FROM agro_marketplace_listings')
        assert cur.fetchone()==('SOLD_OUT',0,1)
    assert b'White maize' not in c.get('/agriculture/marketplace').data

@pytest.mark.parametrize('bad',['NaN','Infinity','-1','1e99'])
def test_invalid_price_rejected(live,bad):
    a,c=live;form=admin(c)
    r=c.post('/admin/agro-marketplace/import-request/10',data={**form,'confirm':'yes','seller_consent':'yes','price_mwk':bad,'price_unit':'50 kg bag'})
    assert r.status_code==400

def test_spam_limit_and_honeypot(live):
    a,c=live;id=listing(a)
    assert c.post(f'/agriculture/marketplace/{id}/enquire', data={'fax_number':'spam'}).status_code==400
    responses=[c.post(f'/agriculture/marketplace/{id}/enquire',data={}).status_code for _ in range(12)]
    assert 429 in responses

def test_existing_public_services_and_navigation(live):
    a,c=live
    for path in ['/','/agriculture','/career-jobs','/scholarships-opportunities','/business-registration','/business-email','/cleaning','/car-wash','/construction','/fumigation','/landscaping','/design-branding','/photo-restoration','/project-discovery','/team','/privacy','/terms','/msj']:
        assert c.get(path).status_code in (200,302),path
    assert b'/agriculture/marketplace' in c.get('/agriculture').data
    assert c.post('/webhook',json={}).status_code in (403,503)

def test_marketplace_failure_does_not_disable_existing_services(live):
    a,c=live
    a.app.config['AGRO_MARKETPLACE_READY']=False
    try:
        assert c.get('/agriculture/marketplace').status_code==503
        assert c.get('/agriculture').status_code==200
    finally: a.app.config['AGRO_MARKETPLACE_READY']=True
