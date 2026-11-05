"""Real Chromium mobile layout and add/remove interaction checks; no production writes."""
from decimal import Decimal
import pytest
from flask import Flask, render_template_string
from playwright.sync_api import sync_playwright
from agro_marketplace import create_agro_marketplace_blueprint
from agro_marketplace_ui import CATALOGUE, IMPORT

@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as p:
        b=p.chromium.launch(args=['--no-sandbox']);yield b;b.close()

@pytest.mark.parametrize('width',[320,360,390,768,1280])
def test_catalogue_mobile_no_horizontal_overflow(browser,width):
    app=Flask(__name__)
    app.register_blueprint(create_agro_marketplace_blueprint(None,lambda f:f,lambda:'token',lambda:None))
    with app.test_request_context():
        html=render_template_string(CATALOGUE,rows=[(1,'Rice','Brown rice',Decimal('2000.000'),'kg',Decimal('7000.25'),'kg','Lilongwe & Blantyre','Delivery through IBROWS.')],commodity='',location='')
    page=browser.new_page(viewport={'width':width,'height':800});page.set_content(html)
    assert page.locator('.produce-card').is_visible()
    assert page.locator('.price').inner_text()=='MK 7,000.25'
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('.produce-card').bounding_box()['y']<650
    assert page.locator('a',has_text='Sell your produce').first.get_attribute('href')=='/agriculture?sell=1'
    page.close()


def test_admin_variety_add_remove_mobile(browser):
    app=Flask(__name__)
    app.register_blueprint(create_agro_marketplace_blueprint(None,lambda f:f,lambda:'token',lambda:None))
    with app.test_request_context():
        html=render_template_string(IMPORT,ref='TEST',commodity='Rice',qty='5000',unit='kg',location='Lilongwe',options=[dict(name='',quantity='',unit='kg',price='',price_unit='kg')],error='',csrf='token')
    page=browser.new_page(viewport={'width':320,'height':800});page.set_content(html)
    page.locator('#add-variety').click()
    assert page.locator('.variant-row').count()==2
    page.locator('.variant-row').last.locator('input[name=variant_name]').fill('Brown rice')
    page.locator('.remove-variety').last.click()
    assert page.locator('.variant-row').count()==1
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.close()
