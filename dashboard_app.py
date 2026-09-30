"""แดชบอร์ด OLAP ของตลาดกลางออนไลน์ Olist — เวอร์ชันภาษาไทย

ออกแบบสำหรับผู้ชมทั่วไป ไม่ใช่ผู้พัฒนา:
  * ป้ายกำกับและชื่อคอลัมน์ทุกจุดเป็นภาษาไทย ไม่มีชื่อตาราง/คอลัมน์ดิบ
  * ชื่อหมวดหมู่สินค้าแปลเป็นไทย (เช่น health_beauty → "สุขภาพและความงาม")
  * ทุกกราฟมีคำอธิบาย 1 บรรทัดว่าอ่านอย่างไร (การจับคู่กราฟกับคำถามธุรกิจอยู่ใน README ข้อ 7)
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

MONTH_TH_ABBR = {1: "ม.ค.", 2: "ก.พ.", 3: "มี.ค.", 4: "เม.ย.", 5: "พ.ค.", 6: "มิ.ย.",
                 7: "ก.ค.", 8: "ส.ค.", 9: "ก.ย.", 10: "ต.ค.", 11: "พ.ย.", 12: "ธ.ค."}

MONTH_TH_FULL = {1: "มกราคม", 2: "กุมภาพันธ์", 3: "มีนาคม", 4: "เมษายน", 5: "พฤษภาคม",
                 6: "มิถุนายน", 7: "กรกฎาคม", 8: "สิงหาคม", 9: "กันยายน", 10: "ตุลาคม",
                 11: "พฤศจิกายน", 12: "ธันวาคม"}

SIZE_BAND_TH = {"Small": "เล็ก", "Medium": "กลาง", "Large": "ใหญ่", "Unknown": "ไม่ระบุ"}
SIZE_BAND_ORDER = ["Small", "Medium", "Large"]


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


# ---------------------------------------------------------------------------
# Chart helpers — every chart prints its value directly on the mark itself,
# so the answer is visible without hovering (อาจารย์ชอบให้เห็นเลยไม่ต้องชี้เมาส์).
# ---------------------------------------------------------------------------
def bar_labeled(df, x, y, x_title, y_title, *, fmt=",.0f", height=300, angle=0,
                sort=None, color="#4C78A8", text_size=12, dy=-6):
    """Vertical bar chart — the y-value is printed above every bar."""
    enc_x = alt.X(f"{x}:N", title=x_title, sort=sort, axis=alt.Axis(labelAngle=angle))
    enc_y = alt.Y(f"{y}:Q", title=y_title)
    base = alt.Chart(df).encode(x=enc_x)
    bars = base.mark_bar(color=color).encode(
        y=enc_y,
        tooltip=[alt.Tooltip(f"{x}:N", title=x_title), alt.Tooltip(f"{y}:Q", title=y_title, format=fmt)],
    )
    text = base.mark_text(dy=dy, fontSize=text_size, fontWeight="bold").encode(
        y=enc_y, text=alt.Text(f"{y}:Q", format=fmt),
    )
    return alt.layer(bars, text).properties(height=height)


def bar_named_labeled(df, x, y, label, x_title, y_title, *, height=360, sort=None,
                       color="#4C78A8", text_size=10):
    """Vertical bar chart where bar height = `y`, but the text on top of each bar
    shows a different (categorical) field `label` — e.g. the winning category's
    name — written vertically so it fits above a narrow bar."""
    enc_x = alt.X(f"{x}:N", title=x_title, sort=sort, axis=alt.Axis(labelAngle=-90))
    enc_y = alt.Y(f"{y}:Q", title=y_title)
    base = alt.Chart(df).encode(x=enc_x)
    bars = base.mark_bar(color=color).encode(
        y=enc_y,
        tooltip=[alt.Tooltip(f"{x}:N", title=x_title), alt.Tooltip(f"{label}:N", title="ผู้ชนะ"),
                 alt.Tooltip(f"{y}:Q", title=y_title, format=",.0f")],
    )
    text = base.mark_text(dy=6, dx=4, fontSize=text_size, angle=270, align="left",
                           baseline="middle").encode(
        y=enc_y, text=alt.Text(f"{label}:N"),
    )
    return alt.layer(bars, text).properties(height=height)


def hbar_labeled(df, x, y, x_title, y_title, *, fmt=",.0f", height=340, sort="-x",
                  color="#4C78A8"):
    """Horizontal bar chart with the value printed right after the bar's end."""
    enc_y = alt.Y(f"{y}:N", title=None, sort=sort)
    enc_x = alt.X(f"{x}:Q", title=x_title)
    base = alt.Chart(df).encode(y=enc_y)
    bars = base.mark_bar(color=color).encode(
        x=enc_x,
        tooltip=[alt.Tooltip(f"{y}:N", title=y_title), alt.Tooltip(f"{x}:Q", title=x_title, format=fmt)],
    )
    text = base.mark_text(dx=4, align="left", fontSize=11, fontWeight="bold").encode(
        x=enc_x, text=alt.Text(f"{x}:Q", format=fmt),
    )
    return alt.layer(bars, text).properties(height=height)


