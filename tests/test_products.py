import sqlite3
from config import Config


def setup_inventory():
    conn = sqlite3.connect(Config.DATABASE)
    cur = conn.cursor()
    cur.execute("INSERT INTO racks (name) VALUES ('R1')")
    rack_id = cur.lastrowid
    cur.execute("INSERT INTO bins (name, rack_id) VALUES ('B1', ?)", (rack_id,))
    bin_id = cur.lastrowid
    cur.execute("INSERT INTO categories (name) VALUES ('عام')")
    category_id = cur.lastrowid
    conn.commit()
    conn.close()
    return rack_id, bin_id, category_id


def test_add_and_update_product(client):
    rack_id, bin_id, category_id = setup_inventory()

    client.post('/auth/login', data={'username': 'admin', 'password': 'adminpass'})

    # Add product
    resp = client.post('/products/add', data={
        'product_code': 'P001',
        'rack_id': str(rack_id),
        'bin_id': str(bin_id),
        'quantity': '5',
        'category_id': str(category_id)
    }, follow_redirects=True)
    assert resp.status_code == 200

    conn = sqlite3.connect(Config.DATABASE)
    product = conn.execute('SELECT id, quantity FROM products WHERE product_code=?', ('P001',)).fetchone()
    conn.close()
    assert product is not None
    product_id = product[0]

    # Increase quantity
    resp = client.post(f'/products/update_quantity/{product_id}', data={
        'action': 'increase',
        'change_amount': '3'
    }, follow_redirects=True)
    assert resp.status_code == 200
    conn = sqlite3.connect(Config.DATABASE)
    new_qty = conn.execute('SELECT quantity FROM products WHERE id=?', (product_id,)).fetchone()[0]
    conn.close()
    assert new_qty == 8
