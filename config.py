"""Configurações centralizadas do projeto (caminhos e conexão com os bancos)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

# --- Pastas de dados e saídas ---
DADOS_DIR = PROJECT_ROOT / "dados"
EXEMPLO_DIR = DADOS_DIR / "exemplo"
REAIS_DIR = DADOS_DIR / "reais"
TRATADOS_DIR = DADOS_DIR / "tratados"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
SQL_SCHEMA_PATH = PROJECT_ROOT / "sql" / "schema.sql"


def _resolver_caminho(env_var: str, default_relative: str) -> Path:
    raw = os.getenv(env_var, default_relative).strip() or default_relative
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


# --- Planilhas de entrada (configuráveis no .env) ---
ARQUIVO_POSTS = _resolver_caminho("ARQUIVO_POSTS", "dados/exemplo/posts_exemplo.csv")
ARQUIVO_ARTIGOS = _resolver_caminho("ARQUIVO_ARTIGOS", "dados/exemplo/artigos_exemplo.csv")

# --- Arquivos gerados após o tratamento ---
POSTS_TRATADOS_JSON = TRATADOS_DIR / "posts_tratados.json"
POSTS_STATS_JSON = TRATADOS_DIR / "posts_stats.json"
ARTIGOS_TRATADOS_CSV = TRATADOS_DIR / "artigos_tratados.csv"
ARTIGOS_STATS_JSON = TRATADOS_DIR / "artigos_stats.json"


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
    collection: str = os.getenv("MONGO_COLLECTION", "posts")


def criar_pastas() -> None:
    """Garante que as pastas de trabalho existam."""
    for pasta in (EXEMPLO_DIR, REAIS_DIR, TRATADOS_DIR, OUTPUTS_DIR):
        pasta.mkdir(parents=True, exist_ok=True)