def grouped_bar_labeled(df, x, y, group, x_title, y_title, group_title, *, fmt=",.0f",
                         height=380, sort=None, scheme="tableau10"):
    """Grouped (dodged) bar chart — compares `group` (e.g. year) side by side
    within every `x` (e.g. category), value labeled on top of each small bar.
    This is the main 'compare across categories AND across years' chart."""
    enc_x = alt.X(f"{x}:N", title=x_title, sort=sort, axis=alt.Axis(labelAngle=-30))
    enc_group = alt.XOffset(f"{group}:N")
    enc_y = alt.Y(f"{y}:Q", title=y_title)
    enc_color = alt.Color(f"{group}:N", title=group_title, scale=alt.Scale(scheme=scheme))
    base = alt.Chart(df).encode(x=enc_x, xOffset=enc_group)
    bars = base.mark_bar().encode(
        y=enc_y, color=enc_color,
        tooltip=[alt.Tooltip(f"{x}:N", title=x_title), alt.Tooltip(f"{group}:N", title=group_title),
                 alt.Tooltip(f"{y}:Q", title=y_title, format=fmt)],
    )
    text = base.mark_text(dy=-4, fontSize=8, angle=270, align="left", baseline="middle").encode(
        y=enc_y, text=alt.Text(f"{y}:Q", format=fmt),
    )
    return alt.layer(bars, text).properties(height=height)


def stacked_bar_labeled(df, x, y, color, x_title, y_title, color_title, *, fmt=",.0f",
                         height=420, sort=None, scheme="tableau10", min_label_share=0.06):
    """Stacked bar chart (genuine 'stack' chart) with a label inside each segment
    that is big enough to hold one — used to compare composition (e.g.
    payment-method mix) across time. Tiny slivers are left unlabeled (their
    number would only overlap the neighbours) but stay fully readable via
    tooltip, so no information is lost."""
    df = df.copy()
    share = df[y] / df.groupby(x)[y].transform("sum")
    big_enough = share >= min_label_share
    df["_label"] = [f"{int(v):,}" if ok else "" for v, ok in zip(df[y], big_enough)]

    enc_x = alt.X(f"{x}:N", title=x_title, sort=sort, axis=alt.Axis(labelAngle=-30))
    enc_y = alt.Y(f"{y}:Q", title=y_title, stack="zero")
    enc_color = alt.Color(f"{color}:N", title=color_title, scale=alt.Scale(scheme=scheme))
    enc_order = alt.Order(f"{color}:N")
    base = alt.Chart(df).encode(x=enc_x, order=enc_order)
    bars = base.mark_bar().encode(
        y=enc_y, color=enc_color,
        tooltip=[alt.Tooltip(f"{x}:N", title=x_title), alt.Tooltip(f"{color}:N", title=color_title),
                 alt.Tooltip(f"{y}:Q", title=y_title, format=fmt)],
    )
    text = base.mark_text(fontSize=10, color="white", fontWeight="bold").encode(
        y=alt.Y(f"{y}:Q", stack="zero"), text=alt.Text("_label:N"),
    )
    return alt.layer(bars, text).properties(height=height)


