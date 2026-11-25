"""Configurações centralizadas e carregamento de variáveis de ambiente."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

RAW_TWEETS_CSV = PROJECT_ROOT / "BaseTweets" / "vaccination_all_tweets.csv"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
SAMPLE_DIR = PROJECT_ROOT / "data" / "sample"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
FIGURES_DIR = OUTPUTS_DIR / "figures"
TABLES_DIR = OUTPUTS_DIR / "tables"
SQL_SCHEMA_PATH = PROJECT_ROOT / "sql" / "schema.sql"

PROCESSED_TWEETS_JSON = PROCESSED_DIR / "conspiracy_tweets.json"
EXTRACTION_STATS_JSON = PROCESSED_DIR / "extraction_stats.json"
ANALYSIS_DIR = OUTPUTS_DIR / "analysis"


@dataclass(frozen=True)
class MySQLConfig:
    """Parâmetros de conexão com o banco relacional MySQL."""

    host: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    port: int = int(os.getenv("MYSQL_PORT", "3306"))
    user: str = os.getenv("MYSQL_USER", "root")
    password: str = os.getenv("MYSQL_PASSWORD", "")
    database: str = os.getenv("MYSQL_DATABASE", "conspiracy_db")


@dataclass(frozen=True)
class MongoConfig:
    """Parâmetros de conexão com o banco NoSQL MongoDB."""

    uri: str = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/")
    database: str = os.getenv("MONGO_DATABASE", "conspiracy_db")
    collection: str = os.getenv("MONGO_COLLECTION", "conspiracy_tweets")


def ensure_project_dirs() -> None:
    """Garante que os diretórios de saída do pipeline existam."""
    for directory in (PROCESSED_DIR, SAMPLE_DIR, OUTPUTS_DIR, FIGURES_DIR, TABLES_DIR):
        directory.mkdir(parents=True, exist_ok=True)
