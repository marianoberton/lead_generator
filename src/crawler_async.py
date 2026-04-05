"""Crawling asíncrono de websites para extraer emails y datos de contacto."""

import asyncio
import re
import sys
import time
from collections import defaultdict

import httpx
from bs4 import BeautifulSoup

from config import (
    CRAWL_CONCURRENCY,
    CRAWL_DELAY,
    CRAWL_MAX_PAGES,
    CRAWL_TIMEOUT,
    DISCARD_EMAIL_PREFIXES,
    GENERIC_EMAIL_PREFIXES,
)
from src.db import update_crawl_result, normalize_domain

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
TITLE_KEYWORDS = [
    "director", "gerente", "ceo", "fundador", "founder", "dueño", "owner",
    "presidente", "jefe", "manager", "chief", "coordinador", "socio",
    "partner", "administrador", "lider", "lead", "head",
]

# Rate limiting por dominio
_domain_locks: dict = defaultdict(asyncio.Lock)
_domain_last_req: dict[str, float] = {}


def _normalize_url(base: str, path: str) -> str:
    if path.startswith("http"):
        return path
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def _extract_emails(html: str, domain: str) -> list[str]:
    raw = EMAIL_REGEX.findall(html)
    emails, seen = [], set()
    for email in raw:
        email = email.lower().strip(".")
        if email in seen:
            continue
        seen.add(email)
        email_domain = email.split("@")[1]
        if re.search(r"\.(jpg|jpeg|png|gif|svg|webp|ico|css|js|pdf)$", email_domain, re.I):
            continue
        skip = ["gmail.com", "hotmail.com", "yahoo.com", "outlook.com",
                "example.com", "sentry.io", "wixpress.com", "wordpress.com"]
        if any(email_domain.endswith(d) for d in skip):
            continue
        prefix = email.split("@")[0]
        if any(prefix.startswith(dp) for dp in DISCARD_EMAIL_PREFIXES):
            continue
        emails.append(email)
    return emails


def _score_email(email: str) -> int:
    prefix = email.split("@")[0].lower()
    if any(prefix.startswith(gp) for gp in GENERIC_EMAIL_PREFIXES):
        return 1
    if "." in prefix or "-" in prefix:
        return 2
    if len(prefix) <= 4:
        return 1
    return 2


def _find_contact_pages(soup: BeautifulSoup, base_url: str) -> list[str]:
    pattern = re.compile(
        r"contact|contacto|contactanos|about|nosotros|quienes|equipo|team",
        re.IGNORECASE,
    )
    pages, seen = [], set()
    for a in soup.select("a[href]"):
        href = a["href"].split("#")[0].split("?")[0].strip()
        text = a.get_text(strip=True).lower()
        if not href or href in ("/", "") or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        if pattern.search(href) or pattern.search(text):
            full = _normalize_url(base_url, href)
            domain = normalize_domain(full)
            if domain == normalize_domain(base_url) and full not in seen:
                seen.add(full)
                pages.append(full)
    return pages[: CRAWL_MAX_PAGES - 1]


def _extract_person(soup: BeautifulSoup) -> dict:
    text = soup.get_text(" ", strip=True)
    for kw in TITLE_KEYWORDS:
        for pat in [
            rf"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)\s*[,\-–|]\s*{kw}",
            rf"{kw}\s*[:\-–|]\s*([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)",
        ]:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return {"contact_name": m.group(1).strip(), "contact_title": kw.capitalize()}
    return {"contact_name": "", "contact_title": ""}


def _extract_description(soup: BeautifulSoup) -> str:
    for attr in [{"name": "description"}, {"property": "og:description"}]:
        tag = soup.find("meta", attrs=attr)
        if tag and tag.get("content") and len(tag["content"]) > 20:
            return tag["content"].strip()[:300]
    return ""


async def _fetch(client: httpx.AsyncClient, url: str, domain: str) -> str | None:
    """Descarga una página respetando 1 req/s por dominio."""
    lock = _domain_locks[domain]
    async with lock:
        last = _domain_last_req.get(domain, 0)
        elapsed = time.monotonic() - last
        if elapsed < CRAWL_DELAY:
            await asyncio.sleep(CRAWL_DELAY - elapsed)
        _domain_last_req[domain] = time.monotonic()

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "es-419,es;q=0.9",
    }
    try:
        resp = await client.get(url, headers=headers, timeout=CRAWL_TIMEOUT, follow_redirects=True)
        if resp.status_code >= 400:
            return None
        ct = resp.headers.get("content-type", "")
        if "text/html" not in ct and "application/xhtml" not in ct:
            return None
        return resp.text
    except Exception:
        return None