# ===========================================================================
# แท็บ 1 — ยอดขายตามเวลาและหมวดหมู่ (ข้อ 1, 2, 3, 13)
# ===========================================================================
def tab_sales_trends(f: Filters):
    iv = item_view(f)

    kpis = run_sql(f"""
        WITH i AS ({iv})
        SELECT
            COALESCE(SUM(price), 0)  AS revenue,
            COUNT(DISTINCT order_id) AS orders
        FROM i
    """)
    if kpis.empty or kpis.loc[0, "orders"] == 0:
        empty_note(); return
    r = kpis.iloc[0]
    aov = r.revenue / r.orders if r.orders else 0
    c1, c2, c3 = st.columns(3)
    c1.metric("รายได้รวม", brl(r.revenue))
    c2.metric("จำนวนคำสั่งซื้อ", f"{int(r.orders):,}")
    c3.metric("ยอดขายเฉลี่ยต่อคำสั่งซื้อ", brl(aov))

    st.divider()

    st.subheader("แต่ละเดือนหมวดหมู่สินค้าใดสร้างยอดขายสูงที่สุด? (ข้อ 1)")
    explain("แต่ละแท่งคือ 1 เดือน ความสูงของแท่ง = รายได้ของหมวดหมู่ที่ชนะเดือนนั้น "
            "ตัวหนังสือแนวตั้งเหนือแท่งคือชื่อหมวดหมู่ที่ชนะ — ไม่ต้องเอาเมาส์ไปชี้ก็เห็นคำตอบ")
    top_month = run_sql(f"""
        {order_id_filter_cte(f)}
        , monthly_category AS (
            SELECT dd.year, dd.month, dp.category, SUM(fi.price) AS revenue
            FROM fact_order_items fi
            JOIN dim_date dd ON dd.date_key = fi.purchase_date_key
            JOIN dim_products dp ON dp.product_key = fi.product_key
            WHERE dp.category <> 'unknown'
              AND fi.order_id IN (SELECT order_id FROM kept_orders)
            GROUP BY 1, 2, 3
        ),
        ranked AS (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY year, month ORDER BY revenue DESC) AS rn
            FROM monthly_category
        )
        SELECT year, month, category, ROUND(revenue, 2) AS revenue
        FROM ranked WHERE rn = 1
        ORDER BY year, month
    """)
    if top_month.empty:
        empty_note()
    else:
        top_month["ym_label"] = top_month.apply(
            lambda row: f"{MONTH_TH_ABBR[int(row['month'])]} {int(row['year'])}", axis=1)
        top_month["ym_sort"] = top_month["year"] * 100 + top_month["month"]
        top_month = top_month.sort_values("ym_sort")
        top_month["category_th"] = top_month["category"].map(cat_label)
        st.altair_chart(
            bar_named_labeled(top_month, "ym_label", "revenue", "category_th",
                              "เดือน", "รายได้ของหมวดหมู่ที่ชนะ (R$)",
                              sort=list(top_month["ym_label"])),
            use_container_width=True,
        )

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("ในแต่ละปี เดือนใดมียอดขายสูงสุด? (ข้อ 2)")
        explain("เปรียบเทียบรายปี — แต่ละแท่งคือ 1 ปี ความสูง = รายได้ของเดือนที่ทำยอดสูงสุดในปีนั้น "
                "ตัวหนังสือบนแท่งบอกชื่อเดือนที่ชนะ")
        top_year_month = run_sql(f"""
            {order_id_filter_cte(f)}
            , monthly AS (
                SELECT dd.year, dd.month, SUM(fi.price) AS revenue
                FROM fact_order_items fi
                JOIN dim_date dd ON dd.date_key = fi.purchase_date_key
                WHERE fi.order_id IN (SELECT order_id FROM kept_orders)
                GROUP BY 1, 2
            ),
            ranked AS (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY year ORDER BY revenue DESC) AS rn
                FROM monthly
            )
            SELECT year, month, ROUND(revenue, 2) AS revenue
            FROM ranked WHERE rn = 1
            ORDER BY year
        """)
        if top_year_month.empty:
            empty_note()
        else:
            top_year_month["year_label"] = top_year_month["year"].astype(str)
            top_year_month["month_th"] = top_year_month["month"].map(MONTH_TH_FULL)
            st.altair_chart(
                bar_named_labeled(top_year_month, "year_label", "revenue", "month_th",
                                  "ปี", "รายได้ของเดือนที่ชนะ (R$)", height=320,
                                  sort=list(top_year_month["year_label"])),
                use_container_width=True,
            )

    with col2:
        st.subheader("ในแต่ละเดือนสินค้าประเภทใดขายได้เยอะที่สุด? (ข้อ 13)")
        explain("เหมือนกราฟข้อ 1 แต่วัดเป็นจำนวนชิ้นที่ขายได้ ไม่ใช่มูลค่าเงิน "
                "หมวดที่ขายเยอะสุดอาจไม่ใช่หมวดที่ทำเงินสูงสุดก็ได้")
        top_units = run_sql(f"""
            {order_id_filter_cte(f)}
            , monthly_category AS (
                SELECT dd.year, dd.month, dp.category, COUNT(*) AS units_sold
                FROM fact_order_items fi
                JOIN dim_date dd ON dd.date_key = fi.purchase_date_key
                JOIN dim_products dp ON dp.product_key = fi.product_key
                WHERE dp.category <> 'unknown'
                  AND fi.order_id IN (SELECT order_id FROM kept_orders)
                GROUP BY 1, 2, 3
            ),
            ranked AS (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY year, month ORDER BY units_sold DESC) AS rn
                FROM monthly_category
            )
            SELECT year, month, category, units_sold
            FROM ranked WHERE rn = 1
            ORDER BY year, month
        """)
        if top_units.empty:
            empty_note()
        else:
            top_units["ym_label"] = top_units.apply(
                lambda row: f"{MONTH_TH_ABBR[int(row['month'])]} {int(row['year'])}", axis=1)
            top_units["ym_sort"] = top_units["year"] * 100 + top_units["month"]
            top_units = top_units.sort_values("ym_sort")
            top_units["category_th"] = top_units["category"].map(cat_label)
            st.altair_chart(
                bar_named_labeled(top_units, "ym_label", "units_sold", "category_th",
                                  "เดือน", "จำนวนชิ้นที่ขายของหมวดที่ชนะ", height=320,
                                  sort=list(top_units["ym_label"])),
                use_container_width=True,
            )

    st.divider()

    st.subheader("แต่ละปีสินค้าแต่ละหมวดหมู่มียอดขายแตกต่างกันเท่าใด? (ข้อ 3)")
    explain("กราฟเปรียบเทียบ — เทียบ 8 หมวดหมู่ที่ทำรายได้สูงสุด แยกสีตามปี "
            "แท่งที่วางคู่กันในแต่ละหมวดคือปีต่างกัน ตัวเลขบนแท่งคือรายได้ (R$) ของหมวดนั้นในปีนั้น")
    yearly_cat = run_sql(f"""
        {order_id_filter_cte(f)}
        , yearly_category AS (
            SELECT dd.year, dp.category, SUM(fi.price) AS revenue
            FROM fact_order_items fi
            JOIN dim_date dd ON dd.date_key = fi.purchase_date_key
            JOIN dim_products dp ON dp.product_key = fi.product_key
            WHERE dp.category <> 'unknown'
              AND fi.order_id IN (SELECT order_id FROM kept_orders)
            GROUP BY 1, 2
        ),
        top_categories AS (
            SELECT category FROM yearly_category
            GROUP BY category ORDER BY SUM(revenue) DESC LIMIT 8
        )
        SELECT yc.year, yc.category, ROUND(yc.revenue, 2) AS revenue
        FROM yearly_category yc
        JOIN top_categories tc ON tc.category = yc.category
        ORDER BY yc.category, yc.year
    """)
    if yearly_cat.empty:
        empty_note()
    else:
        yearly_cat = th_category(yearly_cat)
        yearly_cat["year"] = yearly_cat["year"].astype(str)
        order = (yearly_cat.groupby("category")["revenue"].sum()
                 .sort_values(ascending=False).index.tolist())
        st.altair_chart(
            grouped_bar_labeled(yearly_cat, "category", "revenue", "year",
                                "หมวดหมู่", "รายได้ (R$)", "ปี",
                                sort=order, height=400),
            use_container_width=True,
        )


