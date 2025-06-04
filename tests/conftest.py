import sqlite3
import os
import pytest

from app import create_app
from config import Config
import database

@pytest.fixture
def app(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    Config.DATABASE = str(db_path)

    # patch database connection to use temporary path
    orig_connect = sqlite3.connect
    def connect_override(*args, **kwargs):
        return orig_connect(str(db_path))
    monkeypatch.setattr(database, 'sqlite3', sqlite3)
    monkeypatch.setattr(database.sqlite3, 'connect', connect_override)
    database.init_db()

    app = create_app()
    app.config.update({'TESTING': True, 'WTF_CSRF_ENABLED': False})
    yield app

@pytest.fixture
def client(app):
    return app.test_client()

