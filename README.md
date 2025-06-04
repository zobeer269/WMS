
This warehouse management system (WMS) is a Flask application backed by a SQLite database.

## Requirements

- **Python**: tested with Python 3.13
- **Packages**:
  - [Flask](https://flask.palletsprojects.com/)
  - [pandas](https://pandas.pydata.org/)
  - [qrcode](https://pypi.org/project/qrcode/)
  - Any additional dependencies used by the standard library such as `sqlite3` and `hashlib`.

Install the packages with:

```bash
pip install Flask pandas qrcode
```

## Database setup

Initialize the SQLite database by running [`database.py`](database.py):

```bash
python database.py
```

This script creates the `inventory.db` file with all required tables if they do not already exist.

## Running the application

After the database is initialized, start the Flask development server with:

```bash
python run.py
```

You should then be able to access the application at `http://localhost:5000/`.

## Configuration and environment variables

The application uses a secret key for session management. Set the `SECRET_KEY` environment variable before running in production or edit `config.py` to provide your own key.

Additional configuration values can also be overridden via environment variables as defined in [`config.py`](config.py).
