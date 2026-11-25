# Engenharia de Dados: Artigos sobre Vacinas vs. Conspirações no X

Repositório do trabalho de **Engenharia de Dados** da disciplina de Banco de Dados 2 (ADS — IFSP Jacareí).

## Qual é a ideia?
Montar um fluxo **ETL (Extração, Transformação e Carga)** integrando dois bancos de paradigmas diferentes para analisar a **correlação estatística mensal** entre artigos científicos sobre vacinas e posts conspiracionistas no X (antigo Twitter):

* **Posts (`posts/` → MongoDB):** filtra narrativas conspiratórias, remove sarcasmos/falsos positivos e envia os documentos limpos para o MongoDB.
* **Artigos (`artigos/` → MySQL):** padroniza colunas, extrai vacina/eficácia/eixo temático e envia os metadados estruturados para o MySQL.
* **Análise (`analise/` → Pandas):** cruza as duas bases por mês (`YYYY-MM`), calcula correlação de Pearson, termos frequentes e engajamento por categoria.

## Estrutura do projeto

```text
The-Conspiracy/
├── .env.example              # Modelo de senhas e caminhos das planilhas
├── config.py                 # Lê o .env e centraliza caminhos/credenciais
├── dados/
│   ├── exemplo/              # Planilhas pequenas para testar rápido
│   ├── reais/                # Coloque aqui as planilhas completas (ignorado no Git)
│   └── tratados/             # Gerado automaticamente antes de subir pros bancos
├── sql/schema.sql            # Tabela e view do MySQL
├── posts/
│   ├── tratar.py             # Limpa e filtra a planilha de posts
│   └── enviar_mongo.py       # Envia os posts tratados para o MongoDB
├── artigos/
│   ├── tratar.py             # Padroniza a planilha de artigos
│   └── enviar_mysql.py       # Envia os artigos tratados para o MySQL
└── analise/
    └── correlacao.py         # Gera os CSVs de correlação e engajamento
```

## Como executar

1. Instale as dependências:
```powershell
pip install -r requirements.txt
```

2. Copie `.env.example` para `.env`. Por padrão, ele já aponta para `dados/exemplo/`. Quando baixar as planilhas completas, coloque-as em `dados/reais/` e troque `ARQUIVO_POSTS` e `ARQUIVO_ARTIGOS` no `.env`.

3. **Testar localmente (sem precisar dos bancos ligados):**
```powershell
python posts/tratar.py
python artigos/tratar.py
python analise/correlacao.py
```
Você também pode simular o envio aos bancos sem conectar usando `--dry-run`:
```powershell
python posts/enviar_mongo.py --dry-run
python artigos/enviar_mysql.py --dry-run
```

4. **Executar com MongoDB e MySQL reais:**
```powershell
python posts/tratar.py
python posts/enviar_mongo.py

python artigos/tratar.py
python artigos/enviar_mysql.py

python analise/correlacao.py --bancos
```

Os resultados da análise são gravados em `outputs/analise/` (`monthly.csv`, `correlation.csv`, `top_terms.csv`, `category_engagement.csv` e `top_engagement.csv`).

## Links do Projeto

* 📊 **Dataset Original (Kaggle):** [All COVID-19 Vaccines Tweets](https://www.kaggle.com/datasets/gpreda/all-covid19-vaccines-tweets?resource=download)
* 📁 **Pasta dos Dados (*THE CONSPIRACY*):** [Acessar datasets no Google Drive](https://drive.google.com/drive/u/1/folders/16wup2_OnI6hSlsW3Z0YRCsP4-sA0JP7J)
* 📄 **Documentação (*Relatório 2 de BD*):** [Acessar relatório no Google Docs](https://docs.google.com/document/d/1mJKzjKYycTv7Mla2kXlCSZp6gs8DdDWsR9Jg5Ited5E/edit?tab=t.0)

## Equipe
* Grazielly Galeano
* Maria Luiza Catalan
* Thales Vialta
