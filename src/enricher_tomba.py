"""Enriquecimiento de emails via Tomba.io domain search con key rotation.

Auth: headers X-Tomba-Key + X-Tomba-Secret. Guardar como "key:secret" en DB.
Free tier: 25 busquedas/mes por cuenta.
"""

import time

import requests

from src.db import normalize_domain, get_pending_enrichment, mark_searched, update_lead_email
from src.key_rotator import KeyRotator
from config import ENRICHER_DELAY

TOMBA_URL = "https://api.tomba.io/v1/domain-search"


def search_domain(domain: str, api_key: str, secret: str) -> dict | None:
    """Busca emails para un dominio en Tomba.io."""
    try:
        resp = requests.get(
            TOMBA_URL,
            params={"domain": domain},
            headers={
                "X-Tomba-Key": api_key,
                "X-Tomba-Secret": secret,
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
    """Elige el mejor email de Tomba. Retorna (email, name, position) o None."""
    emails = data.get("data", {}).get("emails") or []
    if not emails:
        return None

    def score(e):
        s = 0
        conf = e.get("confidence") or 0
        s += conf
        if e.get("type") == "personal":
            s += 50
        return s

    candidates = [e for e in emails if e.get("email")]
    if not candidates:
        return None

    best = max(candidates, key=score)
    email = best.get("email", "")
    first = best.get("first_name") or ""
    last = best.get("last_name") or ""
    name = f"{first} {last}".strip()
    position = best.get("position") or best.get("department") or ""
    return email, name, position


def run(conn, rotator: KeyRotator, limit: int = 200) -> int:
    """Enriquece leads sin email usando Tomba.io. Retorna cantidad enriquecida."""
    leads = get_pending_enrichment(conn, "tomba", limit)

    if not leads:
        print("[Tomba] No hay leads pendientes.")
        return 0

    print(f"\n[Tomba] Procesando {len(leads)} leads...")
    enriched = 0

    for i, lead in enumerate(leads, 1):
        domain = normalize_domain(lead.get("website", ""))
        if not domain:
            continue

        key_id, api_key, secret = rotator.get_with_secret()
        if not api_key:
            print("[Tomba] Sin keys disponibles.")
            break

        time.sleep(ENRICHER_DELAY)
        data = search_domain(domain, api_key, secret)

        mark_searched(conn, domain, "tomba")

        if data is None:
            continue

        if data.get("error") == "rate_limit":
            rotator.on_rate_limit(key_id)
            time.sleep(2)
            continue

        if data.get("error") == "denied":
            rotator.on_denied(key_id, "TOMBA_DENIED")
            continue

        rotator.on_success(key_id)

        result = pick_best_email(data)
        if result:
            email, name, position = result
            email_score = 2 if name else 1
            update_lead_email(conn, domain, email, email_score, "tomba", name, position)
            enriched += 1
            print(f"  [{i}/{len(leads)}] {lead.get('company','')[:40]:<40} -> {email}")
        else:
            print(f"  [{i}/{len(leads)}] {lead.get('company','')[:40]:<40} -> sin email en Tomba")

    print(f"\n[Tomba] Completado: {enriched}/{len(leads)} enriquecidos")
    return enriched
