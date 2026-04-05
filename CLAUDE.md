# Lead Generation - FOMO

Script Python para generar 160 leads (cold email) para FOMO (fomologic.com) — agentes IA para empresas medianas en LATAM. Importación a Listmonk.

## Stack
- Python 3.11+
- requests, beautifulsoup4, httpx (async opcional)
- Chart.js (CDN) para dashboard
- Sin Selenium/Playwright — solo HTTP

## Fuentes
- **Apollo API (50 leads):** email verificado + decisor. Distribución 15, Serv. Prof. 15, Manufactura 20.
- **Google Places + Crawling (110 leads):** Salud 40, Distribución 25, Serv. Prof. 25, Manufactura 20.

NO crawlear webs de leads de Apollo (ya tienen email verificado).

## Pipeline
1. Apollo API → `leads/leads_apollo.json`
2. Google Places → `leads/leads_google.json`
3. Web crawling (solo Google Places) → `leads/leads_enriched.json`
4. Personalización (todos) → `leads/leads_final.json`
5. CSV Listmonk → `leads/leads_listmonk.csv` + `leads/leads_no_email.csv`
6. Reporte → `leads/leads_report.md`
7. Dashboard → `leads/dashboard.html`

## Ejecución
```bash
python lead_gen.py           # todo
python lead_gen.py --step N  # paso individual (1-7)
```

## Rate limits
- Apollo: 5 req/min, max 50 leads/mes (free)
- Google Places: 1 req/s
- Web crawling: 1 req/s por dominio, max 3 pages por dominio
- Timeout: 10s, 1 retry

## Env vars
- `APOLLO_API_KEY` — requerido
- `GOOGLE_PLACES_API_KEY` — opcional (si no hay, scraping)
- `HUNTER_API_KEY` — opcional

## Reglas
- No inventar datos — "N/A" o fallback genérico
- No exceder 50 leads de Apollo
- Deduplicar por dominio entre fuentes
- Personalización: max 15 palabras, datos reales
- No guardar API keys en código (usar .env)
