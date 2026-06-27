from __future__ import annotations

from dataclasses import dataclass
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
    import os
    
    load_start = perf_counter()
    
    # Connect to Databricks SQL using app credentials
    conn = sql.connect(
        server_hostname=os.getenv("DATABRICKS_HOST"),
        http_path=os.getenv("DATABRICKS_WAREHOUSE_HTTP_PATH", "/sql/1.0/warehouses/f9a03c44e80b62a1")
    )
    
    # Execute query
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            order_id,
            item_seq,
            order_date as transaction_date,
            customer_id,
            COALESCE(customer_name, 'Unknown') as customer_name,
            COALESCE(country, 'Unknown') as country,
            COALESCE(state, 'Unknown') as state,
            COALESCE(city, 'Unknown') as city,
            product_id,
            COALESCE(product_name, 'Unknown') as product_name,
            category_code,
            COALESCE(category_name, 'Unknown') as category_name,
            brand_code,
            COALESCE(brand_name, 'Unknown') as brand_name,
            channel,
            quantity,
            unit_price,
            discount_percent,
            tax_amount,
            currency as unit_price_currency,
            gross_amount,
            discount_amount,
            net_amount,
            revenue_inr
        FROM ecommerce.gold.fact_transactions_denorm
    """)
    
    # Fetch results into DataFrame
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    gold = pd.DataFrame(rows, columns=columns)
    
    cursor.close()
    conn.close()
    
    load_seconds = perf_counter() - load_start
    
    # Convert date column
    gold["transaction_date"] = pd.to_datetime(gold["transaction_date"])
    
    # Convert numeric columns
    numeric_cols = ["quantity", "unit_price", "discount_percent", "tax_amount", 
                   "gross_amount", "discount_amount", "net_amount", "revenue_inr"]
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
