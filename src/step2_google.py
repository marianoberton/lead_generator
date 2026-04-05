"""Paso 2: Obtener leads adicionales (110) via Apollo organizations/search.

Como el scraping de Google/DDG es poco confiable sin API keys,
usamos Apollo organizations/search para las 4 industrias target,
deduplicando contra los leads del paso 1.

Si hay GOOGLE_PLACES_API_KEY, usa Google Places API en su lugar.
"""

import json
import time

import requests

from config import (
    APOLLO_API_KEY,
    APOLLO_COUNTRIES,
    APOLLO_OUTPUT,
    GOOGLE_INDUSTRIES,
    GOOGLE_MIN_RATING,
    GOOGLE_MIN_REVIEWS,
    GOOGLE_OUTPUT,
    GOOGLE_PLACES_API_KEY,
)

APOLLO_ORGS_ENDPOINT = "https://api.apollo.io/api/v1/organizations/search"
APOLLO_DELAY = 2.0
EMPLOYEE_RANGES = ["11,20", "21,50", "51,100", "101,200"]

# Keywords por industria para Apollo
APOLLO_KEYWORDS = {
    "salud": [
        ["clinica", "hospital", "salud", "medico"],
        ["laboratorio", "diagnostico", "clinica dental"],
        ["rehabilitacion", "oftalmologia", "dermatologia"],
    ],
    "distribucion": [
        ["distribucion", "distribuidora", "mayorista", "logistica"],
        ["importadora", "comercializadora", "almacen"],
    ],
    "servicios_profesionales": [
        ["consultoria", "consulting", "asesoria", "contabilidad"],
        ["legal", "abogados", "marketing agency", "publicidad"],
        ["recursos humanos", "staffing", "reclutamiento"],
    ],
    "manufactura": [
        ["manufactura", "fabrica", "produccion", "industrial"],
        ["empaques", "packaging", "plasticos", "alimentos"],
    ],
}


def extract_domain(url: str) -> str:
    if not url:
        return ""
    domain = url.lower().replace("https://", "").replace("http://", "").split("/")[0]
    return domain.replace("www.", "")


