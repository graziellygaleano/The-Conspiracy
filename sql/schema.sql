-- ============================================================================
-- Schema Relacional (MySQL 8.0) - Metadados de Artigos Científicos
-- Projeto: The Conspiracy (Banco de Dados 2 - IFSP Jacareí)
-- Objetivo: Armazenar metadados estruturados de publicações científicas sobre
-- vacinas contra COVID-19 e sua eficácia para correlação com postagens no X.
-- ============================================================================

CREATE DATABASE IF NOT EXISTS conspiracy_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE conspiracy_db;

CREATE TABLE IF NOT EXISTS scientific_articles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    doi VARCHAR(255) NOT NULL,
    title VARCHAR(1000) NOT NULL,
    publication_date DATE NOT NULL,
    publication_month CHAR(7) NOT NULL COMMENT 'Formato YYYY-MM para agregação temporal',
    journal VARCHAR(500) NULL,
    authors TEXT NULL,
    abstract LONGTEXT NULL,
    keywords TEXT NULL COMMENT 'Palavras-chave separadas por ponto e vírgula',
    vaccine_mentioned VARCHAR(255) NULL COMMENT 'Vacina(s) mencionada(s): Pfizer, Moderna, AstraZeneca, etc.',
    efficacy_reported DECIMAL(5,2) NULL COMMENT 'Percentual de eficácia citado no estudo (0.00 a 100.00)',
    study_type VARCHAR(120) NULL COMMENT 'Ex.: clinical_trial, observational, meta_analysis, review',
    thematic_axis VARCHAR(120) NULL COMMENT 'Ex.: efficacy_immunogenicity, safety_adverse_events, variants',
    source_file VARCHAR(255) NULL COMMENT 'Arquivo de origem carregado pelo pipeline',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_scientific_articles_doi (doi),
    KEY idx_articles_pub_date (publication_date),
    KEY idx_articles_pub_month (publication_month),
    KEY idx_articles_vaccine (vaccine_mentioned),
    KEY idx_articles_thematic (thematic_axis),
    FULLTEXT KEY ft_articles_text (title, abstract, keywords)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- View de resumo mensal para cruzamento temporal rápido com o MongoDB via Pandas
CREATE OR REPLACE VIEW vw_articles_monthly_summary AS
SELECT
    publication_month,
    COUNT(*) AS total_articles,
    COUNT(DISTINCT journal) AS distinct_journals,
    ROUND(AVG(efficacy_reported), 2) AS avg_efficacy_reported,
    SUM(CASE WHEN efficacy_reported IS NOT NULL THEN 1 ELSE 0 END) AS articles_with_efficacy
FROM scientific_articles
GROUP BY publication_month
ORDER BY publication_month ASC;
