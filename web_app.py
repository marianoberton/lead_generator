"""FOMO Lead Gen — Web App (FastAPI + Jinja2 + HTMX)

Uso:
    python web_app.py
    uvicorn web_app:app --reload --port 8000
"""

import asyncio
import json
import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.templating import Jinja2Templates

load_dotenv()

# ── Project imports ──────────────────────────────────────────────
from config import (
    ALL_INDUSTRIES_LIST,
    ALL_COUNTRIES_LIST,
    LISTMONK_CSV,
    NO_EMAIL_CSV,
    LEADS_DIR,
    SERVICE_LIMITS,
)
from src.db import (
    get_connection,
    init_db,
    seed_keys_from_env,
    stats,
    get_all_leads,
    get_keys_status,
    reset_monthly_quotas,
)

# ── App setup ────────────────────────────────────────────────────
app = FastAPI(title="FOMO Lead Gen")
templates = Jinja2Templates(directory="templates")

# Jinja2 custom filters
def from_json(value):
    if not value:
        return []
    try:
        return json.loads(value)
    except Exception:
        return []

templates.env.filters["from_json"] = from_json

# ── DB helper ────────────────────────────────────────────────────
def get_db():
    conn = get_connection()
    init_db(conn)
    seed_keys_from_env(conn)
    return conn


# ── In-memory job registry ───────────────────────────────────────
active_jobs: dict[str, dict] = {}  # job_id -> {lines, done, returncode, command, started_at}


