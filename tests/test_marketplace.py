from pathlib import Path
import importlib.util
import pytest
from flask import Flask, abort, request, session

spec = importlib.util.spec_from_file_location('agro_marketplace', Path(__file__).resolve().parents[1] / 'agro_marketplace.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class Cursor:
    def __init__(self, db): self.db=db; self.row=None; self.rows=[]
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def execute(self, sql, params=()):
        self.db.queries.append((sql,params))
        if 'FROM website_service_requests WHERE id=' in sql:
            self.row=(10,'IBR-SR-2026-0010','AGRICULTURE',{'commodity':'maize','location':'Area 25 Sector 4','quantity':'50','quantity_unit':'50 kg bags','variety_grade':'white'})
        elif 'INSERT INTO agro_marketplace_listings' in sql: self.row=(7,)
        elif 'FROM agro_marketplace_listings' in sql and 'WHERE status=' in sql: self.rows=self.db.public_rows
        elif 'FROM agro_marketplace_listings' in sql: self.row=(7,'maize')
        else: self.row=(1,)
    def fetchone(self): return self.row
    def fetchall(self): return self.rows
class DB:
    def __init__(self): self.queries=[]; self.public_rows=[]
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def cursor(self): return Cursor(self)

@pytest.fixture
def client():
    app=Flask(__name__); app.secret_key='test-key'; app.testing=True
    db=DB()
    def admin(f):
        from functools import wraps
        @wraps(f)
        def wrapped(*a,**kw):
            if not session.get('admin'): abort(403)
            return f(*a,**kw)
        return wrapped
    def csrf():
        if request.form.get('csrf_token')!='token': abort(403)
    app.register_blueprint(m.create_agro_marketplace_blueprint(lambda:db,admin,lambda:'token',csrf))
    return app.test_client(),db

def test_catalogue_only_approved_and_private(client):
    c,db=client
    db.public_rows=[(7,'maize','white',50,'50 kg bags',52000,'50 kg bag','Area 25 Sector 4','Available')]
    response=c.get('/agriculture/marketplace')
    assert response.status_code==200
    assert b'Enquire through IBROWS' in response.data
    assert b'52,000' in response.data
    assert b'seller_phone' not in response.data
    assert "status='APPROVED'" in db.queries[-1][0]

def test_admin_route_requires_login(client):
    c,_=client
    assert c.get('/admin/agro-marketplace/import-request/10').status_code==403

def test_import_requires_csrf_and_consent(client):
    c,db=client
    with c.session_transaction() as s:s['admin']=True
    form={'confirm':'yes','seller_consent':'yes','price_mwk':'52000','price_unit':'50 kg bag'}
    assert c.post('/admin/agro-marketplace/import-request/10',data=form).status_code==403
    form['csrf_token']='token';form.pop('seller_consent')
    assert c.post('/admin/agro-marketplace/import-request/10',data=form).status_code==400
    assert not any('INSERT INTO agro_marketplace_listings' in q[0] for q in db.queries)

def test_import_creates_pending_not_approved(client):
    c,db=client
    with c.session_transaction() as s:s['admin']=True
    r=c.post('/admin/agro-marketplace/import-request/10',data={'confirm':'yes','seller_consent':'yes','price_mwk':'52000','price_unit':'50 kg bag','csrf_token':'token'})
    assert r.status_code==302
    sql,params=next(q for q in db.queries if 'INSERT INTO agro_marketplace_listings' in q[0])
    assert "'PENDING'" in sql and 'ON CONFLICT' in sql
    assert '52000' in str(params)
