"""Envia os posts tratados (JSON) para o MongoDB via upsert."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Permite rodar direto via `python posts/enviar_mongo.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import POSTS_TRATADOS_JSON, MongoConfig


def enviar_para_mongo(
    json_path: Path = POSTS_TRATADOS_JSON,
    mongo_cfg: MongoConfig | None = None,
    replace_collection: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Lê o JSON tratado e carrega no MongoDB (ou apenas valida se dry_run=True)."""
    if not json_path.exists():
        raise FileNotFoundError(
            f"Arquivo de posts tratados não encontrado: {json_path}. "
            "Execute `python posts/tratar.py` primeiro."
        )

    documents: list[dict[str, Any]] = json.loads(json_path.read_text(encoding="utf-8"))
    cfg = mongo_cfg or MongoConfig()

    if dry_run:
        return {
            "dry_run": True,
            "database": cfg.database,
            "collection": cfg.collection,
            "input_json": str(json_path),
            "documents_ready": len(documents),
            "sample_records": documents[:2],
        }

    from pymongo import ASCENDING, DESCENDING, MongoClient, UpdateOne

    client: MongoClient[dict[str, Any]] = MongoClient(cfg.uri, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
        collection = client[cfg.database][cfg.collection]

        if replace_collection:
            collection.delete_many({})

        collection.create_index([("tweet_id", ASCENDING)], unique=True, name="uq_tweet_id")
        collection.create_index([("year_month", ASCENDING)], name="idx_year_month")
        collection.create_index([("primary_category", ASCENDING)], name="idx_primary_category")
        collection.create_index([("engagement_score", DESCENDING)], name="idx_engagement_desc")

        if not documents:
            return {
                "database": cfg.database,
                "collection": cfg.collection,
                "input_documents": 0,
                "upserted": 0,
                "modified": 0,
                "total_in_collection": collection.count_documents({}),
            }

        operations = [
            UpdateOne({"tweet_id": str(doc["tweet_id"])}, {"$set": doc}, upsert=True)
            for doc in documents
        ]
        result = collection.bulk_write(operations, ordered=False)
        return {
            "database": cfg.database,
            "collection": cfg.collection,
            "input_documents": len(documents),
            "upserted": result.upserted_count,
            "modified": result.modified_count,
            "total_in_collection": collection.count_documents({}),
        }
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Envia os posts tratados para o MongoDB.")
    parser.add_argument("--input", type=Path, default=POSTS_TRATADOS_JSON, help="JSON de posts tratados.")
    parser.add_argument("--replace", action="store_true", help="Limpa a coleção antes de inserir.")
    parser.add_argument("--dry-run", action="store_true", help="Valida o JSON sem conectar ao MongoDB.")
    args = parser.parse_args()

    resumo = enviar_para_mongo(
        json_path=args.input,
        replace_collection=args.replace,
        dry_run=args.dry_run,
    )
    print(json.dumps(resumo, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
