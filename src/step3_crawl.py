"""Paso 3: Web crawling de leads de Google Places para extraer emails y datos."""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from config import (
    CRAWL_DELAY,
    CRAWL_MAX_PAGES,
    CRAWL_RETRIES,
    CRAWL_TIMEOUT,
    DISCARD_EMAIL_PREFIXES,
    ENRICHED_OUTPUT,
    GENERIC_EMAIL_PREFIXES,
    GOOGLE_OUTPUT,
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
)

# Patrones para detectar nombres y cargos cerca de emails
TITLE_KEYWORDS = [
    "director", "gerente", "ceo", "fundador", "founder", "dueño", "owner",
    "presidente", "jefe", "manager", "chief", "coordinador", "socio",
    "partner", "administrador", "líder", "lead", "head",
]


def extract_domain(url: str) -> str:
    if not url:
        return ""
    domain = url.lower().replace("https://", "").replace("http://", "").split("/")[0]
    return domain.replace("www.", "")


def normalize_url(base: str, path: str) -> str:
    """Construye URL absoluta desde base y path relativo."""
    if path.startswith("http"):
        return path
    base = base.rstrip("/")
    path = path.lstrip("/")
    return f"{base}/{path}"


def fetch_page(url: str) -> str | None:
    """Descarga una página con retry."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "es-419,es;q=0.9",
    }
    for attempt in range(1 + CRAWL_RETRIES):
        try:
            resp = requests.get(url, headers=headers, timeout=CRAWL_TIMEOUT, allow_redirects=True)
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "")
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                return None
            return resp.text
        except requests.RequestException:
            if attempt < CRAWL_RETRIES:
                time.sleep(CRAWL_DELAY)
    return None


def find_contact_pages(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Encuentra links a páginas de contacto/about."""
    contact_patterns = [
        r"contact", r"contacto", r"contactanos", r"contáctanos",
        r"about", r"nosotros", r"quienes.somos", r"quien.es",
        r"equipo", r"team",
    ]
    pattern = re.compile("|".join(contact_patterns), re.IGNORECASE)

    pages = []
    seen = set()
    for a_tag in soup.select("a[href]"):
        href = a_tag["href"].split("#")[0].split("?")[0].strip()
        text = a_tag.get_text(strip=True).lower()

        if not href or href == "/" or href.startswith("mailto:") or href.startswith("tel:"):
            continue

        if pattern.search(href) or pattern.search(text):
            full_url = normalize_url(base_url, href)
            domain = extract_domain(full_url)
            base_domain = extract_domain(base_url)

            # Solo páginas del mismo dominio
            if domain == base_domain and full_url not in seen:
                seen.add(full_url)
                pages.append(full_url)

    return pages[:CRAWL_MAX_PAGES - 1]  # -1 porque homepage ya se cuenta


def extract_emails_from_html(html: str, domain: str) -> list[str]:
    """Extrae emails del HTML, filtrando irrelevantes."""
    raw = EMAIL_REGEX.findall(html)

    # Deduplicar y limpiar
    emails = []
    seen = set()
    for email in raw:
        email = email.lower().strip(".")
        if email in seen:
            continue
        seen.add(email)

        # Descartar archivos de imagen que matchean el regex
        email_domain = email.split("@")[1]
        if re.search(r"\.(jpg|jpeg|png|gif|svg|webp|ico|pdf|css|js)$", email_domain, re.IGNORECASE):
            continue

        # Descartar emails de redes sociales, imágenes, etc.
        skip_domains = [
            "gmail.com", "hotmail.com", "yahoo.com", "outlook.com",
            "example.com", "sentry.io", "wixpress.com", "wordpress.com",
        ]
        if any(email_domain.endswith(d) for d in skip_domains):
            continue

        prefix = email.split("@")[0]
        if any(prefix.startswith(dp) for dp in DISCARD_EMAIL_PREFIXES):
            continue

        emails.append(email)

    return emails


def score_email(email: str) -> int:
    """Puntúa un email: mayor = mejor.
    3 = email de persona con cargo
    2 = email con nombre de persona
    1 = email genérico (info@, contacto@)
    0 = otros
    """
    prefix = email.split("@")[0].lower()

    if any(prefix.startswith(gp) for gp in GENERIC_EMAIL_PREFIXES):
        return 1

    # Si tiene punto o guion, probablemente es nombre.apellido
    if "." in prefix or "-" in prefix:
        return 2

    # Si es solo una palabra corta, probablemente genérico
    if len(prefix) <= 4:
        return 1

    return 2


