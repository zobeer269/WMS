import sqlite3
from config import Config


def test_login_logout(client):
    # Successful login
    resp = client.post('/auth/login', data={'username': 'admin', 'password': 'adminpass'}, follow_redirects=True)
    assert resp.status_code == 200
    with client.session_transaction() as sess:
        assert sess.get('user_id') is not None

    # Logout
    resp = client.get('/auth/logout', follow_redirects=True)
    assert resp.status_code == 200
    with client.session_transaction() as sess:
        assert 'user_id' not in sess
