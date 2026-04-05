"""Colector Apollo organizations/search con key rotation (compatible con plan free)."""

import time

import requests

from src.db import normalize_domain, upsert_lead
from src.key_rotator import KeyRotator
from config import APOLLO_DELAY, APOLLO_COUNTRIES, APOLLO_INDUSTRIES, APOLLO_SENIORITIES

ORGS_ENDPOINT = "https://api.apollo.io/v1/organizations/search"
EMPLOYEE_RANGES = ["11,20", "21,50", "51,100", "101,200"]


def search_organizations(keywords: list[str], key: str, per_page: int = 25, page: int = 1) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json", "X-Api-Key": key}
    payload = {
        "q_organization_keyword_tags": keywords,
        "organization_num_employees_ranges": EMPLOYEE_RANGES,
        "organization_locations": APOLLO_COUNTRIES,
        "per_page": per_page,
        "page": page,
    }
    resp = requests.post(ORGS_ENDPOINT, json=payload, headers=headers, timeout=30)
    return resp.status_code, resp.json()


def parse_organization(org: dict) -> dict | None:
    name = (org.get("name") or "").strip()
    website = (org.get("website_url") or org.get("primary_domain") or "").rstrip("/")
    if not website.startswith("http") and website:
        website = "https://" + website

    if not website or not name:
        return None

    return {
        "source": "apollo",
        "name": "",
        "email": "",
        "title": "",
        "company": name,
        "website": website,
        "employees": org.get("estimated_num_employees"),
        "industry": org.get("industry", "N/A"),
        "city": org.get("city", "N/A"),
        "country": org.get("country", "N/A"),
        "company_description": org.get("short_description") or "",
        "linkedin_url": org.get("linkedin_url") or "",
        "phone": org.get("phone") or "",
    }


def run(conn, industries: list[str], limit: int, rotator: KeyRotator) -> int:
    """Colecta leads de Apollo. Retorna cantidad de leads nuevos insertados."""
    seen_domains: set[str] = set()
    rows = conn.execute("SELECT domain FROM leads").fetchall()
    for r in rows:
        seen_domains.add(r["domain"])

    inserted = 0
    per_industry = max(1, limit // len(industries)) if industries else limit

    for industry in industries:
        if industry not in APOLLO_INDUSTRIES:
            print(f"  [Apollo] Industria desconocida: {industry}")
            continue

        cfg = APOLLO_INDUSTRIES[industry]
        target = min(per_industry, cfg["target"])
        collected = 0
        page = 1

        print(f"\n  [Apollo] {industry} (target: {target})")

        while collected < target:
            time.sleep(APOLLO_DELAY)

            key_id, key = rotator.get()
            if not key:
                print("  [Apollo] Sin keys disponibles.")
                return inserted

            remaining = target - collected
            status, data = search_organizations(cfg["keywords"], key, per_page=min(remaining, 25), page=page)

            if status == 429:
                rotator.on_rate_limit(key_id)
                continue
            if status in (401, 403):
                rotator.on_denied(key_id, f"HTTP_{status}")
                continue
            if status != 200:
                print(f"  [Apollo] Error {status}")
                break

            orgs = data.get("organizations") or []
            if not orgs:
                print(f"  [Apollo] Sin más resultados en página {page}")
                break

            for org in orgs:
                if collected >= target:
                    break
                lead = parse_organization(org)
                if not lead:
                    continue

                lead["industry_category"] = industry
                domain = normalize_domain(lead["website"])
                if domain in seen_domains:
                    continue

                if upsert_lead(conn, lead):
                    seen_domains.add(domain)
                    inserted += 1
                    collected += 1

            total = data.get("pagination", {}).get("total_entries", 0)
            print(f"  Pagina {page}: {len(orgs)} orgs (total: {total}) -> +{collected} leads")
            page += 1

    return inserted
