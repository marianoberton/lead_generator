"""Colector Apify Google Maps Scraper con key rotation.

Usa el actor compass~crawler-google-places para buscar empresas en Google Maps.
El actor corre async — hay que esperar a que termine y luego descargar resultados.
"""

import time

import requests

from src.db import normalize_domain, upsert_lead
from src.key_rotator import KeyRotator
from config import (
    APIFY_DELAY,
    APIFY_POLL_INTERVAL,
    APIFY_ACTOR_ID,
    GOOGLE_INDUSTRIES,
    GOOGLE_CITIES,
    GOOGLE_MIN_RATING,
    GOOGLE_MIN_REVIEWS,
)

BASE_URL = "https://api.apify.com/v2"


def start_run(queries: list[str], token: str, max_per_search: int = 50) -> tuple[int, dict]:
    """Inicia un actor run en Apify. Retorna (status_code, response_json)."""
    url = f"{BASE_URL}/acts/{APIFY_ACTOR_ID}/runs?token={token}"
    payload = {
        "searchStringsArray": queries,
        "maxCrawledPlacesPerSearch": max_per_search,
        "language": "es",
    }
    resp = requests.post(url, json=payload, timeout=30)
    return resp.status_code, resp.json() if resp.status_code < 500 else {}


def get_run_status(run_id: str, token: str) -> str:
    """Consulta el estado de un run. Retorna: READY, RUNNING, SUCCEEDED, FAILED, etc."""
    url = f"{BASE_URL}/actor-runs/{run_id}?token={token}"
    resp = requests.get(url, timeout=15)
    if resp.status_code != 200:
        return "UNKNOWN"
    return resp.json().get("data", {}).get("status", "UNKNOWN")


def get_run_results(run_id: str, token: str) -> list[dict]:
    """Descarga los resultados del dataset de un run."""
    url = f"{BASE_URL}/actor-runs/{run_id}/dataset/items?token={token}"
    resp = requests.get(url, timeout=30)
    if resp.status_code != 200:
        return []
    return resp.json() if isinstance(resp.json(), list) else []


def wait_for_run(run_id: str, token: str, max_wait: int = 300) -> str:
    """Espera a que un run termine. Retorna el status final."""
    elapsed = 0
    while elapsed < max_wait:
        status = get_run_status(run_id, token)
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            return status
        print(f"    Run {run_id[:8]}... status: {status} ({elapsed}s)")
        time.sleep(APIFY_POLL_INTERVAL)
        elapsed += APIFY_POLL_INTERVAL
    return "TIMEOUT"


def parse_place(item: dict) -> dict | None:
    """Parsea un resultado de Google Maps a formato lead."""
    name = (item.get("title") or item.get("name") or "").strip()
    website = (item.get("website") or "").strip().rstrip("/")

    if not name or not website:
        return None
    if not website.startswith("http"):
        website = "https://" + website

    rating = item.get("totalScore") or item.get("rating")
    reviews = item.get("reviewsCount") or item.get("reviews")

    # Filtros minimos
    if rating and float(rating) < GOOGLE_MIN_RATING:
        return None
    if reviews and int(reviews) < GOOGLE_MIN_REVIEWS:
        return None

    address = item.get("address") or item.get("street") or ""
    city = item.get("city") or ""
    country = item.get("countryCode") or item.get("country") or ""

    # Intentar extraer city/country del address si no vienen
    if not city and address:
        parts = [p.strip() for p in address.split(",")]
        if len(parts) >= 2:
            city = parts[-2] if len(parts) >= 3 else parts[0]

    phone = item.get("phone") or item.get("phoneUnformatted") or ""
    category = item.get("categoryName") or item.get("category") or ""

    return {
        "source": "apify",
        "company": name,
        "website": website,
        "phone": phone,
        "rating": float(rating) if rating else None,
        "reviews_count": int(reviews) if reviews else None,
        "address": address,
        "city": city,
        "country": country,
        "industry": "",  # se asigna desde industry_category
        "company_description": category,
    }


