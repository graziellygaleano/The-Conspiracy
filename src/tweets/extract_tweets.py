"""Extração, filtragem de narrativas conspiratórias e limpeza de sarcasmos (Pandas)."""

from __future__ import annotations

import argparse
import ast
import html
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import (
    EXTRACTION_STATS_JSON,
    PROCESSED_TWEETS_JSON,
    RAW_TWEETS_CSV,
    ensure_project_dirs,
)

# Categorias de narrativas conspiracionistas descritas no projeto
CONSPIRACY_PATTERNS: dict[str, re.Pattern[str]] = {
    "5g_microchip": re.compile(
        r"(?:"
        r"\b5g\b"
        r"|\bmicro-?chip(?:ped|ping|s)?\b"
        r"|\bnano-?chip(?:s)?\b"
        r"|\brfid\b"
        r"|\bmark\s+of\s+the\s+beast\b"
        r"|\b666\b"
        r"|\btracking\s+(?:chip|device|implant|humans|us|people)\b"
        r"|\bbiometric\s+id\s+(?:chip|implant)\b"
        r")",
        re.IGNORECASE,
    ),
    "graphene_toxins": re.compile(
        r"(?:"
        r"\bgraphene(?:\s+oxide)?\b"
        r"|\bóxido\s+de\s+grafeno\b"
        r"|\bluciferase\b"
        r"|\bkill\s*shot\b"
        r"|\bclot\s*shot\b"
        r"|\bpoison\s+(?:shot|jab|vaccine|vaxx)\b"
        r"|\b(?:vaccine|jab|shot)\s+(?:is\s+)?(?:a\s+)?(?:poison|toxic|deadly\s+toxin)\b"
        r"|\btoxic\s+(?:mrna|vaccine|jab|shot|ingredients?)\b"
        r")",
        re.IGNORECASE,
    ),
    "bioweapon_depopulation": re.compile(
        r"(?:"
        r"\bbio-?weapon\b"
        r"|\bplandemic\b"
        r"|\bscamdemic\d*\b"
        r"|\bshamdemic\b"
        r"|\bcondemic\b"
        r"|\bdepopulat(?:e|ion|ing)\b"
        r"|\beugenics\b"
        r"|\bvaccine\s*genocide\b"
        r"|\bglobal\s+genocide\b"
        r"|\bexterminat(?:e|ing|ion)\s+(?:people|humanity|population)\b"
        r"|\bcrimes?\s*against\s*humanity\b"
        r"|\bnuremberg\s*(?:2|code|trials?)?\b"
        r")",
        re.IGNORECASE,
    ),
    "dna_transhumanism": re.compile(
        r"(?:"
        r"(?:alter|change|modify|modifies|modifying|rewrite|rewrites|edit|edits|manipulat\w+)\s+"
        r"(?:your\s+|our\s+|human\s+)?dna\b"
        r"|\bdna\s+(?:altering|modification|manipulation)\b"
        r"|\btranshuman(?:ism|ist)?\b"
        r"|\bgene\s+therapy\s+experiment\b"
        r"|\bhuman\s+guinea\s+pigs?\b"
        r")",
        re.IGNORECASE,
    ),
    "magnet_shedding_fertility": re.compile(
        r"(?:"
        r"#?magnet(?:challenge|gate)\b"
        r"|\bmagnetic\s*(?:vaccine|arm|shoulder|vaccinated|effect)\b"
        r"|\b(?:vaccine|vaccinated|spike\s+protein)\s+shedding\b"
        r"|\bshedding\s+(?:spike|to\s+unvaccinated|on\s+unvaccinated)\b"
        r"|\b(?:female\s+)?steriliz(?:ation|e\s+(?:women|population|us|humans))\b"
        r"|\b(?:make|makes|causes?)\s+(?:you\s+|women\s+)?infertil(?:e|ity)\b"
        r"|\bvaids\b"
        r")",
        re.IGNORECASE,
    ),
    "elites_nwo_agenda": re.compile(
        r"(?:"
        r"\bnew\s+world\s+order\b"
        r"|\bnwo\b"
        r"|\bgreat\s+reset\b"
        r"|\billuminati\b"
        r"|\bdeep\s+state\b"
        r"|\b(?:bill\s+gates|george\s+soros|klaus\s+schwab|rothschild|rockefeller)\b"
        r".{0,80}"
        r"\b(?:evil|control|agenda|microchip|dna|depopulat|eugenics|kill|plot|reset|beast|tyranny|plandemic|genocide)\b"
        r"|\b(?:evil|control|agenda|microchip|dna|depopulat|eugenics|kill|plot|reset|beast|tyranny|plandemic|genocide)\b"
        r".{0,80}"
        r"\b(?:bill\s+gates|george\s+soros|klaus\s+schwab|rothschild|rockefeller)\b"
        r")",
        re.IGNORECASE,
    ),
}

