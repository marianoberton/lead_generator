"""Enriquecimiento de emails via VoilaNorbert con key rotation.

Auth: Basic auth (cualquier email como user, API token como password).
Free tier: 50 creditos al registrarte (no recurrente).
Requiere nombre + dominio, no solo dominio. Solo sirve si el lead ya tiene contact_name.
"""

import time

import requests

from src.db import normalize_domain, get_pending_enrichment, mark_searched, update_lead_email
from src.key_rotator import KeyRotator
from config import ENRICHER_DELAY

NORBERT_URL = "https://api.voilanorbert.com/2018-01-08/search/name"


def search_name(name: str, domain: str, api_token: str) -> dict | None:
    """Busca email por nombre + dominio en VoilaNorbert."""
    try:
        resp = requests.get(
            NORBERT_URL,
            params={"name": name, "domain": domain},
            auth=("", api_token),  # Basic auth, empty user, token as password
            timeout=15,
        )
        if resp.status_code == 429:
            return {"error": "rate_limit"}
        if resp.status_code in (401, 403):
            return {"error": "denied"}
        if resp.status_code == 402:
            return {"error": "exhausted"}  # No credits left
        if resp.status_code != 200:
            return None
        return resp.json()
    except requests.RequestException:
        return None


def run(conn, rotator: KeyRotator, limit: int = 200) -> int:
    """Enriquece leads sin email usando VoilaNorbert.
    Solo procesa leads que YA tienen contact_name (necesario para la API).
    """
    leads = get_pending_enrichment(conn, "norbert", limit)

    # Filtrar: solo leads con nombre de contacto
    leads = [l for l in leads if l.get("contact_name")]

    if not leads:
        print("[Norbert] No hay leads con nombre de contacto para buscar.")
        return 0

    print(f"\n[Norbert] Procesando {len(leads)} leads (con nombre de contacto)...")
    enriched = 0

    for i, lead in enumerate(leads, 1):
        domain = normalize_domain(lead.get("website", ""))
        name = lead.get("contact_name", "").strip()
        if not domain or not name:
            continue

        key_id, token = rotator.get()
        if not token:
            print("[Norbert] Sin keys disponibles.")
            break

        time.sleep(ENRICHER_DELAY)
        data = search_name(name, domain, token)

        mark_searched(conn, domain, "norbert")

        if data is None:
            continue

        if data.get("error") == "rate_limit":
            rotator.on_rate_limit(key_id)
            time.sleep(2)
            continue

        if data.get("error") == "denied":
            rotator.on_denied(key_id, "NORBERT_DENIED")
            continue

        if data.get("error") == "exhausted":
            rotator.on_exhausted(key_id)
            continue

        rotator.on_success(key_id)

        email_data = data.get("email") or {}
        email = ""
        score = 0

        if isinstance(email_data, dict):
            email = email_data.get("email") or ""
            score = email_data.get("score") or 0
        elif isinstance(email_data, str):
            email = email_data
            score = data.get("score") or 0

        if email:
            email_score = 2  # Norbert busca por nombre, siempre es personal
            update_lead_email(conn, domain, email, email_score, "norbert", name)
            enriched += 1
            print(f"  [{i}/{len(leads)}] {lead.get('company','')[:40]:<40} -> {email} (score: {score})")
        else:
            print(f"  [{i}/{len(leads)}] {lead.get('company','')[:40]:<40} -> sin email en Norbert")

    print(f"\n[Norbert] Completado: {enriched}/{len(leads)} enriquecidos")
    return enriched
