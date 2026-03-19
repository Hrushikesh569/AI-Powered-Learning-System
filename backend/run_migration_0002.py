"""Run alembic migration 0002 directly via psycopg2."""
import psycopg2

DSN = 'postgresql://user:pass@db:5432/ai_learning'

conn = psycopg2.connect(DSN)
conn.autocommit = True
cur = conn.cursor()

# Check current state
cur.execute("SELECT version_num FROM alembic_version;")
current = cur.fetchone()[0]
print(f"Current revision: {current}")

if current == '0002_add_unit_topic_pages':
    print("Migration 0002 already applied. Nothing to do.")
else:
    # Add unit_name column
    cur.execute("""
        ALTER TABLE study_materials 
        ADD COLUMN IF NOT EXISTS unit_name VARCHAR;
    """)
    print("Added unit_name column")

    # Add topic_pages column
    cur.execute("""
        ALTER TABLE study_materials 
        ADD COLUMN IF NOT EXISTS topic_pages JSONB;
    """)
    print("Added topic_pages column")

    # Create index on unit_name
    cur.execute("""
        CREATE INDEX IF NOT EXISTS ix_study_materials_unit_name 
        ON study_materials (unit_name);
    """)
    print("Created index on unit_name")

    # Update alembic version
    cur.execute("UPDATE alembic_version SET version_num = '0002_add_unit_topic_pages';")
    print("Updated alembic_version to 0002_add_unit_topic_pages")

# Verify
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='study_materials' ORDER BY ordinal_position;")
print("study_materials columns now:", [r[0] for r in cur.fetchall()])

cur.execute("SELECT version_num FROM alembic_version;")
print("Alembic version now:", cur.fetchone()[0])

conn.close()
print("Migration complete.")
