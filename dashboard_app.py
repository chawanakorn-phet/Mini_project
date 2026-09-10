"""แดชบอร์ด OLAP ของตลาดกลางออนไลน์ Olist — เวอร์ชันภาษาไทย

ออกแบบสำหรับผู้ชมทั่วไป ไม่ใช่ผู้พัฒนา:
  * ป้ายกำกับและชื่อคอลัมน์ทุกจุดเป็นภาษาไทย ไม่มีชื่อตาราง/คอลัมน์ดิบ
  * ชื่อหมวดหมู่สินค้าแปลเป็นไทย (เช่น health_beauty → "สุขภาพและความงาม")
  * ทุกกราฟมีคำอธิบาย 1 บรรทัดว่าอ่านอย่างไร และตอบคำถามธุรกิจข้อไหน
  * ตัวกรองในแถบด้านซ้ายมีผลกับทุกแท็บพร้อมกัน และดึงค่าจากตาราง Dimension เท่านั้น

ข้อมูลทั้งหมดอ่านจาก star schema ใน olist_dw/dev.duckdb (dim_* / fact_*)
ไม่มีการแตะ staging layer หรือไฟล์ CSV ดิบ
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

st.set_page_config(page_title="แดชบอร์ด Olist Marketplace", page_icon="📦", layout="wide")

# ---------------------------------------------------------------------------
# การแปลชื่อ (Localization) — ทำที่ชั้นแสดงผล ไม่แตะโมเดล
# ---------------------------------------------------------------------------
CATEGORY_TH = {
    "agro_industry_and_commerce": "เกษตรอุตสาหกรรมและการค้า",
    "air_conditioning": "เครื่องปรับอากาศ",
    "art": "งานศิลปะ",
    "arts_and_craftmanship": "งานศิลปะและงานฝีมือ",
    "audio": "เครื่องเสียง",
    "auto": "ยานยนต์และอะไหล่รถ",
    "baby": "สินค้าแม่และเด็ก",
    "bed_bath_table": "เครื่องนอน ห้องน้ำ โต๊ะอาหาร",
    "books_general_interest": "หนังสือทั่วไป",
    "books_imported": "หนังสือนำเข้า",
    "books_technical": "หนังสือวิชาการ",
    "cds_dvds_musicals": "ซีดี/ดีวีดี เพลง",
    "christmas_supplies": "ของตกแต่งคริสต์มาส",
    "cine_photo": "กล้องและอุปกรณ์ถ่ายภาพ",
    "computers": "คอมพิวเตอร์",
    "computers_accessories": "อุปกรณ์เสริมคอมพิวเตอร์",
    "consoles_games": "เครื่องเกมและเกม",
    "construction_tools_construction": "เครื่องมือก่อสร้าง",
    "construction_tools_lights": "เครื่องมือช่าง–ระบบไฟ",
    "construction_tools_safety": "เครื่องมือช่าง–อุปกรณ์นิรภัย",
    "cool_stuff": "ของแปลกน่าสนใจ",
    "costruction_tools_garden": "เครื่องมือ–ทำสวน",
    "costruction_tools_tools": "เครื่องมือช่าง",
    "diapers_and_hygiene": "ผ้าอ้อมและของใช้อนามัย",
    "drinks": "เครื่องดื่ม",
    "dvds_blu_ray": "ดีวีดี/บลูเรย์",
    "electronics": "อุปกรณ์อิเล็กทรอนิกส์",
    "fashio_female_clothing": "เสื้อผ้าผู้หญิง",
    "fashion_bags_accessories": "กระเป๋าและเครื่องประดับแฟชั่น",
    "fashion_childrens_clothes": "เสื้อผ้าเด็ก",
    "fashion_male_clothing": "เสื้อผ้าผู้ชาย",
    "fashion_shoes": "รองเท้าแฟชั่น",
    "fashion_sport": "ชุดกีฬา",
    "fashion_underwear_beach": "ชุดชั้นในและชุดว่ายน้ำ",
    "fixed_telephony": "โทรศัพท์บ้าน",
    "flowers": "ดอกไม้",
    "food": "อาหาร",
    "food_drink": "อาหารและเครื่องดื่ม",
    "furniture_bedroom": "เฟอร์นิเจอร์ห้องนอน",
    "furniture_decor": "เฟอร์นิเจอร์และของตกแต่ง",
    "furniture_living_room": "เฟอร์นิเจอร์ห้องนั่งเล่น",
    "furniture_mattress_and_upholstery": "ที่นอนและเบาะ",
    "garden_tools": "อุปกรณ์ทำสวน",
    "health_beauty": "สุขภาพและความงาม",
    "home_appliances": "เครื่องใช้ไฟฟ้าในบ้าน",
    "home_appliances_2": "เครื่องใช้ไฟฟ้าในบ้าน (2)",
    "home_comfort_2": "ของใช้ในบ้าน (2)",
    "home_confort": "ของใช้ในบ้าน",
    "home_construction": "วัสดุก่อสร้างบ้าน",
    "housewares": "เครื่องครัวและของใช้ในบ้าน",
    "industry_commerce_and_business": "อุตสาหกรรมและธุรกิจ",
    "kitchen_dining_laundry_garden_furniture": "เฟอร์นิเจอร์ครัว/ซักล้าง/สวน",
    "la_cuisine": "อุปกรณ์ครัว (La Cuisine)",
    "luggage_accessories": "กระเป๋าเดินทางและอุปกรณ์",
    "market_place": "มาร์เก็ตเพลส",
    "music": "เพลงและเครื่องดนตรี",
    "musical_instruments": "เครื่องดนตรี",
    "office_furniture": "เฟอร์นิเจอร์สำนักงาน",
    "party_supplies": "อุปกรณ์จัดปาร์ตี้",
    "pc_gamer": "อุปกรณ์เกมเมอร์",
    "perfumery": "น้ำหอม",
    "pet_shop": "สัตว์เลี้ยง",
    "portateis_cozinha_e_preparadores_de_alimentos": "เครื่องครัวขนาดพกพา",
    "security_and_services": "ความปลอดภัยและบริการ",
    "signaling_and_security": "ป้ายสัญญาณและความปลอดภัย",
    "small_appliances": "เครื่องใช้ไฟฟ้าขนาดเล็ก",
    "small_appliances_home_oven_and_coffee": "เตาอบและเครื่องชงกาแฟ",
    "sports_leisure": "กีฬาและสันทนาการ",
    "stationery": "เครื่องเขียน",
    "tablets_printing_image": "แท็บเล็ตและงานพิมพ์",
    "telephony": "โทรศัพท์และอุปกรณ์",
    "toys": "ของเล่น",
    "unknown": "ไม่ระบุ",
    "watches_gifts": "นาฬิกาและของขวัญ",
}

REGION_TH = {
    "Norte": "ภาคเหนือ",
    "Nordeste": "ภาคตะวันออกเฉียงเหนือ",
    "Centro-Oeste": "ภาคกลาง-ตะวันตก",
    "Sudeste": "ภาคตะวันออกเฉียงใต้",
    "Sul": "ภาคใต้",
    "Unknown": "ไม่ระบุ",
}

PAYMENT_TH = {
    "Credit card": "บัตรเครดิต",
    "Boleto (bank slip)": "โบเลโต (ใบชำระเงินธนาคาร)",
    "Voucher": "บัตรกำนัล/วอเชอร์",
    "Debit card": "บัตรเดบิต",
}


def _map_col(df: pd.DataFrame, col: str, mapping: dict) -> pd.DataFrame:
    if not df.empty and col in df.columns:
        df = df.copy()
        df[col] = df[col].map(lambda v: mapping.get(v, str(v).replace("_", " ")))
    return df


def th_category(df, col="category"):
    return _map_col(df, col, CATEGORY_TH)


def th_region(df, col="region"):
    return _map_col(df, col, REGION_TH)


def th_payment(df, col="method"):
    return _map_col(df, col, PAYMENT_TH)


def cat_label(value: str) -> str:
    return CATEGORY_TH.get(value, str(value).replace("_", " "))


# On a fresh checkout (e.g. Streamlit Cloud) dev.duckdb does not exist yet;
# build it once by shelling out to dbt.
with st.spinner("กำลังเตรียมคลังข้อมูล (เฉพาะการรันครั้งแรก)…"):
    _ok, _log = ensure_warehouse_built()
if not _ok and not DB_PATH.exists():
    st.error("สร้างคลังข้อมูลไม่สำเร็จ — ผลลัพธ์จาก `dbt run`:")
    st.code(_log or "(ไม่มีข้อความ)")
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
# controls narrow ALL tabs. A field is None when it is not narrowing anything.
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
# Reusable pre-joined item view — filter logic lives in exactly one place.
# ---------------------------------------------------------------------------
def item_view(f: Filters) -> str:
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
    return f"WITH kept_orders AS (SELECT DISTINCT order_id FROM ({item_view(f)}))"


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
def build_sidebar_filters() -> Filters:
    st.sidebar.header("ตัวกรอง")
    st.sidebar.caption("ปรับแล้วมีผลกับทุกกราฟในทุกแท็บ "
                       "ตัวเลือกทั้งหมดดึงจากตาราง Dimension")

    opts = load_filter_options()
    dmin, dmax = load_date_bounds()
    if not opts or dmin is None:
        return Filters()

    dmin, dmax = pd.to_datetime(dmin).date(), pd.to_datetime(dmax).date()

    years = [str(y) for y in range(dmin.year, dmax.year + 1)]
    preset = st.sidebar.radio("ช่วงเวลา", ["ทั้งหมด"] + years + ["กำหนดเอง"],
                              horizontal=True)
    if preset == "ทั้งหมด":
        start, end = dmin, dmax
    elif preset == "กำหนดเอง":
        lo, hi = date(dmin.year, 1, 1), date(dmax.year, 12, 31)
        start = st.sidebar.date_input("ตั้งแต่", dmin, min_value=lo, max_value=hi)
        end = st.sidebar.date_input("ถึง", dmax, min_value=lo, max_value=hi)
    else:
        y = int(preset)
        start = max(dmin, date(y, 1, 1))
        end = min(dmax, date(y, 12, 31))
    if start > end:
        st.sidebar.warning("‘ตั้งแต่’ อยู่หลัง ‘ถึง’ — สลับให้แล้ว")
        start, end = end, start

    def multi(label, key, help_text, mapping=None):
        values = opts.get(key, [])
        fmt = (lambda v: mapping.get(v, str(v))) if mapping else (lambda v: v)
        picked = st.sidebar.multiselect(label, values, default=values,
                                        help=help_text, format_func=fmt)
        return None if set(picked) == set(values) else tuple(picked)

    return Filters(
        start=start.isoformat(),
        end=end.isoformat(),
        regions=multi("ภูมิภาคลูกค้า", "regions",
                      "5 ภูมิภาคทางการของบราซิล (จาก dim_geography)", REGION_TH),
        customer_states=multi("รัฐลูกค้า", "customer_states",
                              "รหัสรัฐ 2 ตัวอักษร (จาก dim_customers)"),
        categories=multi("หมวดหมู่สินค้า", "categories",
                         "ชื่อหมวดหมู่ (จาก dim_products)", CATEGORY_TH),
        payment_labels=multi("วิธีชำระเงิน", "payment_labels",
                             "มีผลเฉพาะแท็บ ‘การชำระเงิน’ (จาก dim_payment_type)", PAYMENT_TH),
    )


def active_filter_summary(f: Filters) -> str:
    bits = [f"{f.start} → {f.end}"]
    for name, val in [("ภูมิภาค", f.regions), ("รัฐ", f.customer_states),
                      ("หมวดหมู่", f.categories), ("วิธีชำระเงิน", f.payment_labels)]:
        if val is not None:
            bits.append(f"{name} {len(val)} รายการ")
    return " · ".join(bits)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def brl(x) -> str:
    try:
        return f"R$ {x:,.0f}"
    except (TypeError, ValueError):
        return "–"


def explain(text: str):
    st.caption("📖 " + text)


def empty_note():
    st.info("ไม่มีข้อมูลตรงกับตัวกรองที่เลือก — ลองขยายการเลือกในแถบด้านซ้าย")


# ===========================================================================
# แท็บ 1 — ภาพรวมยอดขาย
# ===========================================================================
def tab_sales(f: Filters):
    iv = item_view(f)

    kpis = run_sql(f"""
        WITH i AS ({iv})
        SELECT
            COALESCE(SUM(price), 0)        AS revenue,
            COALESCE(SUM(freight_value), 0) AS freight,
            COUNT(DISTINCT order_id)       AS orders,
            COUNT(*)                       AS items
        FROM i
    """)
    if kpis.empty or kpis.loc[0, "orders"] == 0:
        empty_note(); return
    r = kpis.iloc[0]
    aov = r.revenue / r.orders if r.orders else 0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("รายได้จากสินค้า", brl(r.revenue))
    c2.metric("ค่าจัดส่งที่เก็บได้", brl(r.freight))
    c3.metric("จำนวนคำสั่งซื้อ", f"{int(r.orders):,}")
    c4.metric("ยอดขายเฉลี่ยต่อคำสั่งซื้อ", brl(aov))

    st.divider()

    st.subheader("รายได้รายเดือน")
    explain("แต่ละแท่งคือรายได้จากสินค้าใน 1 เดือน ใช้ดูแนวโน้มการเติบโตและช่วงพีคตามฤดูกาล "
            "— คำถามข้อ 2")
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
                x=alt.X("month:O", title="เดือน", axis=alt.Axis(labelAngle=-45)),
                y=alt.Y("revenue:Q", title="รายได้ (R$)"),
                tooltip=[alt.Tooltip("month:O", title="เดือน"),
                         alt.Tooltip("revenue:Q", title="รายได้ (R$)", format=",.0f"),
                         alt.Tooltip("orders:Q", title="คำสั่งซื้อ", format=",")],
            ).properties(height=300),
            use_container_width=True,
        )

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("10 หมวดหมู่ที่ทำรายได้สูงสุด")
        explain("หมวดหมู่ที่ทำรายได้จากสินค้ามากที่สุด แท่งยาว = เงินเยอะ — คำถามข้อ 1")
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
            cats = th_category(cats)
            st.altair_chart(
                alt.Chart(cats).mark_bar().encode(
                    x=alt.X("revenue:Q", title="รายได้ (R$)"),
                    y=alt.Y("category:N", sort="-x", title=None),
                    tooltip=[alt.Tooltip("category:N", title="หมวดหมู่"),
                             alt.Tooltip("revenue:Q", title="รายได้ (R$)", format=",.0f"),
                             alt.Tooltip("items:Q", title="จำนวนชิ้นที่ขาย", format=",")],
                ).properties(height=320),
                use_container_width=True,
            )

    with col2:
        st.subheader("รายได้ตามภูมิภาค")
        explain("รายได้จากสินค้าแบ่งตาม 5 ภูมิภาคของบราซิล ภาคตะวันออกเฉียงใต้ "
                "(เซาเปาโล ริโอ) มักครองสัดส่วนมากที่สุด — คำถามข้อ 4")
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
            reg = th_region(reg)
            st.altair_chart(
                alt.Chart(reg).mark_arc(innerRadius=60).encode(
                    theta=alt.Theta("revenue:Q"),
                    color=alt.Color("region:N", title="ภูมิภาค"),
                    tooltip=[alt.Tooltip("region:N", title="ภูมิภาค"),
                             alt.Tooltip("revenue:Q", title="รายได้ (R$)", format=",.0f"),
                             alt.Tooltip("orders:Q", title="คำสั่งซื้อ", format=",")],
                ).properties(height=320),
                use_container_width=True,
            )

    st.divider()

    st.subheader("ราคาเฉลี่ยต่อชิ้น แยกตามหมวดหมู่ (12 อันดับแรก)")
    explain("ไม่ใช่รายได้รวม แต่คือราคาต่อชิ้นโดยเฉลี่ยของสินค้าในแต่ละหมวดหมู่ พร้อมจำนวนที่ขายได้ "
            "แท่งสูง + ขายน้อย = หมวดสินค้าราคาแพงแต่ปริมาณน้อย — คำถามข้อ 3")
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
        avgp = th_category(avgp)
        st.altair_chart(
            alt.Chart(avgp).mark_bar().encode(
                x=alt.X("avg_price:Q", title="ราคาเฉลี่ยต่อชิ้น (R$)"),
                y=alt.Y("category:N", sort="-x", title=None),
                tooltip=[alt.Tooltip("category:N", title="หมวดหมู่"),
                         alt.Tooltip("avg_price:Q", title="ราคาเฉลี่ย (R$)", format=",.2f"),
                         alt.Tooltip("items_sold:Q", title="จำนวนชิ้นที่ขาย", format=",")],
            ).properties(height=340),
            use_container_width=True,
        )


# ===========================================================================
# แท็บ 2 — ลูกค้า
# ===========================================================================
def tab_customers(f: Filters):
    iv = item_view(f)

    st.subheader("ลูกค้าซื้อครั้งเดียว vs ซื้อซ้ำ")
    explain("ซ้าย: จำนวนคนที่ซื้อครั้งเดียว เทียบกับซื้อมากกว่า 1 ครั้ง "
            "ขวา: รายได้ของแต่ละกลุ่ม ถ้ากลุ่มซื้อซ้ำเล็กแต่รายได้เยอะ คือรูปแบบ 80/20 — คำถามข้อ 5")
    grp = run_sql(f"""
        WITH i AS ({iv}),
        per_person AS (
            SELECT customer_unique_id,
                   COUNT(DISTINCT order_id) AS orders,
                   SUM(price) AS revenue
            FROM i GROUP BY 1
        )
        SELECT CASE WHEN orders = 1 THEN 'ซื้อครั้งเดียว' ELSE 'ซื้อซ้ำ (2 ครั้งขึ้นไป)' END AS grp,
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
                y=alt.Y("customers:Q", title="จำนวนลูกค้า"),
                color=alt.Color("grp:N", legend=None),
                tooltip=[alt.Tooltip("grp:N", title="กลุ่ม"),
                         alt.Tooltip("customers:Q", title="จำนวนลูกค้า", format=",")],
            ).properties(height=280),
            use_container_width=True,
        )
    with c2:
        st.altair_chart(
            alt.Chart(grp).mark_bar().encode(
                x=alt.X("grp:N", title=None),
                y=alt.Y("revenue:Q", title="รายได้ (R$)"),
                color=alt.Color("grp:N", legend=None),
                tooltip=[alt.Tooltip("grp:N", title="กลุ่ม"),
                         alt.Tooltip("revenue:Q", title="รายได้ (R$)", format=",.0f")],
            ).properties(height=280),
            use_container_width=True,
        )
    repeat = grp.loc[grp["grp"].str.startswith("ซื้อซ้ำ")]
    if not repeat.empty:
        share = 100 * repeat["revenue"].iloc[0] / grp["revenue"].sum()
        pct_cust = 100 * repeat["customers"].iloc[0] / grp["customers"].sum()
        st.markdown(f"**ลูกค้าซื้อซ้ำเป็น {pct_cust:.1f}% ของผู้ซื้อ แต่คิดเป็นรายได้ {share:.1f}%**")

    st.divider()

    st.subheader("RFM — รายได้กระจุกอยู่ที่กลุ่มไหน")
    explain("แบ่งลูกค้าเป็น 5 กลุ่มเท่า ๆ กันตามยอดใช้จ่ายรวม (กลุ่ม 5 = จ่ายมากสุด 1 ใน 5) "
            "แต่ละกลุ่มดูจำนวนลูกค้า ความถี่ในการซื้อ และสัดส่วนรายได้ที่สร้าง — คำถามข้อ 7")
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
        rfm["label"] = "กลุ่ม " + rfm["quintile"].astype(str)
        st.altair_chart(
            alt.Chart(rfm).mark_bar().encode(
                x=alt.X("label:N", sort=list(rfm.sort_values("quintile")["label"]),
                        title="กลุ่มตามยอดใช้จ่าย (กลุ่ม 5 = สูงสุด)", axis=alt.Axis(labelAngle=0)),
                y=alt.Y("pct_of_revenue:Q", title="สัดส่วนรายได้ทั้งหมด (%)"),
                color=alt.Color("pct_of_revenue:Q", legend=None, scale=alt.Scale(scheme="blues")),
                tooltip=[alt.Tooltip("label:N", title="กลุ่ม"),
                         alt.Tooltip("customers:Q", title="จำนวนลูกค้า", format=","),
                         alt.Tooltip("avg_frequency:Q", title="คำสั่งซื้อเฉลี่ย/คน"),
                         alt.Tooltip("pct_of_revenue:Q", title="% ของรายได้")],
            ).properties(height=300),
            use_container_width=True,
        )
        top = rfm.loc[rfm["quintile"] == 5]
        if not top.empty:
            st.markdown(f"**ลูกค้ากลุ่มจ่ายเงินสูงสุด 20% สร้างรายได้ "
                        f"{top['pct_of_revenue'].iloc[0]:.1f}% ของทั้งหมด**")


