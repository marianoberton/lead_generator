"""FOMO Lead Generation v2 — CLI parametrizable con múltiples fuentes y key rotation.

Uso:
    python app.py collect --source google --industry salud --countries mexico colombia --limit 1000
    python app.py collect --source apollo --industry manufactura --limit 50
    python app.py crawl --limit 500 --concurrency 20
    python app.py enrich --limit 200
    python app.py process
    python app.py status
    python app.py export
"""

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()

from config import (
    APOLLO_API_KEYS,
    GOOGLE_PLACES_API_KEYS,
    HUNTER_API_KEYS,
    GOOGLE_INDUSTRIES,
    APOLLO_INDUSTRIES,
    CRAWL_CONCURRENCY,
)
from src.db import (
    get_connection, init_db, seed_keys_from_env,
    get_pending_crawl, stats, export_to_json,
)
from src.key_rotator import KeyRotator
from src.collector_google import CITIES_BY_COUNTRY

ALL_INDUSTRIES = list({**GOOGLE_INDUSTRIES, **APOLLO_INDUSTRIES}.keys())
ALL_COUNTRIES = list(CITIES_BY_COUNTRY.keys())


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

def print_status(conn):
    s = stats(conn)
    print(f"\n{'='*55}")
    print(f"  ESTADO DE LA BASE DE DATOS")
    print(f"{'='*55}")
    print(f"  Total leads:      {s['total']:>6}")
    print(f"  Con email:        {s['with_email']:>6}  ({s['pct_email']}%)")
    print(f"  Sin email:        {s['without_email']:>6}")
    print(f"  Pendiente crawl:  {s['pending_crawl']:>6}")
    print(f"\n  Por industria:")
    for row in s["by_industry"]:
        print(f"    {row['industry']:<28} {row['n']:>5} leads  /  {row['e']:>5} con email")
    print(f"\n  Top países:")
    for row in s["by_country"]:
        print(f"    {row['country']:<20} {row['n']:>5}")
    print()


# ─────────────────────────────────────────────
#  Comandos
# ─────────────────────────────────────────────

def cmd_collect(args):
    conn = get_connection()
    init_db(conn)
    seed_keys_from_env(conn)

    industries = args.industries or ALL_INDUSTRIES
    countries = [c.lower().replace(" ", "_") for c in (args.countries or ["mexico", "colombia", "argentina"])]
    limit = args.limit

    if args.source in ("google", "all"):
        if not GOOGLE_PLACES_API_KEYS:
            print("ERROR: Necesitás al menos una GOOGLE_PLACES_API_KEYS en .env")
            if args.source == "google":
                sys.exit(1)
        else:
            from src.collector_google import run as google_run
            rotator = KeyRotator(conn, "google_places")
            print(f"\n[Collect] Google Maps — {len(industries)} industrias, {len(countries)} países, limit {limit}")
            print(f"  Keys disponibles: {rotator.available}")
            inserted = google_run(conn, industries, countries, limit, rotator)
            print(f"\n[Collect] +{inserted} leads nuevos de Google Maps")

    if args.source in ("apollo", "all"):
        if not APOLLO_API_KEYS:
            print("ERROR: Necesitás al menos una APOLLO_API_KEYS en .env")
        else:
            from src.collector_apollo import run as apollo_run
            rotator = KeyRotator(conn, "apollo")
            print(f"\n[Collect] Apollo — {len(industries)} industrias, limit {min(limit, 50)}")
            inserted = apollo_run(conn, industries, min(limit, 50), rotator)
            print(f"\n[Collect] +{inserted} leads nuevos de Apollo")

    print_status(conn)


def cmd_crawl(args):
    conn = get_connection()
    init_db(conn)

    leads = get_pending_crawl(conn, args.limit)
    if not leads:
        print("[Crawl] No hay leads pendientes.")
        return

    concurrency = args.concurrency
    print(f"\n[Crawl] {len(leads)} leads a crawlear (concurrencia: {concurrency})")

    from src.crawler_async import run as crawl_run
    crawl_run(conn, leads, concurrency)
    print_status(conn)


def cmd_enrich(args):
    conn = get_connection()
    init_db(conn)

    if not HUNTER_API_KEYS:
        print("ERROR: Necesitás HUNTER_API_KEYS en .env")
        sys.exit(1)

    rotator = KeyRotator(conn, "hunter")
    print(f"\n[Enrich] Hunter.io — {rotator.available} keys disponibles, limit {args.limit}")

    from src.enricher_hunter import run as hunter_run
    hunter_run(conn, rotator, args.limit)
    print_status(conn)


