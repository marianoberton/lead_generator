"""Colector de leads via Google Places API v1 con key rotation y paginación."""

import asyncio
import sys
import time

import httpx

from src.db import normalize_domain, upsert_lead
from src.key_rotator import KeyRotator
from config import GOOGLE_MIN_RATING, GOOGLE_MIN_REVIEWS

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

PLACES_V1_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = (
    "places.id,places.displayName,places.websiteUri,"
    "places.formattedAddress,places.rating,places.userRatingCount,"
    "places.internationalPhoneNumber"
)

# Industrias → queries de búsqueda
INDUSTRY_QUERIES = {
    "salud": [
        "clinica privada", "hospital privado", "centro medico",
        "laboratorio clinico", "clinica dental", "centro de rehabilitacion",
        "clinica oftalmologica", "diagnostico medico", "clinica dermatologica",
        "policlinico", "clinica pediatrica", "centro de salud",
    ],
    "distribucion": [
        "distribuidora mayorista", "empresa de logistica", "importadora",
        "distribuidora de alimentos", "distribuidora de bebidas",
        "almacen mayorista", "empresa de distribucion", "comercializadora",
        "distribuidora industrial", "operador logistico",
    ],
    "servicios_profesionales": [
        "consultora empresarial", "estudio contable", "bufete de abogados",
        "agencia de marketing digital", "empresa de recursos humanos",
        "consultoria de negocios", "estudio juridico", "agencia de publicidad",
        "empresa de consultoria", "firma de auditoria", "agencia de branding",
    ],
    "manufactura": [
        "fabrica", "planta de produccion", "empresa manufacturera",
        "industria alimentaria", "empresa de empaques", "manufactura",
        "empresa de plasticos", "planta industrial", "empresa de impresion",
        "industria metalurgica",
    ],
}

# Ciudades por país (LATAM)
CITIES_BY_COUNTRY = {
    "mexico": [
        "Ciudad de Mexico", "Guadalajara", "Monterrey", "Puebla",
        "Tijuana", "Leon", "Merida", "Queretaro", "San Luis Potosi",
    ],
    "colombia": [
        "Bogota", "Medellin", "Cali", "Barranquilla",
        "Bucaramanga", "Cartagena", "Pereira",
    ],
    "argentina": [
        "Buenos Aires", "Cordoba", "Rosario", "Mendoza",
        "Tucuman", "La Plata", "Mar del Plata",
    ],
    "chile": [
        "Santiago", "Valparaiso", "Concepcion", "Antofagasta", "Vina del Mar",
    ],
    "peru": [
        "Lima", "Arequipa", "Trujillo", "Chiclayo", "Cusco", "Piura",
    ],
    "ecuador": ["Quito", "Guayaquil", "Cuenca"],
    "uruguay": ["Montevideo"],
    "costa_rica": ["San Jose"],
    "panama": ["Panama"],
    "dominican_republic": ["Santo Domingo"],
    "bolivia": ["La Paz", "Santa Cruz de la Sierra"],
    "paraguay": ["Asuncion"],
    "guatemala": ["Guatemala"],
    "el_salvador": ["San Salvador"],
    "honduras": ["Tegucigalpa"],
    "nicaragua": ["Managua"],
    "venezuela": ["Caracas", "Maracaibo"],
}

ALL_LATAM = list(CITIES_BY_COUNTRY.keys())


def parse_place(place: dict, industry: str, country: str) -> dict | None:
    website = (place.get("websiteUri") or "").rstrip("/")
    name_obj = place.get("displayName") or {}
    name = name_obj.get("text", "") if isinstance(name_obj, dict) else str(name_obj)

    if not website or not name:
        return None

    # Filtros de calidad
    rating = place.get("rating", 0) or 0
    reviews = place.get("userRatingCount", 0) or 0
    if rating < GOOGLE_MIN_RATING and reviews >= GOOGLE_MIN_REVIEWS:
        return None  # rating bajo con suficientes reviews = skip

    return {
        "source": "google_maps",
        "company": name,
        "website": website,
        "address": place.get("formattedAddress", ""),
        "phone": place.get("internationalPhoneNumber", ""),
        "rating": rating,
        "reviews_count": reviews,
        "industry_category": industry,
        "country": country.replace("_", " ").title(),
    }


async def search_places(
    client: httpx.AsyncClient,
    query: str,
    key: str,
    page_token: str | None = None,
) -> dict:
    body = {"textQuery": query, "languageCode": "es", "maxResultCount": 20}
    if page_token:
        body["pageToken"] = page_token
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    resp = await client.post(PLACES_V1_URL, json=body, headers=headers, timeout=30)
    return resp.status_code, resp.json()


async def collect(
    conn,
    industries: list[str],
    countries: list[str],
    limit: int,
    rotator: KeyRotator,
) -> int:
    """Colecta leads de Google Places. Retorna cantidad de leads nuevos insertados."""
    inserted = 0
    seen_domains: set[str] = set()

    # Cargar dominios ya existentes en DB para deduplicar
    rows = conn.execute("SELECT domain FROM leads").fetchall()
    for r in rows:
        seen_domains.add(r["domain"])

    async with httpx.AsyncClient() as client:
        for country in countries:
            if country not in CITIES_BY_COUNTRY:
                print(f"  [Google] País desconocido: {country}. Disponibles: {list(CITIES_BY_COUNTRY.keys())}")
                continue

            cities = CITIES_BY_COUNTRY[country]

            for industry in industries:
                if inserted >= limit:
                    break
                if industry not in INDUSTRY_QUERIES:
                    print(f"  [Google] Industria desconocida: {industry}")
                    continue

                queries = INDUSTRY_QUERIES[industry]
                print(f"\n  [Google] {industry.upper()} — {country} ({len(cities)} ciudades, {len(queries)} queries)")

                for query_tpl in queries:
                    if inserted >= limit:
                        break

                    for city in cities:
                        if inserted >= limit:
                            break

                        query = f"{query_tpl} {city}"
                        key_id, key = rotator.get()
                        if not key:
                            print("  [Google] Sin keys disponibles. Deteniéndose.")
                            return inserted

                        await asyncio.sleep(0.2)  # evitar burst

                        try:
                            status, data = await search_places(client, query, key)
                        except Exception as e:
                            print(f"    Error en '{query}': {e}")
                            continue

                        if status == 429:
                            rotator.on_rate_limit(key_id)
                            await asyncio.sleep(2)
                            continue

                        if status == 403:
                            rotator.on_denied(key_id, "REQUEST_DENIED")
                            continue

                        if status != 200:
                            error = data.get("error", {}).get("message", str(status))
                            if "RESOURCE_EXHAUSTED" in str(error) or "quota" in str(error).lower():
                                rotator.on_exhausted(key_id)
                            else:
                                print(f"    Error {status}: {error}")
                            continue

                        places = data.get("places") or []
                        new_from_query = 0

                        for place in places:
                            if inserted >= limit:
                                break

                            lead = parse_place(place, industry, country)
                            if not lead:
                                continue

                            domain = normalize_domain(lead["website"])
                            if domain in seen_domains:
                                continue

                            if upsert_lead(conn, lead):
                                seen_domains.add(domain)
                                inserted += 1
                                new_from_query += 1

                        if new_from_query:
                            print(f"    '{query}': +{new_from_query} ({inserted}/{limit})")

    return inserted


def run(conn, industries: list[str], countries: list[str], limit: int, rotator: KeyRotator) -> int:
    """Entry point sincrónico para app.py."""
    return asyncio.run(collect(conn, industries, countries, limit, rotator))