# ===========================================================================
# แท็บ 3 — การจัดส่ง
# ===========================================================================
def tab_delivery(f: Filters):
    iv = item_view(f)

    parts = run_sql(f"""
        WITH i AS ({iv})
        SELECT
            ROUND(AVG(delivery_days), 1)            AS total_days,
            ROUND(AVG(seller_processing_days), 1)   AS seller_days,
            ROUND(AVG(carrier_transit_days), 1)     AS carrier_days,
            ROUND(100.0 * AVG(is_late_delivery), 1) AS late_rate
        FROM i
        WHERE delivery_days IS NOT NULL
    """)
    if parts.empty or pd.isna(parts.loc[0, "total_days"]):
        empty_note(); return
    p = parts.iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("เวลาจัดส่งเฉลี่ย", f"{p.total_days:.1f} วัน")
    c2.metric("…ร้านเตรียมของ", f"{p.seller_days:.1f} วัน")
    c3.metric("…ขนส่งวิ่งระหว่างทาง", f"{p.carrier_days:.1f} วัน")
    c4.metric("ช้ากว่าที่สัญญาไว้", f"{p.late_rate:.1f}%")
    explain("แยกเวลาจัดส่งออกเป็น 2 ช่วงที่แพลตฟอร์มควบคุมได้: ร้านใช้เวลาเตรียมของกี่วัน "
            "และขนส่งใช้เวลาวิ่งกี่วัน — คำถามข้อ 10")

    st.divider()

    st.subheader("เวลาที่ผู้ขายใช้เตรียมของ แยกตามรัฐของผู้ขาย")
    explain("จำนวนวันเฉลี่ยที่ผู้ขายใช้ส่งของให้บริษัทขนส่ง แยกตามรัฐที่ผู้ขายตั้งอยู่ "
            "(เฉพาะรัฐที่ส่งของอย่างน้อย 50 ชิ้น) แท่งสูง = ผู้ขายที่นั่นเตรียมช้ากว่า — คำถามข้อ 9")
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
                x=alt.X("seller_state:N", sort="-y", title="รัฐของผู้ขาย",
                        axis=alt.Axis(labelAngle=0)),
                y=alt.Y("avg_processing_days:Q", title="เวลาเตรียมของเฉลี่ย (วัน)"),
                tooltip=[alt.Tooltip("seller_state:N", title="รัฐของผู้ขาย"),
                         alt.Tooltip("avg_processing_days:Q", title="วันเตรียมของเฉลี่ย"),
                         alt.Tooltip("items_shipped:Q", title="จำนวนชิ้นที่ส่ง", format=",")],
            ).properties(height=300),
            use_container_width=True,
        )

    st.divider()

    st.subheader("อัตราการส่งช้ากว่ากำหนด แยกตามภูมิภาค")
    explain("สัดส่วนพัสดุที่ถึงมือลูกค้าช้ากว่าวันที่สัญญาไว้ แยกตามภูมิภาค "
            "แท่งสูง = ผิดสัญญาบ่อยกว่า — คำถามข้อ 10")
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
        late = th_region(late)
        st.altair_chart(
            alt.Chart(late).mark_bar().encode(
                x=alt.X("region:N", sort="-y", title=None),
                y=alt.Y("late_rate_pct:Q", title="ส่งช้า (%)"),
                tooltip=[alt.Tooltip("region:N", title="ภูมิภาค"),
                         alt.Tooltip("late_rate_pct:Q", title="ส่งช้า (%)"),
                         alt.Tooltip("avg_days_late:Q", title="เฉลี่ยช้ากี่วัน (เมื่อช้า)"),
                         alt.Tooltip("delivered_items:Q", title="จำนวนชิ้นที่ส่งถึง", format=",")],
            ).properties(height=300),
            use_container_width=True,
        )

    st.divider()

    st.subheader("การส่งช้าทำให้คะแนนรีวิวแย่ลงไหม?")
    explain("จัดกลุ่มคำสั่งซื้อตามระดับความช้า เส้นคือคะแนนรีวิวเฉลี่ย (1–5) ของแต่ละกลุ่ม "
            "ถ้าเส้นดิ่งลงแรง แปลว่าลูกค้าลงโทษเรื่องความช้าเป็นหลัก "
            "Drill-across: เชื่อม fact สินค้า เข้ากับ fact รีวิว ผ่านคำสั่งซื้อ — คำถามข้อ 13")
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
                WHEN d.was_late = 0 THEN '1. ตรงเวลา / เร็วกว่ากำหนด'
                WHEN d.delay_days < 3 THEN '2. ช้า 1–2 วัน'
                WHEN d.delay_days < 7 THEN '3. ช้า 3–6 วัน'
                ELSE '4. ช้าตั้งแต่ 1 สัปดาห์ขึ้นไป'
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
            y=alt.Y("orders:Q", title="จำนวนคำสั่งซื้อ"),
            tooltip=[alt.Tooltip("outcome:N", title="การจัดส่ง"),
                     alt.Tooltip("orders:Q", title="คำสั่งซื้อ", format=","),
                     alt.Tooltip("avg_review_score:Q", title="คะแนนเฉลี่ย")],
        )
        line = base.mark_line(point=True, color="#d62728").encode(
            y=alt.Y("avg_review_score:Q", title="คะแนนรีวิวเฉลี่ย (1–5)",
                    scale=alt.Scale(domain=[1, 5])),
        )
        st.altair_chart(alt.layer(bars, line).resolve_scale(y="independent").properties(height=320),
                        use_container_width=True)


