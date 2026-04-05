"""Enriquecimiento de emails via Snov.io domain search con key rotation.

Auth: OAuth2 client_credentials. Guardar key como "client_id:client_secret" en DB.
Free tier: 50 creditos/mes por cuenta.
"""

import time

import requests

from src.db import normalize_domain, get_pending_enrichment, mark_searched, update_lead_email
from src.key_rotator import KeyRotator
from config import ENRICHER_DELAY

TOKEN_URL = "https://api.snov.io/v1/oauth/access_token"
DOMAIN_SEARCH_URL = "https://api.snov.io/v1/get-domain-emails-with-info"

# Cache tokens per client_id to avoid re-auth on every request
_token_cache: dict[str, str] = {}


def get_access_token(client_id: str, client_secret: str) -> str | None:
    """Obtiene access token de Snov.io via OAuth2."""
    cache_key = client_id
    if cache_key in _token_cache:
        return _token_cache[cache_key]

    try:
        resp = requests.post(TOKEN_URL, json={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }, timeout=15)
        if resp.status_code != 200:
            return None
        token = resp.json().get("access_token")
        if token:
            _token_cache[cache_key] = token
        return token
    except requests.RequestException:
        return None


def search_domain(domain: str, token: str) -> dict | None:
    """Busca emails para un dominio en Snov.io."""
    try:
        resp = requests.post(DOMAIN_SEARCH_URL, json={
            "domain": domain,
            "type": "all",
            "limit": 10,
            "access_token": token,
        }, timeout=15)
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
    """Elige el mejor email de Snov. Retorna (email, name, position) o None."""
    emails = data.get("emails") or []
    if not emails:
        return None

    # Priorizar: personal verified > personal > generic verified > generic
    def score(e):
        s = 0
        if e.get("type") == "personal":
            s += 10
        status = (e.get("status") or "").lower()
        if status == "verified":
            s += 5
        elif status == "valid":
            s += 3
        return s

    candidates = [e for e in emails if e.get("email")]
    if not candidates:
        return None

    best = max(candidates, key=score)
    email = best.get("email", "")
    first = best.get("first_name") or ""
    last = best.get("last_name") or ""
    name = f"{first} {last}".strip()
    position = best.get("position") or ""
    return email, name, position


def run(conn, rotator: KeyRotator, limit: int = 200) -> int:
    """Enriquece leads sin email usando Snov.io. Retorna cantidad enriquecida."""
    leads = get_pending_enrichment(conn, "snov", limit)

    if not leads:
        print("[Snov] No hay leads pendientes.")
        return 0

    print(f"\n[Snov] Procesando {len(leads)} leads...")
    enriched = 0

    for i, lead in enumerate(leads, 1):
        domain = normalize_domain(lead.get("website", ""))
        if not domain:
            continue

        key_id, client_id, client_secret = rotator.get_with_secret()
        if not client_id:
            print("[Snov] Sin keys disponibles.")
            break

        # Get OAuth token
        token = get_access_token(client_id, client_secret)
        if not token:
            rotator.on_denied(key_id, "OAUTH_FAILED")
            # Clear cache for this client
            _token_cache.pop(client_id, None)
            continue

        time.sleep(ENRICHER_DELAY)
        data = search_domain(domain, token)

        mark_searched(conn, domain, "snov")

        if data is None:
            continue

        if data.get("error") == "rate_limit":
            rotator.on_rate_limit(key_id)
            time.sleep(2)
            continue

        if data.get("error") == "denied":
            _token_cache.pop(client_id, None)
            rotator.on_denied(key_id, "SNOV_DENIED")
            continue

        rotator.on_success(key_id)

        result = pick_best_email(data)
        if result:
            email, name, position = result
            email_score = 2 if name else 1
            update_lead_email(conn, domain, email, email_score, "snov", name, position)
            enriched += 1
            print(f"  [{i}/{len(leads)}] {lead.get('company','')[:40]:<40} -> {email}")
        else:
            print(f"  [{i}/{len(leads)}] {lead.get('company','')[:40]:<40} -> sin email en Snov")

    print(f"\n[Snov] Completado: {enriched}/{len(leads)} enriquecidos")
    return enriched
