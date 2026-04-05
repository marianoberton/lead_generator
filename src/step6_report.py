"""Paso 6: Generar reporte markdown con estadísticas."""

import json
from collections import Counter

from config import FINAL_OUTPUT, REPORT_OUTPUT


def get_email(lead: dict) -> str:
    if lead.get("email"):
        return lead["email"]
    if lead.get("best_email"):
        return lead["best_email"]
    return ""


def run():
    """Ejecuta el paso 6: generación de reporte."""
    try:
        with open(FINAL_OUTPUT, encoding="utf-8") as f:
            leads = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("[Reporte] ERROR: No se encontró leads_final.json.")
        return

    print(f"\n[Reporte] Generando reporte para {len(leads)} leads...")

    # Clasificación
    with_email = [l for l in leads if get_email(l)]
    without_email = [l for l in leads if not get_email(l)]
    apollo = [l for l in leads if l.get("source") == "apollo"]
    google = [l for l in leads if l.get("source") in ("google_places", "apollo_orgs")]

    # Email types
    person_email = [l for l in with_email if l.get("email_score", 3) >= 2]
    generic_email = [l for l in with_email if l.get("email_score", 3) == 1]
    verified_email = [l for l in apollo if get_email(l)]  # Apollo = verified

    # Personalización
    concrete = [l for l in leads if l.get("personalization_type") == "concrete"]
    scale = [l for l in leads if l.get("personalization_type") == "scale"]
    fallback = [l for l in leads if l.get("personalization_type") == "fallback"]

    # Por industria
    industry_counter = Counter(l.get("industry_category", "N/A") for l in leads)
    industry_email = Counter(l.get("industry_category", "N/A") for l in with_email)

    # Por país
    country_counter = Counter(l.get("country", "N/A") for l in leads)

    # --- Construir reporte ---
    lines = []
    lines.append("# Reporte de Generación de Leads — FOMO\n")

    lines.append("## Resumen General\n")
    lines.append(f"| Métrica | Valor |")
    lines.append(f"|---|---|")
    lines.append(f"| Total leads | {len(leads)} |")
    lines.append(f"| Con email | {len(with_email)} |")
    lines.append(f"| Sin email | {len(without_email)} |")
    lines.append(f"| % con email | {len(with_email)*100//max(len(leads),1)}% |")
    lines.append(f"| Apollo (verificado) | {len(apollo)} |")
    lines.append(f"| Google Places | {len(google)} |")
    lines.append("")

    lines.append("## Calidad de Email\n")
    lines.append(f"| Tipo | Cantidad |")
    lines.append(f"|---|---|")
    lines.append(f"| Verificado (Apollo) | {len(verified_email)} |")
    lines.append(f"| Email persona | {len(person_email)} |")
    lines.append(f"| Email genérico | {len(generic_email)} |")
    lines.append(f"| Sin email | {len(without_email)} |")
    lines.append("")

    lines.append("## Por Fuente\n")
    lines.append(f"| Fuente | Total | Con Email |")
    lines.append(f"|---|---|---|")
    apollo_with = sum(1 for l in apollo if get_email(l))
    google_with = sum(1 for l in google if get_email(l))
    lines.append(f"| Apollo | {len(apollo)} | {apollo_with} |")
    lines.append(f"| Google Places | {len(google)} | {google_with} |")
    lines.append("")

    lines.append("## Por Industria\n")
    lines.append(f"| Industria | Total | Con Email |")
    lines.append(f"|---|---|---|")
    for ind in sorted(industry_counter.keys()):
        lines.append(f"| {ind} | {industry_counter[ind]} | {industry_email.get(ind, 0)} |")
    lines.append("")

    lines.append("## Por País\n")
    lines.append(f"| País | Leads |")
    lines.append(f"|---|---|")
    for country, count in country_counter.most_common():
        lines.append(f"| {country} | {count} |")
    lines.append("")

    lines.append("## Personalización\n")
    lines.append(f"| Tipo | Cantidad | % |")
    lines.append(f"|---|---|---|")
    total = max(len(leads), 1)
    lines.append(f"| Datos concretos | {len(concrete)} | {len(concrete)*100//total}% |")
    lines.append(f"| Datos de escala | {len(scale)} | {len(scale)*100//total}% |")
    lines.append(f"| Fallback genérico | {len(fallback)} | {len(fallback)*100//total}% |")
    lines.append(f"| **Real (no fallback)** | **{len(concrete)+len(scale)}** | **{(len(concrete)+len(scale))*100//total}%** |")
    lines.append("")

    if without_email:
        lines.append("## Leads Sin Email\n")
        lines.append(f"| Empresa | Website | Industria | País |")
        lines.append(f"|---|---|---|---|")
        for l in without_email:
            name = l.get("company") or l.get("name", "N/A")
            website = l.get("website", "")
            lines.append(f"| {name} | {website} | {l.get('industry_category', '')} | {l.get('country', '')} |")
        lines.append("")

    report = "\n".join(lines)

    REPORT_OUTPUT.parent.mkdir(exist_ok=True)
    with open(REPORT_OUTPUT, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"[Reporte] Guardado en {REPORT_OUTPUT}")
    print(f"  Total: {len(leads)} | Con email: {len(with_email)} | Sin email: {len(without_email)}")
    print(f"  Personalización real: {len(concrete)+len(scale)}/{len(leads)}")


if __name__ == "__main__":
    run()