# Falsos positivos científicos, notícias neutras, expressões idiomáticas ou spam comercial
FALSE_POSITIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bshedding\s+tears\b", re.IGNORECASE),
    re.compile(r"\bsheds?\s+(?:more\s+)?light\b", re.IGNORECASE),
    re.compile(r"\bdesign\s+and\s+analysis\s+of\s+shedding\s+studies\b", re.IGNORECASE),
    re.compile(r"\bgraphene\s+hydrogels?\s+can\s+help\b", re.IGNORECASE),
    re.compile(r"\bcancer\s+vaccines?\b", re.IGNORECASE),
    re.compile(r"\b(?:buy\s+now|shop\s+now|order\s+now|\brs\s*\d+|earphone)\b", re.IGNORECASE),
]

# Sarcasmo óbvio, humor pró-vacina e checagem de fatos / debunking
SARCASM_OR_DEBUNK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(?:zombie|haven't turned|no 5g chip|cell phone reception|burp|galaxy|kidding|joke)\b", re.IGNORECASE),
    re.compile(r"(?:^|\s)/s(?:\s|$)", re.IGNORECASE),
    re.compile(r"\b(?:just\s+kidding|jk|sarcasm|sarcastic)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:got|had|received)\s+(?:my\s+)?(?:first|second|1st|2nd|covid|pfizer|moderna|az|astrazeneca)?\s*"
        r"(?:vaccine|shot|dose|jab)\b.{0,80}\b(?:5g|microchip|chip|magnet|zombie|bill\s+gates|wifi|bluetooth|signal)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:5g\s+(?:service|signal|reception|tower|wifi|hotspot|enabled|vibrations)|"
        r"fully\s+microchipped|double-?micro-?chipped|no\s+microchip|"
        r"not\s+a\s+5g|haven['’]t\s+turned\s+into|software\s+update|"
        r"beep\s+boop|u2\s+album|happiest.{0,25}microchipped|grateful.{0,25}microchip|"
        r"control\s+my\s+genes|feeling\s+invincible|searching\s+for\s+a\s+magnet|"
        r"donuts\s+remove\s+vaccine\s+toxins)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:does\s+not|doesn['’]t|won['’]t|cannot|can['’]t)\s+(?:alter|change|modify|contain)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:debunk\w*|fact[\s-]*check\w*|conspiracy\s+theor(?:y|ies|ist|ists)|"
        r"misinformation|disinformation|tinfoil\s+hat|anyone\s+worried.{0,30}microchip)\b",
        re.IGNORECASE,
    ),
    re.compile(r"(?:😂|🤣|😆|😅|😜)"),
]

VACCINE_BRAND_PATTERNS: dict[str, re.Pattern[str]] = {
    "Pfizer/BioNTech": re.compile(r"\b(?:pfizer|biontech|bnt162b2|comirnaty)\b", re.IGNORECASE),
    "Moderna": re.compile(r"\b(?:moderna|mrna-?1273|spikevax)\b", re.IGNORECASE),
    "AstraZeneca": re.compile(r"\b(?:astrazeneca|oxford\s*vaccine|chadox1|vaxzevria|covishield)\b", re.IGNORECASE),
    "Janssen": re.compile(r"\b(?:janssen|johnson\s*(?:&|and)\s*johnson|j&j|ad26)\b", re.IGNORECASE),
    "Sputnik V": re.compile(r"\b(?:sputnik\s*v?|gam-?covid-?vac)\b", re.IGNORECASE),
    "Sinovac": re.compile(r"\b(?:sinovac|coronavac)\b", re.IGNORECASE),
    "Sinopharm": re.compile(r"\b(?:sinopharm)\b", re.IGNORECASE),
    "Covaxin": re.compile(r"\b(?:covaxin|bbv152)\b", re.IGNORECASE),
}

URL_RE = re.compile(r"https?://\S+")
MENTION_RE = re.compile(r"@\w+")
WHITESPACE_RE = re.compile(r"\s+")
INLINE_HASHTAG_RE = re.compile(r"#([A-Za-z0-9_]+)")


