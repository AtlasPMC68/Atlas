import os
import pytest
from unittest.mock import patch, MagicMock
from dotenv import load_dotenv

from app.db import get_db_connection

def test_get_db_connection_uses_env_variable():
    load_dotenv(dotenv_path=".env.dev")

    DATABASE_URL = os.getenv("DATABASE_URL")
    with patch("app.db.psycopg2.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        conn = get_db_connection()

        mock_connect.assert_called_once_with(DATABASE_URL)
        assert conn == mock_conn
