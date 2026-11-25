"""Limpeza one-off da exportação Bibliometrix para carga no MySQL."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.config import PROJECT_ROOT

COLUMNS = ["DI", "TI", "AU", "PY", "SO", "AB", "DE", "TC"]


def clean_bibliometrix(input_path: Path, output_path: Path) -> int:
    """Mantém apenas os campos úteis e normaliza ano/citações para inteiros."""
    if not input_path.exists():
        raise FileNotFoundError(f"Arquivo Bibliometrix não encontrado: {input_path}")
    frame = pd.read_csv(input_path, low_memory=False)
    cleaned = frame[[column for column in COLUMNS if column in frame.columns]].copy()
    if "PY" in cleaned:
        cleaned["PY"] = pd.to_numeric(cleaned["PY"], errors="coerce").fillna(0).astype(int)
    if "TC" in cleaned:
        cleaned["TC"] = pd.to_numeric(cleaned["TC"], errors="coerce").fillna(0).astype(int)
    if not ({"TI", "PY"} <= set(cleaned.columns)):
        raise ValueError("A exportação deve conter as colunas TI (título) e PY (ano).")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned.to_csv(output_path, index=False, encoding="utf-8")
    return len(cleaned)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera uma planilha enxuta a partir do Bibliometrix.")
    parser.add_argument("--input", type=Path, default=PROJECT_ROOT / "Bibliometrix-Export-File.csv")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "artigos_mysql.csv")
    args = parser.parse_args()
    count = clean_bibliometrix(args.input, args.output)
    print(f"Total de artigos prontos: {count}")


if __name__ == "__main__":
    main()
