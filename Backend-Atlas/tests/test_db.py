# tests/test_db_connection.py

import os
import pytest
from unittest.mock import patch, MagicMock
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.dev")

from app.db import get_db_connection 

def test_get_db_connection_uses_env_variable():
    DATABASE_URL = os.getenv("DATABASE_URL")
    assert DATABASE_URL is not None, "DATABASE_URL must not be None"

    with patch("app.db.psycopg.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        conn = get_db_connection()

        mock_connect.assert_called_once_with(DATABASE_URL)
        assert conn == mock_conn
