# config.py
# ---------------------------------------------------------------
# Configuration for the Personal Project Manager.
# All secrets are loaded from the .env file via python-dotenv.
# Never hardcode credentials here — edit .env instead.
# ---------------------------------------------------------------

import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "user":     os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "personal_project_manager"),
    "port":     int(os.getenv("DB_PORT", 3306)),
}

# Flask secret key — loaded from .env
SECRET_KEY = os.getenv("SECRET_KEY", "fallback-dev-key-change-in-production")

# Email / SMTP Configuration
MAIL_CONFIG = {
    "server":         os.getenv("MAIL_SERVER", ""),
    "port":           int(os.getenv("MAIL_PORT", 587)),
    "use_tls":        os.getenv("MAIL_USE_TLS", "true").lower() in ("true", "1", "yes"),
    "use_ssl":        os.getenv("MAIL_USE_SSL", "false").lower() in ("true", "1", "yes"),
    "username":       os.getenv("MAIL_USERNAME", ""),
    "password":       os.getenv("MAIL_PASSWORD", ""),
    "default_sender": os.getenv("MAIL_DEFAULT_SENDER", os.getenv("MAIL_USERNAME", "noreply@personalprojectmanager.local")),
}

