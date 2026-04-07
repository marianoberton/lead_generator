# FOMO Lead Generation

Pipeline de generación de leads para [FOMO](https://fomologic.com) — agentes IA para empresas medianas en LATAM. Recolecta empresas, enriquece emails mediante waterfall multi-servicio, y exporta CSV para Listmonk.

---

## Inicio rápido

```bash
pip install -r requirements.txt
cp .env.example .env        # agregar APOLLO_API_KEY
PORT=8001 python web_app.py # abrir http://localhost:8001
```

---

## Arquitectura

```
Fuentes de leads          Enrichment (waterfall)        Salida
─────────────────         ──────────────────────        ──────
Apollo API (50/mes)  ─┐
Apify / Google Maps  ─┤──► SQLite (leads.db) ──► Crawling webs
                      │                      ──► Hunter.io
                      │                      ──► Snov.io
                      │                      ──► Skrapp.io
                      │                      ──► Tomba.io
                      └                      ──► VoilaNorbert
                                                      │
                                             CSV → Listmonk
```

Cada servicio de enrichment solo procesa leads **sin email** y no repite dominios ya buscados (waterfall con estado en DB).

---

## Web App

```bash
PORT=8001 python web_app.py
```

| Ruta | Descripción |
|------|-------------|
| `/` | Dashboard con plan de acción paso a paso y stats |
| `/leads` | Tabla filtrable/paginada de todos los leads |
| `/jobs` | Lanzar collect/crawl/enrich con terminal en tiempo real |
| `/keys` | Gestionar API keys con guías de registro por servicio |
| `/export/csv` | Descargar CSV para Listmonk |

---

## CLI

```bash
# Recolectar empresas
python app.py collect --source apollo --limit 50
python app.py collect --source apify --industries distribucion manufactura salud --countries mexico colombia --limit 500

# Crawlear webs para emails
python app.py crawl --limit 500 --concurrency 20

# Enriquecer (servicio específico o waterfall completo)
python app.py enrich --source skrapp --limit 200
python app.py enrich-all --limit 500

# Generar personalización + CSV + reporte + dashboard
python app.py process

# Ver estado
python app.py status
python app.py keys-status

# Resetear quotas mensuales (1 de cada mes)
python app.py reset-quotas

# Exportar CSV para Listmonk
python app.py export
```

---

## Variables de entorno (`.env`)

| Variable | Descripción |
|----------|-------------|
| `APOLLO_API_KEY` | Apollo.io — 50 leads/mes gratis |
| `APOLLO_API_KEY_2..N` | Cuentas adicionales de Apollo |
| `HUNTER_API_KEY` | Hunter.io — 25 emails/mes gratis |
| `HUNTER_API_KEY_2..N` | Cuentas adicionales de Hunter |
| `SKRAPP_API_KEY` | Skrapp.io — 100 emails/mes gratis |
| `SKRAPP_API_KEY_2..N` | Cuentas adicionales de Skrapp |
| `SNOV_API_KEY` | Snov.io — `client_id:client_secret` — 50/mes |
| `TOMBA_API_KEY` | Tomba.io — `key:secret` — 25/mes |
| `NORBERT_API_KEY` | VoilaNorbert — 50 créditos one-time |
| `APIFY_API_KEY` | Apify — $5 crédito gratis para Google Maps |
| `PORT` | Puerto de la web app (default: 8000) |

Las keys también se pueden cargar desde la web en `/keys` sin editar el `.env`.

---

## Enrichment waterfall

El pipeline intenta cada servicio en orden y para cuando encuentra email para ese lead:

```
Crawling → Hunter → Snov → Skrapp → Tomba → Norbert
```

Cada servicio tiene su columna `{svc}_searched` en la DB para no repetir búsquedas. Para resetear y volver a buscar: borrar el flag en SQLite o usar `reset-quotas`.

---

## Gestión de quotas

Con 10-12 cuentas por servicio (registradas con distintos emails):

| Servicio | Free/cuenta | × 12 | Total/mes |
|----------|-------------|------|-----------|
| Skrapp.io | 100 | × 12 | 1,200 |
| Snov.io | 50 | × 12 | 600 |
| Hunter.io | 25 | × 12 | 300 |
| Tomba.io | 25 | × 12 | 300 |
| **Total** | | | **~2,400/mes** |

El sistema rota automáticamente entre keys y desactiva las que alcanzan su límite mensual. Resetear el 1 de cada mes desde `/keys` → "Reset quotas mensuales".

---

## Flujo recomendado

1. Registrar 10-12 cuentas por servicio y cargar keys en `/keys`
2. Collect con Apify (500+ empresas) + Apollo (50 decisores)
3. Crawl webs para emails directos
4. `enrich-all` para waterfall completo
5. Warm-up de cuentas de email (2-4 semanas)
6. Exportar CSV e importar en Listmonk
7. Empezar envíos a 20-30/día, escalar progresivamente

Ver [PLAN.md](PLAN.md) para el plan detallado con fechas y próximos pasos.

---

## Troubleshooting

**Apollo: `+0 leads` en todas las páginas**
→ Los resultados ya están en la DB (deduplicación por dominio). Normal después de la primera ejecución.

**Enrichment: "Sin keys disponibles"**
→ No hay keys cargadas para ese servicio. Ir a `/keys` y agregar.

**Quota agotada**
→ El sistema desactiva la key automáticamente. Agregar más cuentas o esperar al 1 del mes.

**Web app: puerto en uso**
→ Usar `PORT=8001 python web_app.py` (o cualquier puerto libre).
