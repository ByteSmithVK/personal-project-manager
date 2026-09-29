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