async def _crawl_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    lead: dict,
) -> dict:
    """Crawlea un lead y retorna campos enriquecidos."""
    website = lead.get("website", "")
    domain = normalize_domain(website)
    result = {
        "email": None,
        "email_score": None,
        "email_source": None,
        "emails_all": "[]",
        "contact_name": "",
        "contact_title": "",
        "company_description": "",
        "pages_crawled": 0,
        "crawl_status": "failed",
        "crawl_error": None,
    }

    async with semaphore:
        all_emails: list[str] = []
        person = {"contact_name": "", "contact_title": ""}
        description = ""

        html = await _fetch(client, website, domain)
        if not html:
            result["crawl_error"] = "no_response"
            return {**lead, **result}

        result["pages_crawled"] = 1
        soup = BeautifulSoup(html, "lxml")
        all_emails.extend(_extract_emails(html, domain))
        person = _extract_person(soup)
        description = _extract_description(soup)

        for page_url in _find_contact_pages(soup, website):
            if result["pages_crawled"] >= CRAWL_MAX_PAGES:
                break
            page_html = await _fetch(client, page_url, domain)
            if page_html:
                result["pages_crawled"] += 1
                psoup = BeautifulSoup(page_html, "lxml")
                all_emails.extend(_extract_emails(page_html, domain))
                if not person["contact_name"]:
                    person = _extract_person(psoup)
                if not description:
                    description = _extract_description(psoup)

    # Elegir mejor email
    unique = list(dict.fromkeys(all_emails))
    unique.sort(key=_score_email, reverse=True)

    if unique:
        result["email"] = unique[0]
        result["email_score"] = _score_email(unique[0])
        result["email_source"] = "crawl"
    result["emails_all"] = str(unique)
    result["contact_name"] = person["contact_name"]
    result["contact_title"] = person["contact_title"]
    result["company_description"] = description
    result["crawl_status"] = "done"

    return {**lead, **result}


async def crawl_batch(
    leads: list[dict],
    concurrency: int = CRAWL_CONCURRENCY,
) -> list[dict]:
    """Crawlea una lista de leads en paralelo. Retorna leads enriquecidos."""
    semaphore = asyncio.Semaphore(concurrency)
    results = []

    async with httpx.AsyncClient() as client:
        tasks = [_crawl_one(client, semaphore, lead) for lead in leads]
        total = len(tasks)
        done = 0

        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)
            done += 1
            email = result.get("email") or ""
            company = result.get("company", "N/A")
            print(f"  [{done}/{total}] {company[:40]:<40} -> {email or 'sin email'}")

    return results


def run(conn, leads: list[dict], concurrency: int = CRAWL_CONCURRENCY) -> int:
    """Entry point sincrónico. Crawlea leads y actualiza DB. Retorna count con email."""
    if not leads:
        print("[Crawl] No hay leads para procesar.")
        return 0

    print(f"\n[Crawl] Procesando {len(leads)} leads (concurrencia: {concurrency})...")
    results = asyncio.run(crawl_batch(leads, concurrency))

    with_email = 0
    for result in results:
        domain = normalize_domain(result.get("website", ""))
        if not domain:
            continue
        crawl_data = {
            "email":               result.get("email"),
            "email_score":         result.get("email_score"),
            "email_source":        result.get("email_source"),
            "emails_all":          result.get("emails_all", "[]"),
            "contact_name":        result.get("contact_name", ""),
            "contact_title":       result.get("contact_title", ""),
            "company_description": result.get("company_description", ""),
            "pages_crawled":       result.get("pages_crawled", 0),
            "crawl_status":        result.get("crawl_status", "failed"),
            "crawl_error":         result.get("crawl_error"),
        }
        update_crawl_result(conn, domain, crawl_data)
        if result.get("email"):
            with_email += 1

    print(f"\n[Crawl] Completado: {with_email}/{len(results)} con email")
    return with_email
