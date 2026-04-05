"""Database migrations — adds new columns without breaking existing data."""

MIGRATIONS = [
    # API keys: new tracking columns
    "ALTER TABLE api_keys ADD COLUMN key_secret TEXT DEFAULT ''",
    "ALTER TABLE api_keys ADD COLUMN account_email TEXT DEFAULT ''",
    "ALTER TABLE api_keys ADD COLUMN account_name TEXT DEFAULT ''",
    "ALTER TABLE api_keys ADD COLUMN requests_total INTEGER DEFAULT 0",
    "ALTER TABLE api_keys ADD COLUMN monthly_limit INTEGER DEFAULT 0",
    "ALTER TABLE api_keys ADD COLUMN requests_month INTEGER DEFAULT 0",
    "ALTER TABLE api_keys ADD COLUMN last_used_at TEXT",
    "ALTER TABLE api_keys ADD COLUMN notes TEXT DEFAULT ''",
    "ALTER TABLE api_keys ADD COLUMN created_at TEXT DEFAULT (datetime('now'))",
    # Leads: enrichment search flags
    "ALTER TABLE leads ADD COLUMN snov_searched INTEGER DEFAULT 0",
    "ALTER TABLE leads ADD COLUMN skrapp_searched INTEGER DEFAULT 0",
    "ALTER TABLE leads ADD COLUMN tomba_searched INTEGER DEFAULT 0",
    "ALTER TABLE leads ADD COLUMN norbert_searched INTEGER DEFAULT 0",
]


def run_migrations(conn):
    """Run all migrations. Safe to call repeatedly — already-applied ones are skipped."""
    for sql in MIGRATIONS:
        try:
            conn.execute(sql)
        except Exception:
            pass  # Column already exists
    conn.commit()
