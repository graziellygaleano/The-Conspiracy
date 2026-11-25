"""Cria o schema e envia os artigos tratados (CSV) para o MySQL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

# Permite rodar direto via `python artigos/enviar_mysql.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ARTIGOS_TRATADOS_CSV, SQL_SCHEMA_PATH, MySQLConfig

COLUMNS = [
    "doi", "title", "publication_date", "publication_month", "journal",
    "authors", "abstract", "keywords", "vaccine_mentioned",
    "efficacy_reported", "study_type", "thematic_axis", "source_file",
]


def aplicar_schema(cfg: MySQLConfig, schema_path: Path = SQL_SCHEMA_PATH) -> None:
    """Executa sql/schema.sql para criar banco, tabela, índices e view."""
    import mysql.connector

    sql_text = schema_path.read_text(encoding="utf-8")
    if cfg.database and cfg.database != "conspiracy_db":
        sql_text = sql_text.replace("conspiracy_db", cfg.database)

    conn = mysql.connector.connect(
        host=cfg.host, port=cfg.port, user=cfg.user, password=cfg.password, connection_timeout=5,
    )
    try:
        cursor = conn.cursor()
        for statement in [stmt.strip() for stmt in sql_text.split(";") if stmt.strip()]:
            cursor.execute(statement)
        conn.commit()
    finally:
        conn.close()


def enviar_para_mysql(
    csv_path: Path = ARTIGOS_TRATADOS_CSV,
    mysql_cfg: MySQLConfig | None = None,
    init_schema: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Lê o CSV de artigos tratados e faz upsert na tabela scientific_articles."""
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Arquivo de artigos tratados não encontrado: {csv_path}. "
            "Execute `python artigos/tratar.py` primeiro."
        )

    df = pd.read_csv(csv_path, low_memory=False)
    cfg = mysql_cfg or MySQLConfig()

    if dry_run:
        return {
            "dry_run": True,
            "database": cfg.database,
            "input_csv": str(csv_path),
            "rows_ready": len(df),
            "columns": list(df.columns),
            "sample_records": df.head(2).to_dict(orient="records"),
        }

    import mysql.connector

    if init_schema:
        aplicar_schema(cfg)

    conn = mysql.connector.connect(
        host=cfg.host, port=cfg.port, user=cfg.user,
        password=cfg.password, database=cfg.database, connection_timeout=5,
    )
    upsert_sql = """
        INSERT INTO scientific_articles (
            doi, title, publication_date, publication_month, journal,
            authors, abstract, keywords, vaccine_mentioned,
            efficacy_reported, study_type, thematic_axis, source_file
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            title = VALUES(title),
            publication_date = VALUES(publication_date),
            publication_month = VALUES(publication_month),
            journal = VALUES(journal),
            authors = VALUES(authors),
            abstract = VALUES(abstract),
            keywords = VALUES(keywords),
            vaccine_mentioned = VALUES(vaccine_mentioned),
            efficacy_reported = VALUES(efficacy_reported),
            study_type = VALUES(study_type),
            thematic_axis = VALUES(thematic_axis),
            source_file = VALUES(source_file)
    """
    try:
        cursor = conn.cursor()
        rows = [
            tuple(None if pd.isna(v) else v for v in rec)
            for rec in df[COLUMNS].itertuples(index=False, name=None)
        ]
        if rows:
            cursor.executemany(upsert_sql, rows)
            conn.commit()
        cursor.execute("SELECT COUNT(*) FROM scientific_articles")
        total = int(cursor.fetchone()[0])
        return {
            "dry_run": False,
            "database": cfg.database,
            "input_csv": str(csv_path),
            "loaded_rows": len(rows),
            "total_in_table": total,
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Envia os artigos tratados para o MySQL.")
    parser.add_argument("--input", type=Path, default=ARTIGOS_TRATADOS_CSV, help="CSV de artigos tratados.")
    parser.add_argument("--init-schema-only", action="store_true", help="Apenas aplica sql/schema.sql.")
    parser.add_argument("--dry-run", action="store_true", help="Valida o CSV sem conectar ao MySQL.")
    args = parser.parse_args()

    cfg = MySQLConfig()
    if args.init_schema_only:
        aplicar_schema(cfg)
        print(json.dumps({"schema_applied": True, "database": cfg.database}, ensure_ascii=False, indent=2))
        return

    resumo = enviar_para_mysql(csv_path=args.input, mysql_cfg=cfg, dry_run=args.dry_run)
    print(json.dumps(resumo, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
