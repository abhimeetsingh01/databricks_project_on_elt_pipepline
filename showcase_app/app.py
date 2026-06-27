from __future__ import annotations

import re

import pandas as pd
import plotly.express as px
import streamlit as st

from data_model import filter_data, load_commerce_data


st.set_page_config(
    page_title="E-commerce Intelligence Platform",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .stApp { background: #f5f7f8; color: #17242a; }
      [data-testid="stSidebar"] { background: #102a2e; }
      [data-testid="stSidebar"] * { color: #f7faf9; }
      [data-testid="stMetric"] {
        background: #ffffff; border: 1px solid #dce4e3; border-radius: 6px;
        padding: 14px 16px; box-shadow: 0 3px 12px rgba(16,42,46,.05);
      }
      [data-testid="stMetricValue"] { color: #0f6b62; }
      .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
      .eyebrow { color: #d06b35; font-size: .78rem; font-weight: 700; text-transform: uppercase; }
      .page-title { font-size: 2.15rem; font-weight: 750; color: #102a2e; margin: 0; }
      .page-copy { color: #53666a; margin-top: .25rem; }
      .stage {
        background: white; border-left: 4px solid #0f6b62; border-radius: 5px;
        padding: 13px 15px; min-height: 88px; border-top: 1px solid #dce4e3;
        border-right: 1px solid #dce4e3; border-bottom: 1px solid #dce4e3;
      }
      .stage strong { color: #102a2e; }
      .answer {
        background: #eaf3f1; border: 1px solid #bfd8d3; border-radius: 6px;
        padding: 18px; color: #173f3b;
      }
      div[data-testid="stDataFrame"] { border: 1px solid #dce4e3; border-radius: 6px; }
      .stButton button { border-radius: 5px; border-color: #0f6b62; color: #0f6b62; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner="Building the Gold analytics model...")
def get_data():
    model_version = 2
    _ = model_version
    return load_commerce_data()


def money(value: float) -> str:
    if value >= 10_000_000:
        return f"₹{value / 10_000_000:,.2f} Cr"
    if value >= 100_000:
        return f"₹{value / 100_000:,.2f} L"
    return f"₹{value:,.0f}"


def heading(eyebrow: str, title: str, copy: str) -> None:
    st.markdown(
        f'<div class="eyebrow">{eyebrow}</div><div class="page-title">{title}</div>'
        f'<div class="page-copy">{copy}</div>',
        unsafe_allow_html=True,
    )
    st.write("")


def horizontal_bar(frame, x, y, color="#0f6b62", height=350):
    fig = px.bar(frame, x=x, y=y, orientation="h", text_auto=".2s")
    fig.update_traces(marker_color=color, textposition="outside")
    fig.update_layout(
        height=height,
        margin=dict(l=5, r=30, t=10, b=10),
        yaxis={"categoryorder": "total ascending"},
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=False,
    )
    return fig


data, profile = get_data()

with st.sidebar:
    st.markdown("## E-commerce IQ")
    st.caption("Databricks medallion intelligence")
    st.divider()
    page = st.radio(
        "Workspace",
        ["Executive Overview", "Pipeline Monitor", "Business Explorer", "Ask Your Data"],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption(
        f"Data through {profile.latest_business_date:%d %b %Y}\n\n"
        f"{profile.file_count} incremental source files"
    )

if page == "Executive Overview":
    heading(
        "Commercial pulse",
        "Executive Overview",
        "A single view of growth, customers, products and channel performance.",
    )

    total_revenue = data["revenue_inr"].sum()
    orders = data["order_id"].nunique()
    customers = data["customer_id"].nunique()
    aov = total_revenue / orders if orders else 0
    cols = st.columns(4)
    for col, label, value in zip(
        cols,
        ["Total revenue", "Orders", "Customers", "Average order value"],
        [money(total_revenue), f"{orders:,}", f"{customers:,}", money(aov)],
    ):
        col.metric(label, value)

    st.write("")
    left, right = st.columns([1.65, 1])
    daily = data.groupby("transaction_date", as_index=False)["revenue_inr"].sum()
    trend = px.area(
        daily,
        x="transaction_date",
        y="revenue_inr",
        labels={"transaction_date": "Date", "revenue_inr": "Revenue (INR)"},
        color_discrete_sequence=["#0f6b62"],
    )
    trend.update_layout(
        title="Revenue trend",
        height=365,
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=5, r=10, t=45, b=5),
    )
    left.plotly_chart(trend, use_container_width=True)

    channel = data.groupby("channel", as_index=False)["revenue_inr"].sum()
    donut = px.pie(
        channel,
        names="channel",
        values="revenue_inr",
        hole=.62,
        color_discrete_sequence=["#0f6b62", "#d06b35"],
        title="Revenue by channel",
    )
    donut.update_layout(height=365, margin=dict(l=5, r=5, t=45, b=5))
    right.plotly_chart(donut, use_container_width=True)

    tabs = st.tabs(["Products", "Brands", "Regions", "Countries"])
    dimensions = [
        ("sku", "Product SKU"),
        ("brand_name", "Brand"),
        ("region", "Region"),
        ("country", "Country"),
    ]
    for tab, (column, _label) in zip(tabs, dimensions):
        with tab:
            summary = (
                data.fillna({column: "Unknown"})
                .groupby(column, as_index=False)["revenue_inr"]
                .sum()
                .nlargest(10, "revenue_inr")
            )
            st.plotly_chart(
                horizontal_bar(summary, "revenue_inr", column),
                use_container_width=True,
            )

elif page == "Pipeline Monitor":
    heading(
        "Operational confidence",
        "Pipeline Monitor",
        "Trace data from incremental landing files into trusted business-ready Gold tables.",
    )

    stages = [
        ("Landing", profile.landing_rows, profile.landing_seconds, "Incremental CSV batches"),
        ("Bronze", profile.bronze_rows, 0.0, "Immutable source history"),
        ("Silver", profile.silver_rows, profile.silver_seconds, "Cleaned and standardized"),
        ("Gold", profile.gold_rows, profile.gold_seconds, "Enriched analytics model"),
    ]
    columns = st.columns(4)
    for column, (name, rows, seconds, copy) in zip(columns, stages):
        duration = f"{seconds:.2f}s" if seconds else "Persisted"
        column.markdown(
            f'<div class="stage"><strong>{name}</strong><br>{rows:,} rows<br>'
            f'<small>{copy} · {duration}</small></div>',
            unsafe_allow_html=True,
        )

    st.write("")
    a, b, c = st.columns(3)
    a.metric("Latest business date", f"{profile.latest_business_date:%d %b %Y}")
    b.metric("Local processing time", f"{profile.total_seconds:.2f} sec")
    pass_rate = profile.gold_rows / profile.landing_rows * 100
    c.metric("Data acceptance rate", f"{pass_rate:.2f}%")

    st.write("")
    left, right = st.columns([1.2, 1])
    flow = pd.DataFrame(
        {
            "Layer": ["Landing", "Bronze", "Silver", "Gold"],
            "Rows": [
                profile.landing_rows,
                profile.bronze_rows,
                profile.silver_rows,
                profile.gold_rows,
            ],
        }
    )
    funnel = px.funnel(
        flow,
        x="Rows",
        y="Layer",
        color="Layer",
        color_discrete_sequence=["#d06b35", "#387c85", "#429c8f", "#0f6b62"],
        title="Record flow by medallion layer",
    )
    funnel.update_layout(height=360, margin=dict(l=5, r=5, t=45, b=5))
    left.plotly_chart(funnel, use_container_width=True)

    quality = pd.DataFrame(
        {"Check": profile.quality_issues.keys(), "Affected rows": profile.quality_issues.values()}
    )
    quality["Status"] = quality["Affected rows"].map(lambda count: "Resolved" if count else "Passed")
    right.markdown("#### Data-quality controls")
    right.dataframe(quality, use_container_width=True, hide_index=True, height=285)
    right.success("All blocking quality checks completed before Gold publication.")

elif page == "Business Explorer":
    heading(
        "Self-service analysis",
        "Business Explorer",
        "Filter the Gold model, compare segments and export the exact result set.",
    )

    controls = st.columns([1.4, 1, 1, 1, 1])
    min_date, max_date = data["transaction_date"].min().date(), data["transaction_date"].max().date()
    date_range = controls[0].date_input(
        "Transaction date",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    countries = controls[1].multiselect("Country", sorted(data["country"].dropna().unique()))
    categories = controls[2].multiselect(
        "Category", sorted(data["category_name"].dropna().unique())
    )
    brands = controls[3].multiselect("Brand", sorted(data["brand_name"].dropna().unique()))
    channels = controls[4].multiselect("Channel", sorted(data["channel"].dropna().unique()))

    filtered = filter_data(data, date_range, countries, categories, brands, channels)
    if filtered.empty:
        st.warning("No records match the selected filters.")
        st.stop()

    kpis = st.columns(4)
    kpis[0].metric("Revenue", money(filtered["revenue_inr"].sum()))
    kpis[1].metric("Orders", f"{filtered['order_id'].nunique():,}")
    kpis[2].metric("Customers", f"{filtered['customer_id'].nunique():,}")
    kpis[3].metric("Order lines", f"{len(filtered):,}")

    left, right = st.columns([1.5, 1])
    monthly = filtered.groupby("month", as_index=False)["revenue_inr"].sum()
    month_chart = px.bar(
        monthly,
        x="month",
        y="revenue_inr",
        color_discrete_sequence=["#0f6b62"],
        title="Monthly revenue",
    )
    month_chart.update_layout(height=340, plot_bgcolor="white")
    left.plotly_chart(month_chart, use_container_width=True)

    segment = (
        filtered.groupby("category_name", as_index=False)["revenue_inr"]
        .sum()
        .nlargest(8, "revenue_inr")
    )
    right.plotly_chart(
        horizontal_bar(segment, "revenue_inr", "category_name", "#d06b35", 340),
        use_container_width=True,
    )

    export_columns = [
        "transaction_date",
        "order_id",
        "customer_id",
        "sku",
        "category_name",
        "brand_name",
        "country",
        "region",
        "channel",
        "quantity",
        "unit_price_currency",
        "net_amount",
        "revenue_inr",
    ]
    result = filtered[export_columns].sort_values(
        ["transaction_date", "order_id"], ascending=[False, False]
    )
    st.markdown("#### Drill-down transactions")
    st.dataframe(
        result,
        use_container_width=True,
        hide_index=True,
        column_config={
            "revenue_inr": st.column_config.NumberColumn("Revenue (INR)", format="₹ %.0f"),
            "transaction_date": st.column_config.DateColumn("Date"),
        },
    )
    st.download_button(
        "Download filtered CSV",
        result.to_csv(index=False).encode("utf-8"),
        "ecommerce_business_export.csv",
        "text/csv",
    )

else:
    heading(
        "Conversational analytics",
        "Ask Your Data",
        "Ask common executive questions in plain English and receive an auditable answer.",
    )

    examples = [
        "What was the highest-revenue day?",
        "Show the top products in August.",
        "Compare website and mobile revenue.",
    ]
    st.markdown("**Try a question**")
    example_cols = st.columns(3)
    for column, example in zip(example_cols, examples):
        if column.button(example, use_container_width=True):
            st.session_state["question"] = example

    question = st.text_input(
        "Question",
        value=st.session_state.get("question", ""),
        placeholder="Ask about revenue, products, channels or customers...",
        label_visibility="collapsed",
    )

    if question:
        normalized = re.sub(r"[^a-z0-9]+", " ", question.lower()).strip()
        answer = ""
        answer_frame = None

        if any(word in normalized for word in ["highest revenue day", "biggest day", "best day"]):
            daily = data.groupby("transaction_date", as_index=False)["revenue_inr"].sum()
            winner = daily.loc[daily["revenue_inr"].idxmax()]
            answer = (
                f"The highest-revenue day was **{winner['transaction_date']:%d %B %Y}**, "
                f"generating **{money(winner['revenue_inr'])}**."
            )
            answer_frame = (
                data[data["transaction_date"] == winner["transaction_date"]]
                .groupby("category_name", as_index=False)["revenue_inr"]
                .sum()
                .nlargest(8, "revenue_inr")
            )
        elif "product" in normalized and ("top" in normalized or "august" in normalized):
            august = data[data["transaction_date"].dt.month == 8]
            answer_frame = (
                august.groupby(["sku", "category_name", "brand_name"], as_index=False)[
                    "revenue_inr"
                ]
                .sum()
                .nlargest(10, "revenue_inr")
            )
            leader = answer_frame.iloc[0]
            answer = (
                f"The leading August product was **{leader['sku']}** from "
                f"**{leader['brand_name']}**, with **{money(leader['revenue_inr'])}** in revenue."
            )
        elif any(word in normalized for word in ["website", "mobile", "channel"]):
            answer_frame = (
                data.groupby("channel", as_index=False)
                .agg(
                    revenue_inr=("revenue_inr", "sum"),
                    orders=("order_id", "nunique"),
                    customers=("customer_id", "nunique"),
                )
                .sort_values("revenue_inr", ascending=False)
            )
            leader = answer_frame.iloc[0]
            answer = (
                f"**{leader['channel']}** is the leading channel with "
                f"**{money(leader['revenue_inr'])}**, across **{leader['orders']:,} orders**."
            )
        elif "customer" in normalized:
            answer_frame = (
                data.groupby("country", as_index=False)
                .agg(customers=("customer_id", "nunique"), revenue_inr=("revenue_inr", "sum"))
                .sort_values("customers", ascending=False)
            )
            answer = (
                f"The model contains **{data['customer_id'].nunique():,} purchasing customers** "
                f"across **{data['country'].nunique()} countries**."
            )
        else:
            answer = (
                "I can currently answer questions about the highest-revenue day, top products, "
                "channel comparisons and customer distribution. In Databricks, this interface "
                "can be connected directly to a Genie Space for open-ended questions."
            )

        st.markdown(f'<div class="answer">{answer}</div>', unsafe_allow_html=True)
        if answer_frame is not None:
            st.write("")
            st.dataframe(answer_frame, use_container_width=True, hide_index=True)

    st.info(
        "Demo mode uses governed, pre-defined analytical intents. Production mode can route "
        "questions to Databricks Genie while retaining the same user experience."
    )
