"""Integra dados do MongoDB e MySQL e gera tabelas de análise com Pandas."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import mysql.connector
import pandas as pd
from pymongo import MongoClient

from src.config import (
    ANALYSIS_DIR,
    PROCESSED_TWEETS_JSON,
    MongoConfig,
    MySQLConfig,
    ensure_project_dirs,
)

TOKEN_RE = re.compile(r"(?u)\b[\w#'-]{3,}\b")
STOPWORDS = {
    "about", "after", "again", "against", "also", "been", "before", "being", "between",
    "both", "could", "covid", "covid19", "from", "have", "https", "into", "just",
    "more", "most", "other", "our", "out", "over", "same", "some", "such", "than",
    "that", "them", "then", "there", "these", "they", "this", "those", "their", "the",
    "with", "were", "what", "when", "where", "which", "while", "will", "would", "your",
}


def load_tweets_from_mongo(cfg: MongoConfig | None = None) -> pd.DataFrame:
    """Lê os tweets filtrados na coleção MongoDB configurada."""
    config = cfg or MongoConfig()
    client = MongoClient(config.uri, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
        docs = list(client[config.database][config.collection].find({}, {"_id": 0}))
        return pd.DataFrame(docs)
    finally:
        client.close()


def load_articles_from_mysql(cfg: MySQLConfig | None = None) -> pd.DataFrame:
    """Lê os metadados relacionais do MySQL configurado."""
    config = cfg or MySQLConfig()
    conn = mysql.connector.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=config.database,
        connection_timeout=5,
    )
    try:
        return pd.read_sql("SELECT * FROM scientific_articles", conn)
    finally:
        conn.close()


def load_tweets_json(path: Path) -> pd.DataFrame:
    """Lê o JSON de extração para análise local sem MongoDB."""
    with path.open("r", encoding="utf-8") as fh:
        records = json.load(fh)
    return pd.DataFrame(records)


def _monthly_counts(frame: pd.DataFrame, date_col: str, count_name: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["year_month", count_name])
    dates = pd.to_datetime(frame[date_col], errors="coerce", utc=True)
    months = dates.dt.strftime("%Y-%m")
    return (
        months.dropna().value_counts().rename_axis("year_month").rename(count_name)
        .sort_index().reset_index()
    )


def _top_terms(tweets: pd.DataFrame, top_n: int) -> pd.DataFrame:
    counts: Counter[str] = Counter()
    if "clean_text" not in tweets:
        return pd.DataFrame(columns=["term", "frequency"])
    for text in tweets["clean_text"].dropna().astype(str):
        counts.update(
            token.lower() for token in TOKEN_RE.findall(text)
            if token.lower() not in STOPWORDS and not token.startswith("http")
        )
    return pd.DataFrame(counts.most_common(top_n), columns=["term", "frequency"])


def build_analysis(tweets: pd.DataFrame, articles: pd.DataFrame, top_n: int = 30) -> dict[str, pd.DataFrame]:
    """Monta séries mensais alinhadas e tabelas de termos e engajamento."""
    tweet_monthly = _monthly_counts(tweets, "published_at", "tweet_count")
    article_monthly = _monthly_counts(articles, "publication_date", "article_count")
    monthly = tweet_monthly.merge(article_monthly, on="year_month", how="outer").fillna(0)
    for col in ("tweet_count", "article_count"):
        monthly[col] = monthly[col].astype("int64")

    # Pearson é calculado apenas quando há variação e pelo menos 2 meses observados.
    if len(monthly) >= 2 and monthly["tweet_count"].nunique() > 1 and monthly["article_count"].nunique() > 1:
        correlation = pd.DataFrame([{
            "method": "pearson",
            "months": len(monthly),
            "correlation": monthly["tweet_count"].corr(monthly["article_count"]),
        }])
    else:
        correlation = pd.DataFrame([{
            "method": "pearson",
            "months": len(monthly),
            "correlation": float("nan"),
        }])

    if tweets.empty:
        categories = pd.DataFrame(columns=["category", "tweet_count", "mean_engagement", "total_engagement"])
        engagement = pd.DataFrame()
    else:
        tmp = tweets.copy()
        for col in ("total_engagement", "engagement_score", "retweets", "favorites"):
            if col in tmp:
                tmp[col] = pd.to_numeric(tmp[col], errors="coerce").fillna(0)
        if "conspiracy_categories" in tmp:
            exploded = tmp.explode("conspiracy_categories").dropna(subset=["conspiracy_categories"])
            categories = exploded.groupby("conspiracy_categories").agg(
                tweet_count=("tweet_id", "count"),
                mean_engagement=("total_engagement", "mean"),
                total_engagement=("total_engagement", "sum"),
            ).reset_index().rename(columns={"conspiracy_categories": "category"})
            categories = categories.sort_values("tweet_count", ascending=False)
        else:
            categories = pd.DataFrame(columns=["category", "tweet_count", "mean_engagement", "total_engagement"])
        sort_col = "engagement_score" if "engagement_score" in tmp else "total_engagement"
        engagement = tmp.sort_values(sort_col, ascending=False).head(top_n)

    return {
        "monthly": monthly.sort_values("year_month").reset_index(drop=True),
        "correlation": correlation,
        "top_terms": _top_terms(tweets, top_n),
        "category_engagement": categories,
        "top_engagement": engagement,
    }


def write_analysis(tables: dict[str, pd.DataFrame], output_dir: Path = ANALYSIS_DIR) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in tables.items():
        frame.to_csv(output_dir / f"{name}.csv", index=False, encoding="utf-8-sig")


def main() -> None:
    parser = argparse.ArgumentParser(description="Correlaciona artigos científicos e tweets conspiracionistas por mês.")
    parser.add_argument("--tweets-json", type=Path, help="Usa JSON local em vez da coleção MongoDB.")
    parser.add_argument("--articles", type=Path, help="CSV/JSON/JSONL local em vez do MySQL.")
    parser.add_argument("--from-mongo", action="store_true", help="Lê a coleção MongoDB mesmo se houver JSON local.")
    parser.add_argument("--top", type=int, default=30, help="Quantidade de termos e tweets de maior engajamento.")
    parser.add_argument("--output-dir", type=Path, default=ANALYSIS_DIR)
    args = parser.parse_args()
    ensure_project_dirs()

    if args.tweets_json:
        tweets = load_tweets_json(args.tweets_json)
    elif PROCESSED_TWEETS_JSON.exists() and not args.from_mongo:
        tweets = load_tweets_json(PROCESSED_TWEETS_JSON)
    else:
        tweets = load_tweets_from_mongo()

    if args.articles:
        from src.articles.load_mysql import normalize_articles_dataframe, read_articles_file
        raw = read_articles_file(args.articles)
        articles = normalize_articles_dataframe(raw, args.articles.name)
    else:
        articles = load_articles_from_mysql()

    tables = build_analysis(tweets, articles, max(1, args.top))
    write_analysis(tables, args.output_dir)
    print(json.dumps({
        "tweets": len(tweets), "articles": len(articles), "output_dir": str(args.output_dir),
        "pearson_correlation": tables["correlation"].iloc[0]["correlation"],
        "months": len(tables["monthly"]),
    }, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
