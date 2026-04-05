import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _parse_keys(multi_var: str, single_var: str) -> list[str]:
    """Lee keys separadas por coma (multi) o key única (single)."""
    multi = os.getenv(multi_var, "")
    keys = [k.strip() for k in multi.split(",") if k.strip()]
    if not keys:
        single = os.getenv(single_var, "").strip()
        if single:
            keys = [single]
    return keys


# --- API Keys (multi-key para rotación) ---
APOLLO_API_KEYS = _parse_keys("APOLLO_API_KEYS", "APOLLO_API_KEY")
GOOGLE_PLACES_API_KEYS = _parse_keys("GOOGLE_PLACES_API_KEYS", "GOOGLE_PLACES_API_KEY")
HUNTER_API_KEYS = _parse_keys("HUNTER_API_KEYS", "HUNTER_API_KEY")

# Retrocompatibilidad — primera key disponible
APOLLO_API_KEY = APOLLO_API_KEYS[0] if APOLLO_API_KEYS else ""
GOOGLE_PLACES_API_KEY = GOOGLE_PLACES_API_KEYS[0] if GOOGLE_PLACES_API_KEYS else ""
HUNTER_API_KEY = HUNTER_API_KEYS[0] if HUNTER_API_KEYS else ""

# --- Paths ---
BASE_DIR = Path(__file__).parent
LEADS_DIR = BASE_DIR / "leads"
LEADS_DIR.mkdir(exist_ok=True)
DB_PATH = BASE_DIR / "leads.db"

APOLLO_OUTPUT = LEADS_DIR / "leads_apollo.json"
GOOGLE_OUTPUT = LEADS_DIR / "leads_google.json"
ENRICHED_OUTPUT = LEADS_DIR / "leads_enriched.json"
FINAL_OUTPUT = LEADS_DIR / "leads_final.json"
LISTMONK_CSV = LEADS_DIR / "leads_listmonk.csv"
NO_EMAIL_CSV = LEADS_DIR / "leads_no_email.csv"
REPORT_OUTPUT = LEADS_DIR / "leads_report.md"
DASHBOARD_OUTPUT = LEADS_DIR / "dashboard.html"

# --- Rate Limits ---
APOLLO_DELAY = 12  # segundos entre requests (5 req/min)
GOOGLE_DELAY = 1.0  # 1 req/s
CRAWL_DELAY = 1.0  # 1 req/s por dominio
CRAWL_MAX_PAGES = 3
CRAWL_TIMEOUT = 10
CRAWL_RETRIES = 1

# --- Async crawl ---
CRAWL_CONCURRENCY = int(os.getenv("CRAWL_CONCURRENCY", "20"))

# --- Hunter ---
HUNTER_MIN_SCORE = int(os.getenv("HUNTER_MIN_SCORE", "40"))

# --- Apollo ---
APOLLO_MAX_LEADS = 50
APOLLO_ENDPOINT = "https://api.apollo.io/api/v1/mixed_people/search"
APOLLO_SENIORITIES = ["owner", "founder", "c_suite", "director"]

# Distribución por industria: (label, keywords apollo, target)
APOLLO_INDUSTRIES = {
    "distribucion": {
        "keywords": ["wholesale", "distribution", "logistics", "import export"],
        "target": 15,
    },
    "servicios_profesionales": {
        "keywords": ["professional services", "consulting", "legal", "accounting", "staffing"],
        "target": 15,
    },
    "manufactura": {
        "keywords": ["manufacturing", "industrial", "food production", "packaging"],
        "target": 20,
    },
}

# Países LATAM para Apollo
APOLLO_COUNTRIES = [
    "Mexico", "Colombia", "Argentina", "Chile", "Peru",
    "Ecuador", "Uruguay", "Costa Rica", "Panama", "Dominican Republic",
    "Guatemala", "Bolivia", "Paraguay", "El Salvador", "Honduras",
]

