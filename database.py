# database.py
# ---------------------------------------------------------------
# Reusable MySQL connection helper. Every part of the application
# that needs to talk to MySQL should import get_db_connection()
# from this module instead of creating its own connection.
# ---------------------------------------------------------------

import mysql.connector
from mysql.connector import Error
from config import DB_CONFIG


def get_db_connection():
    """
    Create and return a new MySQL database connection using the
    settings defined in config.py.

    Raises:
        mysql.connector.Error: if the connection cannot be established.
    """
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as err:
        # Re-raise so the caller (route handler) can decide how to
        # respond to the user without exposing raw DB internals.
        raise err