# ===========================================================================
# แท็บ 2 — การยกเลิกคำสั่งซื้อ (ข้อ 4)
# ===========================================================================
def tab_cancellations(f: Filters):
    st.subheader("หมวดหมู่สินค้าใดที่ถูกยกเลิกมากที่สุด? (ข้อ 4)")
    explain("นับจำนวนชิ้นสินค้าที่อยู่ในออเดอร์ที่มีสถานะ 'ยกเลิก' (canceled) แยกตามหมวดหมู่ "
            "ตัวเลขท้ายแท่งคือจำนวนชิ้นที่ถูกยกเลิกจริงในช่วงที่เลือก · "
            "หมายเหตุ: ข้อนี้เดิมตั้งเป็น 'ระยะเวลาจัดส่งมีผลต่อการยกเลิกไหม' แต่ออเดอร์ที่ถูกยกเลิก "
            "มีค่าระยะเวลาจัดส่งอยู่แค่ 7 แถวจาก 542 แถว (ถูกยกเลิกก่อนส่งของจริง) จึงเปลี่ยนมาดูตามหมวดหมู่แทน")
    df = run_sql(f"""
        {order_id_filter_cte(f)}
        SELECT dp.category, COUNT(*) AS cancelled_items
        FROM fact_order_items fi
        JOIN dim_order_status dos ON dos.order_status_key = fi.order_status_key
        JOIN dim_products dp ON dp.product_key = fi.product_key
        WHERE dos.order_status = 'canceled'
          AND dp.category <> 'unknown'
          AND fi.order_id IN (SELECT order_id FROM kept_orders)
        GROUP BY 1
        ORDER BY cancelled_items DESC
        LIMIT 10
    """)
    if df.empty:
        st.info("ไม่มีออเดอร์ที่ถูกยกเลิกในช่วงที่เลือก — ลองขยายตัวกรองวันที่หรือหมวดหมู่")
        return
    df = th_category(df)
    st.altair_chart(
        hbar_labeled(df, "cancelled_items", "category", "จำนวนชิ้นที่ถูกยกเลิก", "หมวดหมู่", fmt=","),
        use_container_width=True,
    )
    st.markdown(f"**หมวดหมู่ที่ถูกยกเลิกมากที่สุด: {df.iloc[0]['category']} "
                f"({int(df.iloc[0]['cancelled_items'])} ชิ้น)**")