def parse_hashtags(raw_hashtags: Any, text: str) -> list[str]:
    """Extrai e normaliza hashtags da coluna `hashtags` e do texto do tweet."""
    tags: list[str] = []
    seen: set[str] = set()

    if isinstance(raw_hashtags, str) and raw_hashtags.strip():
        try:
            parsed = ast.literal_eval(raw_hashtags)
            if isinstance(parsed, (list, tuple)):
                for item in parsed:
                    norm = str(item).strip().lstrip("#").lower()
                    if norm and norm not in seen:
                        seen.add(norm)
                        tags.append(norm)
        except (ValueError, SyntaxError):
            for item in INLINE_HASHTAG_RE.findall(raw_hashtags):
                norm = item.lower()
                if norm not in seen:
                    seen.add(norm)
                    tags.append(norm)

    for item in INLINE_HASHTAG_RE.findall(text):
        norm = item.lower()
        if norm not in seen:
            seen.add(norm)
            tags.append(norm)

    return tags


def clean_tweet_text(text: str) -> str:
    """Remove URLs, menções, entidades HTML e excesso de espaços para análise textual."""
    decoded = html.unescape(text or "")
    without_urls = URL_RE.sub(" ", decoded)
    without_mentions = MENTION_RE.sub(" ", without_urls)
    return WHITESPACE_RE.sub(" ", without_mentions).strip()


def classify_tweet(text: str) -> tuple[list[str], list[str]]:
    """Identifica categorias conspiracionistas e termos correspondentes no texto."""
    categories: list[str] = []
    matched_terms: list[str] = []
    for category, pattern in CONSPIRACY_PATTERNS.items():
        matches = pattern.findall(text)
        if matches:
            categories.append(category)
            for match in matches:
                term = match.strip().lower() if isinstance(match, str) else " ".join(match).strip().lower()
                if term and term not in matched_terms:
                    matched_terms.append(term)
    return categories, matched_terms


def is_false_positive(text: str) -> bool:
    """Verifica se o texto corresponde a contexto científico, idiomático ou spam."""
    return any(pattern.search(text) for pattern in FALSE_POSITIVE_PATTERNS)


def is_sarcasm_or_debunk(text: str) -> bool:
    """Detecta sarcasmo óbvio, piadas pró-vacina ou checagem/desmentido."""
    return any(pattern.search(text) for pattern in SARCASM_OR_DEBUNK_PATTERNS)


def detect_vaccines(text: str) -> list[str]:
    """Detecta quais fabricantes/vacinas de COVID-19 aparecem no tweet."""
    return [brand for brand, pattern in VACCINE_BRAND_PATTERNS.items() if pattern.search(text)]