# --- Google Places ---
GOOGLE_INDUSTRIES = {
    "salud": {
        "queries": [
            "clínica privada {city}",
            "hospital privado {city}",
            "centro médico {city}",
            "laboratorio clínico {city}",
            "clínica dental {city}",
            "centro de rehabilitación {city}",
            "clínica oftalmológica {city}",
            "centro de diagnóstico {city}",
            "clínica dermatológica {city}",
            "policlínico {city}",
            "centro de salud ocupacional {city}",
            "clínica estética {city}",
        ],
        "target": 40,
    },
    "distribucion": {
        "queries": [
            "distribuidora de alimentos {city}",
            "distribuidora mayorista {city}",
            "empresa de logística {city}",
            "importadora {city}",
            "distribuidora de bebidas {city}",
            "distribuidora de productos {city}",
            "mayorista {city}",
            "empresa de distribución {city}",
            "distribuidora industrial {city}",
            "comercializadora {city}",
        ],
        "target": 25,
    },
    "servicios_profesionales": {
        "queries": [
            "consultora empresarial {city}",
            "estudio contable {city}",
            "bufete de abogados {city}",
            "agencia de marketing {city}",
            "empresa de recursos humanos {city}",
            "consultoría de negocios {city}",
            "estudio jurídico {city}",
            "empresa de consultoría {city}",
            "agencia de publicidad {city}",
        ],
        "target": 25,
    },
    "manufactura": {
        "queries": [
            "fábrica {city}",
            "planta de producción {city}",
            "empresa manufacturera {city}",
            "industria alimentaria {city}",
            "empresa de empaques {city}",
            "manufactura {city}",
            "planta industrial {city}",
            "empresa de plásticos {city}",
        ],
        "target": 20,
    },
}

# Ciudades para queries de Google Places
GOOGLE_CITIES = [
    "Ciudad de México", "Guadalajara", "Monterrey", "Puebla",
    "Bogotá", "Medellín", "Cali", "Barranquilla",
    "Buenos Aires", "Córdoba", "Rosario",
    "Santiago de Chile", "Valparaíso",
    "Lima", "Arequipa",
    "Quito", "Guayaquil",
    "San José Costa Rica",
    "Panamá",
    "Santo Domingo",
]

GOOGLE_MIN_RATING = 3.5
GOOGLE_MIN_REVIEWS = 10

# --- Dolores por industria ---
PAIN_POINTS = {
    "salud": (
        "Pacientes esperan días por una cita y el equipo pierde horas "
        "en WhatsApp coordinando agendas manualmente."
    ),
    "distribucion": (
        "Pedidos llegan por WhatsApp, email y teléfono; "
        "el equipo los carga a mano y los errores cuestan devoluciones."
    ),
    "servicios_profesionales": (
        "Cotizaciones y seguimientos se pierden entre emails; "
        "los ejecutivos dedican más tiempo a admin que a cerrar clientes."
    ),
    "manufactura": (
        "Órdenes de producción se coordinan en Excel y WhatsApp; "
        "cualquier cambio genera retrabajos y entregas tardías."
    ),
}

# --- Personalización: fallbacks genéricos por industria ---
PERSONALIZATION_FALLBACKS = {
    "salud": "tu clínica podría agendar citas 24/7 sin intervención manual",
    "distribucion": "podrías recibir y confirmar pedidos en automático",
    "servicios_profesionales": "podrías automatizar cotizaciones y seguimiento de clientes",
    "manufactura": "podrías coordinar órdenes de producción sin Excel ni WhatsApp",
}

# Emails genéricos a desprioritizar
GENERIC_EMAIL_PREFIXES = [
    "info", "contacto", "contact", "admin", "ventas", "sales",
    "soporte", "support", "hola", "hello", "recepcion",
]

# --- Listas para la web app ---
ALL_INDUSTRIES_LIST = list({**GOOGLE_INDUSTRIES, **APOLLO_INDUSTRIES}.keys())
ALL_COUNTRIES_LIST = [c.lower().replace(" ", "_") for c in APOLLO_COUNTRIES]

# Emails a descartar
DISCARD_EMAIL_PREFIXES = [
    "rrhh", "hr", "recruitment", "noreply", "no-reply",
    "newsletter", "unsubscribe", "marketing",
]
