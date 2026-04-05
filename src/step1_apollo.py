"""Paso 1: Obtener leads con email verificado desde Apollo API (mixed_people/search)."""

import json
import time
import requests

from config import (
    APOLLO_API_KEY,
    APOLLO_DELAY,
    APOLLO_COUNTRIES,
    APOLLO_INDUSTRIES,
    APOLLO_MAX_LEADS,
    APOLLO_OUTPUT,
    APOLLO_SENIORITIES,
)

PEOPLE_ENDPOINT = "https://api.apollo.io/api/v1/mixed_people/search"

# Rango de empleados formato Apollo: "min,max"
EMPLOYEE_RANGES = ["11,20", "21,50", "51,100", "101,200"]


def search_people(keywords: list[str], per_page: int, page: int = 1) -> dict:
    """Busca personas decisoras en Apollo con email verificado."""
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": APOLLO_API_KEY,
    }
    payload = {
        "q_organization_keyword_tags": keywords,
        "person_seniorities": APOLLO_SENIORITIES,
        "organization_num_employees_ranges": EMPLOYEE_RANGES,
        "organization_locations": APOLLO_COUNTRIES,
        "per_page": per_page,
        "page": page,
    }
    resp = requests.post(PEOPLE_ENDPOINT, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def parse_person(person: dict) -> dict | None:
    """Extrae campos relevantes de una persona de Apollo."""
    org = person.get("organization") or {}
    name = person.get("name", "").strip()
    email = person.get("email", "").strip()
    title = person.get("title", "").strip()
    company = org.get("name", "").strip()
    website = (org.get("website_url") or "").rstrip("/")

    if not website or not company:
        return None

    return {
        "source": "apollo",
        "name": name,
        "email": email,
        "title": title,
        "company": company,
        "website": website,
        "employees": org.get("estimated_num_employees"),
        "industry": org.get("industry", "N/A"),
        "city": org.get("city", "N/A"),
        "country": org.get("country", "N/A"),
        "company_description": org.get("short_description") or "",
        "linkedin_url": org.get("linkedin_url") or "",
    }


def extract_domain(url: str) -> str:
    """Extrae dominio base de una URL."""
    if not url:
        return ""
    domain = url.lower().replace("https://", "").replace("http://", "").split("/")[0]
    return domain.replace("www.", "")


def dedupe_by_domain(leads: list[dict]) -> list[dict]:
    """Deduplica leads por dominio del website."""
    seen: set[str] = set()
    unique: list[dict] = []
    for lead in leads:
        domain = extract_domain(lead.get("website", ""))
        if not domain or domain not in seen:
            if domain:
                seen.add(domain)
            unique.append(lead)
    return unique


def run():
    """Ejecuta el paso 1: busqueda de personas decisoras en Apollo API."""
    if not APOLLO_API_KEY:
        print("ERROR: APOLLO_API_KEY no configurada en .env")
        return []

    all_leads: list[dict] = []
    industry_results: dict[str, list[dict]] = {}

    # Buscar cada industria con su target
    for industry, cfg in APOLLO_INDUSTRIES.items():
        target = cfg["target"]
        print(f"\n[Apollo] Buscando {industry} (target: {target})...")

        leads: list[dict] = []
        page = 1

        while len(leads) < target:
            time.sleep(APOLLO_DELAY)
            try:
                remaining = target - len(leads)
                data = search_people(cfg["keywords"], per_page=min(remaining, 25), page=page)
            except requests.RequestException as e:
                print(f"  ERROR en busqueda {industry} pag {page}: {e}")
                break

            people = data.get("people") or []
            if not people:
                print(f"  No mas resultados en pagina {page}")
                break

            for person in people:
                parsed = parse_person(person)
                if parsed:
                    parsed["industry_category"] = industry
                    leads.append(parsed)

            total_available = data.get("pagination", {}).get("total_entries", 0)
            print(f"  Pagina {page}: {len(people)} personas (total disponible: {total_available})")
            page += 1

            if len(leads) >= target:
                break

        industry_results[industry] = leads[:target]
        with_email = sum(1 for l in industry_results[industry] if l.get("email"))
        print(f"  {industry}: {len(industry_results[industry])} leads ({with_email} con email)")

    # Redistribuir sobrante si alguna industria dio menos del target
    total_collected = sum(len(v) for v in industry_results.values())
    remaining = APOLLO_MAX_LEADS - total_collected

    if remaining > 0:
        surplus_industries = [
            ind for ind in APOLLO_INDUSTRIES
            if len(industry_results[ind]) >= APOLLO_INDUSTRIES[ind]["target"]
        ]
        if surplus_industries and remaining > 0:
            extra_per = remaining // len(surplus_industries)
            if extra_per > 0:
                for industry in surplus_industries:
                    print(f"\n[Apollo] Redistribuyendo: +{extra_per} para {industry}...")
                    time.sleep(APOLLO_DELAY)
                    try:
                        data = search_people(
                            APOLLO_INDUSTRIES[industry]["keywords"],
                            per_page=extra_per,
                            page=2,
                        )
                    except requests.RequestException as e:
                        print(f"  ERROR redistribucion {industry}: {e}")
                        continue

                    people = data.get("people") or []
                    for person in people:
                        parsed = parse_person(person)
                        if parsed:
                            parsed["industry_category"] = industry
                            industry_results[industry].append(parsed)

    # Consolidar y deduplicar
    for leads in industry_results.values():
        all_leads.extend(leads)

    all_leads = dedupe_by_domain(all_leads)

    # Limitar a max 50
    if len(all_leads) > APOLLO_MAX_LEADS:
        all_leads = all_leads[:APOLLO_MAX_LEADS]

    # Guardar
    APOLLO_OUTPUT.parent.mkdir(exist_ok=True)
    with open(APOLLO_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_leads, f, ensure_ascii=False, indent=2)

    with_email = sum(1 for l in all_leads if l.get("email"))
    print(f"\n[Apollo] Total: {len(all_leads)} leads guardados en {APOLLO_OUTPUT}")
    print(f"  Con email: {with_email} | Sin email: {len(all_leads) - with_email}")

    # Resumen por industria
    for industry in APOLLO_INDUSTRIES:
        count = sum(1 for l in all_leads if l.get("industry_category") == industry)
        print(f"  {industry}: {count}")

    return all_leads


if __name__ == "__main__":
    run()