def extract_conspiracy_tweets(
    input_csv: Path = RAW_TWEETS_CSV,
    output_json: Path = PROCESSED_TWEETS_JSON,
    stats_json: Path = EXTRACTION_STATS_JSON,
    chunksize: int = 50_000,
) -> dict[str, Any]:
    """Executa o ETL de tweets com Pandas, filtra conspirações e exporta JSON."""
    ensure_project_dirs()
    if not input_csv.exists():
        raise FileNotFoundError(f"Arquivo bruto de tweets não encontrado: {input_csv}")

    total_rows = 0
    candidate_rows = 0
    false_positive_removed = 0
    sarcasm_removed = 0
    kept_frames: list[pd.DataFrame] = []

    category_counter: Counter[str] = Counter()
    monthly_counter: Counter[str] = Counter()

    usecols = [
        "id",
        "user_name",
        "user_location",
        "user_followers",
        "user_verified",
        "date",
        "text",
        "hashtags",
        "source",
        "retweets",
        "favorites",
        "is_retweet",
    ]

    for chunk in pd.read_csv(
        input_csv,
        usecols=usecols,
        dtype={"id": "string", "text": "string", "hashtags": "string", "date": "string"},
        chunksize=chunksize,
        low_memory=False,
    ):
        total_rows += len(chunk)
        chunk = chunk.dropna(subset=["id", "text", "date"]).copy()
        chunk["text"] = chunk["text"].astype(str)

        classifications = chunk["text"].map(classify_tweet)
        chunk["conspiracy_categories"] = [item[0] for item in classifications]
        chunk["matched_keywords"] = [item[1] for item in classifications]

        candidates = chunk[chunk["conspiracy_categories"].map(len) > 0].copy()
        if candidates.empty:
            continue
        candidate_rows += len(candidates)

        fp_mask = candidates["text"].map(is_false_positive)
        false_positive_removed += int(fp_mask.sum())
        candidates = candidates[~fp_mask].copy()
        if candidates.empty:
            continue

        sarcasm_mask = candidates["text"].map(is_sarcasm_or_debunk)
        sarcasm_removed += int(sarcasm_mask.sum())
        filtered = candidates[~sarcasm_mask].copy()
        if filtered.empty:
            continue

        parsed_dates = pd.to_datetime(filtered["date"], errors="coerce")
        filtered = filtered[parsed_dates.notna()].copy()
        parsed_dates = parsed_dates.loc[filtered.index]

        filtered["tweet_id"] = filtered["id"].astype(str)
        filtered["published_at"] = parsed_dates.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        filtered["date_day"] = parsed_dates.dt.strftime("%Y-%m-%d")
        filtered["year_month"] = parsed_dates.dt.strftime("%Y-%m")
        filtered["clean_text"] = filtered["text"].map(clean_tweet_text)
        filtered["hashtags_list"] = [
            parse_hashtags(h, t) for h, t in zip(filtered["hashtags"], filtered["text"])
        ]
        filtered["vaccines_mentioned"] = filtered["text"].map(detect_vaccines)
        filtered["primary_category"] = filtered["conspiracy_categories"].map(lambda cats: cats[0])

        for col in ("retweets", "favorites", "user_followers"):
            filtered[col] = pd.to_numeric(filtered[col], errors="coerce").fillna(0).astype(int)

        filtered["user_verified"] = (
            filtered["user_verified"].astype(str).str.strip().str.lower().isin({"true", "1", "yes"})
        )
        filtered["total_engagement"] = filtered["retweets"] + filtered["favorites"]
        filtered["engagement_score"] = filtered["retweets"] * 2 + filtered["favorites"]
        filtered["user_name"] = filtered["user_name"].fillna("unknown").astype(str)
        filtered["user_location"] = filtered["user_location"].fillna("").astype(str)
        filtered["source"] = filtered["source"].fillna("unknown").astype(str)

        for cats in filtered["conspiracy_categories"]:
            category_counter.update(cats)
        monthly_counter.update(filtered["year_month"].tolist())

        kept_frames.append(
            filtered[
                [
                    "tweet_id",
                    "published_at",
                    "date_day",
                    "year_month",
                    "user_name",
                    "user_location",
                    "user_followers",
                    "user_verified",
                    "text",
                    "clean_text",
                    "hashtags_list",
                    "conspiracy_categories",
                    "primary_category",
                    "matched_keywords",
                    "vaccines_mentioned",
                    "retweets",
                    "favorites",
                    "total_engagement",
                    "engagement_score",
                    "source",
                ]
            ]
        )

    if kept_frames:
        result_df = pd.concat(kept_frames, ignore_index=True).drop_duplicates(subset=["tweet_id"])
        result_df = result_df.sort_values("published_at").reset_index(drop=True)
    else:
        result_df = pd.DataFrame()

    records = result_df.to_dict(orient="records") if not result_df.empty else []
    # Renomeia hashtags_list -> hashtags para documento limpo no MongoDB
    for rec in records:
        rec["hashtags"] = rec.pop("hashtags_list")

    output_json.parent.mkdir(parents=True, exist_ok=True)
    with output_json.open("w", encoding="utf-8") as fh:
        json.dump(records, fh, ensure_ascii=False, indent=2)

    stats: dict[str, Any] = {
        "input_csv": str(input_csv),
        "output_json": str(output_json),
        "total_raw_tweets": total_rows,
        "candidate_conspiracy_tweets": candidate_rows,
        "false_positives_removed": false_positive_removed,
        "sarcasm_or_debunk_removed": sarcasm_removed,
        "final_conspiracy_tweets": len(records),
        "retention_pct_from_candidates": round((len(records) / candidate_rows) * 100, 2)
        if candidate_rows
        else 0.0,
        "category_counts": dict(category_counter.most_common()),
        "monthly_counts": dict(sorted(monthly_counter.items())),
    }

    with stats_json.open("w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=2)

    return stats


def main() -> None:
    """Ponto de entrada CLI para extração e filtragem dos tweets."""
    parser = argparse.ArgumentParser(
        description="Extrai, filtra narrativas conspiracionistas e limpa sarcasmos dos tweets."
    )
    parser.add_argument("--input", type=Path, default=RAW_TWEETS_CSV, help="CSV bruto dos tweets.")
    parser.add_argument("--output", type=Path, default=PROCESSED_TWEETS_JSON, help="JSON de saída.")
    parser.add_argument("--stats", type=Path, default=EXTRACTION_STATS_JSON, help="Resumo JSON da extração.")
    args = parser.parse_args()

    stats = extract_conspiracy_tweets(
        input_csv=args.input,
        output_json=args.output,
        stats_json=args.stats,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
