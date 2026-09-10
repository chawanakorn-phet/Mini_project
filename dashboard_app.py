import os
from pathlib import Path
from typing import NamedTuple, Optional, Tuple

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


# --------------------------------------------------------------------------
# Filters — one immutable, hashable object threaded into every query so the
# sidebar controls narrow ALL tabs, not just Overview. A field is None when
# that filter is not narrowing anything (all values selected / full range).
# --------------------------------------------------------------------------
class Filters(NamedTuple):
    start: Optional[str] = None
    end: Optional[str] = None
    categories: Optional[Tuple[str, ...]] = None
    customer_states: Optional[Tuple[str, ...]] = None
    seller_states: Optional[Tuple[str, ...]] = None
    statuses: Optional[Tuple[str, ...]] = None


def _sql_list(values):
    return "(" + ", ".join("'" + str(v).replace("'", "''") + "'" for v in values) + ")"


def item_cte(filters: Filters) -> str:
    """A filtered view of fact_order_items at its own grain, with the three
    dims joined so category / customer-state / seller-state filters apply
    directly at item level (not just 'orders that contain such an item')."""
    conds = []
    if filters.start:
        conds.append(f"f.order_purchase_date >= DATE '{filters.start}'")
    if filters.end:
        conds.append(f"f.order_purchase_date <= DATE '{filters.end}'")
    if filters.statuses is not None:
        conds.append(f"f.order_status IN {_sql_list(filters.statuses)}")
    if filters.categories is not None:
        conds.append(f"dp.category IN {_sql_list(filters.categories)}")
    if filters.customer_states is not None:
        conds.append(f"dc.state IN {_sql_list(filters.customer_states)}")
    if filters.seller_states is not None:
        conds.append(f"ds.state IN {_sql_list(filters.seller_states)}")
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    return f"""
        SELECT f.*
        FROM fact_order_items f
        LEFT JOIN dim_products dp ON dp.product_id = f.product_id
        LEFT JOIN dim_customers dc ON dc.customer_id = f.customer_id
        LEFT JOIN dim_sellers ds ON ds.seller_id = f.seller_id
        {where}
    """


def _run(sql: str) -> pd.DataFrame:
    con = get_connection()
    if not warehouse_ready(con):
        return pd.DataFrame()
    return con.execute(sql).fetchdf()


@st.cache_data
def load_data(filters: Filters):
    sql = f"""
        WITH fi AS ({item_cte(filters)})
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
        FROM fi f
        LEFT JOIN dim_date d ON f.order_purchase_date = d.full_date
        LEFT JOIN (SELECT customer_id, state AS customer_state, city AS customer_city FROM dim_customers) dc
            ON dc.customer_id = f.customer_id
        LEFT JOIN dim_products dp ON dp.product_id = f.product_id
        LEFT JOIN dim_sellers ds ON ds.seller_id = f.seller_id
    """
    df = _run(sql)
    if df.empty:
        return df
    df["order_purchase_date"] = pd.to_datetime(df["order_purchase_date"], errors="coerce")
    df["revenue"] = df["price"].fillna(0)
    df["quantity"] = 1
    return df


@st.cache_data
def load_filter_options():
    """Unfiltered lists for the sidebar multiselects."""
    con = get_connection()
    if not warehouse_ready(con):
        return {}, (None, None)
    opts = {}
    opts["product_category"] = [r[0] for r in con.execute(
        "SELECT DISTINCT category FROM dim_products WHERE category IS NOT NULL ORDER BY 1").fetchall()]
    opts["customer_state"] = [r[0] for r in con.execute(
        "SELECT DISTINCT state FROM dim_customers WHERE state IS NOT NULL ORDER BY 1").fetchall()]
    opts["seller_state"] = [r[0] for r in con.execute(
        "SELECT DISTINCT state FROM dim_sellers WHERE state IS NOT NULL ORDER BY 1").fetchall()]
    opts["order_status"] = [r[0] for r in con.execute(
        "SELECT DISTINCT order_status FROM fact_order_items WHERE order_status IS NOT NULL ORDER BY 1").fetchall()]
    dmin, dmax = con.execute(
        "SELECT MIN(order_purchase_date), MAX(order_purchase_date) FROM fact_order_items").fetchone()
    return opts, (dmin, dmax)