# ===========================================================================
# แท็บ 3 — ปัจจัยที่มีผลต่อค่าจัดส่ง (ข้อ 6, 7, 8)
# ===========================================================================
def tab_shipping_factors(f: Filters):
    iv = item_view(f)

    st.subheader("ราคาสินค้ามีผลต่อค่าส่งหรือไม่? (ข้อ 6)")
    explain("จัดกลุ่มสินค้าตามช่วงราคา แท่งคือค่าจัดส่งเฉลี่ยของกลุ่มนั้น "
            "ถ้าแท่งสูงขึ้นตามราคา แปลว่าของแพงมักมีค่าส่งแพงตามไปด้วย")
    price_df = run_sql(f"""
        WITH i AS ({iv})
        SELECT
            CASE
                WHEN price < 50   THEN '1. ต่ำกว่า R$50'
                WHEN price < 100  THEN '2. R$50-99'
                WHEN price < 200  THEN '3. R$100-199'
                WHEN price < 400  THEN '4. R$200-399'
                ELSE '5. R$400 ขึ้นไป'
            END AS price_bucket,
            COUNT(*) AS items,
            ROUND(AVG(freight_value), 2) AS avg_freight
        FROM i
        GROUP BY 1 ORDER BY 1
    """)
    if price_df.empty:
        empty_note()
    else:
        st.altair_chart(
            bar_labeled(price_df, "price_bucket", "avg_freight", "ช่วงราคาสินค้า",
                        "ค่าจัดส่งเฉลี่ย (R$)", fmt=",.2f",
                        sort=list(price_df["price_bucket"])),
            use_container_width=True,
        )

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("ขนาดสินค้ามีผลต่อค่าส่งหรือไม่? (ข้อ 7)")
        explain("size_band คำนวณจากปริมาตรสินค้า (ยาว×กว้าง×สูง) แบ่งเป็นเล็ก/กลาง/ใหญ่")
        size_df = run_sql(f"""
            WITH i AS ({iv})
            SELECT product_size_band AS size_band, COUNT(*) AS items,
                   ROUND(AVG(freight_value), 2) AS avg_freight
            FROM i
            WHERE product_size_band <> 'Unknown'
            GROUP BY 1
        """)
        if size_df.empty:
            empty_note()
        else:
            size_df["size_th"] = size_df["size_band"].map(SIZE_BAND_TH)
            st.altair_chart(
                bar_labeled(size_df, "size_th", "avg_freight", "ขนาดสินค้า",
                            "ค่าจัดส่งเฉลี่ย (R$)", fmt=",.2f",
                            sort=[SIZE_BAND_TH[s] for s in SIZE_BAND_ORDER], height=320),
                use_container_width=True,
            )

    with col2:
        st.subheader("น้ำหนักสินค้ามีผลต่อค่าส่งหรือไม่? (ข้อ 8)")
        explain("จัดกลุ่มสินค้าตามน้ำหนัก (กรัม) แท่งคือค่าจัดส่งเฉลี่ยของกลุ่มนั้น")
        weight_df = run_sql(f"""
            {order_id_filter_cte(f)}
            SELECT
                CASE
                    WHEN p.weight_g < 500   THEN '1. <500 กรัม'
                    WHEN p.weight_g < 2000  THEN '2. 500ก.-2กก.'
                    WHEN p.weight_g < 5000  THEN '3. 2-5 กก.'
                    WHEN p.weight_g < 10000 THEN '4. 5-10 กก.'
                    ELSE '5. >10 กก.'
                END AS weight_bucket,
                COUNT(*) AS items,
                ROUND(AVG(fi.freight_value), 2) AS avg_freight
            FROM fact_order_items fi
            JOIN dim_products p ON p.product_key = fi.product_key
            WHERE p.weight_g IS NOT NULL
              AND fi.order_id IN (SELECT order_id FROM kept_orders)
            GROUP BY 1 ORDER BY 1
        """)
        if weight_df.empty:
            empty_note()
        else:
            st.altair_chart(
                bar_labeled(weight_df, "weight_bucket", "avg_freight", "ช่วงน้ำหนัก",
                            "ค่าจัดส่งเฉลี่ย (R$)", fmt=",.2f",
                            sort=list(weight_df["weight_bucket"]), height=320),
                use_container_width=True,
            )


