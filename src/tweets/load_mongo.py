"""Carga dos tweets conspiracionistas filtrados para o MongoDB (pymongo + suporte a mongoimport)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pymongo import ASCENDING, DESCENDING, MongoClient, UpdateOne

from src.config import PROCESSED_TWEETS_JSON, MongoConfig


def ensure_mongo_indexes(collection: Any) -> None:
    """Cria índices para consultas temporais, temáticas e de engajamento no MongoDB."""
    collection.create_index([("tweet_id", ASCENDING)], unique=True, name="uq_tweet_id")
    collection.create_index([("year_month", ASCENDING)], name="idx_year_month")
    collection.create_index([("date_day", ASCENDING)], name="idx_date_day")
    collection.create_index([("primary_category", ASCENDING)], name="idx_primary_category")
    collection.create_index([("conspiracy_categories", ASCENDING)], name="idx_categories")
    collection.create_index([("hashtags", ASCENDING)], name="idx_hashtags")
    collection.create_index([("engagement_score", DESCENDING)], name="idx_engagement_desc")


def load_tweets_to_mongo(
    json_path: Path = PROCESSED_TWEETS_JSON,
    mongo_cfg: MongoConfig | None = None,
    replace_collection: bool = False,
) -> dict[str, Any]:
    """Carrega os documentos JSON de tweets conspiracionistas no MongoDB via upsert."""
    if not json_path.exists():
        raise FileNotFoundError(
            f"Arquivo JSON processado não encontrado: {json_path}. "
            "Execute `python -m src.tweets.extract_tweets` primeiro."
        )

    with json_path.open("r", encoding="utf-8") as fh:
        documents: list[dict[str, Any]] = json.load(fh)

    cfg = mongo_cfg or MongoConfig()
    client: MongoClient[dict[str, Any]] = MongoClient(cfg.uri, serverSelectionTimeoutMS=5000)
    try:
        # Verifica conectividade real antes de gravar
        client.admin.command("ping")
        db = client[cfg.database]
        collection = db[cfg.collection]

        if replace_collection:
            collection.delete_many({})

        ensure_mongo_indexes(collection)

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
            UpdateOne(
                {"tweet_id": str(doc["tweet_id"])},
                {"$set": doc},
                upsert=True,
            )
            for doc in documents
        ]
        result = collection.bulk_write(operations, ordered=False)
        total_docs = collection.count_documents({})

        return {
            "database": cfg.database,
            "collection": cfg.collection,
            "input_documents": len(documents),
            "upserted": result.upserted_count,
            "modified": result.modified_count,
            "matched": result.matched_count,
            "total_in_collection": total_docs,
            "mongoimport_equivalent": (
                f'mongoimport --uri "{cfg.uri}" --db {cfg.database} '
                f'--collection {cfg.collection} --jsonArray --file "{json_path}"'
            ),
        }
    finally:
        client.close()


def main() -> None:
    """Ponto de entrada CLI para carga dos tweets no MongoDB."""
    parser = argparse.ArgumentParser(description="Carrega tweets conspiracionistas no MongoDB.")
    parser.add_argument("--input", type=Path, default=PROCESSED_TWEETS_JSON, help="JSON de tweets.")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Limpa a coleção antes de inserir os documentos.",
    )
    args = parser.parse_args()

    summary = load_tweets_to_mongo(json_path=args.input, replace_collection=args.replace)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
