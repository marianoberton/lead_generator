# FOMO Lead Generation

Sistema de generacion de leads B2B para [FOMO](https://fomologic.com) (agentes IA para empresas medianas en LATAM).

Encuentra empresas, consigue los emails de sus decisores, personaliza un mensaje para cada una, y exporta todo listo para enviar cold email masivo via Listmonk.

---

## El problema que resuelve

Necesitas enviar cold emails a cientos de empresas en LATAM, pero:
- Comprar bases de datos es caro y los emails vienen sucios
- Buscar emails manualmente no escala
- Los servicios de email enrichment tienen free tiers muy chicos (25-100 busquedas/mes)

**La solucion:** Este sistema usa multiples cuentas en multiples servicios de enrichment para multiplicar los free tiers. Con 12 cuentas de email registradas en 5 servicios distintos, conseguis ~2,400 emails/mes gratis.

---

## Como funciona (vista general)

```
PASO 1: CONSEGUIR EMPRESAS          PASO 2: CONSEGUIR EMAILS           PASO 3: ENVIAR
========================          =======================           ============

Apollo API ─────────┐              Crawling de webs ──┐
  (busca por industria,  │              (busca emails en     │
   pais, tamaño)         │              la web de la empresa)│
                         │                                   │
Apify (Google Maps) ─┤── leads.db ──► Hunter.io ──────────┤── emails ──► Personalizar
  (scrapea resultados    │              Snov.io ──────────────┤              mensaje
   de Google Maps)       │              Skrapp.io ─────────── ┤                │
                         │              Tomba.io ──────────── ┤            CSV Listmonk
Google Places API ───┘              VoilaNorbert ────────┘                │
  (API directa, paga)                                              Cold email
                                   ↑ WATERFALL: prueba cada            masivo
                                     servicio en orden hasta
                                     encontrar el email
```

### El waterfall de enrichment

Cuando un lead no tiene email, el sistema prueba cada servicio en orden:

1. **Crawling** — busca emails en la web de la empresa (gratis, ilimitado)
2. **Hunter.io** — 25 busquedas/mes gratis por cuenta
3. **Snov.io** — 50 busquedas/mes gratis por cuenta
4. **Skrapp.io** — 100 busquedas/mes gratis por cuenta
5. **Tomba.io** — 25 busquedas/mes gratis por cuenta
6. **VoilaNorbert** — 50 creditos gratis por cuenta (unico, no se renueva)

Si Hunter encuentra el email, no gasta creditos de Snov ni Skrapp. Si no, pasa al siguiente. Cada busqueda queda marcada en la DB para no repetirla.

---

## La estrategia de multiples cuentas

Cada servicio de enrichment tiene un free tier limitado. Pero si te registras con 12 cuentas de email diferentes, multiplicas la capacidad:

| Servicio | Gratis por cuenta | x12 cuentas | Total/mes |
|----------|-------------------|-------------|-----------|
| Skrapp.io | 100 emails/mes | x12 | **1,200** |
| Snov.io | 50 emails/mes | x12 | **600** |
| Hunter.io | 25 emails/mes | x12 | **300** |
| Tomba.io | 25 emails/mes | x12 | **300** |
| VoilaNorbert | 50 one-time | x12 | 600 (unico) |
| **Total** | | | **~2,400/mes** |

El sistema **rota automaticamente** entre las API keys. Cuando una key alcanza su limite mensual, la desactiva y usa la siguiente. El 1 de cada mes, se resetean todas las quotas.

Las keys se cargan desde la web app en `/keys`, donde hay instrucciones paso a paso para registrarse en cada servicio.

---

## Setup

### Requisitos
- Python 3.11+
- Las dependencias de `requirements.txt`

### Instalacion

```bash
git clone https://github.com/marianoberton/lead_generator.git
cd lead_generator
pip install -r requirements.txt
cp .env.example .env
```

Editar `.env` y agregar al menos `APOLLO_API_KEY` (gratis en apollo.io).

### Levantar la web app

```bash
PORT=8001 python web_app.py
# Abrir http://localhost:8001
```

La web app tiene un **plan de accion** en el dashboard que te guia paso a paso.

---

## Web App

La interfaz web es la forma principal de operar el sistema. Tiene 4 secciones:

### Dashboard (`/`)
Vista general con:
- **Plan de accion** — checklist de lo que falta hacer, con indicador de progreso
- **Estadisticas** — total de leads, % con email, por industria, por pais
- **Pipeline de enrichment** — cuantos emails encontro cada servicio
- **Leads recientes** — ultimos leads agregados con su estado

### Leads (`/leads`)
Tabla con todos los leads en la base de datos:
- Filtros por industria, pais, fuente, estado de email
- Busqueda por nombre de empresa o dominio
- Click en un lead para ver/editar todos sus campos
- Paginacion

### Jobs (`/jobs`)
Ejecutar tareas del pipeline con terminal en tiempo real:
- **Collect** — Apollo, Apify, Google Places
- **Crawl** — buscar emails en las webs de los leads
- **Enrich** — un servicio especifico o waterfall completo
- **Process** — personalizar mensajes + exportar CSV + generar reportes

### Keys (`/keys`)
Gestion de API keys de todos los servicios:
- Ver creditos restantes por servicio
- Agregar/deshabilitar/eliminar keys
- **Guias de registro** — instrucciones paso a paso para conseguir la API key gratuita de cada servicio
- Reset de quotas mensuales

---

## CLI

Todo lo que hace la web se puede hacer por linea de comandos:

```bash
# ── Recolectar empresas ──────────────────────────────────────────
python app.py collect --source apollo --limit 50
python app.py collect --source apify --industries salud distribucion --countries mexico colombia --limit 500
python app.py collect --source google --industries salud --countries mexico --limit 100

# ── Crawlear webs buscando emails ────────────────────────────────
python app.py crawl --limit 500 --concurrency 20

# ── Enriquecer emails ────────────────────────────────────────────
python app.py enrich --source skrapp --limit 200    # un servicio
python app.py enrich-all --limit 500                # waterfall completo

# ── Procesar (personalizar + CSV + reporte + dashboard) ──────────
python app.py process

# ── Estado ───────────────────────────────────────────────────────
python app.py status                                # leads en la DB
python app.py keys-status                           # estado de API keys

# ── Exportar ─────────────────────────────────────────────────────
python app.py export                                # CSV para Listmonk

# ── Quotas ───────────────────────────────────────────────────────
python app.py reset-quotas                          # resetear el 1 de cada mes
```

---

## Estructura del proyecto

```
lead_generator/
├── app.py                  # CLI principal (collect, crawl, enrich, process, etc.)
├── web_app.py              # Web app FastAPI + Jinja2
├── config.py               # Toda la configuracion: industrias, paises, limites, queries
├── leads.db                # Base de datos SQLite (se crea automaticamente)
├── .env                    # API keys (no se commitea)
│
├── src/
│   ├── db.py               # Funciones de base de datos (upsert, stats, enrichment helpers)
│   ├── migrations.py       # Migraciones de schema (agregar columnas nuevas)
│   ├── key_rotator.py      # Rotacion de API keys con quota tracking
│   ├── collector_apollo.py # Recolectar empresas desde Apollo API
│   ├── collector_apify.py  # Recolectar empresas desde Google Maps via Apify
│   ├── collector_google.py # Recolectar empresas desde Google Places API
│   ├── crawler_async.py    # Crawling asincrono de websites
│   ├── enricher_hunter.py  # Buscar emails via Hunter.io
│   ├── enricher_snov.py    # Buscar emails via Snov.io (OAuth2)
│   ├── enricher_skrapp.py  # Buscar emails via Skrapp.io
│   ├── enricher_tomba.py   # Buscar emails via Tomba.io
│   ├── enricher_norbert.py # Buscar emails via VoilaNorbert
│   ├── step1_apollo.py     # Legacy: pipeline original paso 1
│   ├── step2_google.py     # Legacy: pipeline original paso 2
│   ├── step3_crawl.py      # Legacy: pipeline original paso 3
│   ├── step4_personalize.py # Personalizar mensaje por lead
│   ├── step5_csv.py        # Generar CSV para Listmonk
│   ├── step6_report.py     # Generar reporte markdown
│   └── step7_dashboard.py  # Generar dashboard HTML estatico
│
├── templates/              # Templates Jinja2 para la web app
│   ├── base.html           # Layout base (sidebar, header)
│   ├── dashboard.html      # Dashboard con plan de accion
│   ├── leads.html          # Tabla de leads
│   ├── lead_detail.html    # Detalle/edicion de un lead
│   ├── jobs.html           # Ejecutar tareas con terminal
│   └── keys.html           # Gestion de API keys
│
├── leads/                  # Archivos generados (no se commitean)
│   ├── leads_listmonk.csv  # CSV listo para importar en Listmonk
│   ├── leads_no_email.csv  # Empresas donde no se encontro email
│   ├── leads_final.json    # Todos los leads con personalizacion
│   ├── leads_report.md     # Reporte de estadisticas
│   └── dashboard.html      # Dashboard HTML estatico
│
├── PLAN.md                 # Plan de accion con estado de cada fase
├── CLAUDE.md               # Instrucciones para Claude Code
└── requirements.txt        # Dependencias Python
```

---

## Base de datos

SQLite (`leads.db`) con dos tablas:

### Tabla `leads`
Cada fila es una empresa. Campos principales:
- **Empresa:** `domain`, `company`, `website`, `industry`, `country`, `city`, `employees`
- **Contacto:** `contact_name`, `contact_title`, `email`, `email_score`, `email_source`
- **Enrichment:** `hunter_searched`, `snov_searched`, `skrapp_searched`, `tomba_searched`, `norbert_searched` (flags 0/1)
- **Output:** `personalization`, `pain_point`

Deduplicacion por `domain` — si dos fuentes encuentran la misma empresa, se mergean los datos.

### Tabla `api_keys`
Cada fila es una API key de un servicio. Campos:
- `service`, `key_value`, `key_secret`, `active`, `monthly_limit`
- `requests_month`, `requests_total`, `last_used_at`, `error_reason`
- `account_email`, `account_name`, `notes`

El `key_rotator` selecciona la key activa con menos uso, trackea cada request, y desactiva automaticamente las que alcanzan su `monthly_limit`.

---

## Variables de entorno

Las keys se pueden cargar de dos formas:
1. **Archivo `.env`** — se leen al iniciar la app y se insertan en la DB
2. **Web app `/keys`** — formulario para agregar keys manualmente (persistidas en SQLite)

### Formato del `.env`

```bash
# Apollo (requerido para collect)
APOLLO_API_KEY=tu_key_aqui

# Multiples keys del mismo servicio (separadas por coma)
HUNTER_API_KEYS=key1,key2,key3

# O una por linea con sufijo numerico
HUNTER_API_KEY=key_principal
HUNTER_API_KEY_2=key_segunda_cuenta
HUNTER_API_KEY_3=key_tercera_cuenta

# Servicios que necesitan dos credenciales (key:secret)
SNOV_API_KEY=client_id:client_secret
TOMBA_API_KEY=api_key:api_secret

# Otros
SKRAPP_API_KEY=tu_key
NORBERT_API_KEY=tu_token
APIFY_API_KEY=tu_token
PORT=8001
```

---

## Industrias y paises target

### Industrias

| Industria | Fuentes | Descripcion |
|-----------|---------|-------------|
| Distribucion | Apollo + Apify + Google | Mayoristas, logistica, importadoras |
| Manufactura | Apollo + Apify + Google | Fabricas, plantas de produccion, empaques |
| Servicios Profesionales | Apollo + Apify + Google | Consultoras, estudios contables, agencias |
| Salud | Apify + Google | Clinicas privadas, centros medicos, laboratorios |

### Paises LATAM
Mexico, Colombia, Argentina, Chile, Peru, Ecuador, Uruguay, Costa Rica, Panama, Republica Dominicana, Guatemala, Bolivia, Paraguay, El Salvador, Honduras.

---

## Rate limits y protecciones

| Servicio | Limite | Comportamiento |
|----------|--------|----------------|
| Apollo | 5 req/min | Delay de 12s entre requests |
| Google Places | 1 req/s | Delay de 1s |
| Crawling | 1 req/s por dominio | Max 3 paginas por dominio, timeout 10s |
| Enrichers | 1 req/s | Delay configurable en `config.py` |
| Apollo circuit breaker | 3 paginas vacias | Corta si no encuentra leads nuevos |

Todos los timeouts y errores de red se manejan sin romper la ejecucion. Las keys que reciben 401/403 se desactivan automaticamente con el motivo del error.

---

## Flujo recomendado para empezar desde cero

### Semana 1: Setup
1. Clonar el repo e instalar dependencias
2. Conseguir API key de Apollo (gratis en apollo.io)
3. Correr `python app.py collect --source apollo --limit 50` para tener los primeros leads
4. Levantar la web app (`PORT=8001 python web_app.py`) y seguir el plan de accion del dashboard

### Semana 1-2: Cargar API keys
5. Registrarse en Skrapp.io, Hunter.io, Snov.io, Tomba.io con cada una de tus cuentas de email
6. Cargar todas las API keys en `/keys` (la web tiene instrucciones por servicio)
7. Opcionalmente: registrar cuentas en Apify para conseguir mas empresas

### Semana 2: Acumular leads
8. Correr collects para llegar a 500+ leads
9. Correr `python app.py enrich-all --limit 500` para buscar emails con el waterfall
10. Repetir hasta tener 200+ leads con email

### Semana 2-4: Warm-up
11. Configurar las cuentas de email que vas a usar para enviar en un servicio de warm-up
12. Esperar 2-4 semanas antes de enviar cold email real

### Mes 2: Primer envio
13. Exportar CSV desde `/export/csv`
14. Importar en Listmonk
15. Enviar 20-30 emails/dia, monitorear bounces y opens
16. Escalar progresivamente

### Cada mes
17. Resetear quotas en `/keys` → "Reset quotas mensuales"
18. Agregar cuentas nuevas si se necesita mas volumen

---

## Troubleshooting

**"Sin keys disponibles"**
No hay API keys cargadas para ese servicio. Ir a `/keys` y agregar una.

**Apollo devuelve +0 leads en todas las paginas**
Los resultados ya estan en la DB (deduplicacion por dominio). Intentar con otras industrias o paises.

**Enrichment no encuentra emails**
Normal — no todas las empresas tienen emails publicos. El rate tipico es 30-50% de exito. Por eso es importante tener muchos leads en la base.

**Quota agotada a mitad de mes**
El sistema desactiva la key automaticamente. Agregar mas cuentas del mismo servicio en `/keys`.

**Puerto en uso**
Usar otro puerto: `PORT=8002 python web_app.py`

**Error de Unicode en terminal Windows**
Los caracteres especiales (→, ñ) pueden fallar en terminales Windows con encoding cp1252. El sistema ya los reemplaza internamente, pero si aparece algun error, agregar `PYTHONIOENCODING=utf-8` al environment.