@st.cache_data
def load_hourly(filters: Filters):
    return _run(f"""
        WITH fi AS ({item_cte(filters)})
        SELECT order_purchase_hour AS hour, COUNT(DISTINCT order_id) AS orders, SUM(price) AS revenue
        FROM fi
        WHERE order_purchase_hour IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """)


@st.cache_data
def load_mom_growth(filters: Filters):
    return _run(f"""
        WITH fi AS ({item_cte(filters)}),
        monthly AS (
            SELECT date_trunc('month', order_purchase_date) AS month, SUM(price) AS revenue
            FROM fi
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
    """)


@st.cache_data
def load_distance_vs_review(filters: Filters):
    return _run(f"""
        WITH fi AS ({item_cte(filters)})
        SELECT
            CASE
                WHEN f.buyer_seller_distance_km < 500 THEN '1. < 500 km'
                WHEN f.buyer_seller_distance_km < 1500 THEN '2. 500-1500 km'
                ELSE '3. > 1500 km'
            END AS distance_bucket,
            ROUND(AVG(f.buyer_seller_distance_km), 0) AS avg_km,
            ROUND(AVG(r.review_score), 2) AS avg_review_score,
            COUNT(*) AS n
        FROM fi f
        JOIN fact_order_reviews r ON r.order_id = f.order_id
        WHERE f.buyer_seller_distance_km IS NOT NULL
        GROUP BY 1
        ORDER BY 1
    """)


@st.cache_data
def load_fulfillment_vs_review(filters: Filters):
    return _run(f"""
        WITH fi AS ({item_cte(filters)})
        SELECT
            CASE
                WHEN f.seller_processing_days <= 1 THEN '1. Fast (<=1 day)'
                WHEN f.seller_processing_days <= 3 THEN '2. Medium (2-3 days)'
                ELSE '3. Slow (>3 days)'
            END AS speed_bucket,
            ROUND(AVG(r.review_score), 2) AS avg_review_score,
            COUNT(*) AS n
        FROM fi f
        JOIN fact_order_reviews r ON r.order_id = f.order_id
        WHERE f.seller_processing_days IS NOT NULL AND f.seller_processing_days >= 0
        GROUP BY 1
        ORDER BY 1
    """)


@st.cache_data
def load_repeat_vs_onetime(filters: Filters):
    return _run(f"""
        WITH fi AS ({item_cte(filters)}),
        customer_orders AS (
            SELECT dc.customer_unique_id, f.order_id, SUM(f.price) AS order_value
            FROM fi f
            JOIN dim_customers dc ON dc.customer_id = f.customer_id
            GROUP BY 1, 2
        ),
        customer_summary AS (
            SELECT customer_unique_id, COUNT(DISTINCT order_id) AS n_orders, AVG(order_value) AS avg_order_value
            FROM customer_orders GROUP BY 1
        )
        SELECT
            CASE WHEN n_orders > 1 THEN 'Repeat customer' ELSE 'One-time customer' END AS segment,
            COUNT(*) AS n_customers,
            ROUND(AVG(avg_order_value), 2) AS avg_order_value
        FROM customer_summary
        GROUP BY 1
    """)


@st.cache_data
def load_payment_aov(filters: Filters):
    return _run(f"""
        WITH fi AS ({item_cte(filters)})
        SELECT
            p.payment_type,
            COUNT(DISTINCT p.order_id) AS n_orders,
            ROUND(AVG(p.payment_value), 2) AS avg_payment_value
        FROM fact_order_payments p
        WHERE p.payment_type != 'not_defined'
          AND p.order_id IN (SELECT DISTINCT order_id FROM fi)
        GROUP BY 1
        ORDER BY n_orders DESC
    """)


@st.cache_data
def load_seller_pareto(filters: Filters):
    return _run(f"""
        WITH fi AS ({item_cte(filters)}),
        seller_revenue AS (
            SELECT seller_id, SUM(price) AS revenue FROM fi GROUP BY 1
        ),
        ranked AS (
            SELECT seller_id, revenue,
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
    """)


