"""Paso 4: Personalización de leads (Apollo + Google Places)."""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from config import (
    APOLLO_OUTPUT,
    CRAWL_DELAY,
    CRAWL_TIMEOUT,
    ENRICHED_OUTPUT,
    FINAL_OUTPUT,
    PAIN_POINTS,
    PERSONALIZATION_FALLBACKS,
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def fetch_description(url: str) -> str:
    """Obtiene meta description de una URL."""
    if not url:
        return ""
    try:
        headers = {"User-Agent": USER_AGENT}
        resp = requests.get(url, headers=headers, timeout=CRAWL_TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            return meta["content"].strip()[:300]
        og = soup.find("meta", attrs={"property": "og:description"})
        if og and og.get("content"):
            return og["content"].strip()[:300]
    except requests.RequestException:
        pass
    return ""


def personalize_lead(lead: dict) -> dict:
    """Genera una línea de personalización basada en datos reales del lead."""
    result = dict(lead)
    industry = lead.get("industry_category", "")
    company = lead.get("company") or lead.get("name", "")
    description = lead.get("company_description", "")

    # --- Prioridad 1: datos concretos de la empresa ---
    if description:
        line = build_from_description(description, company, industry)
        if line:
            result["personalization"] = line
            result["personalization_type"] = "concrete"
            return result

    # --- Prioridad 2: datos de escala ---
    employees = lead.get("employees")
    rating = lead.get("rating")
    reviews = lead.get("reviews_count")

    if employees and employees > 0:
        line = build_from_scale(company, employees, industry)
        result["personalization"] = line
        result["personalization_type"] = "scale"
        return result

    if rating and reviews and reviews > 20:
        line = f"Con {rating} estrellas y {reviews} reseñas, {company} ya tiene la reputación"
        result["personalization"] = truncate(line)
        result["personalization_type"] = "scale"
        return result

    # --- Prioridad 3: fallback genérico por industria ---
    fallback = PERSONALIZATION_FALLBACKS.get(industry, "podrías automatizar procesos clave")
    result["personalization"] = truncate(f"{company}, {fallback}")
    result["personalization_type"] = "fallback"
    return result


def build_from_description(description: str, company: str, industry: str) -> str:
    """Construye personalización desde la descripción de la empresa."""
    desc_lower = description.lower()

    # Buscar datos específicos mencionables
    # Años de experiencia
    years_match = re.search(r"(\d+)\s*años", desc_lower)
    if years_match:
        years = years_match.group(1)
        return truncate(f"Con {years} años en el mercado, {company} ya tiene la operación")

    # Especialidad/servicio
    keywords_map = {
        "salud": ["pacientes", "consultas", "citas", "diagnóstico", "tratamiento"],
        "distribucion": ["distribución", "logística", "entregas", "pedidos", "almacén"],
        "servicios_profesionales": ["clientes", "proyectos", "consultoría", "asesoría"],
        "manufactura": ["producción", "fabricación", "manufactura", "planta", "línea"],
    }

    for kw in keywords_map.get(industry, []):
        if kw in desc_lower:
            return truncate(f"Vi que {company} se enfoca en {kw} — justo donde más ayudamos")

    # Si hay descripción pero no matchea nada específico, usar primer fragmento
    first_sentence = description.split(".")[0].strip()
    if len(first_sentence) > 15:
        return truncate(f"Vi que {company}: \"{first_sentence}\"")

    return ""


def build_from_scale(company: str, employees: int, industry: str) -> str:
    """Construye personalización desde datos de escala."""
    if employees > 100:
        return truncate(f"Con +{employees} personas, {company} tiene la escala ideal")
    elif employees > 30:
        return truncate(f"{company} con ~{employees} personas ya necesita automatizar")
    else:
        return truncate(f"{company} está en el punto justo para escalar con IA")


def truncate(text: str, max_words: int = 15) -> str:
    """Trunca a max_words palabras."""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words])


def run():
    """Ejecuta el paso 4: personalización de todos los leads."""
    all_leads: list[dict] = []

    # Cargar Apollo leads
    try:
        with open(APOLLO_OUTPUT, encoding="utf-8") as f:
            apollo_leads = json.load(f)
        print(f"[Personalización] {len(apollo_leads)} leads de Apollo")

        # Para Apollo: usar description existente, o crawlear homepage
        for i, lead in enumerate(apollo_leads):
            if not lead.get("company_description"):
                print(f"  [{i+1}/{len(apollo_leads)}] Crawling homepage de {lead.get('company', 'N/A')}...")
                time.sleep(CRAWL_DELAY)
                lead["company_description"] = fetch_description(lead.get("website", ""))

            lead = personalize_lead(lead)
            all_leads.append(lead)

    except (FileNotFoundError, json.JSONDecodeError):
        print("[Personalización] No se encontró leads_apollo.json, saltando.")

    # Cargar Google Places leads (enriquecidos del paso 3)
    try:
        with open(ENRICHED_OUTPUT, encoding="utf-8") as f:
            google_leads = json.load(f)
        print(f"[Personalización] {len(google_leads)} leads de Google Places")

        for lead in google_leads:
            lead = personalize_lead(lead)
            all_leads.append(lead)

    except (FileNotFoundError, json.JSONDecodeError):
        print("[Personalización] No se encontró leads_enriched.json, saltando.")

    if not all_leads:
        print("[Personalización] ERROR: No hay leads para personalizar.")
        return []

    # Agregar dolor por industria
    for lead in all_leads:
        industry = lead.get("industry_category", "")
        lead["pain_point"] = PAIN_POINTS.get(industry, "")

    # Guardar
    FINAL_OUTPUT.parent.mkdir(exist_ok=True)
    with open(FINAL_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_leads, f, ensure_ascii=False, indent=2)

    # Stats
    concrete = sum(1 for l in all_leads if l.get("personalization_type") == "concrete")
    scale = sum(1 for l in all_leads if l.get("personalization_type") == "scale")
    fallback = sum(1 for l in all_leads if l.get("personalization_type") == "fallback")

    print(f"\n[Personalización] Total: {len(all_leads)} leads personalizados")
    print(f"  Concretos (datos reales): {concrete}")
    print(f"  Escala (empleados/rating): {scale}")
    print(f"  Fallback (genérico): {fallback}")
    print(f"  Guardado en {FINAL_OUTPUT}")

    return all_leads


if __name__ == "__main__":
    run()
