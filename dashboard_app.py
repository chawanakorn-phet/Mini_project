import os
from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

from warehouse import ensure_warehouse_built

st.set_page_config(page_title="Olist Sales OLAP Dashboard", layout="wide")

PROJECT_ROOT = Path(__file__).resolve().parent

with st.spinner("Building data warehouse (first run only)..."):
    _ok, _log = ensure_warehouse_built()
if not _ok:
    st.error("dbt run failed while building the warehouse. See log below.")
    st.code(_log)
    st.stop()


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


@st.cache_resource
def get_connection():
    db_path = find_duckdb_path()
    if not db_path:
        return None
    return duckdb.connect(db_path, read_only=True)


REQUIRED_TABLES = {
    "fact_order_items", "fact_order_payments", "fact_order_reviews",
    "dim_customers", "dim_products", "dim_sellers", "dim_date",
}


def warehouse_ready(con):
    if con is None:
        return False
    return REQUIRED_TABLES.issubset(set(list_tables(con)))


@st.cache_data
def load_data():
    con = get_connection()
    if not warehouse_ready(con):
        return pd.DataFrame()

    query = """
        SELECT
            f.order_id,
            f.order_item_id,
            f.order_status,
            f.order_purchase_date,
            f.order_purchase_hour,
            f.seller_processing_days,
            f.carrier_transit_days,
            f.buyer_seller_distance_km,
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
            dp.product_photos_qty,
            dp.product_name_length,
            dp.product_description_length,
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


@st.cache_data
def load_hourly():
    con = get_connection()
    if not warehouse_ready(con):
        return pd.DataFrame()
    return con.execute("""
        SELECT order_purchase_hour AS hour, COUNT(DISTINCT order_id) AS orders, SUM(price) AS revenue
        FROM fact_order_items
        WHERE order_purchase_hour IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """).fetchdf()


@st.cache_data
def load_mom_growth():
    con = get_connection()
    if not warehouse_ready(con):
        return pd.DataFrame()
    return con.execute("""
        WITH monthly AS (
            SELECT date_trunc('month', order_purchase_date) AS month, SUM(price) AS revenue
            FROM fact_order_items
            -- Olist's Sep-Dec 2016 pilot had only a handful of orders; including it makes
            -- early MoM % swings (e.g. +1,100,000%) dwarf every real month afterwards.
            WHERE order_purchase_date >= DATE '2017-01-01'
            GROUP BY 1
        )
        SELECT
            month,
            revenue,
            100.0 * (revenue - LAG(revenue) OVER (ORDER BY month))
                / NULLIF(LAG(revenue) OVER (ORDER BY month), 0) AS mom_pct
        FROM monthly
        ORDER BY month
    """).fetchdf()


@st.cache_data
def load_distance_vs_review():
    con = get_connection()
    if not warehouse_ready(con):
        return pd.DataFrame()
    return con.execute("""
        SELECT
            CASE
                WHEN f.buyer_seller_distance_km < 500 THEN '1. < 500 km'
                WHEN f.buyer_seller_distance_km < 1500 THEN '2. 500-1500 km'
                ELSE '3. > 1500 km'
            END AS distance_bucket,
            ROUND(AVG(f.buyer_seller_distance_km), 0) AS avg_km,
            ROUND(AVG(r.review_score), 2) AS avg_review_score,
            COUNT(*) AS n
        FROM fact_order_items f
        JOIN fact_order_reviews r ON r.order_id = f.order_id
        WHERE f.buyer_seller_distance_km IS NOT NULL
        GROUP BY 1
        ORDER BY 1
    """).fetchdf()


@st.cache_data
def load_fulfillment_vs_review():
    con = get_connection()
    if not warehouse_ready(con):
        return pd.DataFrame()
    return con.execute("""
        SELECT
            CASE
                WHEN f.seller_processing_days <= 1 THEN '1. Fast (<=1 day)'
                WHEN f.seller_processing_days <= 3 THEN '2. Medium (2-3 days)'
                ELSE '3. Slow (>3 days)'
            END AS speed_bucket,
            ROUND(AVG(r.review_score), 2) AS avg_review_score,
            COUNT(*) AS n
        FROM fact_order_items f
        JOIN fact_order_reviews r ON r.order_id = f.order_id
        WHERE f.seller_processing_days IS NOT NULL AND f.seller_processing_days >= 0
        GROUP BY 1
        ORDER BY 1
    """).fetchdf()


@st.cache_data
def load_repeat_vs_onetime():
    con = get_connection()
    if not warehouse_ready(con):
        return pd.DataFrame()
    return con.execute("""
        WITH customer_orders AS (
            SELECT dc.customer_unique_id, f.order_id, SUM(f.price) AS order_value
            FROM fact_order_items f
            JOIN dim_customers dc ON dc.customer_id = f.customer_id
            GROUP BY 1, 2
        ),
        customer_summary AS (
            SELECT
                customer_unique_id,
                COUNT(DISTINCT order_id) AS n_orders,
                AVG(order_value) AS avg_order_value
            FROM customer_orders
            GROUP BY 1
        )
        SELECT
            CASE WHEN n_orders > 1 THEN 'Repeat customer' ELSE 'One-time customer' END AS segment,
            COUNT(*) AS n_customers,
            ROUND(AVG(avg_order_value), 2) AS avg_order_value
        FROM customer_summary
        GROUP BY 1
    """).fetchdf()


@st.cache_data
def load_payment_aov():
    con = get_connection()
    if not warehouse_ready(con):
        return pd.DataFrame()
    return con.execute("""
        SELECT
            payment_type,
            COUNT(DISTINCT order_id) AS n_orders,
            ROUND(AVG(payment_value), 2) AS avg_payment_value
        FROM fact_order_payments
        WHERE payment_type != 'not_defined'
        GROUP BY 1
        ORDER BY n_orders DESC
    """).fetchdf()


@st.cache_data
def load_seller_pareto():
    con = get_connection()
    if not warehouse_ready(con):
        return pd.DataFrame()
    return con.execute("""
        WITH seller_revenue AS (
            SELECT seller_id, SUM(price) AS revenue
            FROM fact_order_items
            GROUP BY 1
        ),
        ranked AS (
            SELECT
                seller_id,
                revenue,
                ROW_NUMBER() OVER (ORDER BY revenue DESC) AS rnk,
                COUNT(*) OVER () AS total_sellers
            FROM seller_revenue
        )
        SELECT
            rnk,
            100.0 * rnk / total_sellers AS pct_sellers,
            100.0 * SUM(revenue) OVER (ORDER BY rnk) / SUM(revenue) OVER () AS cum_pct_revenue
        FROM ranked
        ORDER BY rnk
    """).fetchdf()


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


def render_overview_tab(df):
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

    time_level = st.selectbox("Time level", ["year", "quarter", "month"], index=0, key="time_level")

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


def render_customers_tab():
    st.caption("Answers Q2 (peak order hour), Q3 (AOV by payment type), Q4/Q5 (repeat vs one-time customers)")

    hourly_df = load_hourly()
    mom_df = load_mom_growth()
    payment_df = load_payment_aov()
    repeat_df = load_repeat_vs_onetime()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Orders by hour of day")
        if not hourly_df.empty:
            chart = (
                alt.Chart(hourly_df)
                .mark_bar()
                .encode(x=alt.X("hour:O", title="Hour of day"), y=alt.Y("orders:Q"), tooltip=["hour", "orders", "revenue"])
                .properties(height=300)
            )
            st.altair_chart(chart, use_container_width=True)

    with col2:
        st.subheader("Month-over-month revenue growth")
        st.caption("From 2017-01 onward — Olist's 2016 launch pilot had too few orders for a meaningful % change")
        if not mom_df.empty:
            mom_df = mom_df.copy()
            mom_df["month"] = pd.to_datetime(mom_df["month"]).dt.strftime("%Y-%m")
            chart = (
                alt.Chart(mom_df)
                .mark_bar()
                .encode(
                    x=alt.X("month:N", sort=None),
                    y=alt.Y("mom_pct:Q", title="MoM % change"),
                    color=alt.condition(alt.datum.mom_pct > 0, alt.value("#2E7D32"), alt.value("#C62828")),
                    tooltip=["month", "revenue", "mom_pct"],
                )
                .properties(height=300)
            )
            st.altair_chart(chart, use_container_width=True)

    col3, col4 = st.columns(2)
    with col3:
        st.subheader("Avg order value by payment type")
        if not payment_df.empty:
            chart = (
                alt.Chart(payment_df)
                .mark_bar()
                .encode(x=alt.X("payment_type:N", sort="-y"), y="avg_payment_value:Q", tooltip=["payment_type", "n_orders", "avg_payment_value"])
                .properties(height=300)
            )
            st.altair_chart(chart, use_container_width=True)

    with col4:
        st.subheader("Repeat vs one-time customers")
        if not repeat_df.empty:
            st.dataframe(repeat_df, use_container_width=True, hide_index=True)
            repeat_pct = 0.0
            total = repeat_df["n_customers"].sum()
            repeat_row = repeat_df[repeat_df["segment"] == "Repeat customer"]
            if total and not repeat_row.empty:
                repeat_pct = 100.0 * repeat_row["n_customers"].iloc[0] / total
            st.metric("Repeat customer rate", f"{repeat_pct:.1f}%")


def render_delivery_tab():
    st.caption("Answers Q7 (late delivery vs review), Q9/Q10 (distance vs review), Q15 (fulfillment speed vs review)")

    distance_df = load_distance_vs_review()
    fulfillment_df = load_fulfillment_vs_review()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Buyer-seller distance vs review score")
        if not distance_df.empty:
            chart = (
                alt.Chart(distance_df)
                .mark_bar()
                .encode(x=alt.X("distance_bucket:N", sort=None), y=alt.Y("avg_review_score:Q", scale=alt.Scale(domain=[0, 5])), tooltip=["distance_bucket", "avg_km", "avg_review_score", "n"])
                .properties(height=320)
            )
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No distance data available (needs geolocation coverage for the zip codes involved).")

    with col2:
        st.subheader("Seller fulfillment speed vs review score")
        if not fulfillment_df.empty:
            chart = (
                alt.Chart(fulfillment_df)
                .mark_bar()
                .encode(x=alt.X("speed_bucket:N", sort=None), y=alt.Y("avg_review_score:Q", scale=alt.Scale(domain=[0, 5])), tooltip=["speed_bucket", "avg_review_score", "n"])
                .properties(height=320)
            )
            st.altair_chart(chart, use_container_width=True)


def render_sellers_tab():
    st.caption("Answers Q14: is platform revenue concentrated in the top 10% of sellers (Pareto 80/20)?")

    pareto_df = load_seller_pareto()
    if pareto_df.empty:
        st.info("No seller data available.")
        return

    top10_row = pareto_df[pareto_df["pct_sellers"] >= 10].head(1)
    top10_share = top10_row["cum_pct_revenue"].iloc[0] if not top10_row.empty else None

    if top10_share is not None:
        st.metric("Revenue share held by top 10% of sellers", f"{top10_share:.1f}%")

    chart = (
        alt.Chart(pareto_df)
        .mark_line()
        .encode(
            x=alt.X("pct_sellers:Q", title="% of sellers (ranked by revenue)"),
            y=alt.Y("cum_pct_revenue:Q", title="Cumulative % of revenue"),
            tooltip=["pct_sellers", "cum_pct_revenue"],
        )
        .properties(height=380)
    )
    rule = alt.Chart(pd.DataFrame({"x": [10]})).mark_rule(strokeDash=[4, 4], color="gray").encode(x="x:Q")
    st.altair_chart(chart + rule, use_container_width=True)


def main():
    st.title("Olist Sales OLAP Dashboard")
    st.caption("Multi-level view of Brazilian e-commerce sales: time, product category, customer state, delivery, and seller performance")

    df = load_data()
    if df.empty:
        st.warning("Could not load warehouse tables. Run `dbt run` in olist_dw/ first.")
        return

    df = apply_filters(df)
    if df.empty:
        st.warning("No data matches the selected filters.")
        return

    tab_overview, tab_customers, tab_delivery, tab_sellers = st.tabs(
        ["📊 Overview", "👥 Customers & Payments", "🚚 Delivery & Reviews", "🏪 Sellers (Pareto)"]
    )

    with tab_overview:
        render_overview_tab(df)

    with tab_customers:
        render_customers_tab()

    with tab_delivery:
        render_delivery_tab()

    with tab_sellers:
        render_sellers_tab()


if __name__ == "__main__":
    main()
