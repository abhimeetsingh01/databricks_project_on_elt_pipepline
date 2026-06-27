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
3. Add the Gold table or SQL Warehouse as an app resource.
4. Replace `load_commerce_data()` with a Databricks SQL query against
   `ecommerce.gold.fact_transactions_denorm`.
5. Deploy using the included `app.yaml`.

For production, keep the presentation layer unchanged and move data access
behind a repository function that queries governed Gold tables.

