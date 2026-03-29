import os
import psycopg2
from typing import Optional, Tuple
from core.logger import get_logger

logger = get_logger("DB")

class PostgresClient:
    _instance = None

    def __init__(self):
        if PostgresClient._instance is not None:
            raise Exception("PostgresClient is a singleton. Use get_instance().")
        self.connection = None
        self._connect()

    def _connect(self):
        try:
            self.connection = psycopg2.connect(
                host=os.environ.get("POSTGRES_HOST", "localhost"),
                database=os.environ.get("POSTGRES_DB", "postgres"),
                user=os.environ.get("POSTGRES_USER", "postgres"),
                password=os.environ.get("POSTGRES_PASSWORD", "1234"),
                connect_timeout=2
            )
            self._init_schema()
            logger.info("Connected to PostgreSQL successfully.")
        except Exception as e:
            logger.error(f"PostgreSQL connection failed: {e}")
            self.connection = None

    def _init_schema(self):
        if not self.connection:
            return
            
        schema = """
        CREATE TABLE IF NOT EXISTS queries (
            id UUID PRIMARY KEY,
            query_text TEXT,
            timestamp TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS metrics (
            query_id UUID REFERENCES queries(id),
            confidence FLOAT,
            retry_count INT,
            hallucination_risk FLOAT,
            verdict TEXT
        );

        CREATE TABLE IF NOT EXISTS strategies (
            query_id UUID REFERENCES queries(id),
            rewrite_strategy TEXT,
            depth_k INT,
            routing TEXT
        );
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(schema)
            self.connection.commit()
            logger.info("Initialized PostgreSQL schema.")
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL schema: {e}")
            self.connection.rollback()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = PostgresClient()
        return cls._instance

    def execute_query(self, query: str, params: Optional[Tuple] = None) -> None:
        if not self.connection:
            raise Exception("No active PostgreSQL connection.")
            
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, params)
            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            raise e

def get_db_client() -> PostgresClient:
    return PostgresClient.get_instance()
