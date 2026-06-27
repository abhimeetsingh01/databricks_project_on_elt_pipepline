from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_csv(path: Path, **kwargs) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False, **kwargs)


def load_commerce_data() -> tuple[pd.DataFrame, PipelineProfile]:
    root = _repo_root() / "0_data" / "ecomm-raw-data"

    landing_start = perf_counter()
    order_files = sorted((root / "order_items" / "landing").glob("*.csv"))
    frames = []
    for path in order_files:
        frame = _read_csv(path, dtype=str)
        frame["source_file"] = path.name
        frames.append(frame)
    landing = pd.concat(frames, ignore_index=True)
    landing_seconds = perf_counter() - landing_start

    duplicate_count = int(landing.duplicated(["order_id", "item_seq"]).sum())
    text_quantity_count = int((landing["quantity"].str.lower() == "two").sum())
    invalid_price_count = int(
        pd.to_numeric(landing["unit_price"].str.replace("$", "", regex=False), errors="coerce")
        .isna()
        .sum()
    )
    missing_customer_count = int(landing["customer_id"].isna().sum())

    silver_start = perf_counter()
    silver = landing.drop_duplicates(["order_id", "item_seq"]).copy()
    silver["transaction_date"] = pd.to_datetime(silver["dt"], errors="coerce")
    silver["transaction_ts"] = pd.to_datetime(silver["order_ts"], errors="coerce")
    silver["quantity"] = pd.to_numeric(
        silver["quantity"].replace({"Two": "2", "two": "2"}), errors="coerce"
    )
    silver["unit_price"] = pd.to_numeric(
        silver["unit_price"].str.replace("$", "", regex=False), errors="coerce"
    )
    silver["discount_percent"] = pd.to_numeric(
        silver["discount_pct"].str.replace("%", "", regex=False), errors="coerce"
    ).fillna(0)
    silver["tax_amount"] = pd.to_numeric(silver["tax_amount"], errors="coerce").fillna(0)
    silver["channel"] = silver["channel"].str.strip().str.lower().map(
        {"web": "Website", "app": "Mobile"}
    )
    silver["unit_price_currency"] = silver["unit_price_currency"].str.strip().str.upper()
    silver = silver.dropna(
        subset=[
            "transaction_date",
            "customer_id",
            "order_id",
            "product_id",
            "quantity",
            "unit_price",
            "channel",
        ]
    )
    silver_seconds = perf_counter() - silver_start

    gold_start = perf_counter()
    products = _read_csv(root / "products" / "products.csv", dtype=str)
    brands = _read_csv(root / "brands" / "brands.csv", dtype=str)
    categories = _read_csv(root / "category" / "category.csv", dtype=str)
    customers = _read_csv(root / "customers" / "customers.csv", dtype=str)

    for frame, columns in (
        (products, ["category_code", "brand_code"]),
        (brands, ["category_code", "brand_code"]),
        (categories, ["category_code"]),
    ):
        for column in columns:
            frame[column] = (
                frame[column].fillna("").str.replace(r"[^A-Za-z0-9]", "", regex=True).str.upper()
            )

    brands["brand_name"] = brands["brand_name"].str.strip()
    products["sku"] = products["sku"].str.strip()
    categories["category_name"] = categories["category_name"].str.strip()
    customers["country"] = customers["country"].str.strip()
    customers["state"] = customers["state"].str.strip().str.upper()
    customers["region"] = customers["state"].map(STATE_TO_REGION).fillna("Other")

    brands = brands.drop_duplicates("brand_code", keep="first")
    categories = categories.drop_duplicates("category_code", keep="first")
    products = products.drop_duplicates("product_id", keep="first")
    customers = customers.drop_duplicates("customer_id", keep="first")

    product_dim = products.merge(
        brands[["brand_code", "brand_name"]], on="brand_code", how="left", validate="many_to_one"
    ).merge(
        categories[["category_code", "category_name"]],
        on="category_code",
        how="left",
        validate="many_to_one",
    )

    gold = silver.merge(
        product_dim[
            [
                "product_id",
                "sku",
                "category_code",
                "category_name",
                "brand_code",
                "brand_name",
            ]
        ],
        on="product_id",
        how="left",
        validate="many_to_one",
    ).merge(
        customers[["customer_id", "country", "state", "region"]],
        on="customer_id",
        how="left",
        validate="many_to_one",
    )
    gold["country"] = gold["country"].fillna("Unknown")
    gold["state"] = gold["state"].fillna("Unknown")
    gold["region"] = gold["region"].fillna("Unknown")

    gold["gross_amount"] = gold["quantity"] * gold["unit_price"]
    gold["discount_amount"] = np.ceil(
        gold["gross_amount"] * gold["discount_percent"] / 100
    )
    gold["net_amount"] = gold["gross_amount"] - gold["discount_amount"] + gold["tax_amount"]
    gold["inr_rate"] = gold["unit_price_currency"].map(FX_TO_INR)
    gold["revenue_inr"] = np.ceil(gold["net_amount"] * gold["inr_rate"])
    gold["month"] = gold["transaction_date"].dt.to_period("M").astype(str)
    gold["coupon_flag"] = gold["coupon_code"].notna().astype(int)
    gold_seconds = perf_counter() - gold_start

    profile = PipelineProfile(
        file_count=len(order_files),
        landing_rows=len(landing),
        bronze_rows=len(landing),
        silver_rows=len(silver),
        gold_rows=len(gold),
        landing_seconds=landing_seconds,
        silver_seconds=silver_seconds,
        gold_seconds=gold_seconds,
        latest_business_date=gold["transaction_date"].max(),
        quality_issues={
            "Duplicate order lines": duplicate_count,
            "Text quantities normalized": text_quantity_count,
            "Invalid prices rejected": invalid_price_count,
            "Missing customer IDs": missing_customer_count,
            "Rows rejected during cleaning": len(landing) - len(silver),
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
