"""Schema bootstrap e loader configurável de metadados científicos para o MySQL."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import mysql.connector
import pandas as pd

from src.config import SQL_SCHEMA_PATH, MySQLConfig
from src.extract_tweets import detect_vaccines

# Mapeamento flexível de nomes de colunas comuns em bases PubMed / OpenAlex / Crossref / Kaggle
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "doi": ("doi", "article_doi", "pmid", "id"),
    "title": ("title", "titulo", "article_title", "paper_title", "name"),
    "publication_date": (
        "publication_date",
        "pub_date",
        "date",
        "published_at",
        "data_publicacao",
        "publish_time",
        "publication_year",
        "year",
    ),
    "journal": ("journal", "periodico", "journal_name", "venue", "source", "journal/book"),
    "authors": ("authors", "autores", "author", "creators"),
    "abstract": ("abstract", "resumo", "summary", "description"),
    "keywords": ("keywords", "palavras_chave", "mesh_terms", "tags", "topics"),
    "vaccine_mentioned": ("vaccine_mentioned", "vaccine", "vacina", "vaccines"),
    "efficacy_reported": ("efficacy_reported", "efficacy", "eficacia", "effectiveness"),
    "study_type": ("study_type", "tipo_estudo", "publication_type", "type"),
    "thematic_axis": ("thematic_axis", "eixo_tematico", "theme", "topic"),
}

EFFICACY_PCT_RE = re.compile(
    r"(?:efficacy|effectiveness|protection|efic[áa]cia)[^0-9.%]{0,35}(\d{1,2}(?:\.\d+)?|100(?:\.0+)?)\s*%",
    re.IGNORECASE,
)
GENERIC_PCT_RE = re.compile(r"(\d{2}(?:\.\d+)?)\s*%")

THEMATIC_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "efficacy_immunogenicity",
        re.compile(
            r"\b(?:efficacy|effectiveness|immunogenicity|neutralizing\s+antibod|protection|phase\s*3|booster)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "safety_adverse_events",
        re.compile(
            r"\b(?:safety|adverse\s+event|vaers|anaphylaxis|thrombocytopenia|myocarditis|reactogenicity|side\s+effect)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "variants",
        re.compile(
            r"\b(?:variant|delta|alpha|beta|gamma|omicron|b\.1\.617|b\.1\.1\.7|waning\s+immunity|escape)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "hesitancy_misinformation",
        re.compile(
            r"\b(?:hesitancy|misinformation|conspiracy|rumor|social\s+media|anti-?vax)\b",
            re.IGNORECASE,
        ),
    ),
]


def _pick_column(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    lowered = {col.strip().lower(): col for col in columns}
    for alias in candidates:
        if alias in lowered:
            return lowered[alias]
    return None


def _parse_publication_date(raw_value: Any) -> pd.Timestamp | None:
    if raw_value is None or (isinstance(raw_value, float) and pd.isna(raw_value)):
        return None
    text = str(raw_value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{4}", text):
        text = f"{text}-01-01"
    elif re.fullmatch(r"\d{4}-\d{2}", text):
        text = f"{text}-01"
    ts = pd.to_datetime(text, errors="coerce")
    if pd.isna(ts):
        return None
    return ts


def _extract_efficacy(raw_value: Any, title: str, abstract: str) -> float | None:
    if raw_value is not None and not (isinstance(raw_value, float) and pd.isna(raw_value)):
        cleaned = str(raw_value).replace("%", "").replace(",", ".").strip()
        if cleaned:
            try:
                val = float(cleaned)
                if 0.0 <= val <= 100.0:
                    return round(val, 2)
            except ValueError:
                pass

    combined = f"{title} {abstract}"
    match = EFFICACY_PCT_RE.search(combined)
    if match:
        val = float(match.group(1))
        if 0.0 <= val <= 100.0:
            return round(val, 2)

    if "efficacy" in combined.lower() or "effectiveness" in combined.lower():
        generic = GENERIC_PCT_RE.search(combined)
        if generic:
            val = float(generic.group(1))
            if 0.0 <= val <= 100.0:
                return round(val, 2)
    return None


def _infer_thematic_axis(raw_value: Any, title: str, abstract: str, keywords: str) -> str:
    if raw_value is not None and str(raw_value).strip() and str(raw_value).lower() != "nan":
        return str(raw_value).strip()[:120]
    combined = f"{title} {abstract} {keywords}"
    for axis, pattern in THEMATIC_RULES:
        if pattern.search(combined):
            return axis
    return "general_vaccine_research"


def _infer_study_type(raw_value: Any, title: str, abstract: str) -> str:
    if raw_value is not None and str(raw_value).strip() and str(raw_value).lower() != "nan":
        return str(raw_value).strip()[:120]
    combined = f"{title} {abstract}".lower()
    if any(k in combined for k in ("randomized", "phase 3", "phase iii", "placebo-controlled", "clinical trial")):
        return "clinical_trial"
    if any(k in combined for k in ("meta-analysis", "systematic review")):
        return "meta_analysis"
    if any(k in combined for k in ("cohort", "nationwide", "real-world", "vaers", "observational", "retrospective")):
        return "observational"
    if "review" in combined:
        return "review"
    return "scientific_article"


def read_articles_file(input_path: Path) -> pd.DataFrame:
    """Lê arquivos CSV, JSON ou JSONL de metadados científicos com Pandas."""
    if not input_path.exists():
        raise FileNotFoundError(f"Arquivo de artigos não encontrado: {input_path}")

    suffix = input_path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(input_path, low_memory=False)
    if suffix == ".jsonl":
        return pd.read_json(input_path, lines=True)
    if suffix == ".json":
        return pd.read_json(input_path)
    raise ValueError(f"Formato não suportado ({suffix}). Use .csv, .json ou .jsonl.")


def normalize_articles_dataframe(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    """Padroniza colunas e deriva campos analíticos (mês, vacina, eficácia, eixo temático)."""
    if df.empty:
        return pd.DataFrame()

    cols = list(df.columns)
    mapped: dict[str, str | None] = {
        target: _pick_column(cols, aliases) for target, aliases in COLUMN_ALIASES.items()
    }

    if not mapped["title"]:
        raise ValueError(
            "O arquivo de entrada precisa ter uma coluna de título "
            f"(ex.: title, titulo, article_title). Colunas encontradas: {cols}"
        )
    if not mapped["publication_date"]:
        raise ValueError(
            "O arquivo de entrada precisa ter uma coluna de data de publicação "
            f"(ex.: publication_date, date, pub_date, year). Colunas encontradas: {cols}"
        )

    records: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        title = str(row[mapped["title"]]).strip() if pd.notna(row[mapped["title"]]) else ""
        if not title:
            continue

        pub_ts = _parse_publication_date(row[mapped["publication_date"]])
        if pub_ts is None:
            continue

        raw_doi = row[mapped["doi"]] if mapped["doi"] else None
        doi = str(raw_doi).strip() if raw_doi is not None and pd.notna(raw_doi) and str(raw_doi).strip() else ""
        if not doi:
            digest = hashlib.sha256(f"{title}|{pub_ts.strftime('%Y-%m-%d')}".encode("utf-8")).hexdigest()[:16]
            doi = f"no-doi-{digest}"

        journal = (
            str(row[mapped["journal"]]).strip()[:500]
            if mapped["journal"] and pd.notna(row[mapped["journal"]])
            else None
        )
        authors = (
            str(row[mapped["authors"]]).strip()
            if mapped["authors"] and pd.notna(row[mapped["authors"]])
            else None
        )
        abstract = (
            str(row[mapped["abstract"]]).strip()
            if mapped["abstract"] and pd.notna(row[mapped["abstract"]])
            else ""
        )
        keywords = (
            str(row[mapped["keywords"]]).strip()
            if mapped["keywords"] and pd.notna(row[mapped["keywords"]])
            else ""
        )

        raw_vaccine = row[mapped["vaccine_mentioned"]] if mapped["vaccine_mentioned"] else None
        if raw_vaccine is not None and pd.notna(raw_vaccine) and str(raw_vaccine).strip():
            vaccine_mentioned = str(raw_vaccine).strip()[:255]
        else:
            detected = detect_vaccines(f"{title} {abstract} {keywords}")
            vaccine_mentioned = "; ".join(detected)[:255] if detected else None

        raw_eff = row[mapped["efficacy_reported"]] if mapped["efficacy_reported"] else None
        efficacy = _extract_efficacy(raw_eff, title, abstract)

        raw_study = row[mapped["study_type"]] if mapped["study_type"] else None
        study_type = _infer_study_type(raw_study, title, abstract)

        raw_axis = row[mapped["thematic_axis"]] if mapped["thematic_axis"] else None
        thematic_axis = _infer_thematic_axis(raw_axis, title, abstract, keywords)

        records.append(
            {
                "doi": doi[:255],
                "title": title[:1000],
                "publication_date": pub_ts.strftime("%Y-%m-%d"),
                "publication_month": pub_ts.strftime("%Y-%m"),
                "journal": journal,
                "authors": authors,
                "abstract": abstract or None,
                "keywords": keywords or None,
                "vaccine_mentioned": vaccine_mentioned,
                "efficacy_reported": efficacy,
                "study_type": study_type,
                "thematic_axis": thematic_axis,
                "source_file": source_name[:255],
            }
        )

    normalized = pd.DataFrame(records)
    if not normalized.empty:
        normalized = normalized.drop_duplicates(subset=["doi"]).reset_index(drop=True)
    return normalized


def apply_mysql_schema(cfg: MySQLConfig, schema_path: Path = SQL_SCHEMA_PATH) -> None:
    """Executa o arquivo schema.sql para criar o banco, tabela, índices e view."""
    sql_text = schema_path.read_text(encoding="utf-8")
    # Substitui o nome padrão caso MYSQL_DATABASE seja customizado
    if cfg.database and cfg.database != "conspiracy_db":
        sql_text = sql_text.replace("conspiracy_db", cfg.database)

    conn = mysql.connector.connect(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        connection_timeout=5,
    )
    try:
        cursor = conn.cursor()
        for statement in [stmt.strip() for stmt in sql_text.split(";") if stmt.strip()]:
            cursor.execute(statement)
        conn.commit()
    finally:
        conn.close()


def load_articles_to_mysql(
    input_path: Path,
    mysql_cfg: MySQLConfig | None = None,
    init_schema: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Lê, normaliza e carrega metadados de artigos científicos no MySQL."""
    cfg = mysql_cfg or MySQLConfig()
    raw_df = read_articles_file(input_path)
    norm_df = normalize_articles_dataframe(raw_df, source_name=input_path.name)

    if dry_run:
        return {
            "dry_run": True,
            "input_file": str(input_path),
            "raw_rows": len(raw_df),
            "normalized_rows": len(norm_df),
            "preview_columns": list(norm_df.columns),
            "sample_records": norm_df.head(3).to_dict(orient="records"),
        }

    if init_schema:
        apply_mysql_schema(cfg)

    conn = mysql.connector.connect(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        database=cfg.database,
        connection_timeout=5,
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
        rows_to_insert = [
            tuple(None if pd.isna(v) else v for v in rec)
            for rec in norm_df[
                [
                    "doi",
                    "title",
                    "publication_date",
                    "publication_month",
                    "journal",
                    "authors",
                    "abstract",
                    "keywords",
                    "vaccine_mentioned",
                    "efficacy_reported",
                    "study_type",
                    "thematic_axis",
                    "source_file",
                ]
            ].itertuples(index=False, name=None)
        ]
        if rows_to_insert:
            cursor.executemany(upsert_sql, rows_to_insert)
            conn.commit()
        cursor.execute("SELECT COUNT(*) FROM scientific_articles")
        total_in_table = int(cursor.fetchone()[0])

        return {
            "dry_run": False,
            "database": cfg.database,
            "input_file": str(input_path),
            "raw_rows": len(raw_df),
            "loaded_rows": len(rows_to_insert),
            "total_in_table": total_in_table,
        }
    finally:
        conn.close()


def main() -> None:
    """Ponto de entrada CLI para criação do schema e carga de artigos no MySQL."""
    parser = argparse.ArgumentParser(
        description="Aplica o schema MySQL e carrega metadados de artigos científicos (CSV/JSON)."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Caminho do arquivo CSV/JSON/JSONL com metadados dos artigos.",
    )
    parser.add_argument(
        "--init-schema-only",
        action="store_true",
        help="Apenas cria banco, tabela, índices e view definidos em sql/schema.sql.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida e normaliza o arquivo com Pandas sem conectar ao MySQL.",
    )
    args = parser.parse_args()

    cfg = MySQLConfig()
    if args.init_schema_only:
        apply_mysql_schema(cfg)
        print(json.dumps({"schema_applied": True, "database": cfg.database}, ensure_ascii=False, indent=2))
        return

    if args.input is None:
        parser.error("Informe --input <arquivo.csv|json|jsonl> ou use --init-schema-only.")

    result = load_articles_to_mysql(input_path=args.input, mysql_cfg=cfg, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
