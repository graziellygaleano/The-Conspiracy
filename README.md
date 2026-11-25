# Engenharia de Dados: Artigos sobre Vacinas vs. Conspirações no X

Repositório do trabalho da parte de **Engenharia de Dados** da disciplina de Banco de Dados 2 (ADS — IFSP Jacareí).

## Qual é a ideia?
Montar um fluxo **ETL (Extração, Transformação e Carga)** juntando duas fontes diferentes em dois bancos de paradigmas distintos para fazer uma **correlação estatística** entre a publicação de artigos científicos sobre vacinas e a frequência/engajamento de posts conspiracionistas no X (antigo Twitter).

## Como o pipeline funciona

* **Extração e Limpeza (`Python` + `Pandas`):** Um script vasculha a base bruta de tweets sobre vacinação (`vaccination_all_tweets.csv`), filtra narrativas conspiratórias (5G/microchip, grafeno, arma biológica, etc.), limpa sarcasmos óbvios e exporta tudo em `.json`.
* **Carga Relacional (`MySQL`):** Guarda os metadados estruturados dos artigos científicos sobre vacinação (DOI, título, data, periódico e resumo) para servir de referência temporal e temática.
* **Carga NoSQL (`MongoDB`):** Recebe os tweets já filtrados e categorizados via PyMongo (upsert), aproveitando a estrutura flexível de documentos para cruzar datas, hashtags, métricas e categorias na análise estatística.
* **Análise integrada (`Pandas`):** Lê os tweets do MongoDB e metadados do MySQL, agrega contagens mensais, calcula correlação de Pearson entre publicações e tweets, extrai termos frequentes e resume engajamento por categoria.

## Executar o pipeline

## Status atual do projeto

O projeto está na etapa de **implementação e validação local do pipeline**. Já estão implementados: extração e classificação de tweets da base local, filtro heurístico de sarcasmo/debunk (incluindo o padrão de termos atualizado), carga dos tweets no MongoDB, normalização/carga de metadados no MySQL e análise integrada mensal com termos frequentes e engajamento. A análise foi validada offline com dados demonstrativos. Próximos passos para concluir a validação ponta a ponta: configurar e testar as conexões reais dos bancos, carregar metadados científicos reais (o CSV em `data/sample` é ilustrativo), executar a extração sobre a base completa e revisar os resultados/qualidade das heurísticas.

Instale as dependências (`pip install -r requirements.txt`), copie `.env.example` para `.env` e configure as conexões. O CSV original de tweets deve estar em `BaseTweets/vaccination_all_tweets.csv` (ele é ignorado pelo Git por ser grande). Os serviços MySQL e MongoDB precisam estar ativos.

```powershell
python -m src.extract_tweets
python -m src.load_mongo
python -m src.load_mysql --input caminho\para\artigos.csv
python -m src.analyze --from-mongo
```

O carregador MySQL aceita CSV, JSON e JSONL; `--dry-run` valida e mostra uma prévia sem conectar ao banco. A análise grava `monthly.csv`, `correlation.csv`, `top_terms.csv`, `category_engagement.csv` e `top_engagement.csv` em `outputs/analysis/`. A união entre os bancos é temporal, por mês (`YYYY-MM`): correlação não implica causalidade e Pearson não é reportado como interpretável quando há menos de dois meses ou nenhuma variação em uma série.

Para experimentar a análise sem os bancos, gere primeiro o JSON dos tweets e use o CSV de demonstração:

```powershell
python -m src.extract_tweets
python -m src.analyze --tweets-json data/processed/conspiracy_tweets.json --articles data/sample/artigos_exemplo.csv
```

`data/sample/artigos_exemplo.csv` contém registros ilustrativos para validar o fluxo; substitua-o por metadados reais de publicações científicas antes de interpretar os resultados.

## Links do Projeto

* 📊 **Dataset Original (Kaggle):** [All COVID-19 Vaccines Tweets](https://www.kaggle.com/datasets/gpreda/all-covid19-vaccines-tweets?resource=download)
* 📁 **Pasta dos Dados (*THE CONSPIRACY*):** [Acessar datasets no Google Drive](https://drive.google.com/drive/u/1/folders/16wup2_OnI6hSlsW3Z0YRCsP4-sA0JP7J)
* 📄 **Documentação (*Relatório 2 de BD*):** [Acessar relatório no Google Docs](https://docs.google.com/document/d/1mJKzjKYycTv7Mla2kXlCSZp6gs8DdDWsR9Jg5Ited5E/edit?tab=t.0)

## Equipe
* Grazielly Galeano
* Maria Luiza Catalan
* Thales Vialta
