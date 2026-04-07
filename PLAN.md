# Plan de Acción — Lead Generation FOMO
*Actualizado: Abril 2026*

## Estado general

| Fase | Descripción | Estado |
|------|-------------|--------|
| 1 | Infraestructura base (DB, config, CLI) | ✅ Completo |
| 2 | Recolección de leads (Apollo + Apify) | ✅ Completo |
| 3 | Crawling de emails desde webs | ✅ Completo |
| 4 | Enrichment multi-servicio (waterfall) | ✅ Completo |
| 5 | Web app (FastAPI + dashboard) | ✅ Completo |
| 6 | Cargar API keys y acumular leads | 🔄 En curso |
| 7 | Warm-up de cuentas de email | ⏳ Pendiente |
| 8 | Campañas de cold email (Listmonk) | ⏳ Pendiente |

---

## Lo que está listo

### Infraestructura
- **`leads.db`** — SQLite con tabla `leads` y `api_keys`, deduplicación por dominio
- **`src/migrations.py`** — migraciones seguras y repetibles
- **`src/db.py`** — upsert, stats, enrichment helpers, quota tracking
- **`src/key_rotator.py`** — rotación con quota mensual automática, desactiva keys agotadas
- **`config.py`** — industrias, países, queries, límites de servicio
- **`app.py`** — CLI completa: collect, crawl, enrich, enrich-all, process, status, keys-status, reset-quotas, export

### Recolección
- **`src/collector_apollo.py`** — Apollo `organizations/search` (compatible free plan, 50/mes). Circuit breaker en 3 páginas vacías consecutivas. Timeout manejado.
- **`src/collector_apify.py`** — Google Maps via Apify (`compass~crawler-google-places`). Patrón async: start run → poll → fetch results.
- **`src/collector_google.py`** — Google Places API directo (requiere API key paga)
- **`src/crawler_async.py`** — crawling async de webs para extraer emails

### Enrichment (waterfall)
Cada servicio procesa solo los leads **sin email** y marca el dominio como buscado para no repetir.

| Servicio | Archivo | Free tier | Notas |
|----------|---------|-----------|-------|
| Hunter.io | `src/enricher_hunter.py` | 25/mes | Solo API key |
| Snov.io | `src/enricher_snov.py` | 50/mes | OAuth2: client_id:client_secret |
| Skrapp.io | `src/enricher_skrapp.py` | 100/mes | Solo API key — mejor free tier |
| Tomba.io | `src/enricher_tomba.py` | 25/mes | key:secret |
| VoilaNorbert | `src/enricher_norbert.py` | 50 one-time | Requiere contact_name en el lead |

### Web app
- **`web_app.py`** — FastAPI + Jinja2, puerto 8001 (`PORT=8001 python web_app.py`)
- **Dashboard `/`** — Plan de acción paso a paso, stats, enrichment pipeline, leads recientes
- **Leads `/leads`** — tabla filtrable/paginada, edición de campos, eliminación
- **Jobs `/jobs`** — lanzar collect/crawl/enrich/process con terminal en tiempo real (SSE)
- **Keys `/keys`** — agregar/habilitar/deshabilitar keys, guías de registro por servicio, quotas

---

## Capacidad teórica con 12 cuentas por servicio

| Servicio | Por cuenta | × 12 cuentas | Total/mes |
|----------|------------|--------------|-----------|
| Skrapp.io | 100 | × 12 | 1,200 |
| Snov.io | 50 | × 12 | 600 |
| VoilaNorbert | 50 one-time | × 12 | 600 (único) |
| Hunter.io | 25 | × 12 | 300 |
| Tomba.io | 25 | × 12 | 300 |
| **Total emails/mes** | | | **~3,000** |

---

## Próximos pasos (en orden)

### Paso 1 — Cargar API keys (esta semana)
Registrarse en cada servicio con cada una de las 10-12 cuentas de email disponibles.
Cargar en `http://localhost:8001/keys`.

Orden recomendado (mayor volumen primero):
1. **Skrapp.io** — skrapp.io → Settings → API → copiar token (solo API key)
2. **Snov.io** — snov.io → Integrations → API → Client ID + Client Secret
3. **Hunter.io** — hunter.io → Dashboard → API → copiar key (solo API key)
4. **Tomba.io** — tomba.io → Settings → API Keys → Key + Secret
5. **Apify** — apify.com → Settings → Integrations → Personal API tokens

### Paso 2 — Acumular leads (semanas 1-2)
```bash
# Collect con Apollo (50/mes, ya hay key)
python app.py collect --source apollo --limit 50

# Collect con Apify (carga keys primero)
python app.py collect --source apify --industries distribucion manufactura salud --countries mexico colombia argentina chile peru --limit 500

# Crawl webs para emails directos
python app.py crawl --limit 500 --concurrency 20

# Enriquecer todo con waterfall
python app.py enrich-all --limit 500
```

Objetivo: **500+ leads, 200+ con email** antes de arrancar warm-up.

### Paso 3 — Warm-up de cuentas (semanas 2-4)
- Configurar 2-3 cuentas de email en un servicio de warm-up (Lemwarm, Mailwarm, o Instantly)
- Empezar con 5-10 emails/día por cuenta, escalar 5/día cada semana
- Objetivo: 50-100 emails/día por cuenta a las 4 semanas
- **No enviar cold email hasta completar 2 semanas de warm-up**

### Paso 4 — Primer envío (mes 2)
- Exportar CSV desde `/export/csv` o `python app.py export`
- Importar en Listmonk
- Crear template con variables: `{{ .Attributes.dato }}`, `{{ .Attributes.empresa }}`, etc.
- Segmentar por industria para personalizar el pain_point
- Arrancar con 20-30 emails/día, monitorear open rate y bounce rate

### Paso 5 — Escalar (mes 2+)
- Agregar más cuentas de enrichment según se agoten las quotas
- Resetear quotas el 1 de cada mes: en `/keys` → "Reset quotas mensuales"
- Apuntar a 500 emails enviados/mes como primer milestone

---

## Comandos rápidos de referencia

```bash
# Levantar web app
PORT=8001 python web_app.py

# Ver estado de la DB
python app.py status

# Ver estado de las keys
python app.py keys-status

# Resetear quotas mensuales (hacerlo el 1 de cada mes)
python app.py reset-quotas

# Exportar CSV para Listmonk
python app.py export

# Pipeline completo de enriquecimiento
python app.py enrich-all --limit 500
```

---

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Apollo 50/mes se agota rápido | Usar Apify como fuente principal, Apollo solo para decisores verificados |
| Servicios de enrichment bloquean IPs | Usar diferentes cuentas con distintos emails, no abusar el rate limit |
| Emails rebotan (alta bounce rate) | Verificar con NeverBounce antes de enviar en volumen, empezar lento |
| Warm-up insuficiente → spam | Respetar las 2-4 semanas antes del primer envío en volumen |
| Quotas agotadas a mitad de mes | Monitorear desde `/keys`, distribuir uso entre servicios |