def cmd_process(args):
    """Exporta DB a JSON y corre steps 4-7."""
    conn = get_connection()
    init_db(conn)

    print("\n[Process] Exportando DB a JSON para steps 4-7...")
    n_apollo, n_google = export_to_json(conn)
    print(f"  Apollo: {n_apollo} leads | Google/Other: {n_google} leads")

    steps = args.steps or [4, 5, 6, 7]

    STEPS = {
        4: ("Personalización",  "src.step4_personalize"),
        5: ("CSV Listmonk",     "src.step5_csv"),
        6: ("Reporte",          "src.step6_report"),
        7: ("Dashboard",        "src.step7_dashboard"),
    }

    for step_num in steps:
        if step_num not in STEPS:
            print(f"  Paso {step_num} no válido. Disponibles: 4-7")
            continue
        name, module_path = STEPS[step_num]
        print(f"\n{'='*50}")
        print(f"  PASO {step_num}: {name}")
        print(f"{'='*50}")
        try:
            mod = __import__(module_path, fromlist=["run"])
            mod.run()
            print(f"  [OK] Paso {step_num} completado.")
        except Exception as e:
            print(f"  [FAIL] Paso {step_num}: {e}")
            import traceback
            traceback.print_exc()


def cmd_status(args):
    conn = get_connection()
    init_db(conn)
    print_status(conn)


def cmd_export(args):
    """Exporta leads a CSV directamente desde DB sin pasar por steps."""
    import csv
    import json as _json
    from config import LISTMONK_CSV, NO_EMAIL_CSV
    from src.db import get_all_leads

    conn = get_connection()
    init_db(conn)
    leads = get_all_leads(conn)

    min_score = args.min_score
    with_email = [l for l in leads if l.get("email") and (l.get("email_score", 0) >= min_score)]
    without_email = [l for l in leads if not l.get("email")]

    LISTMONK_CSV.parent.mkdir(exist_ok=True)
    with open(LISTMONK_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["email", "name", "attributes"])
        for lead in with_email:
            contact = lead.get("contact_name") or lead.get("company", "")
            attrs = _json.dumps({
                "empresa":   lead.get("company", ""),
                "cargo":     lead.get("contact_title") or lead.get("title", ""),
                "industria": lead.get("industry", ""),
                "dato":      lead.get("personalization", ""),
                "pais":      lead.get("country", ""),
                "dolor":     lead.get("pain_point", ""),
                "website":   lead.get("website", ""),
                "source":    lead.get("source", ""),
            }, ensure_ascii=False)
            writer.writerow([lead["email"], contact, attrs])

    with open(NO_EMAIL_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["empresa", "website", "industria", "pais", "rating", "telefono"])
        for lead in without_email:
            writer.writerow([
                lead.get("company", ""),
                lead.get("website", ""),
                lead.get("industry", ""),
                lead.get("country", ""),
                lead.get("rating", ""),
                lead.get("phone", ""),
            ])

    print(f"\n[Export] {len(with_email)} leads con email -> {LISTMONK_CSV}")
    print(f"[Export] {len(without_email)} leads sin email -> {NO_EMAIL_CSV}")


# ─────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="app.py",
        description="FOMO Lead Generation v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python app.py collect --source google --industries salud manufactura --countries mexico colombia --limit 1000
  python app.py collect --source apollo --industries distribucion --limit 50
  python app.py crawl --limit 500 --concurrency 20
  python app.py enrich --limit 200
  python app.py process
  python app.py export
  python app.py status
        """,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # collect
    col = sub.add_parser("collect", help="Recolectar empresas de fuentes")
    col.add_argument("--source", choices=["google", "apollo", "all"], default="google")
    col.add_argument("--industries", nargs="+", choices=ALL_INDUSTRIES, metavar="INDUSTRIA",
                     help=f"Opciones: {', '.join(ALL_INDUSTRIES)}")
    col.add_argument("--countries", nargs="+", metavar="PAÍS",
                     help=f"Opciones: {', '.join(ALL_COUNTRIES)}")
    col.add_argument("--limit", type=int, default=1000,
                     help="Máximo de leads a recolectar (default: 1000)")

    # crawl
    cr = sub.add_parser("crawl", help="Crawlear websites para extraer emails")
    cr.add_argument("--limit", type=int, default=500,
                    help="Cantidad de leads a procesar (default: 500)")
    cr.add_argument("--concurrency", type=int, default=CRAWL_CONCURRENCY,
                    help=f"Requests paralelos (default: {CRAWL_CONCURRENCY})")

    # enrich
    en = sub.add_parser("enrich", help="Enriquecer emails via Hunter.io")
    en.add_argument("--limit", type=int, default=200,
                    help="Cantidad de leads a procesar (default: 200)")

    # process
    pr = sub.add_parser("process", help="Correr steps 4-7 (personalización, CSV, reporte, dashboard)")
    pr.add_argument("--steps", nargs="+", type=int, default=[4, 5, 6, 7],
                    help="Steps a ejecutar (default: 4 5 6 7)")

    # status
    sub.add_parser("status", help="Ver estadísticas de la base de datos")

    # export
    ex = sub.add_parser("export", help="Exportar CSV para Listmonk")
    ex.add_argument("--min-score", type=int, default=0, dest="min_score",
                    help="Score mínimo de email (0-3, default: 0)")

    args = parser.parse_args()

    dispatch = {
        "collect": cmd_collect,
        "crawl":   cmd_crawl,
        "enrich":  cmd_enrich,
        "process": cmd_process,
        "status":  cmd_status,
        "export":  cmd_export,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