@st.cache_data
def load_category_quantity(filters: Filters):
    return _run(f"""
        WITH fi AS ({item_cte(filters)})
        SELECT dp.category AS product_category, COUNT(*) AS quantity, SUM(f.price) AS revenue
        FROM fi f
        JOIN dim_products dp ON dp.product_id = f.product_id
        GROUP BY 1
        ORDER BY quantity DESC
        LIMIT 10
    """)


@st.cache_data
def load_rfm_summary(filters: Filters):
    return _run(f"""
        WITH fi AS ({item_cte(filters)}),
        customer_orders AS (
            SELECT dc.customer_unique_id, f.order_id, MAX(f.order_purchase_date) AS order_date, SUM(f.price) AS order_value
            FROM fi f
            JOIN dim_customers dc ON dc.customer_id = f.customer_id
            GROUP BY 1, 2
        ),
        rfm AS (
            SELECT
                customer_unique_id,
                DATE_DIFF('day', MAX(order_date), (SELECT MAX(order_date) FROM customer_orders)) AS recency_days,
                COUNT(DISTINCT order_id) AS frequency,
                SUM(order_value) AS monetary
            FROM customer_orders GROUP BY 1
        ),
        scored AS (SELECT *, NTILE(5) OVER (ORDER BY monetary) AS monetary_quintile FROM rfm)
        SELECT
            monetary_quintile,
            COUNT(*) AS n_customers,
            ROUND(SUM(monetary), 2) AS total_monetary,
            ROUND(100.0 * SUM(monetary) / SUM(SUM(monetary)) OVER (), 1) AS pct_of_revenue,
            ROUND(AVG(recency_days), 0) AS avg_recency_days,
            ROUND(AVG(frequency), 2) AS avg_frequency
        FROM scored
        GROUP BY 1
        ORDER BY monetary_quintile DESC
    """)


@st.cache_data
def load_frequency_buckets(filters: Filters):
    return _run(f"""
        WITH fi AS ({item_cte(filters)}),
        customer_orders AS (
            SELECT dc.customer_unique_id, f.order_id, SUM(f.price) AS order_value
            FROM fi f
            JOIN dim_customers dc ON dc.customer_id = f.customer_id
            GROUP BY 1, 2
        ),
        summary AS (
            SELECT customer_unique_id, COUNT(DISTINCT order_id) AS n_orders, AVG(order_value) AS avg_order_value
            FROM customer_orders GROUP BY 1
        )
        SELECT
            CASE WHEN n_orders = 1 THEN '1. Bought once'
                 WHEN n_orders = 2 THEN '2. Bought twice'
                 ELSE '3. Bought 3+ times' END AS bucket,
            COUNT(*) AS n_customers,
            ROUND(AVG(avg_order_value), 2) AS avg_order_value
        FROM summary
        GROUP BY 1
        ORDER BY bucket
    """)


@st.cache_data
def load_new_customer_growth(filters: Filters):
    return _run(f"""
        WITH fi AS ({item_cte(filters)}),
        first_orders AS (
            SELECT dc.customer_unique_id, dc.state, MIN(f.order_purchase_date) AS first_order_date
            FROM fi f
            JOIN dim_customers dc ON dc.customer_id = f.customer_id
            GROUP BY 1, 2
        ),
        by_period AS (
            SELECT
                state,
                CASE WHEN first_order_date < DATE '2017-10-01' THEN 'first_half' ELSE 'second_half' END AS period,
                COUNT(*) AS n_new
            FROM first_orders
            WHERE first_order_date >= DATE '2017-01-01'
            GROUP BY 1, 2
        )
        SELECT
            state,
            SUM(CASE WHEN period = 'first_half' THEN n_new ELSE 0 END) AS new_customers_early,
            SUM(CASE WHEN period = 'second_half' THEN n_new ELSE 0 END) AS new_customers_recent,
            ROUND(100.0 * (SUM(CASE WHEN period = 'second_half' THEN n_new ELSE 0 END)
                - SUM(CASE WHEN period = 'first_half' THEN n_new ELSE 0 END))
                / NULLIF(SUM(CASE WHEN period = 'first_half' THEN n_new ELSE 0 END), 0), 1) AS growth_pct
        FROM by_period
        GROUP BY 1
        HAVING SUM(CASE WHEN period = 'first_half' THEN n_new ELSE 0 END) >= 20
        ORDER BY growth_pct DESC
        LIMIT 10
    """)