# ===========================================================================
# แท็บ 4 — การจัดส่งและความพึงพอใจของลูกค้า (ข้อ 5, 9, 14)
# ===========================================================================
def tab_delivery_quality(f: Filters):
    st.subheader("ระยะเวลาขนส่งสินค้ามีผลต่อคะแนนรีวิวหรือไม่? (ข้อ 5, Drill-Across)")
    explain("เชื่อม fact สินค้า (ระยะเวลาจัดส่ง) เข้ากับ fact รีวิว ผ่านคำสั่งซื้อ "
            "จัดกลุ่มตามจำนวนวันที่ใช้ส่ง แท่งคือคะแนนรีวิวเฉลี่ยของกลุ่มนั้น")
    q5 = run_sql(f"""
        {order_id_filter_cte(f)}
        , delivery AS (
            SELECT order_id, AVG(delivery_days) AS delivery_days
            FROM fact_order_items
            WHERE delivery_days IS NOT NULL AND order_id IN (SELECT order_id FROM kept_orders)
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
                WHEN d.delivery_days < 7  THEN '1. <7 วัน'
                WHEN d.delivery_days < 14 THEN '2. 7-13 วัน'
                WHEN d.delivery_days < 21 THEN '3. 14-20 วัน'
                ELSE '4. 21+ วัน'
            END AS delivery_bucket,
            COUNT(*) AS orders,
            ROUND(AVG(r.review_score), 2) AS avg_review_score
        FROM delivery d JOIN review r ON r.order_id = d.order_id
        GROUP BY 1 ORDER BY 1
    """)
    if q5.empty:
        empty_note()
    else:
        st.altair_chart(
            bar_labeled(q5, "delivery_bucket", "avg_review_score", "ระยะเวลาจัดส่ง",
                        "คะแนนรีวิวเฉลี่ย (1-5)", fmt=".2f",
                        sort=list(q5["delivery_bucket"]), color="#d62728", height=320),
            use_container_width=True,
        )

    st.divider()

    st.subheader("ค่าส่งมีผลต่อคะแนนรีวิวหรือไม่? (ข้อ 9, Drill-Across)")
    explain("จัดกลุ่มออเดอร์ตามค่าส่งคิดเป็น % ของมูลค่าสินค้า แท่งคือคะแนนรีวิวเฉลี่ยของกลุ่มนั้น")
    q9 = run_sql(f"""
        {order_id_filter_cte(f)}
        , freight AS (
            SELECT order_id, SUM(freight_value) AS freight_value, SUM(price) AS basket_value
            FROM fact_order_items
            WHERE order_id IN (SELECT order_id FROM kept_orders)
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
                WHEN 100.0 * fr.freight_value / NULLIF(fr.basket_value, 0) < 10 THEN '1. <10%'
                WHEN 100.0 * fr.freight_value / NULLIF(fr.basket_value, 0) < 20 THEN '2. 10-19%'
                WHEN 100.0 * fr.freight_value / NULLIF(fr.basket_value, 0) < 30 THEN '3. 20-29%'
                ELSE '4. 30%+'
            END AS freight_pct_bucket,
            COUNT(*) AS orders,
            ROUND(AVG(r.review_score), 2) AS avg_review_score
        FROM freight fr JOIN review r ON r.order_id = fr.order_id
        WHERE fr.basket_value > 0
        GROUP BY 1 ORDER BY 1
    """)
    if q9.empty:
        empty_note()
    else:
        st.altair_chart(
            bar_labeled(q9, "freight_pct_bucket", "avg_review_score", "ค่าส่ง % ของราคาสินค้า",
                        "คะแนนรีวิวเฉลี่ย (1-5)", fmt=".2f",
                        sort=list(q9["freight_pct_bucket"]), color="#d62728", height=320),
            use_container_width=True,
        )

    st.divider()

    st.subheader("ขนาดสินค้ามีผลทำให้การส่งเกิดการล่าช้าหรือไม่? (ข้อ 14)")
    explain("เทียบอัตราส่งช้า (%) ระหว่างสินค้าขนาดเล็ก/กลาง/ใหญ่")
    iv = item_view(f)
    q14 = run_sql(f"""
        WITH i AS ({iv})
        SELECT product_size_band AS size_band,
               COUNT(*) AS items,
               ROUND(100.0 * AVG(is_late_delivery), 1) AS late_rate_pct
        FROM i
        WHERE product_size_band <> 'Unknown' AND is_late_delivery IS NOT NULL
        GROUP BY 1
    """)
    if q14.empty:
        empty_note()
    else:
        q14["size_th"] = q14["size_band"].map(SIZE_BAND_TH)
        st.altair_chart(
            bar_labeled(q14, "size_th", "late_rate_pct", "ขนาดสินค้า",
                        "อัตราส่งช้า (%)", fmt=".1f",
                        sort=[SIZE_BAND_TH[s] for s in SIZE_BAND_ORDER], height=300),
            use_container_width=True,
        )


