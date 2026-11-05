"""The approved repair must touch only the three known unit errors."""
from agro_marketplace import initialize_marketplace
from test_agro_postgres import application, live


def test_rice_repair_is_scoped_preserves_data_and_is_idempotent(live):
    a, _ = live
    with a.get_db() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO website_service_requests
            (reference,service_key,full_name,phone,payload)
            VALUES ('IBR-SR-2026-0011','AGRICULTURE','Test seller','0000000000',
                    '{"quantity":"5000","variety_grade":"White/Brown"}') RETURNING id""")
        request_id = cur.fetchone()[0]
        for listing_id, name, price, unit in (
            (436, 'White rice', 5000, 'Kilograms'),
            (437, 'Brown rice', 7000, '5'),
            (438, 'Other rice', 7000, '5'),
        ):
            cur.execute("""INSERT INTO agro_marketplace_listings
                (id,seller_name,seller_phone,commodity,variety_grade,quantity,
                 quantity_unit,price_mwk,price_unit,location,status)
                VALUES (%s,'Test seller','0000000000','Rice',%s,1000,%s,%s,'1','Lilongwe','APPROVED')""",
                (listing_id, name, unit, price))
            cur.execute("""INSERT INTO agro_marketplace_listing_sources
                (listing_id,source_request_id,variant_key) VALUES (%s,%s,%s)""",
                (listing_id, request_id, name.lower()))
        cur.execute('SELECT * FROM website_service_requests ORDER BY id')
        requests_before = cur.fetchall()
        cur.execute('SELECT * FROM agro_marketplace_listings WHERE id NOT IN (436,437) ORDER BY id')
        others_before = cur.fetchall()

    initialize_marketplace(a.get_db)
    with a.get_db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT id,quantity,quantity_unit,price_mwk,price_unit,status
            FROM agro_marketplace_listings WHERE id IN (436,437) ORDER BY id""")
        assert cur.fetchall() == [
            (436,1000,'Kilograms',5000,'kg','APPROVED'),
            (437,1000,'kg',7000,'kg','APPROVED'),
        ]
        cur.execute('SELECT * FROM website_service_requests ORDER BY id')
        assert cur.fetchall() == requests_before
        cur.execute('SELECT * FROM agro_marketplace_listings WHERE id NOT IN (436,437) ORDER BY id')
        assert cur.fetchall() == others_before
        cur.execute('SELECT * FROM agro_marketplace_listings ORDER BY id')
        after_once = cur.fetchall()

    initialize_marketplace(a.get_db)
    with a.get_db() as conn, conn.cursor() as cur:
        cur.execute('SELECT * FROM agro_marketplace_listings ORDER BY id')
        assert cur.fetchall() == after_once
        # A later stock change is outside this approved repair's scope.
        cur.execute("UPDATE agro_marketplace_listings SET quantity=1001,price_unit='1' WHERE id=436")
    initialize_marketplace(a.get_db)
    with a.get_db() as conn, conn.cursor() as cur:
        cur.execute('SELECT quantity,price_unit FROM agro_marketplace_listings WHERE id=436')
        assert cur.fetchone() == (1001,'1')
