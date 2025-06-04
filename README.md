# WMS

## Configuration

- `SECRET_KEY` is used to sign Flask sessions. When `FLASK_ENV` is set to
  `production` the application requires this variable to be defined. If it is
  missing, a `RuntimeError` will be raised during startup. In development, a
  fallback key is used.

