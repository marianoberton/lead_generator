"""Base de datos SQLite — persistencia y deduplicación de leads."""

import json
import sqlite3
from pathlib import Path

from config import (
    APOLLO_API_KEYS,
    GOOGLE_PLACES_API_KEYS,
    HUNTER_API_KEYS,
    DB_PATH,
    APOLLO_OUTPUT,
    ENRICHED_OUTPUT,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    domain               TEXT NOT NULL UNIQUE,
    company              TEXT NOT NULL,
    website              TEXT,
    source               TEXT,
    industry             TEXT,
    city                 TEXT,
    country              TEXT,
    address              TEXT,
    phone                TEXT,
    rating               REAL,
    reviews_count        INTEGER,
    employees            INTEGER,
    linkedin_url         TEXT,

    contact_name         TEXT,
    contact_title        TEXT,
    email                TEXT,
    email_score          INTEGER DEFAULT 0,
    email_source         TEXT,
    emails_all           TEXT,

    company_description  TEXT,
    pages_crawled        INTEGER DEFAULT 0,
    crawl_status         TEXT DEFAULT 'pending',
    crawl_error          TEXT,

    hunter_searched      INTEGER DEFAULT 0,
    hunter_score         INTEGER,

    personalization      TEXT,
    personalization_type TEXT,
    pain_point           TEXT,

    created_at           TEXT DEFAULT (datetime('now')),
    updated_at           TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_domain   ON leads(domain);
CREATE INDEX IF NOT EXISTS idx_industry ON leads(industry);
CREATE INDEX IF NOT EXISTS idx_country  ON leads(country);
CREATE INDEX IF NOT EXISTS idx_crawl    ON leads(crawl_status);
CREATE INDEX IF NOT EXISTS idx_email    ON leads(email);

CREATE TABLE IF NOT EXISTS api_keys (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    service        TEXT NOT NULL,
    key_value      TEXT NOT NULL,
    active         INTEGER DEFAULT 1,
    requests_today INTEGER DEFAULT 0,
    error_reason   TEXT,
    UNIQUE(service, key_value)
);
"""


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection):
    conn.executescript(SCHEMA)
    conn.commit()


def normalize_domain(url: str) -> str:
    if not url:
        return ""
    d = url.lower().replace("https://", "").replace("http://", "").split("/")[0].split("?")[0]
    return d.replace("www.", "").strip(".")


def upsert_lead(conn: sqlite3.Connection, lead: dict) -> bool:
    """Inserta un lead. Retorna True si fue nuevo, False si ya existía."""
    domain = normalize_domain(lead.get("website", ""))
    if not domain:
        return False

    company = lead.get("company") or lead.get("name", "")
    if not company:
        return False

    # Map old field names → new schema
    row = {
        "domain":              domain,
        "company":             company,
        "website":             (lead.get("website") or "").rstrip("/"),
        "source":              lead.get("source", ""),
        "industry":            lead.get("industry_category") or lead.get("industry", ""),
        "city":                lead.get("city", ""),
        "country":             lead.get("country", ""),
        "address":             lead.get("address", ""),
        "phone":               lead.get("phone", ""),
        "rating":              lead.get("rating"),
        "reviews_count":       lead.get("reviews_count"),
        "employees":           lead.get("employees"),
        "linkedin_url":        lead.get("linkedin_url", ""),
        "email":               lead.get("email") or lead.get("best_email", ""),
        "email_score":         lead.get("email_score", 0),
        "email_source":        lead.get("email_source", "apollo" if lead.get("email") else ""),
        "company_description": lead.get("company_description", ""),
    }

    cur = conn.execute(
        """INSERT OR IGNORE INTO leads
           (domain, company, website, source, industry, city, country, address, phone,
            rating, reviews_count, employees, linkedin_url, email, email_score,
            email_source, company_description)
           VALUES
           (:domain, :company, :website, :source, :industry, :city, :country, :address, :phone,
            :rating, :reviews_count, :employees, :linkedin_url, :email, :email_score,
            :email_source, :company_description)""",
        row,
    )
    conn.commit()
    return cur.rowcount > 0


def update_lead(conn: sqlite3.Connection, domain: str, fields: dict):
    if not fields:
        return
    fields["updated_at"] = "datetime('now')"
    sets = ", ".join(f"{k} = :{k}" for k in fields if k != "updated_at")
    sets += ", updated_at = datetime('now')"
    fields["domain"] = domain
    conn.execute(f"UPDATE leads SET {sets} WHERE domain = :domain", fields)
    conn.commit()


def update_crawl_result(conn: sqlite3.Connection, domain: str, result: dict):
    conn.execute(
        """UPDATE leads SET
            email          = COALESCE(:email, email),
            email_score    = COALESCE(:email_score, email_score),
            email_source   = COALESCE(:email_source, email_source),
            emails_all     = :emails_all,
            contact_name   = :contact_name,
            contact_title  = :contact_title,
            company_description = COALESCE(NULLIF(:company_description,''), company_description),
            pages_crawled  = :pages_crawled,
            crawl_status   = :crawl_status,
            crawl_error    = :crawl_error,
            updated_at     = datetime('now')
        WHERE domain = :domain""",
        {**result, "domain": domain},
    )
    conn.commit()


def get_pending_crawl(conn: sqlite3.Connection, limit: int = 500) -> list[dict]:
    """Leads sin email y sin crawlear (o con crawl fallido)."""
    rows = conn.execute(
        """SELECT * FROM leads
           WHERE (email IS NULL OR email = '')
             AND crawl_status IN ('pending', 'failed')
             AND website != ''
           ORDER BY rating DESC NULLS LAST
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_pending_hunter(conn: sqlite3.Connection, limit: int = 200) -> list[dict]:
    """Leads sin email, con website, no buscados en Hunter."""
    rows = conn.execute(
        """SELECT * FROM leads
           WHERE (email IS NULL OR email = '')
             AND hunter_searched = 0
             AND website != ''
           ORDER BY rating DESC NULLS LAST
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_all_leads(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM leads ORDER BY rating DESC NULLS LAST").fetchall()
    leads = []
    for r in rows:
        d = dict(r)
        # Compatibilidad con steps 4-7 que usan estos nombres
        d["industry_category"] = d.get("industry", "")
        d["best_email"] = d.get("email", "")
        d["name"] = d.get("contact_name", "")
        d["title"] = d.get("contact_title", "")
        leads.append(d)
    return leads


def stats(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    with_email = conn.execute("SELECT COUNT(*) FROM leads WHERE email != '' AND email IS NOT NULL").fetchone()[0]
    pending_crawl = conn.execute("SELECT COUNT(*) FROM leads WHERE crawl_status='pending'").fetchone()[0]
    by_industry = conn.execute(
        "SELECT industry, COUNT(*) as n, SUM(CASE WHEN email!='' AND email IS NOT NULL THEN 1 ELSE 0 END) as e FROM leads GROUP BY industry"
    ).fetchall()
    by_country = conn.execute(
        "SELECT country, COUNT(*) as n FROM leads GROUP BY country ORDER BY n DESC LIMIT 10"
    ).fetchall()
    return {
        "total": total,
        "with_email": with_email,
        "without_email": total - with_email,
        "pct_email": round(with_email * 100 / max(total, 1)),
        "pending_crawl": pending_crawl,
        "by_industry": [dict(r) for r in by_industry],
        "by_country": [dict(r) for r in by_country],
    }


# --- JSON export for steps 4-7 ---

def export_to_json(conn: sqlite3.Connection):
    """Exporta DB a JSON files para compatibilidad con steps 4-7."""
    leads = get_all_leads(conn)

    apollo = [l for l in leads if l.get("source") == "apollo"]
    google = [l for l in leads if l.get("source") != "apollo"]

    APOLLO_OUTPUT.parent.mkdir(exist_ok=True)
    import json as _json
    with open(APOLLO_OUTPUT, "w", encoding="utf-8") as f:
        _json.dump(apollo, f, ensure_ascii=False, indent=2)
    with open(ENRICHED_OUTPUT, "w", encoding="utf-8") as f:
        _json.dump(google, f, ensure_ascii=False, indent=2)

    return len(apollo), len(google)


# --- API key management ---

def seed_keys_from_env(conn: sqlite3.Connection):
    """Registra keys del .env en la tabla api_keys."""
    services = {
        "apollo": APOLLO_API_KEYS,
        "google_places": GOOGLE_PLACES_API_KEYS,
        "hunter": HUNTER_API_KEYS,
    }
    for service, keys in services.items():
        for key in keys:
            conn.execute(
                "INSERT OR IGNORE INTO api_keys (service, key_value) VALUES (?, ?)",
                (service, key),
            )
    conn.commit()


def get_active_keys(conn: sqlite3.Connection, service: str) -> list[tuple]:
    """Retorna lista de (id, key_value) activas para un servicio."""
    rows = conn.execute(
        "SELECT id, key_value FROM api_keys WHERE service=? AND active=1",
        (service,),
    ).fetchall()
    return [(r["id"], r["key_value"]) for r in rows]


def disable_key(conn: sqlite3.Connection, key_id: int, reason: str):
    conn.execute(
        "UPDATE api_keys SET active=0, error_reason=? WHERE id=?",
        (reason, key_id),
    )
    conn.commit()
