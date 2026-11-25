# Engenharia de Dados: Artigos sobre Vacinas vs. Conspirações no X

Repositório do trabalho da parte de **Engenharia de Dados** da disciplina de Banco de Dados 2 (ADS — IFSP Jacareí).

## Qual é a ideia?
Montar um fluxo **ETL (Extração, Transformação e Carga)** juntando duas fontes diferentes em dois bancos de paradigmas distintos para fazer uma **correlação estatística** entre a publicação de artigos científicos sobre vacinas e a frequência/engajamento de posts conspiracionistas no X (antigo Twitter).

## Como o pipeline funciona

* **Extração e Limpeza (`Python` + `Pandas`):** Um script vasculha a base bruta de tweets sobre vacinação (`vaccination_all_tweets.csv`), filtra narrativas conspiratórias (5G/microchip, grafeno, arma biológica, etc.), limpa sarcasmos óbvios e exporta tudo em `.json`.
* **Carga Relacional (`MySQL`):** Guarda os metadados estruturados dos artigos científicos sobre vacinação (DOI, título, data, periódico e resumo) para servir de referência temporal e temática.
* **Carga NoSQL (`MongoDB`):** Recebe os tweets já filtrados e categorizados via `mongoimport`, aproveitando a estrutura flexível de documentos para cruzar datas, hashtags, métricas e categorias na análise estatística.

## Links do Projeto

* 📁 **Pasta dos Dados (*THE CONSPIRACY*):** [Acessar datasets no Google Drive](https://drive.google.com/drive/u/1/folders/16wup2_OnI6hSlsW3Z0YRCsP4-sA0JP7J)
* 📄 **Documentação (*Relatório 2 de BD*):** [Acessar relatório no Google Docs](https://docs.google.com/document/d/1mJKzjKYycTv7Mla2kXlCSZp6gs8DdDWsR9Jg5Ited5E/edit?tab=t.0)

## Equipe
* Grazielly Galeano
* Maria Luiza Catalan
* Thales Vialta