@st.cache_data
def load_lateness_vs_review(filters: Filters):
    return _run(f"""
        WITH fi AS ({item_cte(filters)})
        SELECT
            CASE WHEN f.order_delivered_customer_date > f.order_estimated_delivery_date
                 THEN '1. Late' ELSE '2. On-time' END AS status,
            COUNT(*) AS n,
            ROUND(AVG(r.review_score), 2) AS avg_review_score
        FROM fi f
        JOIN fact_order_reviews r ON r.order_id = f.order_id
        WHERE f.order_delivered_customer_date IS NOT NULL AND f.order_estimated_delivery_date IS NOT NULL
        GROUP BY 1
        ORDER BY 1
    """)


@st.cache_data
def load_freight_ratio(filters: Filters):
    return _run(f"""
        WITH fi AS ({item_cte(filters)})
        SELECT
            dp.category AS product_category,
            ROUND(100.0 * SUM(f.freight_value) / NULLIF(SUM(f.price), 0), 1) AS freight_pct_of_price,
            COUNT(*) AS n
        FROM fi f
        JOIN dim_products dp ON dp.product_id = f.product_id
        GROUP BY 1
        HAVING COUNT(*) >= 30
        ORDER BY freight_pct_of_price DESC
        LIMIT 10
    """)


@st.cache_data
def load_late_routes(filters: Filters):
    return _run(f"""
        WITH fi AS ({item_cte(filters)})
        SELECT
            ds.state AS seller_state,
            dc.state AS customer_state,
            COUNT(*) AS n_orders,
            ROUND(100.0 * SUM(CASE WHEN f.order_delivered_customer_date > f.order_estimated_delivery_date THEN 1 ELSE 0 END)
                / COUNT(*), 1) AS late_pct,
            ROUND(AVG(f.seller_processing_days), 1) AS avg_seller_processing_days,
            ROUND(AVG(f.carrier_transit_days), 1) AS avg_carrier_transit_days
        FROM fi f
        JOIN dim_sellers ds ON ds.seller_id = f.seller_id
        JOIN dim_customers dc ON dc.customer_id = f.customer_id
        WHERE f.order_delivered_customer_date IS NOT NULL AND f.order_estimated_delivery_date IS NOT NULL
        GROUP BY 1, 2
        HAVING COUNT(*) >= 20
        ORDER BY late_pct DESC
        LIMIT 10
    """)


@st.cache_data
def load_category_review(filters: Filters):
    return _run(f"""
        WITH fi AS ({item_cte(filters)})
        SELECT
            dp.category AS product_category,
            SUM(f.price) AS revenue,
            ROUND(AVG(r.review_score), 2) AS avg_review_score,
            COUNT(*) AS n
        FROM fi f
        JOIN dim_products dp ON dp.product_id = f.product_id
        JOIN fact_order_reviews r ON r.order_id = f.order_id
        GROUP BY 1
        HAVING COUNT(*) >= 30
        ORDER BY revenue DESC
        LIMIT 15
    """)


@st.cache_data
def load_product_photos_vs_perf(filters: Filters):
    return _run(f"""
        WITH fi AS ({item_cte(filters)})
        SELECT
            CASE WHEN dp.product_photos_qty <= 1 THEN '1. 0-1 photo'
                 WHEN dp.product_photos_qty <= 3 THEN '2. 2-3 photos'
                 ELSE '3. 4+ photos' END AS photo_bucket,
            ROUND(AVG(r.review_score), 2) AS avg_review_score,
            COUNT(DISTINCT f.order_id) AS n_orders
        FROM fi f
        JOIN dim_products dp ON dp.product_id = f.product_id
        JOIN fact_order_reviews r ON r.order_id = f.order_id
        WHERE dp.product_photos_qty IS NOT NULL
        GROUP BY 1
        ORDER BY 1
    """)


