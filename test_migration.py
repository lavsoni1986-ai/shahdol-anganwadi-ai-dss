import sqlite3
from sqlalchemy import create_engine, inspect, text
from app.models import Base
from app.config import settings

db_url = settings.database_url
if db_url.startswith("sqlite+aiosqlite:"):
    db_url = db_url.replace("sqlite+aiosqlite:", "sqlite:")

engine = create_engine(db_url)

with engine.connect() as conn:
    inspector = inspect(conn)
    for table_name, table in Base.metadata.tables.items():
        if not inspector.has_table(table_name):
            print(f"Table {table_name} does not exist yet.")
            continue
        existing_cols = {col["name"].lower() for col in inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name.lower() not in existing_cols:
                col_type = column.type.compile(conn.dialect)
                alter_stmt = f'ALTER TABLE "{table_name}" ADD COLUMN "{column.name}" {col_type}'
                print(f"Executing: {alter_stmt}")
                conn.execute(text(alter_stmt))
                conn.commit()

print("Schema sync test completed.")