def _run_job_thread(job_id: str, cmd: list[str]):
    """Background thread: runs subprocess, captures output line by line."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
        cwd=str(Path(__file__).parent),
    )
    active_jobs[job_id]["process"] = proc
    for line in proc.stdout:
        active_jobs[job_id]["lines"].append(line.rstrip())
    proc.wait()
    active_jobs[job_id]["done"] = True
    active_jobs[job_id]["returncode"] = proc.returncode


def start_job(command: str, extra_args: list[str]) -> str:
    job_id = uuid.uuid4().hex[:10]
    cmd = [sys.executable, "-u", "app.py", command] + extra_args
    active_jobs[job_id] = {
        "command": command,
        "cmd": cmd,
        "lines": [],
        "done": False,
        "returncode": None,
        "started_at": datetime.now().isoformat(),
        "process": None,
    }
    t = threading.Thread(target=_run_job_thread, args=(job_id, cmd), daemon=True)
    t.start()
    return job_id


# ── Dashboard ─────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    conn = get_db()
    s = stats(conn)
    all_leads = get_all_leads(conn)
    recent = all_leads[:10]

    # Enrichment pipeline stats
    enrichment_stats = {}
    for svc in ["crawl", "hunter", "snov", "skrapp", "tomba", "norbert"]:
        if svc == "crawl":
            found = conn.execute(
                "SELECT COUNT(*) FROM leads WHERE crawl_status='done' AND email != '' AND email IS NOT NULL AND email_source='crawl'"
            ).fetchone()[0]
            not_found = conn.execute(
                "SELECT COUNT(*) FROM leads WHERE crawl_status='done' AND (email IS NULL OR email = '' OR email_source != 'crawl')"
            ).fetchone()[0]
            enrichment_stats[svc] = {"found": found, "not_found": not_found}
        else:
            col = f"{svc}_searched"
            found = conn.execute(
                f"SELECT COUNT(*) FROM leads WHERE email_source = ?", (svc,)
            ).fetchone()[0]
            searched = conn.execute(
                f"SELECT COUNT(*) FROM leads WHERE {col} = 1"
            ).fetchone()[0]
            enrichment_stats[svc] = {"found": found, "not_found": max(0, searched - found)}

    # Keys summary for dashboard
    keys = get_keys_status(conn)
    keys_summary = {}
    for k in keys:
        svc = k.get("service", "")
        if svc not in keys_summary:
            keys_summary[svc] = {"used": 0, "limit": 0, "label": SERVICE_LIMITS.get(svc, {}).get("label", svc)}
        keys_summary[svc]["used"] += k.get("requests_month", 0)
        keys_summary[svc]["limit"] += k.get("monthly_limit", 0)

    conn.close()
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "stats": s,
            "recent_leads": recent,
            "total_leads": s["total"],
            "enrichment_stats": enrichment_stats,
            "keys_summary": keys_summary,
        },
    )


# ── Leads ─────────────────────────────────────────────────────────
PER_PAGE = 30


@app.get("/leads", response_class=HTMLResponse)
async def leads_list(
    request: Request,
    q: str = "",
    industry: str = "",
    country: str = "",
    source: str = "",
    has_email: str = "",
    crawl_status: str = "",
    page: int = 1,
):
    conn = get_db()

    # Build WHERE clause
    conditions = []
    params: list = []

    if q:
        conditions.append("(company LIKE ? OR domain LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if industry:
        conditions.append("industry = ?")
        params.append(industry)
    if country:
        conditions.append("country = ?")
        params.append(country)
    if source:
        conditions.append("source = ?")
        params.append(source)
    if has_email == "1":
        conditions.append("email != '' AND email IS NOT NULL")
    elif has_email == "0":
        conditions.append("(email IS NULL OR email = '')")
    if crawl_status:
        conditions.append("crawl_status = ?")
        params.append(crawl_status)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    total_row = conn.execute(f"SELECT COUNT(*) FROM leads {where}", params).fetchone()
    total = total_row[0]
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, total_pages))
    offset = (page - 1) * PER_PAGE

    rows = conn.execute(
        f"SELECT * FROM leads {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [PER_PAGE, offset],
    ).fetchall()
    leads = [dict(r) for r in rows]

    # Distinct values for filters
    industries = [
        r[0] for r in conn.execute("SELECT DISTINCT industry FROM leads WHERE industry != '' ORDER BY industry").fetchall()
    ]
    countries = [
        r[0] for r in conn.execute("SELECT DISTINCT country FROM leads WHERE country != '' ORDER BY country").fetchall()
    ]
    conn.close()

    # Build query string without page for pagination links
    filter_params = {k: v for k, v in {"q": q, "industry": industry, "country": country,
                                         "source": source, "has_email": has_email,
                                         "crawl_status": crawl_status}.items() if v}
    query_string = urlencode(filter_params)

    return templates.TemplateResponse(
        "leads.html",
        {
            "request": request,
            "leads": leads,
            "total": total,
            "page": page,
            "per_page": PER_PAGE,
            "total_pages": total_pages,
            "filters": {"q": q, "industry": industry, "country": country,
                         "source": source, "has_email": has_email, "crawl_status": crawl_status},
            "industries": industries,
            "countries": countries,
            "query_string": query_string,
            "total_leads": total,
        },
    )


@app.get("/leads/{lead_id}", response_class=HTMLResponse)
async def lead_detail(request: Request, lead_id: int, message: str = ""):
    conn = get_db()
    row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    conn.close()
    if not row:
        return RedirectResponse("/leads")
    return templates.TemplateResponse(
        "lead_detail.html",
        {"request": request, "lead": dict(row), "message": message, "total_leads": None},
    )


@app.post("/leads/{lead_id}/update")
async def lead_update(
    lead_id: int,
    email: str = Form(""),
    contact_name: str = Form(""),
    contact_title: str = Form(""),
    personalization: str = Form(""),
    personalization_type: str = Form(""),
    pain_point: str = Form(""),
):
    conn = get_db()
    conn.execute(
        """UPDATE leads SET
             email = ?,
             contact_name = ?,
             contact_title = ?,
             personalization = ?,
             personalization_type = ?,
             pain_point = ?,
             updated_at = datetime('now')
           WHERE id = ?""",
        (email, contact_name, contact_title, personalization, personalization_type, pain_point, lead_id),
    )
    conn.commit()
    conn.close()
    return RedirectResponse(f"/leads/{lead_id}?message=Guardado+exitosamente", status_code=303)


@app.post("/leads/{lead_id}/delete")
async def lead_delete(lead_id: int):
    conn = get_db()
    conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/leads", status_code=303)


# ── Jobs ──────────────────────────────────────────────────────────
@app.get("/jobs", response_class=HTMLResponse)
async def jobs_page(request: Request, preset: str = ""):
    conn = get_db()
    s = stats(conn)
    conn.close()
    return templates.TemplateResponse(
        "jobs.html",
        {
            "request": request,
            "preset": preset,
            "all_industries": ALL_INDUSTRIES_LIST,
            "all_countries": ALL_COUNTRIES_LIST,
            "stats": s,
            "total_leads": s["total"],
        },
    )


@app.post("/jobs/start")
async def jobs_start(
    request: Request,
    command: str = Form(...),
    source: str = Form("google"),
    industries: list[str] = Form(default=[]),
    countries: list[str] = Form(default=[]),
    limit: int = Form(100),
    concurrency: int = Form(20),
    steps: list[str] = Form(default=[]),
    enrich_source: str = Form("hunter"),
):
    extra: list[str] = []

    if command == "collect":
        extra += ["--source", source]
        if industries:
            extra += ["--industries"] + industries
        if countries and source not in ("apollo",):
            extra += ["--countries"] + countries
        extra += ["--limit", str(limit)]

    elif command == "crawl":
        extra += ["--limit", str(limit), "--concurrency", str(concurrency)]

    elif command == "enrich":
        extra += ["--source", enrich_source, "--limit", str(limit)]

    elif command == "enrich-all":
        extra += ["--limit", str(limit)]

    elif command == "process":
        if steps:
            extra += ["--steps"] + steps

    else:
        return JSONResponse({"error": f"Comando desconocido: {command}"}, status_code=400)

    job_id = start_job(command, extra)
    return JSONResponse({"job_id": job_id})


@app.get("/jobs/{job_id}/stream")
async def job_stream(job_id: str):
    async def generate():
        if job_id not in active_jobs:
            yield "data: [ERROR] Job no encontrado\n\n"
            yield "data: [DONE:1]\n\n"
            return

        sent = 0
        while True:
            job = active_jobs[job_id]
            lines = job["lines"]

            # Send new lines
            while sent < len(lines):
                line = lines[sent].replace("\n", " ")
                yield f"data: {line}\n\n"
                sent += 1

            if job["done"]:
                rc = job.get("returncode", 0) or 0
                yield f"data: [DONE:{rc}]\n\n"
                break

            await asyncio.sleep(0.15)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/jobs/{job_id}/status")
async def job_status(job_id: str):
    if job_id not in active_jobs:
        return JSONResponse({"error": "not found"}, status_code=404)
    j = active_jobs[job_id]
    return JSONResponse({
        "done": j["done"],
        "returncode": j["returncode"],
        "lines": len(j["lines"]),
        "command": j["command"],
    })


# ── API Keys ──────────────────────────────────────────────────────
@app.get("/keys", response_class=HTMLResponse)
async def keys_page(request: Request, message: str = ""):
    conn = get_db()
    keys = get_keys_status(conn)
    s = stats(conn)

    # Compute summaries per service
    service_summary = {}
    for k in keys:
        svc = k.get("service", "")
        if svc not in service_summary:
            service_summary[svc] = {"total": 0, "active": 0, "used": 0, "limit": 0,
                                     "label": SERVICE_LIMITS.get(svc, {}).get("label", svc)}
        service_summary[svc]["total"] += 1
        if k.get("active"):
            service_summary[svc]["active"] += 1
        service_summary[svc]["used"] += k.get("requests_month", 0)
        service_summary[svc]["limit"] += k.get("monthly_limit", 0)

    conn.close()
    return templates.TemplateResponse(
        "keys.html",
        {
            "request": request,
            "keys": keys,
            "message": message,
            "total_leads": s["total"],
            "service_limits": SERVICE_LIMITS,
            "service_summary": service_summary,
        },
    )


@app.post("/keys/add")
async def keys_add(
    service: str = Form(...),
    key_value: str = Form(...),
    key_secret: str = Form(""),
    account_email: str = Form(""),
    account_name: str = Form(""),
    monthly_limit: int = Form(0),
    notes: str = Form(""),
):
    key_value = key_value.strip()
    if not key_value:
        return RedirectResponse("/keys?message=Error:+key+vacia", status_code=303)
    conn = get_db()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO api_keys
               (service, key_value, key_secret, account_email, account_name, monthly_limit, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (service, key_value, key_secret.strip(), account_email.strip(),
             account_name.strip(), monthly_limit, notes.strip()),
        )
        conn.commit()
        msg = f"Key+de+{service}+agregada+correctamente"
    except Exception as e:
        msg = f"Error:+{e}"
    conn.close()
    return RedirectResponse(f"/keys?message={msg}", status_code=303)


@app.post("/keys/{key_id}/enable")
async def keys_enable(key_id: int):
    conn = get_db()
    conn.execute("UPDATE api_keys SET active=1, error_reason=NULL WHERE id=?", (key_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/keys?message=Key+habilitada", status_code=303)


@app.post("/keys/{key_id}/disable")
async def keys_disable(key_id: int):
    conn = get_db()
    conn.execute("UPDATE api_keys SET active=0, error_reason='Manual' WHERE id=?", (key_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/keys?message=Key+deshabilitada", status_code=303)


@app.post("/keys/{key_id}/delete")
async def keys_delete(key_id: int):
    conn = get_db()
    conn.execute("DELETE FROM api_keys WHERE id=?", (key_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/keys?message=Key+eliminada", status_code=303)


@app.post("/keys/reset-quotas")
async def keys_reset():
    conn = get_db()
    reset_monthly_quotas(conn)
    conn.close()
    return RedirectResponse("/keys?message=Quotas+mensuales+reseteadas", status_code=303)


# ── Export ────────────────────────────────────────────────────────
@app.get("/export/csv")
async def export_csv(min_score: int = 0):
    """Genera y descarga el CSV de Listmonk."""
    import csv
    import io

    conn = get_db()
    leads = get_all_leads(conn)
    conn.close()

    with_email = [l for l in leads if l.get("email") and (l.get("email_score", 0) >= min_score)]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["email", "name", "attributes"])
    for lead in with_email:
        contact = lead.get("contact_name") or lead.get("company", "")
        attrs = json.dumps(
            {
                "empresa":   lead.get("company", ""),
                "cargo":     lead.get("contact_title") or lead.get("title", ""),
                "industria": lead.get("industry", ""),
                "dato":      lead.get("personalization", ""),
                "pais":      lead.get("country", ""),
                "dolor":     lead.get("pain_point", ""),
                "website":   lead.get("website", ""),
                "source":    lead.get("source", ""),
            },
            ensure_ascii=False,
        )
        writer.writerow([lead["email"], contact, attrs])

    content = output.getvalue().encode("utf-8")
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads_listmonk.csv"},
    )


# ── Entry point ───────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    print("FOMO Lead Gen — Web App")
    print("Abrí http://localhost:8000 en tu browser")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("web_app:app", host="0.0.0.0", port=port)
