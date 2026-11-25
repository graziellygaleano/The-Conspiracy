"""Trata e padroniza a planilha de artigos científicos (CSV/JSON/JSONL)."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

# Permite rodar direto via `python artigos/tratar.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ARQUIVO_ARTIGOS, ARTIGOS_TRATADOS_CSV, criar_pastas
from posts.tratar import detectar_vacinas

# Nomes comuns de colunas em bases como PubMed, OpenAlex, Crossref, Scopus/Bibliometrix e Kaggle
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "doi": ("doi", "di", "article_doi", "pmid", "id"),
    "title": ("title", "ti", "titulo", "article_title", "paper_title", "name"),
    "publication_date": (
        "publication_date", "pub_date", "date", "published_at",
        "data_publicacao", "publish_time", "publication_year", "year", "py",
    ),
    "journal": ("journal", "so", "periodico", "journal_name", "venue", "source", "source title", "journal/book"),
    "authors": ("authors", "au", "autores", "author", "creators"),
    "abstract": ("abstract", "ab", "resumo", "summary", "description"),
    "keywords": ("keywords", "de", "author keywords", "palavras_chave", "mesh_terms", "tags", "topics"),
    "vaccine_mentioned": ("vaccine_mentioned", "vaccine", "vacina", "vaccines"),
    "efficacy_reported": ("efficacy_reported", "efficacy", "eficacia", "effectiveness"),
    "study_type": ("study_type", "dt", "document type", "tipo_estudo", "publication_type", "type"),
    "thematic_axis": ("thematic_axis", "eixo_tematico", "theme", "topic"),
}

EFFICACY_PCT_RE = re.compile(
    r"(?:efficacy|effectiveness|protection|efic[áa]cia)[^0-9.%]{0,35}(\d{1,2}(?:\.\d+)?|100(?:\.0+)?)\s*%",
    re.IGNORECASE,
)
GENERIC_PCT_RE = re.compile(r"(\d{2}(?:\.\d+)?)\s*%")

THEMATIC_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("efficacy_immunogenicity", re.compile(r"\b(?:efficacy|effectiveness|immunogenicity|neutralizing\s+antibod|protection|phase\s*3|booster)\b", re.IGNORECASE)),
    ("safety_adverse_events", re.compile(r"\b(?:safety|adverse\s+event|vaers|anaphylaxis|thrombocytopenia|myocarditis|reactogenicity|side\s+effect)\b", re.IGNORECASE)),
    ("variants", re.compile(r"\b(?:variant|delta|alpha|beta|gamma|omicron|b\.1\.617|b\.1\.1\.7|waning\s+immunity|escape)\b", re.IGNORECASE)),
    ("hesitancy_misinformation", re.compile(r"\b(?:hesitancy|misinformation|conspiracy|rumor|social\s+media|anti-?vax)\b", re.IGNORECASE)),
]


def _encontrar_coluna(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    lowered = {col.strip().lower(): col for col in columns}
    for alias in candidates:
        if alias in lowered:
            return lowered[alias]
    return None


def _converter_data(raw_value: Any) -> pd.Timestamp | None:
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
    return None if pd.isna(ts) else ts


def _extrair_eficacia(raw_value: Any, title: str, abstract: str) -> float | None:
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


def _inferir_eixo_tematico(raw_value: Any, title: str, abstract: str, keywords: str) -> str:
    if raw_value is not None and str(raw_value).strip() and str(raw_value).lower() != "nan":
        return str(raw_value).strip()[:120]
    combined = f"{title} {abstract} {keywords}"
    for axis, pattern in THEMATIC_RULES:
        if pattern.search(combined):
            return axis
    return "general_vaccine_research"


def _inferir_tipo_estudo(raw_value: Any, title: str, abstract: str) -> str:
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


def ler_planilha_artigos(input_path: Path) -> pd.DataFrame:
    if not input_path.exists():
        raise FileNotFoundError(
            f"Planilha de artigos não encontrada: {input_path}. "
            "Verifique ARQUIVO_ARTIGOS no .env ou coloque o arquivo na pasta indicada."
        )
    suffix = input_path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(input_path, low_memory=False)
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(input_path)
    if suffix == ".jsonl":
        return pd.read_json(input_path, lines=True)
    if suffix == ".json":
        return pd.read_json(input_path)
    raise ValueError(f"Formato não suportado ({suffix}). Use .csv, .xlsx, .xls, .json ou .jsonl.")


def normalizar_artigos(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    cols = list(df.columns)
    mapped = {target: _encontrar_coluna(cols, aliases) for target, aliases in COLUMN_ALIASES.items()}

    if not mapped["title"]:
        raise ValueError(f"Falta uma coluna de título (ex.: title, titulo). Encontradas: {cols}")
    if not mapped["publication_date"]:
        raise ValueError(f"Falta uma coluna de data (ex.: publication_date, date, year). Encontradas: {cols}")

    records: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        title = str(row[mapped["title"]]).strip() if pd.notna(row[mapped["title"]]) else ""
        if not title:
            continue

        pub_ts = _converter_data(row[mapped["publication_date"]])
        if pub_ts is None:
            continue

        raw_doi = row[mapped["doi"]] if mapped["doi"] else None
        doi = str(raw_doi).strip() if raw_doi is not None and pd.notna(raw_doi) and str(raw_doi).strip() else ""
        if not doi:
            digest = hashlib.sha256(f"{title}|{pub_ts.strftime('%Y-%m-%d')}".encode("utf-8")).hexdigest()[:16]
            doi = f"no-doi-{digest}"

        journal = str(row[mapped["journal"]]).strip()[:500] if mapped["journal"] and pd.notna(row[mapped["journal"]]) else None
        authors = str(row[mapped["authors"]]).strip() if mapped["authors"] and pd.notna(row[mapped["authors"]]) else None
        abstract = str(row[mapped["abstract"]]).strip() if mapped["abstract"] and pd.notna(row[mapped["abstract"]]) else ""
        keywords = str(row[mapped["keywords"]]).strip() if mapped["keywords"] and pd.notna(row[mapped["keywords"]]) else ""

        raw_vaccine = row[mapped["vaccine_mentioned"]] if mapped["vaccine_mentioned"] else None
        if raw_vaccine is not None and pd.notna(raw_vaccine) and str(raw_vaccine).strip():
            vaccine_mentioned = str(raw_vaccine).strip()[:255]
        else:
            detected = detectar_vacinas(f"{title} {abstract} {keywords}")
            vaccine_mentioned = "; ".join(detected)[:255] if detected else None

        raw_eff = row[mapped["efficacy_reported"]] if mapped["efficacy_reported"] else None
        raw_study = row[mapped["study_type"]] if mapped["study_type"] else None
        raw_axis = row[mapped["thematic_axis"]] if mapped["thematic_axis"] else None

        records.append({
            "doi": doi[:255],
            "title": title[:1000],
            "publication_date": pub_ts.strftime("%Y-%m-%d"),
            "publication_month": pub_ts.strftime("%Y-%m"),
            "journal": journal,
            "authors": authors,
            "abstract": abstract or None,
            "keywords": keywords or None,
            "vaccine_mentioned": vaccine_mentioned,
            "efficacy_reported": _extrair_eficacia(raw_eff, title, abstract),
            "study_type": _inferir_tipo_estudo(raw_study, title, abstract),
            "thematic_axis": _inferir_eixo_tematico(raw_axis, title, abstract, keywords),
            "source_file": source_name[:255],
        })

    normalized = pd.DataFrame(records)
    if not normalized.empty:
        normalized = normalized.drop_duplicates(subset=["doi"]).reset_index(drop=True)
    return normalized


def tratar_artigos(
    input_path: Path = ARQUIVO_ARTIGOS,
    output_csv: Path = ARTIGOS_TRATADOS_CSV,
) -> dict[str, Any]:
    """Lê a planilha de artigos, padroniza colunas e salva o CSV tratado."""
    criar_pastas()
    raw_df = ler_planilha_artigos(input_path)
    norm_df = normalizar_artigos(raw_df, source_name=input_path.name)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    norm_df.to_csv(output_csv, index=False, encoding="utf-8-sig")

    return {
        "input_file": str(input_path),
        "output_csv": str(output_csv),
        "raw_rows": len(raw_df),
        "normalized_rows": len(norm_df),
        "columns": list(norm_df.columns),
        "sample_records": norm_df.head(2).to_dict(orient="records"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Trata a planilha de artigos científicos e salva CSV padronizado.")
    parser.add_argument("--input", type=Path, default=ARQUIVO_ARTIGOS, help="Planilha de entrada (padrão: ARQUIVO_ARTIGOS do .env).")
    parser.add_argument("--output", type=Path, default=ARTIGOS_TRATADOS_CSV, help="CSV tratado de saída.")
    args = parser.parse_args()

    resumo = tratar_artigos(input_path=args.input, output_csv=args.output)
    print(json.dumps(resumo, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
