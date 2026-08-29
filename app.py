import streamlit as st
import duckdb
import pandas as pd

from warehouse import ensure_warehouse_built, DB_PATH

# Page config
st.set_page_config(
    page_title="Olist DW Explorer",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

with st.spinner("Building data warehouse (first run only)..."):
    ok, log = ensure_warehouse_built()
if not ok:
    st.error("dbt run failed while building the warehouse. See log below.")
    st.code(log)
    st.stop()

@st.cache_resource
def get_connection():
    return duckdb.connect(str(DB_PATH), read_only=True)

# Helper to execute queries safely
def run_query(query):
    conn = get_connection()
    try:
        return conn.execute(query).fetch_df()
    except Exception as e:
        st.error(f"Error running query: {e}")
        return pd.DataFrame()

# App Title & Style
st.markdown("""
    <style>
    .main-title {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1F2937;
        margin-bottom: 0.2rem;
    }
    .subtitle {
        font-size: 1.1rem;
        color: #4B5563;
        margin-bottom: 2rem;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">📦 Olist DW Explorer</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Inspect and preview raw datasets, staging tables, and dimension views in dev.duckdb</div>', unsafe_allow_html=True)

# Fetch all tables
tables_df = run_query("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' ORDER BY table_name")
tables = tables_df['table_name'].tolist() if not tables_df.empty else []

if not tables:
    st.warning("No tables found in the database. Please make sure the dbt run was successful.")
else:
    # Get row counts for all tables
    table_stats = []
    for t in tables:
        count_df = run_query(f"SELECT COUNT(*) as count FROM main.{t}")
        count = count_df['count'].iloc[0] if not count_df.empty else 0
        table_stats.append({"table_name": t, "row_count": count})

    stats_df = pd.DataFrame(table_stats)

    # Sidebar
    st.sidebar.title("🗂️ Table Browser")
    selected_table = st.sidebar.selectbox("Select a table to inspect", tables)

    st.sidebar.markdown("---")
    st.sidebar.subheader("Quick Stats")
    st.sidebar.markdown(f"**Total Tables:** {len(tables)}")
    st.sidebar.markdown(f"**Total Rows Staged:** {stats_df['row_count'].sum():,}")

    # Layout tabs
    tab1, tab2 = st.tabs(["📋 Database Schema & Overview", "🔍 Data Viewer & Metadata"])

    with tab1:
        st.subheader("Database Tables Overview")

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Tables in 'main' Schema", len(tables))
        with col2:
            st.metric("Total Records Across All Tables", f"{stats_df['row_count'].sum():,}")

        st.markdown("### Table List & Record Counts")
        st.dataframe(
            stats_df.rename(columns={"table_name": "Table Name", "row_count": "Row Count"}),
            use_container_width=True,
            hide_index=True
        )

    with tab2:
        st.subheader(f"Table Details: `{selected_table}`")

        cols_df = run_query(f"PRAGMA table_info('main.{selected_table}')")

        col1, col2 = st.columns([1, 3])
        with col1:
            st.write("**Table Summary**")
            row_cnt = stats_df[stats_df['table_name'] == selected_table]['row_count'].values[0]
            st.write(f"- **Rows**: `{row_cnt}`")
            st.write(f"- **Columns**: `{len(cols_df)}`")

            st.markdown("---")
            st.write("**Columns & Types**")
            st.dataframe(
                cols_df[['name', 'type']].rename(columns={"name": "Column", "type": "Type"}),
                use_container_width=True,
                hide_index=True
            )

        with col2:
            st.write("**Data Preview (First 100 rows)**")
            data_df = run_query(f"SELECT * FROM main.{selected_table} LIMIT 100")
            st.dataframe(data_df, use_container_width=True, hide_index=True)

            csv_data = data_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label=f"📥 Download `{selected_table}` as CSV",
                data=csv_data,
                file_name=f"{selected_table}_preview.csv",
                mime="text/csv"
            )
