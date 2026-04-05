# Plan de Acción — Lead Generation FOMO

## Fase 1: Setup
- [ ] Crear estructura: `leads/`, `src/`
- [ ] `requirements.txt` (requests, beautifulsoup4, httpx, lxml, python-dotenv)
- [ ] `.env.example` con APOLLO_API_KEY, GOOGLE_PLACES_API_KEY, HUNTER_API_KEY
- [ ] `config.py` — queries, industrias, constantes, mapeo de dolores

## Fase 2: Apollo API (`src/step1_apollo.py`)
- [ ] Endpoint: `POST https://api.apollo.io/api/v1/mixed_people/search`
- [ ] 3 búsquedas: distribuidoras (15), serv. prof. (15), manufactura (20) = 50 total
- [ ] Filtros: seniority owner/founder/c_suite/director, email verified, LATAM, 11-200 empleados
- [ ] Si una búsqueda devuelve menos, redistribuir sobrante a las otras
- [ ] Extraer: name, email, title, org name/website/employees/industry/city/country/description
- [ ] Rate limit: 5 req/min
- [ ] Guardar `leads/leads_apollo.json`

## Fase 3: Google Places (`src/step2_google.py`)
- [ ] Queries: salud (12 queries→40 leads), distribución (10→25), serv. prof. (9→25), manufactura (8→20)
- [ ] Si hay API key: Text Search API. Si no: scraping Google Maps via HTTP
- [ ] Filtros: tiene website, rating 3.5+, 10+ reviews, no cadenas, no duplica Apollo (por dominio)
- [ ] Extraer: name, address, phone, website, rating, reviews_count, industry, country
- [ ] Guardar `leads/leads_google.json`

## Fase 4: Web Crawling (`src/step3_crawl.py`)
- [ ] SOLO leads de Google Places
- [ ] Crawlear: homepage + /contacto + /about (max 3 pages por dominio)
- [ ] Extraer emails (regex), nombres+cargos, descripción empresa
- [ ] Priorizar: email persona con cargo > email con nombre > contacto@/info@ > descartar soporte/rrhh
- [ ] Rate limit: 1 req/s, timeout 10s, 1 retry
- [ ] Guardar `leads/leads_enriched.json`

## Fase 5: Personalización (`src/step4_personalize.py`)
- [ ] TODOS los leads (Apollo + Google Places)
- [ ] Apollo: usar org.short_description + crawl solo homepage
- [ ] Google Places: usar info del crawling del paso 3
- [ ] Patrones por prioridad: datos concretos > datos de escala > fallback genérico
- [ ] Max 15 palabras, basado en datos reales
- [ ] Guardar `leads/leads_final.json`

## Fase 6: CSV Listmonk (`src/step5_csv.py`)
- [ ] Formato: `email,name,attributes` (attributes = JSON string)
- [ ] Attributes: empresa, cargo, industria, dato, pais, dolor, website, source
- [ ] Generar `leads/leads_listmonk.csv` + `leads/leads_no_email.csv`

## Fase 7: Reporte (`src/step6_report.py`)
- [ ] Tablas: por fuente, por industria, por país
- [ ] Email persona vs genérico, personalización real vs fallback
- [ ] Lista empresas sin email, errores
- [ ] Guardar `leads/leads_report.md`

## Fase 8: Dashboard (`src/step7_dashboard.py`)
- [ ] HTML estático con datos embebidos como JS vars (no fetch)
- [ ] 4 cards métricas: total con email, sin email, % personalización real, deliverability
- [ ] Gráfico barras: leads por industria (Apollo vs Google Places) — Chart.js
- [ ] Gráfico dona: calidad email (verificado, persona, genérico, sin email)
- [ ] Tabla por país
- [ ] Tabla interactiva: todos los leads, filtrable, sorteable, búsqueda por texto
- [ ] Color coding: verde (email persona), amarillo (genérico), rojo (sin email)
- [ ] Sección leads sin email con links a websites
- [ ] Responsive, sans-serif, colores suaves
- [ ] Guardar `leads/dashboard.html`

## Fase 9: Orquestador (`lead_gen.py`)
- [ ] Ejecuta pasos 1-7 en secuencia
- [ ] `--step N` para paso individual
- [ ] Carga .env con python-dotenv
- [ ] Manejo de errores + retry

## Orden de desarrollo
1. `config.py` + estructura → base
2. `step1_apollo.py` → API limpia, resultados rápido
3. `step2_google.py` → depende de si hay API key
4. `step3_crawl.py` → muchos edge cases
5. `step4_personalize.py` → lógica con datos recolectados
6. `step5_csv.py` → transformación directa
7. `step6_report.py` → agregación
8. `step7_dashboard.py` → HTML con datos embebidos
9. `lead_gen.py` → orquestador
10. Test con 1 búsqueda Apollo + 1 query Google antes de correr todo

## Riesgos
- **Apollo free = 50 leads/mes**: no exceder, redistribuir si da menos
- **Google bloquea scraping**: fallback manual o usar API key
- **Webs no responden**: timeout + skip + anotar en reporte
- **Pocos emails de crawling**: considerar Hunter.io
- **Duplicados entre fuentes**: deduplicar por dominio del website
