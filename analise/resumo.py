"""Junta os resumos de posts e artigos em um único arquivo (outputs/resumo_geral.json)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Permite rodar direto via `python analise/resumo.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ARTIGOS_STATS_JSON, OUTPUTS_DIR, POSTS_STATS_JSON, criar_pastas

ARQUIVO_RESUMO = OUTPUTS_DIR / "resumo_geral.json"


def ler_resumo(caminho: Path, comando: str) -> dict:
    if not caminho.exists():
        raise FileNotFoundError(f"Resumo não encontrado: {caminho}. Execute `{comando}` primeiro.")
    return json.loads(caminho.read_text(encoding="utf-8"))


def main() -> None:
    criar_pastas()
    resumo = {
        "posts": ler_resumo(POSTS_STATS_JSON, "python posts/tratar.py"),
        "artigos": ler_resumo(ARTIGOS_STATS_JSON, "python artigos/tratar.py"),
    }
    ARQUIVO_RESUMO.write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Resumo salvo em: {ARQUIVO_RESUMO}")


if __name__ == "__main__":
    main()