# ===========================================================================
# แท็บ 4 — การชำระเงิน
# ===========================================================================
def tab_payments(f: Filters):
    pay_filter = ""
    if f.payment_labels is not None:
        pay_filter = f"AND dpt.payment_label IN ({_sql_str_list(f.payment_labels)})"

    st.subheader("ลูกค้าจ่ายเงินด้วยวิธีใด")
    explain("จำนวนคำสั่งซื้อ และมูลค่าเฉลี่ยต่อรายการชำระ ของแต่ละวิธีชำระเงิน "
            "บัตรเครดิตมักนำทั้งสองด้าน — คำถามข้อ 8")
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
    mix = th_payment(mix)
    c1, c2 = st.columns(2)
    with c1:
        st.altair_chart(
            alt.Chart(mix).mark_bar().encode(
                x=alt.X("orders:Q", title="จำนวนคำสั่งซื้อ"),
                y=alt.Y("method:N", sort="-x", title=None),
                tooltip=[alt.Tooltip("method:N", title="วิธีชำระเงิน"),
                         alt.Tooltip("orders:Q", title="คำสั่งซื้อ", format=",")],
            ).properties(height=260),
            use_container_width=True,
        )
    with c2:
        st.altair_chart(
            alt.Chart(mix).mark_bar(color="#2ca02c").encode(
                x=alt.X("avg_transaction:Q", title="มูลค่าเฉลี่ยต่อรายการ (R$)"),
                y=alt.Y("method:N", sort="-x", title=None),
                tooltip=[alt.Tooltip("method:N", title="วิธีชำระเงิน"),
                         alt.Tooltip("avg_transaction:Q", title="เฉลี่ย (R$)", format=",.2f")],
            ).properties(height=260),
            use_container_width=True,
        )

    st.divider()

    st.subheader("การผ่อนชำระสัมพันธ์กับตะกร้าที่ใหญ่ขึ้นไหม?")
    explain("จัดกลุ่มคำสั่งซื้อตามจำนวนงวดผ่อน แท่งคือยอดจ่ายเฉลี่ย "
            "ถ้าแท่งสูงขึ้นเรื่อย ๆ แปลว่าคนเลือกผ่อนตอนซื้อของแพง — คำถามข้อ 6")
    inst = run_sql(f"""
        {order_id_filter_cte(f)}
        SELECT
            CASE
                WHEN fp.payment_installments <= 1 THEN '1 (จ่ายเต็ม)'
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
                x=alt.X("instalments:N", sort=alt.SortField("sort_key"), title="จำนวนงวดผ่อน",
                        axis=alt.Axis(labelAngle=0)),
                y=alt.Y("avg_paid:Q", title="ยอดจ่ายเฉลี่ย (R$)"),
                tooltip=[alt.Tooltip("instalments:N", title="จำนวนงวด"),
                         alt.Tooltip("avg_paid:Q", title="ยอดจ่ายเฉลี่ย (R$)", format=",.2f"),
                         alt.Tooltip("orders:Q", title="คำสั่งซื้อ", format=",")],
            ).properties(height=300),
            use_container_width=True,
        )

    st.divider()

    st.subheader("มูลค่าสินค้าในตะกร้า เทียบกับยอดที่จ่ายจริง")
    explain("แต่ละกลุ่มงวดผ่อน: มูลค่าสินค้าที่สั่งเฉลี่ย เทียบกับยอดรวมที่ลูกค้าจ่ายจริงเฉลี่ย "
            "ช่องว่างที่ถ่างขึ้นคือดอกเบี้ยจากการผ่อน "
            "Drill-across: เชื่อม fact สินค้า เข้ากับ fact การชำระเงิน — คำถามข้อ 6")
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
            CASE WHEN p.mi <= 1 THEN '1 (จ่ายเต็ม)' WHEN p.mi <= 6 THEN '2–6' ELSE '7+' END AS instalments,
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
        long["measure"] = long["measure"].map({"avg_basket_value": "มูลค่าสินค้าที่สั่ง",
                                               "avg_amount_paid": "ยอดที่จ่ายจริง"})
        st.altair_chart(
            alt.Chart(long).mark_bar().encode(
                x=alt.X("instalments:N", title="จำนวนงวดผ่อน", axis=alt.Axis(labelAngle=0)),
                xOffset="measure:N",
                y=alt.Y("amount:Q", title="R$"),
                color=alt.Color("measure:N", title=None),
                tooltip=[alt.Tooltip("instalments:N", title="จำนวนงวด"),
                         alt.Tooltip("measure:N", title=None),
                         alt.Tooltip("amount:Q", title="R$", format=",.2f")],
            ).properties(height=300),
            use_container_width=True,
        )


# ===========================================================================
# แท็บ 5 — คุณภาพและรีวิว
# ===========================================================================
def tab_quality(f: Filters):
    iv = item_view(f)

    st.subheader("การกระจายของคะแนนรีวิว")
    explain("คะแนน 1–5 ดาวกระจายอย่างไรสำหรับคำสั่งซื้อในช่วงที่เลือก "
            "แท่ง 5 ดาวสูงและแท่ง 1 ดาวเตี้ย = สุขภาพดี — บริบทของคำถามข้อ 12")
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
            x=alt.X("score:O", title="คะแนนรีวิว (ดาว)"),
            y=alt.Y("reviews:Q", title="จำนวนรีวิว"),
            color=alt.Color("score:O", legend=None, scale=alt.Scale(scheme="redyellowgreen")),
            tooltip=[alt.Tooltip("score:O", title="คะแนน"),
                     alt.Tooltip("reviews:Q", title="จำนวนรีวิว", format=",")],
        ).properties(height=280),
        use_container_width=True,
    )

    st.divider()

    st.subheader("คะแนนรีวิวเฉลี่ย แยกตามหมวดหมู่สินค้า")
    explain("หมวดหมู่หลักของแต่ละคำสั่งซื้อ เทียบกับคะแนนเฉลี่ย 1–5 ที่ลูกค้าให้ "
            "(เฉพาะหมวดที่มีคำสั่งซื้อรีวิวอย่างน้อย 50) บนสุด = ลูกค้าพอใจสุด ล่างสุด = หมวดที่ต้องแก้ "
            "Drill-across: เชื่อม fact สินค้า (หมวดหมู่) เข้ากับ fact รีวิว — คำถามข้อ 12")
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
        best_c, best_s = catrev.iloc[0]["category"], catrev.iloc[0]["avg_review_score"]
        worst_c, worst_s = catrev.iloc[-1]["category"], catrev.iloc[-1]["avg_review_score"]
        show = pd.concat([catrev.head(8), catrev.tail(8)]).drop_duplicates("category")
        show = th_category(show)
        st.altair_chart(
            alt.Chart(show).mark_bar().encode(
                x=alt.X("avg_review_score:Q", title="คะแนนรีวิวเฉลี่ย (1–5)",
                        scale=alt.Scale(domain=[0, 5])),
                y=alt.Y("category:N", sort="-x", title=None),
                color=alt.Color("avg_review_score:Q", legend=None,
                                scale=alt.Scale(scheme="redyellowgreen", domain=[3, 4.5])),
                tooltip=[alt.Tooltip("category:N", title="หมวดหมู่"),
                         alt.Tooltip("avg_review_score:Q", title="คะแนนเฉลี่ย"),
                         alt.Tooltip("orders_reviewed:Q", title="คำสั่งซื้อที่รีวิว", format=",")],
            ).properties(height=380),
            use_container_width=True,
        )
        st.caption(f"ดีที่สุด: {cat_label(best_c)} ({best_s}) · "
                   f"แย่ที่สุด: {cat_label(worst_c)} ({worst_s})")

    st.divider()

    st.subheader("ค่าจัดส่งคิดเป็นสัดส่วนของราคาสินค้า แยกตามหมวดหมู่")
    explain("สำหรับหมวดหมู่ใหญ่ ๆ: ค่าจัดส่งบวกเพิ่มจากราคาสินค้ากี่ % "
            "แท่งสูง = ค่าส่งแพงเมื่อเทียบกับของที่ขาย มักเป็นของใหญ่แต่ราคาไม่สูง — คำถามข้อ 11")
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
        fr = th_category(fr)
        st.altair_chart(
            alt.Chart(fr).mark_bar().encode(
                x=alt.X("freight_pct:Q", title="ค่าจัดส่งคิดเป็น % ของราคา"),
                y=alt.Y("category:N", sort="-x", title=None),
                tooltip=[alt.Tooltip("category:N", title="หมวดหมู่"),
                         alt.Tooltip("freight_pct:Q", title="ค่าส่ง % ของราคา"),
                         alt.Tooltip("items:Q", title="จำนวนชิ้น", format=",")],
            ).properties(height=340),
            use_container_width=True,
        )

    st.divider()

    st.subheader("ระยะทางระหว่างผู้ซื้อกับผู้ขาย ส่งผลต่อคะแนนรีวิวไหม?")
    explain("จัดกลุ่มคำสั่งซื้อตามระยะทางระหว่างผู้ซื้อกับผู้ขาย เส้นคือคะแนนรีวิวเฉลี่ย "
            "ระยะทางคำนวณจากพิกัด 2 บทบาท (ลูกค้า/ผู้ขาย) บน fact สินค้า "
            "Drill-across: fact สินค้า ⋈ fact รีวิว — คำถามข้อ 13")
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
                WHEN d.distance_km < 100 THEN '1. น้อยกว่า 100 กม.'
                WHEN d.distance_km < 500 THEN '2. 100–500 กม.'
                WHEN d.distance_km < 1500 THEN '3. 500–1500 กม.'
                ELSE '4. มากกว่า 1500 กม.'
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
            y=alt.Y("orders:Q", title="จำนวนคำสั่งซื้อ"),
            tooltip=[alt.Tooltip("band:N", title="ระยะทาง"),
                     alt.Tooltip("orders:Q", title="คำสั่งซื้อ", format=","),
                     alt.Tooltip("avg_km:Q", title="ระยะทางเฉลี่ย (กม.)"),
                     alt.Tooltip("avg_review_score:Q", title="คะแนนเฉลี่ย")],
        )
        line = base.mark_line(point=True, color="#1f77b4").encode(
            y=alt.Y("avg_review_score:Q", title="คะแนนรีวิวเฉลี่ย (1–5)",
                    scale=alt.Scale(domain=[1, 5])),
        )
        st.altair_chart(alt.layer(bars, line).resolve_scale(y="independent").properties(height=300),
                        use_container_width=True)


# ===========================================================================
# แท็บ 6 — ผู้ขายและตะกร้าสินค้า
# ===========================================================================
def tab_sellers_basket(f: Filters):
    st.subheader("รายได้กระจุกตัวอยู่กับผู้ขายไม่กี่รายไหม? (Pareto 80/20)")
    explain("เรียงผู้ขายตามรายได้ แล้วอ่านว่า: ผู้ขาย X% แรก ทำรายได้ Y% ของทั้งหมด "
            "ถ้า ‘10% แรก’ ใกล้ 80% แปลว่าแพลตฟอร์มพึ่งพาผู้ขายกลุ่มเล็ก ๆ — คำถามข้อ 14")
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
        SELECT '1% แรก' AS bucket, ROUND(MAX(pct_revenue), 1) AS pct_of_revenue, 1 AS srt FROM bands WHERE pct_sellers <= 1
        UNION ALL SELECT '5% แรก',  ROUND(MAX(pct_revenue), 1), 2 FROM bands WHERE pct_sellers <= 5
        UNION ALL SELECT '10% แรก', ROUND(MAX(pct_revenue), 1), 3 FROM bands WHERE pct_sellers <= 10
        UNION ALL SELECT '20% แรก', ROUND(MAX(pct_revenue), 1), 4 FROM bands WHERE pct_sellers <= 20
        ORDER BY srt
    """)
    if pareto.empty:
        empty_note()
    else:
        st.altair_chart(
            alt.Chart(pareto).mark_bar().encode(
                x=alt.X("bucket:N", sort=list(pareto["bucket"]), title="สัดส่วนผู้ขาย",
                        axis=alt.Axis(labelAngle=0)),
                y=alt.Y("pct_of_revenue:Q", title="สัดส่วนรายได้ทั้งหมด (%)",
                        scale=alt.Scale(domain=[0, 100])),
                color=alt.Color("pct_of_revenue:Q", legend=None, scale=alt.Scale(scheme="oranges")),
                tooltip=[alt.Tooltip("bucket:N", title="กลุ่มผู้ขาย"),
                         alt.Tooltip("pct_of_revenue:Q", title="% ของรายได้")],
            ).properties(height=300),
            use_container_width=True,
        )
        top10 = pareto.loc[pareto["bucket"] == "10% แรก"]
        if not top10.empty:
            st.markdown(f"**ผู้ขาย 10% แรก ทำรายได้ {top10['pct_of_revenue'].iloc[0]:.0f}% ของทั้งหมด**")

    st.divider()

    st.subheader("หมวดหมู่สินค้าใดถูกซื้อร่วมกันบ่อย?")
    explain("คู่หมวดหมู่ที่ปรากฏในคำสั่งซื้อเดียวกันบ่อยที่สุด เป็นจุดเริ่มต้นของการจัดชุด cross-sell "
            "สร้างโดยการ self-join fact สินค้า ที่คำสั่งซื้อ — คำถามข้อ 15")
    basket = run_sql(f"""
        {order_id_filter_cte(f)},
        order_categories AS (
            SELECT DISTINCT f.order_id, dp.category
            FROM fact_order_items f
            JOIN dim_products dp ON dp.product_key = f.product_key
            WHERE dp.category <> 'unknown'
              AND f.order_id IN (SELECT order_id FROM kept_orders)
        )
        SELECT a.category AS cat_a, b.category AS cat_b,
               COUNT(*) AS orders_together
        FROM order_categories a
        JOIN order_categories b ON a.order_id = b.order_id AND a.category < b.category
        GROUP BY 1, 2 ORDER BY orders_together DESC LIMIT 12
    """)
    if basket.empty:
        st.info("ไม่มีหมวดหมู่ใดปรากฏคู่กับหมวดอื่นในช่วงที่เลือก "
                "(คำสั่งซื้อส่วนใหญ่ของ Olist มีสินค้าชิ้นเดียว)")
    else:
        basket["pair"] = (basket["cat_a"].map(cat_label) + "  +  "
                          + basket["cat_b"].map(cat_label))
        st.altair_chart(
            alt.Chart(basket).mark_bar().encode(
                x=alt.X("orders_together:Q", title="จำนวนคำสั่งซื้อที่มีทั้งคู่"),
                y=alt.Y("pair:N", sort="-x", title=None),
                tooltip=[alt.Tooltip("pair:N", title="คู่หมวดหมู่"),
                         alt.Tooltip("orders_together:Q", title="คำสั่งซื้อ", format=",")],
            ).properties(height=340),
            use_container_width=True,
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    st.title("📦 แดชบอร์ดตลาดกลางออนไลน์ Olist")
    st.caption("ข้อมูลธุรกรรมจริงจากตลาดกลางอีคอมเมิร์ซ Olist ประเทศบราซิล "
               "(ก.ย. 2016 – ต.ค. 2018) ทุกตัวเลขอ่านจากโมเดลหลายมิติใน olist_dw/dev.duckdb")

    con = get_connection()
    if not warehouse_ready(con):
        st.error("ไม่พบตารางคลังข้อมูล — รัน `dbt run` ในโฟลเดอร์ olist_dw/ ก่อน")
        st.stop()

    filters = build_sidebar_filters()
    st.info("กำลังแสดง: " + active_filter_summary(filters))

    t1, t2, t3, t4, t5, t6 = st.tabs([
        "📊 ภาพรวมยอดขาย", "👥 ลูกค้า", "🚚 การจัดส่ง",
        "💳 การชำระเงิน", "⭐ คุณภาพและรีวิว", "🏪 ผู้ขายและตะกร้า",
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