@st.cache_data
def load_product_description_vs_perf(filters: Filters):
    return _run(f"""
        WITH fi AS ({item_cte(filters)})
        SELECT
            CASE WHEN dp.product_description_length <= 300 THEN '1. Short (<=300 chars)'
                 WHEN dp.product_description_length <= 800 THEN '2. Medium (301-800)'
                 ELSE '3. Long (800+)' END AS description_bucket,
            ROUND(AVG(r.review_score), 2) AS avg_review_score,
            COUNT(DISTINCT f.order_id) AS n_orders
        FROM fi f
        JOIN dim_products dp ON dp.product_id = f.product_id
        JOIN fact_order_reviews r ON r.order_id = f.order_id
        WHERE dp.product_description_length IS NOT NULL
        GROUP BY 1
        ORDER BY 1
    """)


@st.cache_data
def load_basket_pairs(filters: Filters):
    return _run(f"""
        WITH fi AS ({item_cte(filters)}),
        order_cats AS (
            SELECT DISTINCT f.order_id, dp.category
            FROM fi f
            JOIN dim_products dp ON dp.product_id = f.product_id
        )
        SELECT
            a.category AS category_a,
            b.category AS category_b,
            COUNT(*) AS n_orders_together
        FROM order_cats a
        JOIN order_cats b ON a.order_id = b.order_id AND a.category < b.category
        GROUP BY 1, 2
        ORDER BY n_orders_together DESC
        LIMIT 10
    """)


def build_sidebar_filters() -> Filters:
    st.sidebar.header("Filters")
    st.sidebar.caption("These narrow every chart on every tab.")

    opts, (dmin, dmax) = load_filter_options()
    if not opts:
        return Filters()

    dmin = pd.to_datetime(dmin).date()
    dmax = pd.to_datetime(dmax).date()
    start_date = st.sidebar.date_input("Start date", dmin, min_value=dmin, max_value=dmax)
    end_date = st.sidebar.date_input("End date", dmax, min_value=dmin, max_value=dmax)

    def pick(col, label):
        values = opts.get(col, [])
        selected = st.sidebar.multiselect(label, values, default=values)
        return None if set(selected) == set(values) else tuple(selected)

    return Filters(
        start=start_date.isoformat(),
        end=end_date.isoformat(),
        categories=pick("product_category", "Product Category"),
        customer_states=pick("customer_state", "Customer State"),
        seller_states=pick("seller_state", "Seller State"),
        statuses=pick("order_status", "Order Status"),
    )


def build_time_chart(df, level):
    group_col = {"year": "year", "quarter": "quarter", "month": "month_name"}.get(level, "year")
    grouped = (
        df.groupby(group_col, as_index=False)
        .agg(revenue=("revenue", "sum"), orders=("order_id", "nunique"))
        .rename(columns={group_col: "label"})
    )
    return grouped.sort_values("label")


def build_category_chart(df):
    return (
        df.groupby("product_category", as_index=False)
        .agg(revenue=("revenue", "sum"), orders=("order_id", "nunique"))
        .sort_values("revenue", ascending=False)
        .head(10)
    )


def build_state_chart(df):
    return (
        df.groupby("customer_state", as_index=False)
        .agg(revenue=("revenue", "sum"), orders=("order_id", "nunique"))
        .sort_values("revenue", ascending=False)
        .head(10)
    )


