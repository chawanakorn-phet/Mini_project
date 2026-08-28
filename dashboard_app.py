import os
from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Olist Sales OLAP Dashboard", layout="wide")

PROJECT_ROOT = Path(__file__).resolve().parent


def find_duckdb_path():
    candidates = [
        os.getenv("DUCKDB_PATH"),
        str(PROJECT_ROOT / "olist_dw" / "dev.duckdb"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def list_tables(con):
    return [
        row[0]
        for row in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    ]


@st.cache_data
def load_data():
    db_path = find_duckdb_path()
    if not db_path:
        return pd.DataFrame()

    con = duckdb.connect(db_path, read_only=True)
    tables = list_tables(con)
    required = {"fact_order_items", "dim_customers", "dim_products", "dim_sellers", "dim_date"}
    if not required.issubset(set(tables)):
        return pd.DataFrame()

    query = """
        SELECT
            f.order_id,
            f.order_item_id,
            f.order_status,
            f.order_purchase_date,
            d.year,
            d.quarter,
            d.month_name,
            d.day_name,
            d.day_is_weekday,
            dc.customer_id,
            dc.customer_state,
            dc.customer_city,
            dp.product_id,
            dp.category AS product_category,
            ds.seller_id,
            ds.state AS seller_state,
            f.price,
            f.freight_value,
            f.total_item_value,
            f.delivery_days
        FROM fact_order_items f
        LEFT JOIN dim_date d
            ON f.order_purchase_date = d.full_date
        LEFT JOIN (SELECT customer_id, state AS customer_state, city AS customer_city FROM dim_customers) dc
            ON dc.customer_id = f.customer_id
        LEFT JOIN dim_products dp
            ON dp.product_id = f.product_id
        LEFT JOIN dim_sellers ds
            ON ds.seller_id = f.seller_id
    """
    df = con.execute(query).fetchdf()
    if df.empty:
        return df

    df["order_purchase_date"] = pd.to_datetime(df["order_purchase_date"], errors="coerce")
    df["revenue"] = df["price"].fillna(0)
    df["quantity"] = 1
    return df


def apply_filters(df):
    st.sidebar.header("Filters")

    if "order_purchase_date" in df.columns and df["order_purchase_date"].notna().any():
        min_date = df["order_purchase_date"].min().date()
        max_date = df["order_purchase_date"].max().date()
        start_date = st.sidebar.date_input("Start date", min_date, min_value=min_date, max_value=max_date)
        end_date = st.sidebar.date_input("End date", max_date, min_value=min_date, max_value=max_date)
        df = df[
            (df["order_purchase_date"].dt.date >= start_date) &
            (df["order_purchase_date"].dt.date <= end_date)
        ]

    for col, label in [
        ("product_category", "Product Category"),
        ("customer_state", "Customer State"),
        ("seller_state", "Seller State"),
        ("order_status", "Order Status"),
    ]:
        if col in df.columns:
            values = sorted(df[col].dropna().astype(str).unique().tolist())
            if values:
                selected = st.sidebar.multiselect(label, values, default=values)
                df = df[df[col].astype(str).isin(selected)]

    return df


def build_time_chart(df, level):
    if level == "year":
        group_col = "year"
    elif level == "quarter":
        group_col = "quarter"
    elif level == "month":
        group_col = "month_name"
    else:
        group_col = "year"

    grouped = (
        df.groupby(group_col, as_index=False)
        .agg(revenue=("revenue", "sum"), orders=("order_id", "nunique"))
        .rename(columns={group_col: "label"})
    )
    return grouped.sort_values("label")


def build_category_chart(df):
    grouped = (
        df.groupby("product_category", as_index=False)
        .agg(revenue=("revenue", "sum"), orders=("order_id", "nunique"))
        .sort_values("revenue", ascending=False)
        .head(10)
    )
    return grouped


def build_state_chart(df):
    grouped = (
        df.groupby("customer_state", as_index=False)
        .agg(revenue=("revenue", "sum"), orders=("order_id", "nunique"))
        .sort_values("revenue", ascending=False)
        .head(10)
    )
    return grouped


def main():
    st.title("Olist Sales OLAP Dashboard")
    st.caption("Multi-level view of Brazilian e-commerce sales: time, product category, customer state")

    df = load_data()
    if df.empty:
        st.warning("Could not load warehouse tables. Run `dbt run` in olist_dw/ first.")
        return

    df = apply_filters(df)
    if df.empty:
        st.warning("No data matches the selected filters.")
        return

    revenue = df["revenue"].sum()
    freight = df["freight_value"].sum()
    orders = df["order_id"].nunique()
    avg_order = revenue / orders if orders else 0
    avg_delivery = df["delivery_days"].dropna().mean()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Revenue", f"R$ {revenue:,.2f}")
    c2.metric("Freight", f"R$ {freight:,.2f}")
    c3.metric("Orders", f"{orders:,.0f}")
    c4.metric("Avg Order Value", f"R$ {avg_order:,.2f}")
    c5.metric("Avg Delivery Days", f"{avg_delivery:,.1f}" if pd.notna(avg_delivery) else "N/A")

    st.sidebar.header("OLAP Views")
    time_level = st.sidebar.selectbox("Time level", ["year", "quarter", "month"], index=0)

    time_df = build_time_chart(df, time_level)
    category_df = build_category_chart(df)
    state_df = build_state_chart(df)

    st.subheader(f"Revenue by {time_level}")
    time_chart = (
        alt.Chart(time_df)
        .mark_line(point=True)
        .encode(x=alt.X("label:N", title=time_level), y=alt.Y("revenue:Q"), tooltip=["label:N", "revenue:Q", "orders:Q"])
        .properties(height=320)
    )
    st.altair_chart(time_chart, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Top 10 Product Categories by Revenue")
        cat_chart = (
            alt.Chart(category_df)
            .mark_bar()
            .encode(x=alt.X("product_category:N", sort="-y"), y="revenue:Q", tooltip=["product_category:N", "revenue:Q"])
            .properties(height=350)
        )
        st.altair_chart(cat_chart, use_container_width=True)

    with col2:
        st.subheader("Top 10 Customer States by Revenue")
        state_chart = (
            alt.Chart(state_df)
            .mark_bar()
            .encode(x=alt.X("customer_state:N", sort="-y"), y="revenue:Q", tooltip=["customer_state:N", "revenue:Q"])
            .properties(height=350)
        )
        st.altair_chart(state_chart, use_container_width=True)

    st.subheader("Detail table")
    st.dataframe(df.head(200), use_container_width=True)


if __name__ == "__main__":
    main()
