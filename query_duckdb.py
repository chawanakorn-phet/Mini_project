import duckdb
import pandas as pd

# Connect to the DuckDB database
conn = duckdb.connect('olist_dw/dev.duckdb')

# Get all table names
tables = conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'").fetchall()

print("Tables in dev.duckdb:")
for table in tables:
    print(f"  - {table[0]}")
print("\n" + "=" * 80)
print("Table: fact_order_items")
print("=" * 80)
result2 = conn.execute("SELECT * FROM main.fact_order_items LIMIT 20").fetchall()
df2 = pd.DataFrame(result2, columns=[desc[0] for desc in conn.description])
print(df2)
conn.close()
