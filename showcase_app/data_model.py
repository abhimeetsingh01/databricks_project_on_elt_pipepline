from __future__ import annotations

from dataclasses import dataclass
import os
from time import perf_counter

import numpy as np
import pandas as pd


FX_TO_INR = {
    "INR": 1.00,
    "AED": 24.18,
    "AUD": 57.55,
    "CAD": 62.93,
    "GBP": 117.98,
    "SGD": 68.18,
    "USD": 88.29,
}

STATE_TO_REGION = {
    "MH": "West",
    "GJ": "West",
    "GA": "West",
    "TN": "South",
    "KA": "South",
    "KL": "South",
    "AP": "South",
    "TG": "South",
    "DL": "North",
    "UP": "North",
    "PB": "North",
    "HR": "North",
    "RJ": "North",
    "WB": "East",
    "OD": "East",
    "BR": "East",
    "VIC": "South East",
    "NSW": "East",
    "QLD": "North East",
    "CA": "West",
    "NY": "North East",
    "TX": "South",
    "ON": "Central",
    "BC": "West",
}


@dataclass
class PipelineProfile:
    file_count: int
    landing_rows: int
    bronze_rows: int
    silver_rows: int
    gold_rows: int
    landing_seconds: float
    silver_seconds: float
    gold_seconds: float
    latest_business_date: pd.Timestamp
    quality_issues: dict[str, int]

    @property
    def total_seconds(self) -> float:
        return self.landing_seconds + self.silver_seconds + self.gold_seconds


def load_commerce_data() -> tuple[pd.DataFrame, PipelineProfile]:
    """Load data from Unity Catalog denormalized table."""
    from databricks import sql

    load_start = perf_counter()

    server_hostname = _normalized_databricks_host(os.getenv("DATABRICKS_HOST"))
    http_path = os.getenv("DATABRICKS_WAREHOUSE_HTTP_PATH")
    row_limit = int(os.getenv("DATABRICKS_SQL_ROW_LIMIT", "250000"))

    if not server_hostname:
        raise RuntimeError("DATABRICKS_HOST is required for Databricks SQL access.")
    if not http_path:
        raise RuntimeError("DATABRICKS_WAREHOUSE_HTTP_PATH is required for Databricks SQL access.")

    # Connect to Databricks SQL using app credentials
    connect_args = {"server_hostname": server_hostname, "http_path": http_path}
    access_token = os.getenv("DATABRICKS_TOKEN")
    if access_token:
        connect_args["access_token"] = access_token

    conn = sql.connect(**connect_args)
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            SELECT
                order_id,
                item_seq,
                order_date AS transaction_date,
                customer_id,
                COALESCE(customer_name, 'Unknown') AS customer_name,
                COALESCE(country, 'Unknown') AS country,
                COALESCE(state, 'Unknown') AS state,
                COALESCE(city, 'Unknown') AS city,
                product_id AS sku,
                COALESCE(product_name, 'Unknown') AS product_name,
                category_code,
                COALESCE(category_name, 'Unknown') AS category_name,
                brand_code,
                COALESCE(brand_name, 'Unknown') AS brand_name,
                channel,
                quantity,
                unit_price,
                discount_percent,
                tax_amount,
                currency AS unit_price_currency,
                gross_amount,
                discount_amount,
                net_amount,
                revenue_inr
            FROM ecommerce.gold.fact_transactions_denorm
            LIMIT {row_limit}
            """
        )

        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    gold = pd.DataFrame(rows, columns=columns)

    if gold.empty:
        raise RuntimeError("ecommerce.gold.fact_transactions_denorm returned zero rows.")

    load_seconds = perf_counter() - load_start

    # Convert date column
    gold["transaction_date"] = pd.to_datetime(gold["transaction_date"])
    
    # Convert numeric columns
    numeric_cols = [
        "quantity",
        "unit_price",
        "discount_percent",
        "tax_amount",
        "gross_amount",
        "discount_amount",
        "net_amount",
        "revenue_inr",
    ]
    for col in numeric_cols:
        if col in gold.columns:
            gold[col] = pd.to_numeric(gold[col], errors="coerce")
    
    # Map channel names
    gold["channel"] = gold["channel"].str.strip().str.lower().map(
        {"web": "Website", "app": "Mobile"}
    ).fillna(gold["channel"])
    
    # Add region mapping
    gold["region"] = gold["state"].map(STATE_TO_REGION).fillna("Other")
    
    # Add computed columns
    gold["month"] = gold["transaction_date"].dt.to_period("M").astype(str)
    gold["inr_rate"] = gold["unit_price_currency"].map(FX_TO_INR).fillna(1.0)
    
    # Create profile with simplified metrics
    profile = PipelineProfile(
        file_count=1,  # Single table source
        landing_rows=len(gold),
        bronze_rows=len(gold),
        silver_rows=len(gold),
        gold_rows=len(gold),
        landing_seconds=load_seconds,
        silver_seconds=0.0,
        gold_seconds=0.0,
        latest_business_date=gold["transaction_date"].max(),
        quality_issues={
            "Records loaded": len(gold),
            "Missing customer names": int(gold["customer_name"].eq("Unknown").sum()),
            "Missing locations": int(gold["country"].eq("Unknown").sum()),
        },
    )
    
    return gold, profile


def _normalized_databricks_host(host: str | None) -> str:
    if not host:
        return ""
    return host.strip().removeprefix("https://").removeprefix("http://").rstrip("/")


def filter_data(
    frame: pd.DataFrame,
    date_range: tuple,
    countries: list[str],
    categories: list[str],
    brands: list[str],
    channels: list[str],
) -> pd.DataFrame:
    start, end = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[-1])
    mask = frame["transaction_date"].between(start, end)
    for column, values in (
        ("country", countries),
        ("category_name", categories),
        ("brand_name", brands),
        ("channel", channels),
    ):
        if values:
            mask &= frame[column].isin(values)
    return frame.loc[mask].copy()
