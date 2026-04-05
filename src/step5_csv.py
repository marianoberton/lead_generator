"""Paso 5: Generar CSV para importación a Listmonk."""

import csv
import json

from config import FINAL_OUTPUT, LISTMONK_CSV, NO_EMAIL_CSV


def get_email(lead: dict) -> str:
    """Obtiene el mejor email disponible del lead."""
    # Apollo leads ya tienen email directo
    if lead.get("email"):
        return lead["email"]
    # Google Places leads tienen best_email del crawling
    if lead.get("best_email"):
        return lead["best_email"]
    return ""


def get_name(lead: dict) -> str:
    """Obtiene el nombre del contacto o la empresa."""
    # Nombre del contacto (Apollo o crawling)
    if lead.get("name") and lead["name"] != "N/A" and lead.get("source") == "apollo":
        return lead["name"]
    if lead.get("contact_name"):
        return lead["contact_name"]
    # Fallback: nombre de la empresa
    return lead.get("company") or lead.get("name", "N/A")


def build_attributes(lead: dict) -> str:
    """Construye JSON string de atributos para Listmonk."""
    attrs = {
        "empresa": lead.get("company") or lead.get("name", ""),
        "cargo": lead.get("title") or lead.get("contact_title", ""),
        "industria": lead.get("industry_category", ""),
        "dato": lead.get("personalization", ""),
        "pais": lead.get("country", ""),
        "dolor": lead.get("pain_point", ""),
        "website": lead.get("website", ""),
        "source": lead.get("source", ""),
    }
    return json.dumps(attrs, ensure_ascii=False)


def run():
    """Ejecuta el paso 5: generación de CSV para Listmonk."""
    try:
        with open(FINAL_OUTPUT, encoding="utf-8") as f:
            leads = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("[CSV] ERROR: No se encontró leads_final.json. Ejecutá el paso 4 primero.")
        return

    print(f"\n[CSV] Procesando {len(leads)} leads...")

    with_email = []
    without_email = []

    for lead in leads:
        email = get_email(lead)
        if email:
            with_email.append(lead)
        else:
            without_email.append(lead)

    # CSV principal para Listmonk
    LISTMONK_CSV.parent.mkdir(exist_ok=True)
    with open(LISTMONK_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["email", "name", "attributes"])
        for lead in with_email:
            writer.writerow([
                get_email(lead),
                get_name(lead),
                build_attributes(lead),
            ])

    # CSV de leads sin email
    with open(NO_EMAIL_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["empresa", "website", "industria", "pais", "rating", "telefono"])
        for lead in without_email:
            writer.writerow([
                lead.get("company") or lead.get("name", ""),
                lead.get("website", ""),
                lead.get("industry_category", ""),
                lead.get("country", ""),
                lead.get("rating", ""),
                lead.get("phone", ""),
            ])

    print(f"[CSV] {len(with_email)} leads con email -> {LISTMONK_CSV}")
    print(f"[CSV] {len(without_email)} leads sin email -> {NO_EMAIL_CSV}")


if __name__ == "__main__":
    run()
