"""Enriquecimiento de emails via Skrapp.io con key rotation.

Auth: header X-Access-Key.
Free tier: 100 emails/mes por cuenta.
"""

import time

import requests

from src.db import normalize_domain, get_pending_enrichment, mark_searched, update_lead_email
from src.key_rotator import KeyRotator
from config import ENRICHER_DELAY

SKRAPP_URL = "https://api.skrapp.io/api/v2/find"


def search_domain(domain: str, key: str) -> dict | None:
    """Busca emails para un dominio en Skrapp.io."""
    try:
        resp = requests.get(
            SKRAPP_URL,
            params={"company": domain},
            headers={
                "X-Access-Key": key,
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        if resp.status_code == 429:
            return {"error": "rate_limit"}
        if resp.status_code in (401, 403):
            return {"error": "denied"}
        if resp.status_code != 200:
            return None
        return resp.json()
    except requests.RequestException:
        return None


def pick_best_email(data: dict) -> tuple[str, str, str] | None:
    """Elige el mejor email de Skrapp. Retorna (email, name, position) o None."""
    emails = data.get("emails") or data.get("results") or []
    if not emails:
        return None

    def score(e):
        s = 0
        conf = e.get("confidence") or e.get("accuracy") or 0
        s += conf
        if e.get("type") == "personal" or "@" in (e.get("email") or "") and not any(
            p in (e.get("email") or "").split("@")[0].lower()
            for p in ["info", "contact", "admin", "support", "ventas"]
        ):
            s += 50
        return s

    candidates = [e for e in emails if e.get("email")]
    if not candidates:
        return None

    best = max(candidates, key=score)
    email = best.get("email", "")
    first = best.get("first_name") or best.get("firstName") or ""
    last = best.get("last_name") or best.get("lastName") or ""
    name = f"{first} {last}".strip()
    position = best.get("position") or best.get("title") or ""
    return email, name, position


def run(conn, rotator: KeyRotator, limit: int = 200) -> int:
    """Enriquece leads sin email usando Skrapp.io. Retorna cantidad enriquecida."""
    leads = get_pending_enrichment(conn, "skrapp", limit)

    if not leads:
        print("[Skrapp] No hay leads pendientes.")
        return 0

    print(f"\n[Skrapp] Procesando {len(leads)} leads...")
    enriched = 0

    for i, lead in enumerate(leads, 1):
        domain = normalize_domain(lead.get("website", ""))
        if not domain:
            continue

        key_id, key = rotator.get()
        if not key:
            print("[Skrapp] Sin keys disponibles.")
            break

        time.sleep(ENRICHER_DELAY)
        data = search_domain(domain, key)

        mark_searched(conn, domain, "skrapp")

        if data is None:
            continue

        if data.get("error") == "rate_limit":
            rotator.on_rate_limit(key_id)
            time.sleep(2)
            continue

        if data.get("error") == "denied":
            rotator.on_denied(key_id, "SKRAPP_DENIED")
            continue

        rotator.on_success(key_id)

        result = pick_best_email(data)
        if result:
            email, name, position = result
            email_score = 2 if name else 1
            update_lead_email(conn, domain, email, email_score, "skrapp", name, position)
            enriched += 1
            print(f"  [{i}/{len(leads)}] {lead.get('company','')[:40]:<40} -> {email}")
        else:
            print(f"  [{i}/{len(leads)}] {lead.get('company','')[:40]:<40} -> sin email en Skrapp")

    print(f"\n[Skrapp] Completado: {enriched}/{len(leads)} enriquecidos")
    return enriched
