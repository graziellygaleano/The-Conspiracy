"""Cruza posts e artigos por mês e gera tabelas de correlação, termos e engajamento."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

# Permite rodar direto via `python analise/correlacao.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (
    ARTIGOS_TRATADOS_CSV,
    OUTPUTS_DIR,
    POSTS_TRATADOS_JSON,
    MongoConfig,
    MySQLConfig,
    criar_pastas,
)

TOKEN_RE = re.compile(r"(?u)\b[\w#'-]{3,}\b")
STOPWORDS = {
    "about", "after", "again", "against", "also", "been", "before", "being", "between",
    "both", "could", "covid", "covid19", "from", "have", "https", "into", "just",
    "more", "most", "other", "our", "out", "over", "same", "some", "such", "than",
    "that", "them", "then", "there", "these", "they", "this", "those", "their", "the",
    "with", "were", "what", "when", "where", "which", "while", "will", "would", "your",
}


def ler_posts_mongo(cfg: MongoConfig | None = None) -> pd.DataFrame:
    from pymongo import MongoClient

    config = cfg or MongoConfig()
    client = MongoClient(config.uri, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
        docs = list(client[config.database][config.collection].find({}, {"_id": 0}))
        return pd.DataFrame(docs)
    finally:
        client.close()


def ler_artigos_mysql(cfg: MySQLConfig | None = None) -> pd.DataFrame:
    import mysql.connector

    config = cfg or MySQLConfig()
    conn = mysql.connector.connect(
        host=config.host, port=config.port, user=config.user,
        password=config.password, database=config.database, connection_timeout=5,
    )
    try:
        return pd.read_sql("SELECT * FROM scientific_articles", conn)
    finally:
        conn.close()


def ler_posts_local(path: Path = POSTS_TRATADOS_JSON) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Posts tratados não encontrados: {path}. Execute `python posts/tratar.py` primeiro."
        )
    return pd.DataFrame(json.loads(path.read_text(encoding="utf-8")))


def ler_artigos_local(path: Path = ARTIGOS_TRATADOS_CSV) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Artigos tratados não encontrados: {path}. Execute `python artigos/tratar.py` primeiro."
        )
    return pd.read_csv(path, low_memory=False)


def _contagem_mensal(frame: pd.DataFrame, date_col: str, count_name: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["year_month", count_name])
    dates = pd.to_datetime(frame[date_col], errors="coerce", utc=True)
    months = dates.dt.strftime("%Y-%m")
    return (
        months.dropna().value_counts().rename_axis("year_month").rename(count_name)
        .sort_index().reset_index()
    )


def _termos_frequentes(posts: pd.DataFrame, top_n: int) -> pd.DataFrame:
    counts: Counter[str] = Counter()
    if "clean_text" not in posts:
        return pd.DataFrame(columns=["term", "frequency"])
    for text in posts["clean_text"].dropna().astype(str):
        counts.update(
            token.lower() for token in TOKEN_RE.findall(text)
            if token.lower() not in STOPWORDS and not token.startswith("http")
        )
    return pd.DataFrame(counts.most_common(top_n), columns=["term", "frequency"])


def gerar_analise(posts: pd.DataFrame, artigos: pd.DataFrame, top_n: int = 30) -> dict[str, pd.DataFrame]:
    posts_mensal = _contagem_mensal(posts, "published_at", "post_count")
    artigos_mensal = _contagem_mensal(artigos, "publication_date", "article_count")
    monthly = posts_mensal.merge(artigos_mensal, on="year_month", how="outer").fillna(0)
    for col in ("post_count", "article_count"):
        monthly[col] = monthly[col].astype("int64")

    if len(monthly) >= 2 and monthly["post_count"].nunique() > 1 and monthly["article_count"].nunique() > 1:
        corr_val = monthly["post_count"].corr(monthly["article_count"])
    else:
        corr_val = float("nan")

    correlation = pd.DataFrame([{"method": "pearson", "months": len(monthly), "correlation": corr_val}])

    if posts.empty:
        categories = pd.DataFrame(columns=["category", "post_count", "mean_engagement", "total_engagement"])
        engagement = pd.DataFrame()
    else:
        tmp = posts.copy()
        for col in ("total_engagement", "engagement_score", "retweets", "favorites"):
            if col in tmp:
                tmp[col] = pd.to_numeric(tmp[col], errors="coerce").fillna(0)
        if "conspiracy_categories" in tmp:
            exploded = tmp.explode("conspiracy_categories").dropna(subset=["conspiracy_categories"])
            categories = exploded.groupby("conspiracy_categories").agg(
                post_count=("tweet_id", "count"),
                mean_engagement=("total_engagement", "mean"),
                total_engagement=("total_engagement", "sum"),
            ).reset_index().rename(columns={"conspiracy_categories": "category"})
            categories = categories.sort_values("post_count", ascending=False)
        else:
            categories = pd.DataFrame(columns=["category", "post_count", "mean_engagement", "total_engagement"])
        sort_col = "engagement_score" if "engagement_score" in tmp else "total_engagement"
        engagement = tmp.sort_values(sort_col, ascending=False).head(top_n)

    return {
        "monthly": monthly.sort_values("year_month").reset_index(drop=True),
        "correlation": correlation,
        "top_terms": _termos_frequentes(posts, top_n),
        "category_engagement": categories,
        "top_engagement": engagement,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Correlaciona artigos científicos e posts conspiracionistas por mês.")
    parser.add_argument("--bancos", action="store_true", help="Lê direto do MongoDB e MySQL em vez de dados/tratados/.")
    parser.add_argument("--top", type=int, default=30, help="Quantidade de termos e posts no ranking.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUTS_DIR / "analise")
    args = parser.parse_args()

    criar_pastas()
    if args.bancos:
        posts = ler_posts_mongo()
        artigos = ler_artigos_mysql()
        origem = "mongodb + mysql"
    else:
        posts = ler_posts_local()
        artigos = ler_artigos_local()
        origem = "dados/tratados/"

    tabelas = gerar_analise(posts, artigos, max(1, args.top))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for nome, df in tabelas.items():
        df.to_csv(args.output_dir / f"{nome}.csv", index=False, encoding="utf-8-sig")

    print(json.dumps({
        "origem": origem,
        "posts": len(posts),
        "artigos": len(artigos),
        "meses": len(tabelas["monthly"]),
        "correlacao_pearson": tabelas["correlation"].iloc[0]["correlation"],
        "output_dir": str(args.output_dir),
    }, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