def build_queries(industries: list[str], countries: list[str]) -> dict[str, list[str]]:
    """Construye queries agrupadas por industria a partir de las ciudades."""
    # Map country codes to city substrings for filtering
    country_cities = {}
    country_map = {
        "mexico": ["México", "Guadalajara", "Monterrey", "Puebla"],
        "colombia": ["Bogotá", "Medellín", "Cali", "Barranquilla"],
        "argentina": ["Buenos Aires", "Córdoba", "Rosario"],
        "chile": ["Santiago", "Valparaíso"],
        "peru": ["Lima", "Arequipa"],
        "ecuador": ["Quito", "Guayaquil"],
        "costa_rica": ["San José"],
        "panama": ["Panamá"],
        "dominican_republic": ["Santo Domingo"],
    }

    # Filter cities by selected countries
    selected_cities = []
    if countries:
        for c in countries:
            selected_cities.extend(country_map.get(c, []))
    if not selected_cities:
        selected_cities = GOOGLE_CITIES

    queries_by_industry = {}
    for industry in industries:
        if industry not in GOOGLE_INDUSTRIES:
            continue
        cfg = GOOGLE_INDUSTRIES[industry]
        queries = []
        for template in cfg["queries"]:
            for city in selected_cities:
                queries.append(template.replace("{city}", city))
        queries_by_industry[industry] = queries

    return queries_by_industry


def run(conn, industries: list[str], countries: list[str], limit: int, rotator: KeyRotator) -> int:
    """Colecta leads de Apify Google Maps. Retorna cantidad de leads nuevos."""
    seen_domains: set[str] = set()
    rows = conn.execute("SELECT domain FROM leads").fetchall()
    for r in rows:
        seen_domains.add(r["domain"])

    queries_by_industry = build_queries(industries, countries)
    if not queries_by_industry:
        print("  [Apify] Sin industrias validas.")
        return 0

    inserted = 0

    for industry, queries in queries_by_industry.items():
        if inserted >= limit:
            break

        key_id, token = rotator.get()
        if not token:
            print("  [Apify] Sin keys disponibles.")
            return inserted

        # Limitar queries para no gastar mucho credito
        batch_queries = queries[:10]  # max 10 queries por run
        max_per = min(50, (limit - inserted) // max(1, len(batch_queries)))

        print(f"\n  [Apify] {industry}: {len(batch_queries)} queries, max {max_per}/query")

        time.sleep(APIFY_DELAY)
        status_code, data = start_run(batch_queries, token, max_per)

        if status_code == 402:
            rotator.on_exhausted(key_id)
            continue
        if status_code in (401, 403):
            rotator.on_denied(key_id, f"HTTP_{status_code}")
            continue
        if status_code != 201:
            print(f"  [Apify] Error al iniciar run: HTTP {status_code}")
            continue

        run_id = data.get("data", {}).get("id")
        if not run_id:
            print("  [Apify] No se obtuvo run_id")
            continue

        rotator.on_success(key_id)
        print(f"  [Apify] Run iniciado: {run_id}")

        # Esperar a que termine
        final_status = wait_for_run(run_id, token)
        if final_status != "SUCCEEDED":
            print(f"  [Apify] Run termino con status: {final_status}")
            continue

        # Descargar resultados
        results = get_run_results(run_id, token)
        print(f"  [Apify] {len(results)} resultados obtenidos")

        for item in results:
            if inserted >= limit:
                break
            lead = parse_place(item)
            if not lead:
                continue

            lead["industry_category"] = industry
            domain = normalize_domain(lead["website"])
            if domain in seen_domains:
                continue

            if upsert_lead(conn, lead):
                seen_domains.add(domain)
                inserted += 1

        print(f"  [Apify] {industry}: +{inserted} leads insertados (acumulado)")

    return inserted