def render_overview_tab(df, filters):
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
    st.altair_chart(
        alt.Chart(time_df).mark_line(point=True).encode(
            x=alt.X("label:N", title=time_level), y=alt.Y("revenue:Q"),
            tooltip=["label:N", "revenue:Q", "orders:Q"],
        ).properties(height=320),
        use_container_width=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Top 10 Product Categories by Revenue")
        st.altair_chart(
            alt.Chart(category_df).mark_bar().encode(
                x=alt.X("product_category:N", sort="-y"), y="revenue:Q",
                tooltip=["product_category:N", "revenue:Q"],
            ).properties(height=350),
            use_container_width=True,
        )
        st.caption("Q1: same top 10, ranked by quantity sold instead — does the ranking change?")
        qty_df = load_category_quantity(filters)
        if not qty_df.empty:
            st.altair_chart(
                alt.Chart(qty_df).mark_bar(color="#8E6C8A").encode(
                    x=alt.X("product_category:N", sort="-y"), y="quantity:Q",
                    tooltip=["product_category:N", "quantity:Q", "revenue:Q"],
                ).properties(height=300),
                use_container_width=True,
            )

    with col2:
        st.subheader("Top 10 Customer States by Revenue")
        st.altair_chart(
            alt.Chart(state_df).mark_bar().encode(
                x=alt.X("customer_state:N", sort="-y"), y="revenue:Q",
                tooltip=["customer_state:N", "revenue:Q"],
            ).properties(height=350),
            use_container_width=True,
        )

    st.subheader("Detail table")
    st.dataframe(df.head(200), use_container_width=True)


def render_customers_tab(filters):
    st.caption("Answers Q2 (peak order hour + MoM growth), Q3 (AOV by payment type), Q4 (RFM), Q5 (frequency), Q6 (new markets)")

    hourly_df = load_hourly(filters)
    mom_df = load_mom_growth(filters)
    payment_df = load_payment_aov(filters)
    repeat_df = load_repeat_vs_onetime(filters)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Orders by hour of day")
        if not hourly_df.empty:
            st.altair_chart(
                alt.Chart(hourly_df).mark_bar().encode(
                    x=alt.X("hour:O", title="Hour of day"), y=alt.Y("orders:Q"),
                    tooltip=["hour", "orders", "revenue"],
                ).properties(height=300),
                use_container_width=True,
            )

    with col2:
        st.subheader("Month-over-month revenue growth")
        st.caption("From 2017-01 onward — Olist's 2016 launch pilot had too few orders for a meaningful % change")
        if not mom_df.empty:
            mom_df = mom_df.copy()
            mom_df["month"] = pd.to_datetime(mom_df["month"]).dt.strftime("%Y-%m")
            st.altair_chart(
                alt.Chart(mom_df).mark_bar().encode(
                    x=alt.X("month:N", sort=None),
                    y=alt.Y("mom_pct:Q", title="MoM % change"),
                    color=alt.condition(alt.datum.mom_pct > 0, alt.value("#2E7D32"), alt.value("#C62828")),
                    tooltip=["month", "revenue", "mom_pct"],
                ).properties(height=300),
                use_container_width=True,
            )

    col3, col4 = st.columns(2)
    with col3:
        st.subheader("Avg order value by payment type")
        if not payment_df.empty:
            st.altair_chart(
                alt.Chart(payment_df).mark_bar().encode(
                    x=alt.X("payment_type:N", sort="-y"), y="avg_payment_value:Q",
                    tooltip=["payment_type", "n_orders", "avg_payment_value"],
                ).properties(height=300),
                use_container_width=True,
            )

    with col4:
        st.subheader("Repeat vs one-time customers")
        if not repeat_df.empty:
            st.dataframe(repeat_df, use_container_width=True, hide_index=True)
            total = repeat_df["n_customers"].sum()
            repeat_row = repeat_df[repeat_df["segment"] == "Repeat customer"]
            repeat_pct = 100.0 * repeat_row["n_customers"].iloc[0] / total if total and not repeat_row.empty else 0.0
            st.metric("Repeat customer rate", f"{repeat_pct:.1f}%")

    st.divider()
    col5, col6 = st.columns(2)
    with col5:
        st.subheader("RFM: revenue share by monetary quintile")
        st.caption("Q4 — quintile 5 = top 20% of customers by total spend")
        rfm_df = load_rfm_summary(filters)
        if not rfm_df.empty:
            top_row = rfm_df[rfm_df["monetary_quintile"] == 5]
            if not top_row.empty:
                st.metric("Revenue share from top 20% of customers", f"{top_row['pct_of_revenue'].iloc[0]:.1f}%")
            st.altair_chart(
                alt.Chart(rfm_df).mark_bar().encode(
                    x=alt.X("monetary_quintile:O", title="Monetary quintile (5 = highest spend)"),
                    y=alt.Y("pct_of_revenue:Q", title="% of total revenue"),
                    tooltip=["monetary_quintile", "n_customers", "total_monetary", "pct_of_revenue", "avg_recency_days", "avg_frequency"],
                ).properties(height=300),
                use_container_width=True,
            )

    with col6:
        st.subheader("Avg order value by purchase frequency")
        st.caption("Q5 — how much more do frequent buyers spend per order?")
        freq_df = load_frequency_buckets(filters)
        if not freq_df.empty:
            st.altair_chart(
                alt.Chart(freq_df).mark_bar().encode(
                    x=alt.X("bucket:N", sort=None), y="avg_order_value:Q",
                    tooltip=["bucket", "n_customers", "avg_order_value"],
                ).properties(height=300),
                use_container_width=True,
            )

    st.subheader("Fastest-growing new-customer markets")
    st.caption("Q6 — states ranked by % growth in new customers, early 2017 vs late 2017/2018 (min. 20 early customers)")
    growth_df = load_new_customer_growth(filters)
    if not growth_df.empty:
        st.altair_chart(
            alt.Chart(growth_df).mark_bar().encode(
                x=alt.X("state:N", sort="-y"), y="growth_pct:Q",
                tooltip=["state", "new_customers_early", "new_customers_recent", "growth_pct"],
            ).properties(height=320),
            use_container_width=True,
        )
    else:
        st.info("No new-customer growth to show for the current filters.")


def render_delivery_tab(filters):
    st.caption("Answers Q10 (distance vs review), Q15 (fulfillment speed vs review)")

    distance_df = load_distance_vs_review(filters)
    fulfillment_df = load_fulfillment_vs_review(filters)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Buyer-seller distance vs review score")
        if not distance_df.empty:
            st.altair_chart(
                alt.Chart(distance_df).mark_bar().encode(
                    x=alt.X("distance_bucket:N", sort=None),
                    y=alt.Y("avg_review_score:Q", scale=alt.Scale(domain=[0, 5])),
                    tooltip=["distance_bucket", "avg_km", "avg_review_score", "n"],
                ).properties(height=320),
                use_container_width=True,
            )
        else:
            st.info("No distance data for the current filters.")

    with col2:
        st.subheader("Seller fulfillment speed vs review score")
        if not fulfillment_df.empty:
            st.altair_chart(
                alt.Chart(fulfillment_df).mark_bar().encode(
                    x=alt.X("speed_bucket:N", sort=None),
                    y=alt.Y("avg_review_score:Q", scale=alt.Scale(domain=[0, 5])),
                    tooltip=["speed_bucket", "avg_review_score", "n"],
                ).properties(height=320),
                use_container_width=True,
            )


def render_sellers_tab(filters):
    st.caption("Answers Q14: is platform revenue concentrated in the top 10% of sellers (Pareto 80/20)?")

    pareto_df = load_seller_pareto(filters)
    if pareto_df.empty:
        st.info("No seller data for the current filters.")
        return

    top10_row = pareto_df[pareto_df["pct_sellers"] >= 10].head(1)
    top10_share = top10_row["cum_pct_revenue"].iloc[0] if not top10_row.empty else None
    if top10_share is not None:
        st.metric("Revenue share held by top 10% of sellers", f"{top10_share:.1f}%")

    chart = alt.Chart(pareto_df).mark_line().encode(
        x=alt.X("pct_sellers:Q", title="% of sellers (ranked by revenue)"),
        y=alt.Y("cum_pct_revenue:Q", title="Cumulative % of revenue"),
        tooltip=["pct_sellers", "cum_pct_revenue"],
    ).properties(height=380)
    rule = alt.Chart(pd.DataFrame({"x": [10]})).mark_rule(strokeDash=[4, 4], color="gray").encode(x="x:Q")
    st.altair_chart(chart + rule, use_container_width=True)


def render_routes_tab(filters):
    st.caption("Answers Q7 (late vs on-time review impact), Q8 (freight/price ratio), Q9 (late delivery routes + who's at fault)")

    lateness_df = load_lateness_vs_review(filters)
    freight_df = load_freight_ratio(filters)
    routes_df = load_late_routes(filters)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("On-time vs late delivery: review score impact")
        if not lateness_df.empty:
            st.altair_chart(
                alt.Chart(lateness_df).mark_bar().encode(
                    x=alt.X("status:N", sort=None),
                    y=alt.Y("avg_review_score:Q", scale=alt.Scale(domain=[0, 5])),
                    tooltip=["status", "n", "avg_review_score"],
                ).properties(height=300),
                use_container_width=True,
            )

    with col2:
        st.subheader("Freight as % of price, by category")
        if not freight_df.empty:
            st.altair_chart(
                alt.Chart(freight_df).mark_bar().encode(
                    x=alt.X("product_category:N", sort="-y"), y="freight_pct_of_price:Q",
                    tooltip=["product_category", "freight_pct_of_price", "n"],
                ).properties(height=300),
                use_container_width=True,
            )

    st.subheader("Top 10 seller→customer routes by late-delivery rate")
    st.caption("avg_seller_processing_days = time to hand off to carrier (seller's fault zone); avg_carrier_transit_days = time in transit (carrier's fault zone)")
    if not routes_df.empty:
        st.dataframe(routes_df, use_container_width=True, hide_index=True)
    else:
        st.info("Not enough data to compute route-level lateness for the current filters (needs at least 20 orders per route).")


def render_products_tab(filters):
    st.caption("Answers Q11 (revenue vs review by category), Q12 (product-page attributes vs review), Q13 (Market Basket Analysis)")

    category_review_df = load_category_review(filters)
    photos_df = load_product_photos_vs_perf(filters)
    description_df = load_product_description_vs_perf(filters)
    basket_df = load_basket_pairs(filters)

    st.subheader("Revenue vs average review score, by category")
    if not category_review_df.empty:
        base = alt.Chart(category_review_df).encode(x=alt.X("product_category:N", sort="-y"))
        bar = base.mark_bar(color="#4C78A8").encode(y=alt.Y("revenue:Q", title="Revenue"), tooltip=["product_category", "revenue", "avg_review_score", "n"])
        line = base.mark_line(color="#E45756", point=True).encode(y=alt.Y("avg_review_score:Q", title="Avg review score", scale=alt.Scale(domain=[0, 5])))
        st.altair_chart(alt.layer(bar, line).resolve_scale(y="independent").properties(height=380), use_container_width=True)
        st.caption("Bars = revenue (left scale) · Red line = avg review score (right scale, 0-5)")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Product photos vs review score")
        if not photos_df.empty:
            st.altair_chart(
                alt.Chart(photos_df).mark_bar().encode(
                    x=alt.X("photo_bucket:N", sort=None),
                    y=alt.Y("avg_review_score:Q", scale=alt.Scale(domain=[0, 5])),
                    tooltip=["photo_bucket", "avg_review_score", "n_orders"],
                ).properties(height=300),
                use_container_width=True,
            )

    with col2:
        st.subheader("Product description length vs review score")
        if not description_df.empty:
            st.altair_chart(
                alt.Chart(description_df).mark_bar().encode(
                    x=alt.X("description_bucket:N", sort=None),
                    y=alt.Y("avg_review_score:Q", scale=alt.Scale(domain=[0, 5])),
                    tooltip=["description_bucket", "avg_review_score", "n_orders"],
                ).properties(height=300),
                use_container_width=True,
            )

    st.subheader("Market Basket Analysis: top category pairs bought together")
    if not basket_df.empty:
        st.dataframe(basket_df, use_container_width=True, hide_index=True)
    else:
        st.info("No co-purchased category pairs for the current filters.")


def main():
    st.title("Olist Sales OLAP Dashboard")
    st.caption("Multi-level view of Brazilian e-commerce sales: time, product category, customer state, delivery, and seller performance")

    filters = build_sidebar_filters()
    df = load_data(filters)
    if df.empty:
        st.warning("No data matches the selected filters.")
        return

    tab_overview, tab_customers, tab_delivery, tab_sellers, tab_routes, tab_products = st.tabs(
        [
            "📊 Overview", "👥 Customers & Payments", "🚚 Delivery & Reviews", "🏪 Sellers (Pareto)",
            "🌍 Delivery Routes", "📦 Products & Basket",
        ]
    )

    with tab_overview:
        render_overview_tab(df, filters)
    with tab_customers:
        render_customers_tab(filters)
    with tab_delivery:
        render_delivery_tab(filters)
    with tab_sellers:
        render_sellers_tab(filters)
    with tab_routes:
        render_routes_tab(filters)
    with tab_products:
        render_products_tab(filters)


if __name__ == "__main__":
    main()
