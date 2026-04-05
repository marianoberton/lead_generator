# FOMO Lead Generation

Pipeline Python para generar ~160 leads de cold email para [FOMO](https://fomologic.com) — agentes IA para empresas medianas en LATAM. Genera el CSV listo para importar a Listmonk.

---

## Setup

```bash
# Instalar dependencias
pip install -r requirements.txt

# Configurar API keys
cp .env.example .env
# Editar .env con tus keys
```

### Variables de entorno

| Variable | Estado | Descripción |
|---|---|---|
| `APOLLO_API_KEY` | **Requerida** | Free plan = 50 exports de email/mes |
| `GOOGLE_PLACES_API_KEY` | Opcional | Si no hay, Step 2 usa Apollo como fallback |
| `HUNTER_API_KEY` | Opcional | No implementado aún |

---

## Cómo ejecutar

```bash
# Pipeline completo (pasos 1-7)
python lead_gen.py

# Un paso individual
python lead_gen.py --step 1
python lead_gen.py --step 2
# ... hasta --step 7
```

---

## Pipeline — paso a paso

```
[Step 1]          [Step 2]
Apollo People  →  Google Places / Apollo Orgs
(50 leads)        (110 leads)
    │                   │
    │             [Step 3] Web Crawling
    │             (solo Step 2, busca emails en webs)
    │                   │
    └─────────┬─────────┘
              ▼
         [Step 4] Personalización
         (todos los leads, genera frase 15 palabras)
              │
         [Step 5] CSV
         ┌────┴─────┐
         ▼           ▼
  leads_listmonk  leads_no_email
  (con email)     (sin email)
              │
         [Step 6] Reporte Markdown
         [Step 7] Dashboard HTML
```

### Step 1 — Apollo People Search (`src/step1_apollo.py`)
- **Endpoint:** `POST /api/v1/mixed_people/search`
- **Filtros:** seniority owner/founder/c_suite/director, empleados 11-200, países LATAM
- **Distribución:** Distribución 15, Servicios Prof. 15, Manufactura 20 = 50 total
- **Output:** `leads/leads_apollo.json`
- Cada lead tiene: `name`, `email`, `title`, `company`, `website`, `employees`, `country`, `company_description`

### Step 2 — Google Places / Apollo Orgs (`src/step2_google.py`)
- **Con `GOOGLE_PLACES_API_KEY`:** usa Google Places Text Search API → `source: "google_places"`
- **Sin key:** usa Apollo `organizations/search` como fallback → `source: "apollo_orgs"`
- **Distribución:** Salud 40, Distribución 25, Servicios Prof. 25, Manufactura 20 = 110 total
- **Output:** `leads/leads_google.json`
- Deduplica contra dominios del Step 1
- Cada lead tiene: `name`, `website`, `phone`, `rating`, `reviews_count`, `country`
- **No tiene email** — el email se obtiene en Step 3

### Step 3 — Web Crawling (`src/step3_crawl.py`)
- **Solo** procesa los leads de `leads_google.json` (Step 2)
- Por cada lead: crawlea homepage + /contacto + /about (máx 3 páginas)
- Extrae emails con regex, prioriza emails de persona vs genéricos
- **Rate limit:** 1 req/s, timeout 10s, 1 retry
- **Output:** `leads/leads_enriched.json`
- Agrega a cada lead: `best_email`, `email_score`, `contact_name`, `contact_title`, `company_description`

### Step 4 — Personalización (`src/step4_personalize.py`)
- Procesa **todos** los leads (Apollo + Google/Orgs)
- Genera una frase de personalización (máx 15 palabras) por prioridad:
  1. **concrete** — dato específico de la descripción (años, especialidad)
  2. **scale** — datos de escala (nro empleados, rating + reseñas)
  3. **fallback** — frase genérica por industria
- Agrega `pain_point` por industria
- **Output:** `leads/leads_final.json`

### Step 5 — CSV Listmonk (`src/step5_csv.py`)
- Lee `leads_final.json`, separa con email / sin email
- **`leads/leads_listmonk.csv`** — formato `email,name,attributes` listo para importar
- **`leads/leads_no_email.csv`** — empresas sin email para seguimiento manual
- El campo `attributes` es un JSON string con: empresa, cargo, industria, dato, pais, dolor, website, source

### Step 6 — Reporte (`src/step6_report.py`)
- Estadísticas por fuente, industria, país, tipo de email, tipo de personalización
- Lista de empresas sin email
- **Output:** `leads/leads_report.md`

### Step 7 — Dashboard (`src/step7_dashboard.py`)
- HTML estático con datos embebidos (sin servidor, abrir directo en browser)
- 4 cards métricas, gráfico por industria, gráfico calidad email, tabla por país
- Tabla interactiva de todos los leads (filtrable, sorteable, búsqueda por texto)
- Color coding: verde (email persona), amarillo (email genérico), rojo (sin email)
- **Output:** `leads/dashboard.html`

---

## Archivos generados

```
leads/
├── leads_apollo.json      # Step 1: 50 leads con email verificado
├── leads_google.json      # Step 2: 110 leads sin email (solo empresa + web)
├── leads_enriched.json    # Step 3: Step 2 + emails encontrados en sus webs
├── leads_final.json       # Step 4: todos los leads con personalización
├── leads_listmonk.csv     # Step 5: CSV para importar a Listmonk
├── leads_no_email.csv     # Step 5: empresas sin email
├── leads_report.md        # Step 6: reporte de estadísticas
└── dashboard.html         # Step 7: abrir en browser
```

---

## Industrias target

| Industria | Apollo | Google/Orgs | Total |
|---|---|---|---|
| Distribución | 15 | 25 | 40 |
| Servicios Profesionales | 15 | 25 | 40 |
| Manufactura | 20 | 20 | 40 |
| Salud | — | 40 | 40 |
| **Total** | **50** | **110** | **160** |

## Países LATAM

México, Colombia, Argentina, Chile, Perú, Ecuador, Uruguay, Costa Rica, Panamá, República Dominicana, Guatemala, Bolivia, Paraguay, El Salvador, Honduras.

---

## Rate limits

| Fuente | Límite | Configurado en |
|---|---|---|
| Apollo API | 5 req/min (delay 12s) | `config.py → APOLLO_DELAY` |
| Google Places | 1 req/s | `config.py → GOOGLE_DELAY` |
| Web crawling | 1 req/s por dominio | `config.py → CRAWL_DELAY` |
| Timeout crawl | 10s + 1 retry | `config.py → CRAWL_TIMEOUT` |

**Apollo free plan:** máximo 50 exports de email por mes. No re-ejecutar Step 1 si ya se obtuvieron 50.

---

## Troubleshooting

**Apollo devuelve 0 emails:**
- Verificar que `APOLLO_API_KEY` sea válida
- El free plan tiene 50 exports/mes — puede estar agotado
- Ejecutar `python lead_gen.py --step 1` para ver el error

**Step 2 usa Apollo en lugar de Google Places:**
- Comportamiento esperado cuando `GOOGLE_PLACES_API_KEY` está vacía
- Los leads tendrán `source: "apollo_orgs"` y serán crawleados en Step 3

**Step 3 lento:**
- Normal — crawlea hasta 330 páginas (110 leads × 3 páginas) a 1 req/s ≈ 5-6 min
- Muchos sitios bloquean scraping → leads quedarán sin email

**Dashboard no carga datos:**
- Ejecutar Step 4 antes que Step 7
- Abrir `leads/dashboard.html` directamente en browser (no necesita servidor)
