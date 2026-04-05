"""Enriquecimiento de emails via Hunter.io domain search con key rotation."""

import time

import requests

from src.db import normalize_domain, update_lead
from src.key_rotator import KeyRotator
from config import HUNTER_MIN_SCORE

HUNTER_URL = "https://api.hunter.io/v2/domain-search"


def search_domain(domain: str, key: str) -> dict | None:
    """Busca emails para un dominio en Hunter.io."""
    try:
        resp = requests.get(
            HUNTER_URL,
            params={"domain": domain, "api_key": key, "limit": 10},
            timeout=15,
        )
        if resp.status_code == 429:
            return {"error": "rate_limit"}
        if resp.status_code == 401:
            return {"error": "denied"}
        if resp.status_code != 200:
            return None
        return resp.json().get("data", {})
    except requests.RequestException:
        return None


def pick_best_email(data: dict, min_score: int = HUNTER_MIN_SCORE) -> tuple[str, int, str, str] | None:
    """Elige el mejor email del resultado de Hunter.
    Retorna (email, score, first_name, position) o None.
    """
    emails = data.get("emails") or []
    if not emails:
        return None

    # Priorizar: tipo "personal" > "generic", mayor confidence primero
    personal = [e for e in emails if e.get("type") == "personal" and e.get("confidence", 0) >= min_score]
    generic = [e for e in emails if e.get("type") == "generic" and e.get("confidence", 0) >= min_score]

    candidates = personal or generic
    if not candidates:
        return None

    best = max(candidates, key=lambda e: e.get("confidence", 0))
    email = best.get("value", "")
    score = best.get("confidence", 0)
    first_name = best.get("first_name") or ""
    last_name = best.get("last_name") or ""
    name = f"{first_name} {last_name}".strip()
    position = best.get("position") or ""
    return email, score, name, position


def run(conn, rotator: KeyRotator, limit: int = 200) -> int:
    """Enriquece leads sin email usando Hunter.io. Retorna cantidad enriquecida."""
    from src.db import get_pending_hunter
    leads = get_pending_hunter(conn, limit)

    if not leads:
        print("[Hunter] No hay leads pendientes para enriquecer.")
        return 0

    print(f"\n[Hunter] Procesando {len(leads)} leads...")
    enriched = 0

    for i, lead in enumerate(leads, 1):
        domain = normalize_domain(lead.get("website", ""))
        if not domain:
            continue

        key_id, key = rotator.get()
        if not key:
            print("[Hunter] Sin keys disponibles.")
            break

        time.sleep(0.5)  # 2 req/s max en free plan
        data = search_domain(domain, key)

        # Marcar como buscado siempre
        update_lead(conn, domain, {"hunter_searched": 1})

        if data is None:
            continue

        if data.get("error") == "rate_limit":
            rotator.on_rate_limit(key_id)
            time.sleep(2)
            continue

        if data.get("error") == "denied":
            rotator.on_denied(key_id, "HUNTER_UNAUTHORIZED")
            continue

        result = pick_best_email(data)
        if result:
            email, score, name, position = result
            fields = {
                "email":        email,
                "email_score":  2 if score >= 80 else 1,
                "email_source": "hunter",
                "hunter_score": score,
            }
            if name and not lead.get("contact_name"):
                fields["contact_name"] = name
            if position and not lead.get("contact_title"):
                fields["contact_title"] = position

            update_lead(conn, domain, fields)
            enriched += 1
            print(f"  [{i}/{len(leads)}] {lead.get('company','')[:40]:<40} -> {email} (score: {score})")
        else:
            print(f"  [{i}/{len(leads)}] {lead.get('company','')[:40]:<40} -> sin email en Hunter")

    print(f"\n[Hunter] Completado: {enriched}/{len(leads)} enriquecidos")
    return enriched