def extract_person_info(soup: BeautifulSoup) -> dict:
    """Intenta extraer nombre y cargo de decisor de la página."""
    text = soup.get_text(" ", strip=True).lower()

    best_name = ""
    best_title = ""

    for keyword in TITLE_KEYWORDS:
        # Buscar patrones como "Juan Pérez, Director General" o "CEO: María López"
        patterns = [
            rf"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)\s*[,\-–|]\s*{keyword}",
            rf"{keyword}\s*[:\-–|]\s*([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)",
        ]
        for pat in patterns:
            match = re.search(pat, soup.get_text(" ", strip=True), re.IGNORECASE)
            if match:
                best_name = match.group(1).strip()
                best_title = keyword.capitalize()
                return {"contact_name": best_name, "contact_title": best_title}

    return {"contact_name": "", "contact_title": ""}


def extract_description(soup: BeautifulSoup) -> str:
    """Extrae una descripción corta de la empresa desde meta tags o contenido."""
    # Meta description
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        desc = meta["content"].strip()
        if len(desc) > 20:
            return desc[:300]

    # OG description
    og = soup.find("meta", attrs={"property": "og:description"})
    if og and og.get("content"):
        desc = og["content"].strip()
        if len(desc) > 20:
            return desc[:300]

    return ""


def crawl_lead(lead: dict) -> dict:
    """Crawlea el website de un lead y enriquece con datos encontrados."""
    website = lead.get("website", "")
    if not website:
        return lead

    enriched = dict(lead)
    all_emails: list[str] = []
    person_info = {"contact_name": "", "contact_title": ""}
    description = ""
    domain = extract_domain(website)
    pages_crawled = 0

    # 1. Homepage
    print(f"    Crawling: {website}")
    html = fetch_page(website)
    if html:
        pages_crawled += 1
        soup = BeautifulSoup(html, "lxml")
        all_emails.extend(extract_emails_from_html(html, domain))
        person_info = extract_person_info(soup)
        description = extract_description(soup)

        # 2. Páginas de contacto/about
        contact_pages = find_contact_pages(soup, website)
        for page_url in contact_pages:
            if pages_crawled >= CRAWL_MAX_PAGES:
                break
            time.sleep(CRAWL_DELAY)
            page_html = fetch_page(page_url)
            if page_html:
                pages_crawled += 1
                page_soup = BeautifulSoup(page_html, "lxml")
                all_emails.extend(extract_emails_from_html(page_html, domain))
                if not person_info["contact_name"]:
                    person_info = extract_person_info(page_soup)
                if not description:
                    description = extract_description(page_soup)

    # Deduplicar y ordenar emails por score
    unique_emails = list(dict.fromkeys(all_emails))
    unique_emails.sort(key=score_email, reverse=True)

    enriched["emails_found"] = unique_emails
    enriched["best_email"] = unique_emails[0] if unique_emails else ""
    enriched["email_score"] = score_email(unique_emails[0]) if unique_emails else 0
    enriched["contact_name"] = person_info["contact_name"]
    enriched["contact_title"] = person_info["contact_title"]
    enriched["company_description"] = description
    enriched["pages_crawled"] = pages_crawled

    return enriched


def run():
    """Ejecuta el paso 3: crawling de leads de Google Places."""
    try:
        with open(GOOGLE_OUTPUT, encoding="utf-8") as f:
            leads = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("[Crawl] ERROR: No se encontró leads_google.json. Ejecutá el paso 2 primero.")
        return []

    print(f"\n[Crawl] Procesando {len(leads)} leads de Google Places...")

    enriched = []
    for i, lead in enumerate(leads, 1):
        print(f"\n  [{i}/{len(leads)}] {lead.get('name', 'N/A')}")
        time.sleep(CRAWL_DELAY)
        result = crawl_lead(lead)
        enriched.append(result)

        email_status = result["best_email"] or "sin email"
        print(f"    -> {email_status} (score: {result.get('email_score', 0)})")

    # Guardar
    ENRICHED_OUTPUT.parent.mkdir(exist_ok=True)
    with open(ENRICHED_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)

    with_email = sum(1 for l in enriched if l.get("best_email"))
    print(f"\n[Crawl] Total: {len(enriched)} leads procesados")
    print(f"  Con email: {with_email}")
    print(f"  Sin email: {len(enriched) - with_email}")
    print(f"  Guardado en {ENRICHED_OUTPUT}")

    return enriched


if __name__ == "__main__":
    run()