def load_step1_domains() -> set[str]:
    """Carga dominios del paso 1 para deduplicar."""
    try:
        with open(APOLLO_OUTPUT, encoding="utf-8") as f:
            return {extract_domain(l.get("website", "")) for l in json.load(f) if l.get("website")}
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def search_apollo_orgs(keywords: list[str], per_page: int = 25, page: int = 1) -> dict:
    headers = {"Content-Type": "application/json", "X-Api-Key": APOLLO_API_KEY}
    payload = {
        "q_organization_keyword_tags": keywords,
        "organization_num_employees_ranges": EMPLOYEE_RANGES,
        "organization_locations": APOLLO_COUNTRIES,
        "per_page": per_page,
        "page": page,
    }
    resp = requests.post(APOLLO_ORGS_ENDPOINT, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def parse_org(org: dict, industry: str) -> dict | None:
    name = org.get("name", "")
    website = (org.get("website_url") or "").rstrip("/")
    if not website or not name:
        return None

    return {
        "source": "apollo_orgs",
        "name": name,
        "address": "",
        "phone": org.get("phone") or "",
        "website": website,
        "rating": 0,
        "reviews_count": 0,
        "industry_category": industry,
        "city": org.get("city") or "N/A",
        "country": org.get("country") or "N/A",
        "employees": org.get("estimated_num_employees"),
        "company_description": org.get("short_description") or "",
        "industry_apollo": org.get("industry") or "",
        "linkedin_url": org.get("linkedin_url") or "",
    }


# --- Google Places API (cuando hay key) ---

def run_with_places_api():
    """Usa Google Places API."""
    from config import GOOGLE_CITIES
    seen_domains = load_step1_domains()
    all_leads = []
    cities = ["Ciudad de Mexico", "Bogota", "Buenos Aires", "Lima", "Santiago de Chile", "Medellin"]

    for industry, cfg in GOOGLE_INDUSTRIES.items():
        target = cfg["target"]
        industry_leads = []
        for qt in cfg["queries"][:4]:
            if len(industry_leads) >= target:
                break
            for city in cities:
                if len(industry_leads) >= target:
                    break
                query = qt.format(city=city)
                time.sleep(1)
                try:
                    params = {"query": query, "key": GOOGLE_PLACES_API_KEY, "language": "es"}
                    results = requests.get(
                        "https://maps.googleapis.com/maps/api/place/textsearch/json",
                        params=params, timeout=15,
                    ).json().get("results", [])
                except Exception:
                    continue
                for r in results:
                    if len(industry_leads) >= target:
                        break
                    pid = r.get("place_id")
                    if not pid:
                        continue
                    if r.get("rating", 0) < GOOGLE_MIN_RATING or r.get("user_ratings_total", 0) < GOOGLE_MIN_REVIEWS:
                        continue
                    time.sleep(0.5)
                    try:
                        det = requests.get(
                            "https://maps.googleapis.com/maps/api/place/details/json",
                            params={"place_id": pid, "fields": "website,formatted_phone_number", "key": GOOGLE_PLACES_API_KEY},
                            timeout=15,
                        ).json().get("result", {})
                    except Exception:
                        continue
                    website = (det.get("website") or "").rstrip("/")
                    if not website:
                        continue
                    domain = extract_domain(website)
                    if domain in seen_domains:
                        continue
                    seen_domains.add(domain)
                    import unicodedata
                    city_norm = "".join(c for c in unicodedata.normalize("NFKD", city.lower()) if not unicodedata.combining(c))
                    country_map = {"ciudad de mexico": "Mexico", "bogota": "Colombia", "buenos aires": "Argentina", "lima": "Peru", "santiago de chile": "Chile", "medellin": "Colombia"}
                    industry_leads.append({
                        "source": "google_places", "name": r.get("name", ""),
                        "address": r.get("formatted_address", ""),
                        "phone": det.get("formatted_phone_number", ""),
                        "website": website, "rating": r.get("rating", 0),
                        "reviews_count": r.get("user_ratings_total", 0),
                        "industry_category": industry, "city": city,
                        "country": country_map.get(city_norm, "N/A"),
                    })
        print(f"  {industry}: {len(industry_leads)} leads")
        all_leads.extend(industry_leads)
    return all_leads


# --- Apollo orgs (fallback sin Places API) ---

def run_with_apollo_orgs():
    """Usa Apollo organizations/search para obtener 110 leads adicionales."""
    seen_domains = load_step1_domains()
    all_leads = []

    print(f"[Step2] {len(seen_domains)} dominios del paso 1 para deduplicar")

    for industry, cfg in GOOGLE_INDUSTRIES.items():
        target = cfg["target"]
        industry_leads = []
        keyword_sets = APOLLO_KEYWORDS.get(industry, [cfg["queries"][0].split()[0:2]])

        print(f"\n[Step2] {industry} (target: {target})")

        for keywords in keyword_sets:
            if len(industry_leads) >= target:
                break

            page = 1
            while len(industry_leads) < target and page <= 5:
                remaining = target - len(industry_leads)
                time.sleep(APOLLO_DELAY)

                try:
                    data = search_apollo_orgs(keywords, per_page=min(remaining + 10, 25), page=page)
                except requests.RequestException as e:
                    print(f"  Error: {e}")
                    break

                orgs = data.get("organizations") or []
                if not orgs:
                    break

                for org in orgs:
                    if len(industry_leads) >= target:
                        break

                    lead = parse_org(org, industry)
                    if not lead:
                        continue

                    domain = extract_domain(lead["website"])
                    if domain in seen_domains:
                        continue

                    seen_domains.add(domain)
                    industry_leads.append(lead)

                total_avail = data.get("pagination", {}).get("total_entries", 0)
                print(f"  [{', '.join(keywords[:2])}] p{page}: +{len(orgs)} orgs (total: {total_avail})")
                page += 1

        print(f"  {industry}: {len(industry_leads)} leads")
        all_leads.extend(industry_leads)

    return all_leads


# --- Main ---

def run():
    use_api = bool(GOOGLE_PLACES_API_KEY)
    mode = "Google Places API" if use_api else "Apollo organizations"
    print(f"\n[Step2] Modo: {mode}")

    if use_api:
        all_leads = run_with_places_api()
    else:
        if not APOLLO_API_KEY:
            print("[Step2] ERROR: Se necesita APOLLO_API_KEY o GOOGLE_PLACES_API_KEY")
            return []
        all_leads = run_with_apollo_orgs()

    GOOGLE_OUTPUT.parent.mkdir(exist_ok=True)
    with open(GOOGLE_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_leads, f, ensure_ascii=False, indent=2)

    print(f"\n[Step2] Total: {len(all_leads)} leads guardados en {GOOGLE_OUTPUT}")
    for industry in GOOGLE_INDUSTRIES:
        count = sum(1 for l in all_leads if l.get("industry_category") == industry)
        print(f"  {industry}: {count}")

    return all_leads


if __name__ == "__main__":
    run()