# ===========================================================================
# แท็บ 5 — พฤติกรรมการสั่งซื้อและการชำระเงิน (ข้อ 10, 11, 12, 15)
# ===========================================================================
def tab_ordering_payment(f: Filters):
    pay_filter = ""
    if f.payment_labels is not None:
        pay_filter = f"AND dpt.payment_label IN ({_sql_str_list(f.payment_labels)})"

    st.subheader("ในแต่ละเดือน วิธีการชำระเงินใดถูกใช้มากที่สุด? (ข้อ 10)")
    explain("กราฟบน: แต่ละแท่งคือ 1 เดือน ตัวหนังสือบนแท่งคือชื่อวิธีชำระเงินที่ถูกใช้บ่อยสุดเดือนนั้น "
            "กราฟล่าง: กราฟ stack แสดงสัดส่วนการใช้ทั้ง 4 วิธีจริงในแต่ละไตรมาส ให้เห็นภาพรวมทั้งหมด")
    q10_winner = run_sql(f"""
        {order_id_filter_cte(f)}
        , monthly_method AS (
            SELECT dd.year, dd.month, dpt.payment_label, COUNT(DISTINCT fp.order_id) AS orders
            FROM fact_order_payments fp
            JOIN dim_date dd ON dd.date_key = fp.purchase_date_key
            JOIN dim_payment_type dpt ON dpt.payment_type_key = fp.payment_type_key
            WHERE dpt.is_valid_method
              AND fp.order_id IN (SELECT order_id FROM kept_orders)
              {pay_filter}
            GROUP BY 1, 2, 3
        ),
        ranked AS (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY year, month ORDER BY orders DESC) AS rn
            FROM monthly_method
        )
        SELECT year, month, payment_label, orders
        FROM ranked WHERE rn = 1
        ORDER BY year, month
    """)
    if q10_winner.empty:
        empty_note()
    else:
        q10_winner = th_payment(q10_winner, col="payment_label")
        q10_winner["ym_label"] = q10_winner.apply(
            lambda row: f"{MONTH_TH_ABBR[int(row['month'])]} {int(row['year'])}", axis=1)
        q10_winner["ym_sort"] = q10_winner["year"] * 100 + q10_winner["month"]
        q10_winner = q10_winner.sort_values("ym_sort")
        st.altair_chart(
            bar_named_labeled(q10_winner, "ym_label", "orders", "payment_label",
                              "เดือน", "จำนวนคำสั่งซื้อของวิธีที่ชนะ", height=320,
                              sort=list(q10_winner["ym_label"])),
            use_container_width=True,
        )

    q10_stack = run_sql(f"""
        {order_id_filter_cte(f)}
        SELECT dd.year, dd.quarter, dpt.payment_label, COUNT(DISTINCT fp.order_id) AS orders
        FROM fact_order_payments fp
        JOIN dim_date dd ON dd.date_key = fp.purchase_date_key
        JOIN dim_payment_type dpt ON dpt.payment_type_key = fp.payment_type_key
        WHERE dpt.is_valid_method
          AND fp.order_id IN (SELECT order_id FROM kept_orders)
          {pay_filter}
        GROUP BY 1, 2, 3
        ORDER BY 1, 2
    """)
    if not q10_stack.empty:
        q10_stack = th_payment(q10_stack, col="payment_label")
        q10_stack["q_label"] = "Q" + q10_stack["quarter"].astype(str) + "/" + q10_stack["year"].astype(str)
        q10_stack["q_sort"] = q10_stack["year"] * 10 + q10_stack["quarter"]
        order_q = (q10_stack[["q_label", "q_sort"]].drop_duplicates()
                   .sort_values("q_sort")["q_label"].tolist())
        st.altair_chart(
            stacked_bar_labeled(q10_stack, "q_label", "orders", "payment_label",
                                "ไตรมาส", "จำนวนคำสั่งซื้อ", "วิธีชำระเงิน",
                                sort=order_q, fmt=","),
            use_container_width=True,
        )

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("จำนวนรูปภาพของสินค้ามีผลต่อยอดคำสั่งซื้อหรือไม่? (ข้อ 11)")
        explain("จัดกลุ่มสินค้าตามจำนวนรูปที่ผู้ขายลงไว้ แท่งคือจำนวนคำสั่งซื้อของกลุ่มนั้น")
        q11 = run_sql(f"""
            {order_id_filter_cte(f)}
            SELECT
                CASE
                    WHEN p.photos_qty = 0  THEN '0 รูป'
                    WHEN p.photos_qty <= 2 THEN '1-2 รูป'
                    WHEN p.photos_qty <= 4 THEN '3-4 รูป'
                    WHEN p.photos_qty <= 6 THEN '5-6 รูป'
                    ELSE '7+ รูป'
                END AS photo_bucket,
                MIN(p.photos_qty) AS sort_key,
                COUNT(DISTINCT fi.order_id) AS orders
            FROM fact_order_items fi
            JOIN dim_products p ON p.product_key = fi.product_key
            WHERE p.photos_qty IS NOT NULL
              AND fi.order_id IN (SELECT order_id FROM kept_orders)
            GROUP BY 1 ORDER BY sort_key
        """)
        if q11.empty:
            empty_note()
        else:
            st.altair_chart(
                bar_labeled(q11, "photo_bucket", "orders", "จำนวนรูปภาพ", "จำนวนคำสั่งซื้อ",
                            fmt=",", sort=list(q11["photo_bucket"]), height=320),
                use_container_width=True,
            )

    with col2:
        st.subheader("ช่วงเวลาไหนของวันที่มีปริมาณคำสั่งซื้อมากที่สุด? (ข้อ 12)")
        explain("แกน X คือชั่วโมงของวัน (0-23 น.) แท่งสีแดง = ชั่วโมงที่พีคสุด")
        iv = item_view(f)
        q12 = run_sql(f"""
            WITH i AS ({iv})
            SELECT purchase_hour, COUNT(DISTINCT order_id) AS orders
            FROM i
            WHERE purchase_hour IS NOT NULL
            GROUP BY 1 ORDER BY 1
        """)
        if q12.empty:
            empty_note()
        else:
            peak = q12.loc[q12["orders"].idxmax()]
            chart = alt.Chart(q12).mark_bar().encode(
                x=alt.X("purchase_hour:O", title="ชั่วโมง (0-23 น.)"),
                y=alt.Y("orders:Q", title="จำนวนคำสั่งซื้อ"),
                color=alt.condition(
                    alt.datum.purchase_hour == int(peak["purchase_hour"]),
                    alt.value("#d62728"), alt.value("#4C78A8"),
                ),
                tooltip=[alt.Tooltip("purchase_hour:O", title="ชั่วโมง"),
                         alt.Tooltip("orders:Q", title="คำสั่งซื้อ", format=",")],
            ).properties(height=320)
            st.altair_chart(chart, use_container_width=True)
            st.markdown(f"**ช่วงพีคสุดคือ {int(peak['purchase_hour'])}:00 น. "
                        f"({int(peak['orders']):,} คำสั่งซื้อ)**")

    st.divider()

    st.subheader("หมวดหมู่สินค้าใดมีการชำระแบบผ่อนสูงสุด? (ข้อ 15, Drill-Across)")
    explain("เชื่อม fact สินค้า (หมวดหมู่หลักของออเดอร์) เข้ากับ fact การชำระเงิน (จำนวนงวดผ่อน) "
            "ผ่านคำสั่งซื้อ แท่งคือจำนวนงวดผ่อนเฉลี่ยของหมวดหมู่นั้น (เฉพาะหมวดที่มีอย่างน้อย 50 ออเดอร์)")
    q15 = run_sql(f"""
        {order_id_filter_cte(f)}
        , order_category AS (
            SELECT order_id, category FROM (
                SELECT fi.order_id, p.category,
                       ROW_NUMBER() OVER (PARTITION BY fi.order_id ORDER BY COUNT(*) DESC) AS rn
                FROM fact_order_items fi
                JOIN dim_products p ON p.product_key = fi.product_key
                WHERE p.category <> 'unknown'
                  AND fi.order_id IN (SELECT order_id FROM kept_orders)
                GROUP BY 1, 2
            ) WHERE rn = 1
        ),
        order_payment AS (
            SELECT order_id, MAX(payment_installments) AS installments
            FROM fact_order_payments
            WHERE order_id IN (SELECT order_id FROM kept_orders)
            GROUP BY 1
        )
        SELECT oc.category, COUNT(*) AS orders,
               ROUND(AVG(op.installments), 2) AS avg_installments
        FROM order_category oc JOIN order_payment op ON op.order_id = oc.order_id
        GROUP BY 1 HAVING COUNT(*) >= 50
        ORDER BY avg_installments DESC
        LIMIT 10
    """)
    if q15.empty:
        empty_note()
    else:
        q15 = th_category(q15)
        st.altair_chart(
            hbar_labeled(q15, "avg_installments", "category", "จำนวนงวดผ่อนเฉลี่ย", "หมวดหมู่",
                        fmt=".2f"),
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

    t1, t2, t3, t4, t5 = st.tabs([
        "📊 ยอดขายตามเวลาและหมวดหมู่", "❌ การยกเลิกคำสั่งซื้อ",
        "📦 ปัจจัยค่าจัดส่ง", "⭐ การจัดส่งและความพึงพอใจ",
        "💳 พฤติกรรมการสั่งซื้อและการชำระเงิน",
    ])
    with t1:
        tab_sales_trends(filters)
    with t2:
        tab_cancellations(filters)
    with t3:
        tab_shipping_factors(filters)
    with t4:
        tab_delivery_quality(filters)
    with t5:
        tab_ordering_payment(filters)


if __name__ == "__main__":
    main()
