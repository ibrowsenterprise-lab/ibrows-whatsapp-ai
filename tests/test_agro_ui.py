from decimal import Decimal
import pytest
from test_marketplace import m, client

@pytest.mark.parametrize('quantity,unit,amount,noun,pack',[
    ('50.000','50 kg bags','50','bags','50 kg per bag'),
    ('1.000','90 kg bags','1','bag','90 kg per bag'),
    ('1.500','Tonnes','1.5','tonnes',''),
    ('1000','KG','1000','kg',''),
    ('3','Other bag size','3','bags',''),
])
def test_stock_and_package_are_separate(quantity,unit,amount,noun,pack):
    assert m.stock_summary(Decimal(quantity),unit)==dict(amount=amount,unit=noun,pack=pack)

def test_catalogue_clear_stock_and_no_duplicate_grade(client):
    c,db=client
    db.public_rows=[(7,'White maize','White',Decimal('50.000'),'50 kg bags',52000,'50 kg bag','Area 25 Sector 4, Lilongwe',None)]
    response=c.get('/agriculture/marketplace')
    assert response.status_code==200
    assert b'50 bags available' in response.data and b'50 kg per bag' in response.data
    assert b'50 50 kg bags' not in response.data and b'Grade / variety: White' not in response.data
    assert b'per 50 kg bag' in response.data
