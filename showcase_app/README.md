# E-commerce Intelligence Platform

A client-facing Streamlit application built on the e-commerce Databricks
medallion project.

## Views

- Executive Overview: revenue, orders, customers, AOV and segment rankings.
- Pipeline Monitor: Landing to Bronze to Silver to Gold record flow, timing and
  data-quality controls.
- Business Explorer: business filters, drill-down records and CSV export.
- Ask Your Data: guided natural-language analytics with a production path to
  Databricks Genie.

## Run locally

From the repository root:

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r showcase_app/requirements.txt
streamlit run showcase_app/app.py
```

On PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r showcase_app\requirements.txt
streamlit run showcase_app\app.py
```

The app reads the existing CSV files from `0_data/ecomm-raw-data` and reproduces
the key Silver cleaning and Gold enrichment logic documented in the notebooks.

## Deploy to Databricks Apps

1. Upload the repository to a Databricks Git folder.
2. Create a Databricks App that points to `showcase_app`.
3. Add the SQL Warehouse as an app resource, or configure these environment
   variables:
   - `DATABRICKS_HOST`: workspace host, for example
     `adb-xxxx.azuredatabricks.net` or `dbc-xxxx.cloud.databricks.com`.
   - `DATABRICKS_WAREHOUSE_HTTP_PATH`: SQL Warehouse HTTP path, for example
     `/sql/1.0/warehouses/<warehouse-id>`.
   - `DATABRICKS_TOKEN`: optional personal access token if app service
     credentials are not available.
   - `DATABRICKS_SQL_ROW_LIMIT`: optional row limit, defaults to `250000`.
4. Confirm `ecommerce.gold.fact_transactions_denorm` exists and the app
   principal has `SELECT` access.
5. Deploy using the included `app.yaml`.

For production, keep the presentation layer unchanged and move data access
behind a repository function that queries governed Gold tables.
