"""Olist marketplace — interactive OLAP dashboard.

Written for a general business audience, not for engineers:
  * every control and column is labelled in plain language, never with a raw
    table or column name;
  * every chart carries a one-line "how to read this" note and says which of
    the 15 business questions (README section 2) it answers;
  * the sidebar filters narrow EVERY tab at once, and they only ever read from
    the dimension tables, exactly as the brief requires.

All data comes from the star-schema tables in olist_dw/dev.duckdb
(dim_* / fact_*). Nothing here touches the staging layer or the raw CSVs.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import NamedTuple, Optional, Tuple

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

from warehouse import ensure_warehouse_built

PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "olist_dw" / "dev.duckdb"

st.set_page_config(page_title="Olist Marketplace Dashboard", page_icon="📦", layout="wide")

# On a fresh checkout (e.g. Streamlit Cloud) dev.duckdb does not exist yet;
# build it once by shelling out to dbt.
with st.spinner("Preparing the data warehouse (first run only)…"):
    _ok, _log = ensure_warehouse_built()
if not _ok and not DB_PATH.exists():
    st.error("Could not build the data warehouse. `dbt run` output:")
    st.code(_log or "(no output)")
    st.stop()


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------
@st.cache_resource
def get_connection() -> Optional[duckdb.DuckDBPyConnection]:
    if not DB_PATH.exists():
        return None
    con = duckdb.connect(str(DB_PATH), read_only=True)
    # The staging models are views over the CSVs, which DuckDB resolves against
    # the process working directory. Point it at olist_dw/ so those views work
    # no matter where the app is launched from (locally or on Streamlit Cloud).
    con.execute(f"SET file_search_path = '{(PROJECT_ROOT / 'olist_dw').as_posix()}'")
    return con


REQUIRED_TABLES = {
    "dim_date", "dim_geography", "dim_customers", "dim_sellers", "dim_products",
    "dim_order_status", "dim_payment_type",
    "fact_order_items", "fact_order_payments", "fact_order_reviews",
}


def warehouse_ready(con) -> bool:
    if con is None:
        return False
    have = {r[0] for r in con.execute(
        "select table_name from information_schema.tables where table_schema='main'"
    ).fetchall()}
    return REQUIRED_TABLES.issubset(have)


def run_sql(sql: str) -> pd.DataFrame:
    con = get_connection()
    if not warehouse_ready(con):
        return pd.DataFrame()
    return con.execute(sql).fetchdf()


def _sql_str_list(values) -> str:
    """Render a Python list as a SQL IN(...) body, safely quoted."""
    if not values:
        return "NULL"  # `col IN (NULL)` matches nothing — the caller wants an empty result
    return ", ".join("'" + str(v).replace("'", "''") + "'" for v in values)


# ---------------------------------------------------------------------------
# Filters — one immutable object threaded into every query so the sidebar
# controls narrow ALL tabs. A field is None when it is not narrowing anything
# (the whole range / every value selected).
# ---------------------------------------------------------------------------
class Filters(NamedTuple):
    start: Optional[str] = None
    end: Optional[str] = None
    regions: Optional[Tuple[str, ...]] = None
    customer_states: Optional[Tuple[str, ...]] = None
    categories: Optional[Tuple[str, ...]] = None
    payment_labels: Optional[Tuple[str, ...]] = None


@st.cache_data(ttl=600)
def load_filter_options() -> dict:
    con = get_connection()
    if not warehouse_ready(con):
        return {}
    g = lambda s: [r[0] for r in con.execute(s).fetchall()]
    return {
        "regions": g("select distinct region from dim_geography "
                     "where region <> 'Unknown' order by 1"),
        "customer_states": g("select distinct state from dim_customers "
                             "where state <> 'XX' order by 1"),
        "categories": g("select distinct category from dim_products "
                        "where category <> 'unknown' order by 1"),
        "payment_labels": g("select distinct payment_label from dim_payment_type "
                            "where is_valid_method order by 1"),
    }


@st.cache_data(ttl=120)
def load_date_bounds() -> Tuple[Optional[date], Optional[date]]:
    con = get_connection()
    if not warehouse_ready(con):
        return None, None
    row = con.execute("""
        select min(d.full_date), max(d.full_date)
        from fact_order_items f
        join dim_date d on d.date_key = f.purchase_date_key
        where d.date_key <> -1
    """).fetchone()
    return row[0], row[1]


# ---------------------------------------------------------------------------
# Reusable pre-joined item view. Every "sales" chart starts from this CTE so
# that the filter logic lives in exactly one place.
# ---------------------------------------------------------------------------
def item_view(f: Filters) -> str:
    """A SELECT that returns fact_order_items rows already joined to every
    dimension a chart might slice by, with the active filters applied."""
    conds = ["1 = 1"]
    if f.start:
        conds.append(f"dd.full_date >= DATE '{f.start}'")
    if f.end:
        conds.append(f"dd.full_date <= DATE '{f.end}'")
    if f.regions is not None:
        conds.append(f"gc.region IN ({_sql_str_list(f.regions)})")
    if f.customer_states is not None:
        conds.append(f"dc.state IN ({_sql_str_list(f.customer_states)})")
    if f.categories is not None:
        conds.append(f"dp.category IN ({_sql_str_list(f.categories)})")
    where = " AND ".join(conds)
    return f"""
        SELECT
            f.order_id,
            f.price,
            f.freight_value,
            f.total_item_value,
            f.delivery_days,
            f.seller_processing_days,
            f.carrier_transit_days,
            f.delivery_delay_days,
            f.buyer_seller_distance_km,
            f.is_late_delivery,
            f.purchase_hour,
            dd.full_date        AS purchase_date,
            dd.year             AS purchase_year,
            dd.year_month       AS purchase_year_month,
            dp.category         AS product_category,
            dp.size_band        AS product_size_band,
            dc.customer_unique_id,
            dc.state            AS customer_state,
            gc.region           AS customer_region,
            dos.status_label    AS order_status,
            dos.lifecycle_step  AS status_step
        FROM fact_order_items f
        JOIN dim_date         dd  ON dd.date_key         = f.purchase_date_key
        JOIN dim_products     dp  ON dp.product_key       = f.product_key
        JOIN dim_customers    dc  ON dc.customer_key      = f.customer_key
        JOIN dim_geography    gc  ON gc.geography_key     = f.customer_geography_key
        JOIN dim_order_status dos ON dos.order_status_key = f.order_status_key
        WHERE {where}
    """


def order_id_filter_cte(f: Filters) -> str:
    """The set of order_ids that pass the sales-side filters — used to keep the
    payments and reviews tabs in step with the same sidebar selection."""
    return f"WITH kept_orders AS (SELECT DISTINCT order_id FROM ({item_view(f)}))"


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
def build_sidebar_filters() -> Filters:
    st.sidebar.header("Filters")
    st.sidebar.caption("These narrow every chart on every tab. "
                       "All options come straight from the dimension tables.")

    opts = load_filter_options()
    dmin, dmax = load_date_bounds()
    if not opts or dmin is None:
        return Filters()

    dmin, dmax = pd.to_datetime(dmin).date(), pd.to_datetime(dmax).date()

    years = [str(y) for y in range(dmin.year, dmax.year + 1)]
    preset = st.sidebar.radio("Time period", ["All time"] + years + ["Custom"],
                              horizontal=True)
    if preset == "All time":
        start, end = dmin, dmax
    elif preset == "Custom":
        lo, hi = date(dmin.year, 1, 1), date(dmax.year, 12, 31)
        start = st.sidebar.date_input("From", dmin, min_value=lo, max_value=hi)
        end = st.sidebar.date_input("To", dmax, min_value=lo, max_value=hi)
    else:
        y = int(preset)
        start = max(dmin, date(y, 1, 1))
        end = min(dmax, date(y, 12, 31))
    if start > end:
        st.sidebar.warning("‘From’ is after ‘To’ — swapped.")
        start, end = end, start

    def multi(label, key, help_text):
        values = opts.get(key, [])
        picked = st.sidebar.multiselect(label, values, default=values, help=help_text)
        return None if set(picked) == set(values) else tuple(picked)

    return Filters(
        start=start.isoformat(),
        end=end.isoformat(),
        regions=multi("Customer region", "regions",
                      "Brazil's five official regions (from dim_geography)."),
        customer_states=multi("Customer state", "customer_states",
                              "Two-letter state code (from dim_customers)."),
        categories=multi("Product category", "categories",
                         "English category name (from dim_products)."),
        payment_labels=multi("Payment method", "payment_labels",
                             "Only affects the Payments tab (from dim_payment_type)."),
    )


def active_filter_summary(f: Filters) -> str:
    bits = [f"{f.start} → {f.end}"]
    for name, val in [("regions", f.regions), ("states", f.customer_states),
                      ("categories", f.categories), ("payment methods", f.payment_labels)]:
        if val is not None:
            bits.append(f"{len(val)} {name}")
    return " · ".join(bits)


# ---------------------------------------------------------------------------
# Small chart helpers
# ---------------------------------------------------------------------------
def brl(x) -> str:
    try:
        return f"R$ {x:,.0f}"
    except (TypeError, ValueError):
        return "–"


def explain(text: str):
    """One-line 'how to read this chart' note, styled consistently."""
    st.caption("📖 " + text)


def empty_note():
    st.info("No data matches the current filters. Widen the selection in the sidebar.")


# ---------------------------------------------------------------------------
# TAB 1 — Sales overview
# ---------------------------------------------------------------------------
def tab_sales(f: Filters):
    iv = item_view(f)

    kpis = run_sql(f"""
        WITH i AS ({iv})
        SELECT
            COALESCE(SUM(price), 0)                AS revenue,
            COALESCE(SUM(freight_value), 0)        AS freight,
            COUNT(DISTINCT order_id)              AS orders,
            COUNT(*)                              AS items
        FROM i
    """)
    if kpis.empty or kpis.loc[0, "orders"] == 0:
        empty_note(); return
    r = kpis.iloc[0]
    aov = r.revenue / r.orders if r.orders else 0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Revenue (products)", brl(r.revenue))
    c2.metric("Freight charged", brl(r.freight))
    c3.metric("Orders", f"{int(r.orders):,}")
    c4.metric("Average order value", brl(aov))

    st.divider()

    # Monthly revenue trend --------------------------------------------------
    st.subheader("Revenue by month")
    explain("Each bar is one calendar month of product revenue. Use it to see the "
            "growth trend and the seasonal peak. — Business question 2")
    monthly = run_sql(f"""
        WITH i AS ({iv})
        SELECT purchase_year_month AS month,
               ROUND(SUM(price), 2) AS revenue,
               COUNT(DISTINCT order_id) AS orders
        FROM i GROUP BY 1 ORDER BY 1
    """)
    if monthly.empty:
        empty_note()
    else:
        st.altair_chart(
            alt.Chart(monthly).mark_bar().encode(
                x=alt.X("month:O", title="Month", axis=alt.Axis(labelAngle=-45)),
                y=alt.Y("revenue:Q", title="Revenue (R$)"),
                tooltip=[alt.Tooltip("month:O", title="Month"),
                         alt.Tooltip("revenue:Q", title="Revenue (R$)", format=",.0f"),
                         alt.Tooltip("orders:Q", title="Orders", format=",")],
            ).properties(height=300),
            use_container_width=True,
        )

    col1, col2 = st.columns(2)

    # Top categories -------------------------------------------------------
    with col1:
        st.subheader("Top 10 categories by revenue")
        explain("The categories that bring in the most product revenue. "
                "Longer bar = more money. — Business question 1")
        cats = run_sql(f"""
            WITH i AS ({iv})
            SELECT product_category AS category,
                   ROUND(SUM(price), 2) AS revenue,
                   COUNT(*) AS items
            FROM i GROUP BY 1 ORDER BY revenue DESC LIMIT 10
        """)
        if cats.empty:
            empty_note()
        else:
            st.altair_chart(
                alt.Chart(cats).mark_bar().encode(
                    x=alt.X("revenue:Q", title="Revenue (R$)"),
                    y=alt.Y("category:N", sort="-x", title=None),
                    tooltip=[alt.Tooltip("category:N", title="Category"),
                             alt.Tooltip("revenue:Q", title="Revenue (R$)", format=",.0f"),
                             alt.Tooltip("items:Q", title="Items sold", format=",")],
                ).properties(height=320),
                use_container_width=True,
            )

    # Revenue by region --------------------------------------------------
    with col2:
        st.subheader("Revenue by region")
        explain("How product revenue splits across Brazil's five regions. "
                "The Southeast (São Paulo, Rio) usually dominates. — Business question 4")
        reg = run_sql(f"""
            WITH i AS ({iv})
            SELECT customer_region AS region,
                   ROUND(SUM(price), 2) AS revenue,
                   COUNT(DISTINCT order_id) AS orders
            FROM i WHERE customer_region <> 'Unknown' GROUP BY 1 ORDER BY revenue DESC
        """)
        if reg.empty:
            empty_note()
        else:
            st.altair_chart(
                alt.Chart(reg).mark_arc(innerRadius=60).encode(
                    theta=alt.Theta("revenue:Q"),
                    color=alt.Color("region:N", title="Region"),
                    tooltip=[alt.Tooltip("region:N", title="Region"),
                             alt.Tooltip("revenue:Q", title="Revenue (R$)", format=",.0f"),
                             alt.Tooltip("orders:Q", title="Orders", format=",")],
                ).properties(height=320),
                use_container_width=True,
            )

    st.divider()

    # Average price per item, by category ------------------------------------
    st.subheader("Average price per item, by category (top 12)")
    explain("Not total revenue, but the typical price tag of one item in each "
            "category — with how many were sold. Tall bar + short 'items sold' = a "
            "high-ticket, low-volume category. — Business question 3")
    avgp = run_sql(f"""
        WITH i AS ({iv})
        SELECT product_category AS category,
               COUNT(*) AS items_sold,
               ROUND(AVG(price), 2) AS avg_price
        FROM i GROUP BY 1 HAVING COUNT(*) >= 30
        ORDER BY avg_price DESC LIMIT 12
    """)
    if avgp.empty:
        empty_note()
    else:
        st.altair_chart(
            alt.Chart(avgp).mark_bar().encode(
                x=alt.X("avg_price:Q", title="Average price per item (R$)"),
                y=alt.Y("category:N", sort="-x", title=None),
                tooltip=[alt.Tooltip("category:N", title="Category"),
                         alt.Tooltip("avg_price:Q", title="Avg price (R$)", format=",.2f"),
                         alt.Tooltip("items_sold:Q", title="Items sold", format=",")],
            ).properties(height=340),
            use_container_width=True,
        )


# ---------------------------------------------------------------------------
# TAB 2 — Customers
# ---------------------------------------------------------------------------
def tab_customers(f: Filters):
    iv = item_view(f)

    st.subheader("One-time vs repeat customers")
    explain("Left: how many distinct people bought once vs more than once. "
            "Right: how much revenue each group is worth. A big revenue share from "
            "a small repeat group is the classic 80/20 pattern. — Business question 5")
    grp = run_sql(f"""
        WITH i AS ({iv}),
        per_person AS (
            SELECT customer_unique_id,
                   COUNT(DISTINCT order_id) AS orders,
                   SUM(price) AS revenue
            FROM i GROUP BY 1
        )
        SELECT CASE WHEN orders = 1 THEN 'Bought once' ELSE 'Bought again (2+)' END AS grp,
               COUNT(*) AS customers,
               ROUND(SUM(revenue), 2) AS revenue
        FROM per_person GROUP BY 1
    """)
    if grp.empty:
        empty_note(); return
    c1, c2 = st.columns(2)
    with c1:
        st.altair_chart(
            alt.Chart(grp).mark_bar().encode(
                x=alt.X("grp:N", title=None),
                y=alt.Y("customers:Q", title="Customers"),
                color=alt.Color("grp:N", legend=None),
                tooltip=[alt.Tooltip("grp:N", title="Group"),
                         alt.Tooltip("customers:Q", title="Customers", format=",")],
            ).properties(height=280),
            use_container_width=True,
        )
    with c2:
        st.altair_chart(
            alt.Chart(grp).mark_bar().encode(
                x=alt.X("grp:N", title=None),
                y=alt.Y("revenue:Q", title="Revenue (R$)"),
                color=alt.Color("grp:N", legend=None),
                tooltip=[alt.Tooltip("grp:N", title="Group"),
                         alt.Tooltip("revenue:Q", title="Revenue (R$)", format=",.0f")],
            ).properties(height=280),
            use_container_width=True,
        )
    repeat = grp.loc[grp["grp"].str.startswith("Bought again")]
    if not repeat.empty:
        share = 100 * repeat["revenue"].iloc[0] / grp["revenue"].sum()
        pct_cust = 100 * repeat["customers"].iloc[0] / grp["customers"].sum()
        st.markdown(f"**Repeat customers are {pct_cust:.1f}% of buyers but "
                    f"{share:.1f}% of revenue.**")

    st.divider()

    st.subheader("RFM — where the money sits")
    explain("Customers split into five equal groups by total spend (quintile 5 = the "
            "top fifth). For each group: how many customers, how often they buy "
            "(frequency), and what share of all revenue they bring. — Business question 7")
    rfm = run_sql(f"""
        WITH i AS ({iv}),
        per_person AS (
            SELECT customer_unique_id,
                   COUNT(DISTINCT order_id) AS frequency,
                   SUM(price) AS monetary
            FROM i GROUP BY 1
        ),
        scored AS (
            SELECT frequency, monetary,
                   NTILE(5) OVER (ORDER BY monetary) AS quintile
            FROM per_person
        )
        SELECT quintile,
               COUNT(*) AS customers,
               ROUND(AVG(frequency), 2) AS avg_frequency,
               ROUND(100.0 * SUM(monetary) / SUM(SUM(monetary)) OVER (), 1) AS pct_of_revenue
        FROM scored GROUP BY 1 ORDER BY quintile DESC
    """)
    if rfm.empty:
        empty_note()
    else:
        rfm["label"] = "Q" + rfm["quintile"].astype(str)
        st.altair_chart(
            alt.Chart(rfm).mark_bar().encode(
                x=alt.X("label:N", sort=list(rfm.sort_values("quintile")["label"]),
                        title="Spend quintile (Q5 = top fifth)", axis=alt.Axis(labelAngle=0)),
                y=alt.Y("pct_of_revenue:Q", title="Share of total revenue (%)"),
                color=alt.Color("pct_of_revenue:Q", legend=None, scale=alt.Scale(scheme="blues")),
                tooltip=[alt.Tooltip("label:N", title="Quintile"),
                         alt.Tooltip("customers:Q", title="Customers", format=","),
                         alt.Tooltip("avg_frequency:Q", title="Avg orders / customer"),
                         alt.Tooltip("pct_of_revenue:Q", title="% of revenue")],
            ).properties(height=300),
            use_container_width=True,
        )
        top = rfm.loc[rfm["quintile"] == 5]
        if not top.empty:
            st.markdown(f"**The top-spending 20% of customers bring "
                        f"{top['pct_of_revenue'].iloc[0]:.1f}% of all revenue.**")


# ---------------------------------------------------------------------------
# TAB 3 — Delivery
# ---------------------------------------------------------------------------
def tab_delivery(f: Filters):
    iv = item_view(f)

    parts = run_sql(f"""
        WITH i AS ({iv})
        SELECT
            ROUND(AVG(delivery_days), 1)           AS total_days,
            ROUND(AVG(seller_processing_days), 1)  AS seller_days,
            ROUND(AVG(carrier_transit_days), 1)    AS carrier_days,
            ROUND(100.0 * AVG(is_late_delivery), 1) AS late_rate
        FROM i
        WHERE delivery_days IS NOT NULL
    """)
    if parts.empty or pd.isna(parts.loc[0, "total_days"]):
        empty_note(); return
    p = parts.iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Avg delivery time", f"{p.total_days:.1f} days")
    c2.metric("… seller prepares", f"{p.seller_days:.1f} days")
    c3.metric("… carrier in transit", f"{p.carrier_days:.1f} days")
    c4.metric("Late vs promised", f"{p.late_rate:.1f}%")
    explain("The delivery clock split into the two stages a marketplace can act on: "
            "how long the seller takes to hand the parcel over, and how long the "
            "carrier takes to move it. — Business question 10")

    st.divider()

    st.subheader("Seller preparation time by state")
    explain("Average days the seller takes to hand a parcel to the carrier, by the "
            "seller's home state (states with at least 50 shipped items). Tall bar = "
            "slower sellers there. — Business question 9")
    sp = run_sql(f"""
        {order_id_filter_cte(f)}
        SELECT ds.state AS seller_state,
               COUNT(*) AS items_shipped,
               ROUND(AVG(f.seller_processing_days), 1) AS avg_processing_days
        FROM fact_order_items f
        JOIN dim_sellers ds ON ds.seller_key = f.seller_key
        WHERE f.seller_processing_days IS NOT NULL
          AND ds.seller_id <> 'unknown'
          AND f.order_id IN (SELECT order_id FROM kept_orders)
        GROUP BY 1 HAVING COUNT(*) >= 50
        ORDER BY avg_processing_days DESC
    """)
    if sp.empty:
        empty_note()
    else:
        st.altair_chart(
            alt.Chart(sp).mark_bar().encode(
                x=alt.X("seller_state:N", sort="-y", title="Seller state",
                        axis=alt.Axis(labelAngle=0)),
                y=alt.Y("avg_processing_days:Q", title="Avg preparation time (days)"),
                tooltip=[alt.Tooltip("seller_state:N", title="Seller state"),
                         alt.Tooltip("avg_processing_days:Q", title="Avg prep days"),
                         alt.Tooltip("items_shipped:Q", title="Items shipped", format=",")],
            ).properties(height=300),
            use_container_width=True,
        )

    st.divider()

    st.subheader("Late-delivery rate by region")
    explain("Share of parcels that arrived after the promised date, per region. "
            "Higher bar = more broken promises there. — Business question 10")
    late = run_sql(f"""
        WITH i AS ({iv})
        SELECT customer_region AS region,
               COUNT(*) AS delivered_items,
               ROUND(100.0 * AVG(is_late_delivery), 1) AS late_rate_pct,
               ROUND(AVG(CASE WHEN is_late_delivery = 1 THEN delivery_delay_days END), 1) AS avg_days_late
        FROM i
        WHERE is_late_delivery IS NOT NULL AND customer_region <> 'Unknown'
        GROUP BY 1 ORDER BY late_rate_pct DESC
    """)
    if late.empty:
        empty_note()
    else:
        st.altair_chart(
            alt.Chart(late).mark_bar().encode(
                x=alt.X("region:N", sort="-y", title=None),
                y=alt.Y("late_rate_pct:Q", title="Late deliveries (%)"),
                tooltip=[alt.Tooltip("region:N", title="Region"),
                         alt.Tooltip("late_rate_pct:Q", title="Late (%)"),
                         alt.Tooltip("avg_days_late:Q", title="Avg days late when late"),
                         alt.Tooltip("delivered_items:Q", title="Delivered items", format=",")],
            ).properties(height=300),
            use_container_width=True,
        )

    st.divider()

    st.subheader("Does a late delivery hurt the review score?")
    explain("Orders grouped by how late they were; the line is the average 1–5 review "
            "score for each group. A steep drop means lateness is what customers "
            "punish. Drill-across: joins the items fact to the reviews fact through the "
            "order. — Business question 13")
    di = run_sql(f"""
        {order_id_filter_cte(f)},
        delivery AS (
            SELECT order_id,
                   MAX(is_late_delivery) AS was_late,
                   AVG(delivery_delay_days) AS delay_days,
                   AVG(delivery_days) AS delivery_days
            FROM fact_order_items
            WHERE is_late_delivery IS NOT NULL AND order_id IN (SELECT order_id FROM kept_orders)
            GROUP BY 1
        ),
        review AS (
            SELECT order_id, AVG(review_score) AS review_score
            FROM fact_order_reviews
            WHERE order_id IN (SELECT order_id FROM kept_orders)
            GROUP BY 1
        )
        SELECT
            CASE
                WHEN d.was_late = 0 THEN '1. On time / early'
                WHEN d.delay_days < 3 THEN '2. Late 1–2 days'
                WHEN d.delay_days < 7 THEN '3. Late 3–6 days'
                ELSE '4. Late a week+'
            END AS outcome,
            COUNT(*) AS orders,
            ROUND(AVG(r.review_score), 2) AS avg_review_score
        FROM delivery d JOIN review r ON r.order_id = d.order_id
        GROUP BY 1 ORDER BY 1
    """)
    if di.empty:
        empty_note()
    else:
        base = alt.Chart(di).encode(x=alt.X("outcome:N", title=None, axis=alt.Axis(labelAngle=0)))
        bars = base.mark_bar(opacity=0.35).encode(
            y=alt.Y("orders:Q", title="Orders"),
            tooltip=[alt.Tooltip("outcome:N", title="Delivery"),
                     alt.Tooltip("orders:Q", title="Orders", format=","),
                     alt.Tooltip("avg_review_score:Q", title="Avg score")],
        )
        line = base.mark_line(point=True, color="#d62728").encode(
            y=alt.Y("avg_review_score:Q", title="Avg review score (1–5)",
                    scale=alt.Scale(domain=[1, 5])),
        )
        st.altair_chart(alt.layer(bars, line).resolve_scale(y="independent").properties(height=320),
                        use_container_width=True)


# ---------------------------------------------------------------------------
# TAB 4 — Payments
# ---------------------------------------------------------------------------
def tab_payments(f: Filters):
    pay_filter = ""
    if f.payment_labels is not None:
        pay_filter = f"AND dpt.payment_label IN ({_sql_str_list(f.payment_labels)})"

    st.subheader("How customers pay")
    explain("Number of orders and the average transaction size for each payment "
            "method. Credit card usually leads on both. — Business question 8")
    mix = run_sql(f"""
        {order_id_filter_cte(f)}
        SELECT dpt.payment_label AS method,
               COUNT(DISTINCT fp.order_id) AS orders,
               ROUND(AVG(fp.payment_value), 2) AS avg_transaction
        FROM fact_order_payments fp
        JOIN dim_payment_type dpt ON dpt.payment_type_key = fp.payment_type_key
        WHERE dpt.is_valid_method
          AND fp.order_id IN (SELECT order_id FROM kept_orders)
          {pay_filter}
        GROUP BY 1 ORDER BY orders DESC
    """)
    if mix.empty:
        empty_note(); return
    c1, c2 = st.columns(2)
    with c1:
        st.altair_chart(
            alt.Chart(mix).mark_bar().encode(
                x=alt.X("orders:Q", title="Orders"),
                y=alt.Y("method:N", sort="-x", title=None),
                tooltip=[alt.Tooltip("method:N", title="Method"),
                         alt.Tooltip("orders:Q", title="Orders", format=",")],
            ).properties(height=260),
            use_container_width=True,
        )
    with c2:
        st.altair_chart(
            alt.Chart(mix).mark_bar(color="#2ca02c").encode(
                x=alt.X("avg_transaction:Q", title="Average transaction (R$)"),
                y=alt.Y("method:N", sort="-x", title=None),
                tooltip=[alt.Tooltip("method:N", title="Method"),
                         alt.Tooltip("avg_transaction:Q", title="Avg (R$)", format=",.2f")],
            ).properties(height=260),
            use_container_width=True,
        )

    st.divider()

    st.subheader("Do instalment plans go with bigger baskets?")
    explain("Orders grouped by the number of instalments; the bar is the average "
            "amount paid. If it rises, people reach for instalments on their "
            "pricier purchases. — Business question 6")
    inst = run_sql(f"""
        {order_id_filter_cte(f)}
        SELECT
            CASE
                WHEN fp.payment_installments <= 1 THEN '1 (in full)'
                WHEN fp.payment_installments <= 3 THEN '2–3'
                WHEN fp.payment_installments <= 6 THEN '4–6'
                WHEN fp.payment_installments <= 12 THEN '7–12'
                ELSE '13+'
            END AS instalments,
            MIN(fp.payment_installments) AS sort_key,
            COUNT(DISTINCT fp.order_id) AS orders,
            ROUND(AVG(fp.payment_value), 2) AS avg_paid
        FROM fact_order_payments fp
        WHERE fp.payment_installments IS NOT NULL
          AND fp.order_id IN (SELECT order_id FROM kept_orders)
        GROUP BY 1 ORDER BY sort_key
    """)
    if inst.empty:
        empty_note()
    else:
        st.altair_chart(
            alt.Chart(inst).mark_bar().encode(
                x=alt.X("instalments:N", sort=alt.SortField("sort_key"), title="Instalments",
                        axis=alt.Axis(labelAngle=0)),
                y=alt.Y("avg_paid:Q", title="Average amount paid (R$)"),
                tooltip=[alt.Tooltip("instalments:N", title="Instalments"),
                         alt.Tooltip("avg_paid:Q", title="Avg paid (R$)", format=",.2f"),
                         alt.Tooltip("orders:Q", title="Orders", format=",")],
            ).properties(height=300),
            use_container_width=True,
        )

    st.divider()

    st.subheader("Basket value vs amount actually paid")
    explain("For each instalment band: the average value of the items ordered vs the "
            "average total the customer paid. A widening gap is interest on the "
            "instalment plan. This joins the items fact to the payments fact. "
            "— Business question 6")
    gap = run_sql(f"""
        {order_id_filter_cte(f)},
        basket AS (
            SELECT order_id, SUM(total_item_value) AS basket_value
            FROM fact_order_items
            WHERE order_id IN (SELECT order_id FROM kept_orders)
            GROUP BY 1
        ),
        paid AS (
            SELECT order_id, SUM(payment_value) AS amount_paid, MAX(payment_installments) AS mi
            FROM fact_order_payments
            WHERE order_id IN (SELECT order_id FROM kept_orders)
            GROUP BY 1
        )
        SELECT
            CASE WHEN p.mi <= 1 THEN '1 (in full)' WHEN p.mi <= 6 THEN '2–6' ELSE '7+' END AS instalments,
            COUNT(*) AS orders,
            ROUND(AVG(b.basket_value), 2) AS avg_basket_value,
            ROUND(AVG(p.amount_paid), 2)  AS avg_amount_paid
        FROM basket b JOIN paid p ON p.order_id = b.order_id
        GROUP BY 1 ORDER BY 1
    """)
    if gap.empty:
        empty_note()
    else:
        long = gap.melt(id_vars=["instalments", "orders"],
                        value_vars=["avg_basket_value", "avg_amount_paid"],
                        var_name="measure", value_name="amount")
        long["measure"] = long["measure"].map({"avg_basket_value": "Items ordered",
                                               "avg_amount_paid": "Amount paid"})
        st.altair_chart(
            alt.Chart(long).mark_bar().encode(
                x=alt.X("instalments:N", title="Instalments", axis=alt.Axis(labelAngle=0)),
                xOffset="measure:N",
                y=alt.Y("amount:Q", title="R$"),
                color=alt.Color("measure:N", title=None),
                tooltip=[alt.Tooltip("instalments:N", title="Instalments"),
                         alt.Tooltip("measure:N", title=None),
                         alt.Tooltip("amount:Q", title="R$", format=",.2f")],
            ).properties(height=300),
            use_container_width=True,
        )


# ---------------------------------------------------------------------------
# TAB 5 — Quality & reviews
# ---------------------------------------------------------------------------
def tab_quality(f: Filters):
    iv = item_view(f)

    st.subheader("Review score distribution")
    explain("How the 1–5 star ratings are spread for orders in the current "
            "selection. A tall 5-star bar with a small 1-star bar is healthy. "
            "— Business question 12 context")
    dist = run_sql(f"""
        {order_id_filter_cte(f)}
        SELECT review_score AS score, COUNT(*) AS reviews
        FROM fact_order_reviews
        WHERE order_id IN (SELECT order_id FROM kept_orders)
        GROUP BY 1 ORDER BY 1
    """)
    if dist.empty:
        empty_note(); return
    st.altair_chart(
        alt.Chart(dist).mark_bar().encode(
            x=alt.X("score:O", title="Review score (stars)"),
            y=alt.Y("reviews:Q", title="Number of reviews"),
            color=alt.Color("score:O", legend=None,
                            scale=alt.Scale(scheme="redyellowgreen")),
            tooltip=[alt.Tooltip("score:O", title="Score"),
                     alt.Tooltip("reviews:Q", title="Reviews", format=",")],
        ).properties(height=280),
        use_container_width=True,
    )

    st.divider()

    st.subheader("Average review score by product category")
    explain("Each order's main category vs the average 1–5 score its buyers gave "
            "(categories with at least 50 reviewed orders). Top of the list = "
            "happiest customers, bottom = the categories to fix. Drill-across: the "
            "items fact (category) joined to the reviews fact. — Business question 12")
    catrev = run_sql(f"""
        {order_id_filter_cte(f)},
        order_category AS (
            SELECT order_id, category FROM (
                SELECT f.order_id, dp.category,
                       ROW_NUMBER() OVER (PARTITION BY f.order_id ORDER BY COUNT(*) DESC) AS rn
                FROM fact_order_items f
                JOIN dim_products dp ON dp.product_key = f.product_key
                WHERE f.order_id IN (SELECT order_id FROM kept_orders)
                GROUP BY 1, 2
            ) WHERE rn = 1
        ),
        order_score AS (
            SELECT order_id, AVG(review_score) AS review_score
            FROM fact_order_reviews
            WHERE order_id IN (SELECT order_id FROM kept_orders)
            GROUP BY 1
        )
        SELECT oc.category,
               COUNT(*) AS orders_reviewed,
               ROUND(AVG(os.review_score), 2) AS avg_review_score
        FROM order_category oc JOIN order_score os ON os.order_id = oc.order_id
        GROUP BY 1 HAVING COUNT(*) >= 50
        ORDER BY avg_review_score DESC
    """)
    if not catrev.empty:
        show = pd.concat([catrev.head(8), catrev.tail(8)]).drop_duplicates("category")
        st.altair_chart(
            alt.Chart(show).mark_bar().encode(
                x=alt.X("avg_review_score:Q", title="Avg review score (1–5)",
                        scale=alt.Scale(domain=[0, 5])),
                y=alt.Y("category:N", sort="-x", title=None),
                color=alt.Color("avg_review_score:Q", legend=None,
                                scale=alt.Scale(scheme="redyellowgreen", domain=[3, 4.5])),
                tooltip=[alt.Tooltip("category:N", title="Category"),
                         alt.Tooltip("avg_review_score:Q", title="Avg score"),
                         alt.Tooltip("orders_reviewed:Q", title="Reviewed orders", format=",")],
            ).properties(height=380),
            use_container_width=True,
        )
        st.caption(f"Best: {catrev.iloc[0]['category']} ({catrev.iloc[0]['avg_review_score']}) · "
                   f"Worst: {catrev.iloc[-1]['category']} ({catrev.iloc[-1]['avg_review_score']})")

    st.divider()

    st.subheader("Freight cost as a share of price, by category")
    explain("For the biggest categories: how much freight adds on top of the item "
            "price. A high bar means shipping is expensive relative to what is being "
            "sold — usually bulky, low-value goods. — Business question 11")
    fr = run_sql(f"""
        WITH i AS ({iv})
        SELECT product_category AS category,
               COUNT(*) AS items,
               ROUND(100.0 * SUM(freight_value) / NULLIF(SUM(price), 0), 1) AS freight_pct
        FROM i GROUP BY 1 HAVING COUNT(*) >= 50
        ORDER BY freight_pct DESC LIMIT 12
    """)
    if fr.empty:
        empty_note()
    else:
        st.altair_chart(
            alt.Chart(fr).mark_bar().encode(
                x=alt.X("freight_pct:Q", title="Freight as % of price"),
                y=alt.Y("category:N", sort="-x", title=None),
                tooltip=[alt.Tooltip("category:N", title="Category"),
                         alt.Tooltip("freight_pct:Q", title="Freight % of price"),
                         alt.Tooltip("items:Q", title="Items", format=",")],
            ).properties(height=340),
            use_container_width=True,
        )

    st.divider()

    st.subheader("Does buyer–seller distance affect the review score?")
    explain("Orders grouped by how far apart the buyer and seller are; the line is "
            "the average review score. Distance is computed from the two geography "
            "roles on the items fact. Drill-across: items fact ⋈ reviews fact. — Business question 13")
    dis = run_sql(f"""
        {order_id_filter_cte(f)},
        item_distance AS (
            SELECT order_id, AVG(buyer_seller_distance_km) AS distance_km
            FROM fact_order_items
            WHERE buyer_seller_distance_km IS NOT NULL
              AND order_id IN (SELECT order_id FROM kept_orders)
            GROUP BY 1
        ),
        order_score AS (
            SELECT order_id, AVG(review_score) AS review_score
            FROM fact_order_reviews
            WHERE order_id IN (SELECT order_id FROM kept_orders)
            GROUP BY 1
        )
        SELECT
            CASE
                WHEN d.distance_km < 100 THEN '1. under 100 km'
                WHEN d.distance_km < 500 THEN '2. 100–500 km'
                WHEN d.distance_km < 1500 THEN '3. 500–1500 km'
                ELSE '4. over 1500 km'
            END AS band,
            COUNT(*) AS orders,
            ROUND(AVG(d.distance_km), 0) AS avg_km,
            ROUND(AVG(s.review_score), 2) AS avg_review_score
        FROM item_distance d JOIN order_score s ON s.order_id = d.order_id
        GROUP BY 1 ORDER BY 1
    """)
    if dis.empty:
        empty_note()
    else:
        base = alt.Chart(dis).encode(x=alt.X("band:N", title=None, axis=alt.Axis(labelAngle=0)))
        bars = base.mark_bar(opacity=0.35).encode(
            y=alt.Y("orders:Q", title="Orders"),
            tooltip=[alt.Tooltip("band:N", title="Distance"),
                     alt.Tooltip("orders:Q", title="Orders", format=","),
                     alt.Tooltip("avg_km:Q", title="Avg km"),
                     alt.Tooltip("avg_review_score:Q", title="Avg score")],
        )
        line = base.mark_line(point=True, color="#1f77b4").encode(
            y=alt.Y("avg_review_score:Q", title="Avg review score (1–5)",
                    scale=alt.Scale(domain=[1, 5])),
        )
        st.altair_chart(alt.layer(bars, line).resolve_scale(y="independent").properties(height=300),
                        use_container_width=True)


# ---------------------------------------------------------------------------
# TAB 6 — Sellers & basket
# ---------------------------------------------------------------------------
def tab_sellers_basket(f: Filters):
    st.subheader("Is revenue concentrated in a few sellers? (Pareto 80/20)")
    explain("Sellers ranked by revenue, then read as: the top X% of sellers earn Y% "
            "of all revenue. If ‘top 20%’ is near 80%, the marketplace runs on a "
            "small core of sellers. — Business question 14")
    pareto = run_sql(f"""
        {order_id_filter_cte(f)},
        seller_revenue AS (
            SELECT seller_key, SUM(price) AS revenue
            FROM fact_order_items
            WHERE order_id IN (SELECT order_id FROM kept_orders)
            GROUP BY 1
        ),
        ranked AS (
            SELECT revenue,
                   ROW_NUMBER() OVER (ORDER BY revenue DESC) AS rnk,
                   COUNT(*) OVER () AS total_sellers,
                   SUM(revenue) OVER (ORDER BY revenue DESC
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_rev,
                   SUM(revenue) OVER () AS total_rev
            FROM seller_revenue
        ),
        bands AS (
            SELECT 100.0 * rnk / total_sellers AS pct_sellers,
                   100.0 * running_rev / total_rev AS pct_revenue
            FROM ranked
        )
        SELECT 'Top 1%' AS bucket, ROUND(MAX(pct_revenue), 1) AS pct_of_revenue, 1 AS srt FROM bands WHERE pct_sellers <= 1
        UNION ALL SELECT 'Top 5%',  ROUND(MAX(pct_revenue), 1), 2 FROM bands WHERE pct_sellers <= 5
        UNION ALL SELECT 'Top 10%', ROUND(MAX(pct_revenue), 1), 3 FROM bands WHERE pct_sellers <= 10
        UNION ALL SELECT 'Top 20%', ROUND(MAX(pct_revenue), 1), 4 FROM bands WHERE pct_sellers <= 20
        ORDER BY srt
    """)
    if pareto.empty:
        empty_note()
    else:
        st.altair_chart(
            alt.Chart(pareto).mark_bar().encode(
                x=alt.X("bucket:N", sort=list(pareto["bucket"]), title="Share of sellers",
                        axis=alt.Axis(labelAngle=0)),
                y=alt.Y("pct_of_revenue:Q", title="Share of total revenue (%)",
                        scale=alt.Scale(domain=[0, 100])),
                color=alt.Color("pct_of_revenue:Q", legend=None, scale=alt.Scale(scheme="oranges")),
                tooltip=[alt.Tooltip("bucket:N", title="Sellers"),
                         alt.Tooltip("pct_of_revenue:Q", title="% of revenue")],
            ).properties(height=300),
            use_container_width=True,
        )
        top10 = pareto.loc[pareto["bucket"] == "Top 10%"]
        if not top10.empty:
            st.markdown(f"**The top 10% of sellers earn "
                        f"{top10['pct_of_revenue'].iloc[0]:.0f}% of all revenue.**")

    st.divider()

    st.subheader("Which product categories are bought together?")
    explain("Pairs of categories that appear in the same order most often — the "
            "starting point for cross-sell bundles. Built by self-joining the items "
            "fact on the order. — Business question 15")
    basket = run_sql(f"""
        {order_id_filter_cte(f)},
        order_categories AS (
            SELECT DISTINCT f.order_id, dp.category
            FROM fact_order_items f
            JOIN dim_products dp ON dp.product_key = f.product_key
            WHERE dp.category <> 'unknown'
              AND f.order_id IN (SELECT order_id FROM kept_orders)
        )
        SELECT a.category || '  +  ' || b.category AS pair,
               COUNT(*) AS orders_together
        FROM order_categories a
        JOIN order_categories b ON a.order_id = b.order_id AND a.category < b.category
        GROUP BY 1 ORDER BY orders_together DESC LIMIT 12
    """)
    if basket.empty:
        st.info("No category appears alongside another in the current selection "
                "(most Olist orders contain a single item).")
    else:
        st.altair_chart(
            alt.Chart(basket).mark_bar().encode(
                x=alt.X("orders_together:Q", title="Orders containing both"),
                y=alt.Y("pair:N", sort="-x", title=None),
                tooltip=[alt.Tooltip("pair:N", title="Category pair"),
                         alt.Tooltip("orders_together:Q", title="Orders", format=",")],
            ).properties(height=340),
            use_container_width=True,
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    st.title("📦 Olist Marketplace Dashboard")
    st.caption("Real transactions from the Brazilian e-commerce marketplace Olist "
               "(Sept 2016 – Oct 2018). Every number below is read from the "
               "dimensional model in olist_dw/dev.duckdb.")

    con = get_connection()
    if not warehouse_ready(con):
        st.error("The warehouse tables are not available. Run `dbt run` inside olist_dw/.")
        st.stop()

    filters = build_sidebar_filters()
    st.info("Showing: " + active_filter_summary(filters))

    t1, t2, t3, t4, t5, t6 = st.tabs([
        "Sales overview", "Customers", "Delivery", "Payments", "Quality & reviews",
        "Sellers & basket",
    ])
    with t1:
        tab_sales(filters)
    with t2:
        tab_customers(filters)
    with t3:
        tab_delivery(filters)
    with t4:
        tab_payments(filters)
    with t5:
        tab_quality(filters)
    with t6:
        tab_sellers_basket(filters)


if __name__ == "__main__":
    main()
