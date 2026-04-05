"""Paso 7: Generar dashboard HTML con Chart.js."""

import json
from collections import Counter

from config import DASHBOARD_OUTPUT, FINAL_OUTPUT


def get_email(lead: dict) -> str:
    if lead.get("email"):
        return lead["email"]
    if lead.get("best_email"):
        return lead["best_email"]
    return ""


def run():
    """Ejecuta el paso 7: generación de dashboard HTML."""
    try:
        with open(FINAL_OUTPUT, encoding="utf-8") as f:
            leads = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("[Dashboard] ERROR: No se encontró leads_final.json.")
        return

    print(f"\n[Dashboard] Generando dashboard para {len(leads)} leads...")

    # --- Calcular datos ---
    with_email = [l for l in leads if get_email(l)]
    without_email = [l for l in leads if not get_email(l)]
    apollo = [l for l in leads if l.get("source") == "apollo"]
    google = [l for l in leads if l.get("source") in ("google_places", "apollo_orgs")]

    real_personalization = sum(
        1 for l in leads if l.get("personalization_type") in ("concrete", "scale")
    )
    pct_personalization = round(real_personalization * 100 / max(len(leads), 1))
    pct_deliverability = round(len(with_email) * 100 / max(len(leads), 1))

    # Por industria
    industries = sorted(set(l.get("industry_category", "N/A") for l in leads))
    apollo_by_ind = Counter(l.get("industry_category", "") for l in apollo)
    google_by_ind = Counter(l.get("industry_category", "") for l in google)

    # Calidad email
    verified = len([l for l in apollo if get_email(l)])
    person = len([l for l in with_email if l.get("email_score", 3) >= 2 and l.get("source") != "apollo"])
    generic = len([l for l in with_email if l.get("email_score", 0) == 1])
    no_email = len(without_email)

    # Por país
    country_counter = Counter(l.get("country", "N/A") for l in leads)
    country_email = Counter(l.get("country", "N/A") for l in with_email)

    # JSON para tabla
    table_data = []
    for l in leads:
        email = get_email(l)
        score = l.get("email_score", 3 if l.get("source") == "apollo" else 0)
        table_data.append({
            "name": l.get("company") or l.get("name", "N/A"),
            "contact": l.get("name") if l.get("source") == "apollo" else l.get("contact_name", ""),
            "email": email,
            "emailScore": score,
            "industry": l.get("industry_category", ""),
            "country": l.get("country", ""),
            "source": l.get("source", ""),
            "personalization": l.get("personalization", ""),
            "pType": l.get("personalization_type", ""),
            "website": l.get("website", ""),
        })

    # --- HTML ---
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FOMO Lead Generation Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f7fa; color: #333; padding: 20px; }}
h1 {{ text-align: center; color: #1a1a2e; margin-bottom: 8px; }}
.subtitle {{ text-align: center; color: #666; margin-bottom: 30px; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 30px; }}
.card {{ background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); text-align: center; }}
.card .value {{ font-size: 2.2em; font-weight: 700; color: #1a1a2e; }}
.card .label {{ font-size: 0.9em; color: #888; margin-top: 4px; }}
.charts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 30px; }}
.chart-box {{ background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
.chart-box h3 {{ margin-bottom: 12px; color: #1a1a2e; }}
@media (max-width: 768px) {{ .charts {{ grid-template-columns: 1fr; }} }}
table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
th {{ background: #1a1a2e; color: #fff; padding: 12px 10px; text-align: left; font-size: 0.85em; cursor: pointer; }}
th:hover {{ background: #2d2d5e; }}
td {{ padding: 10px; border-bottom: 1px solid #eee; font-size: 0.85em; }}
tr:hover {{ background: #f0f4ff; }}
.email-green {{ color: #27ae60; font-weight: 600; }}
.email-yellow {{ color: #f39c12; font-weight: 600; }}
.email-red {{ color: #e74c3c; font-weight: 600; }}
.search-box {{ width: 100%; padding: 12px; border: 2px solid #ddd; border-radius: 8px; font-size: 1em; margin-bottom: 16px; }}
.search-box:focus {{ border-color: #1a1a2e; outline: none; }}
.section {{ margin-bottom: 30px; }}
.section h2 {{ color: #1a1a2e; margin-bottom: 16px; }}
.country-table {{ margin-bottom: 20px; }}
.no-email-section a {{ color: #3498db; text-decoration: none; }}
.no-email-section a:hover {{ text-decoration: underline; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.75em; font-weight: 600; }}
.badge-apollo {{ background: #e8f5e9; color: #2e7d32; }}
.badge-google {{ background: #e3f2fd; color: #1565c0; }}
</style>
</head>
<body>
<h1>FOMO Lead Generation</h1>
<p class="subtitle">Dashboard de leads generados para campañas de cold email</p>

<div class="cards">
  <div class="card"><div class="value">{len(with_email)}</div><div class="label">Con Email</div></div>
  <div class="card"><div class="value">{no_email}</div><div class="label">Sin Email</div></div>
  <div class="card"><div class="value">{pct_personalization}%</div><div class="label">Personalización Real</div></div>
  <div class="card"><div class="value">{pct_deliverability}%</div><div class="label">Deliverability Est.</div></div>
</div>

<div class="charts">
  <div class="chart-box">
    <h3>Leads por Industria</h3>
    <canvas id="industryChart"></canvas>
  </div>
  <div class="chart-box">
    <h3>Calidad de Email</h3>
    <canvas id="emailChart"></canvas>
  </div>
</div>

<div class="section country-table">
  <h2>Por País</h2>
  <table>
    <thead><tr><th>País</th><th>Total</th><th>Con Email</th></tr></thead>
    <tbody>
      {"".join(f'<tr><td>{c}</td><td>{n}</td><td>{country_email.get(c, 0)}</td></tr>' for c, n in country_counter.most_common())}
    </tbody>
  </table>
</div>

<div class="section">
  <h2>Todos los Leads</h2>
  <input type="text" class="search-box" id="searchBox" placeholder="Buscar por empresa, industria, país, email...">
  <table id="leadsTable">
    <thead>
      <tr>
        <th onclick="sortTable(0)">Empresa</th>
        <th onclick="sortTable(1)">Contacto</th>
        <th onclick="sortTable(2)">Email</th>
        <th onclick="sortTable(3)">Industria</th>
        <th onclick="sortTable(4)">País</th>
        <th onclick="sortTable(5)">Fuente</th>
        <th onclick="sortTable(6)">Personalización</th>
      </tr>
    </thead>
    <tbody id="leadsBody"></tbody>
  </table>
</div>

{"" if not without_email else f'''
<div class="section no-email-section">
  <h2>Leads Sin Email ({no_email})</h2>
  <table>
    <thead><tr><th>Empresa</th><th>Website</th><th>Industria</th><th>País</th></tr></thead>
    <tbody>
      {"".join(
          f'<tr><td>{l.get("company") or l.get("name","")}</td>'
          f'<td><a href="{l.get("website","")}" target="_blank">{l.get("website","")}</a></td>'
          f'<td>{l.get("industry_category","")}</td>'
          f'<td>{l.get("country","")}</td></tr>'
          for l in without_email
      )}
    </tbody>
  </table>
</div>
'''}

<script>
const DATA = {json.dumps(table_data, ensure_ascii=False)};

// Render table
const tbody = document.getElementById('leadsBody');
function renderTable(data) {{
  tbody.innerHTML = data.map(l => {{
    let emailClass = l.emailScore >= 2 ? 'email-green' : l.emailScore === 1 ? 'email-yellow' : 'email-red';
    let emailText = l.email || '—';
    let source = l.source === 'apollo'
      ? '<span class="badge badge-apollo">Apollo</span>'
      : '<span class="badge badge-google">Google</span>';
    return `<tr>
      <td>${{l.name}}</td>
      <td>${{l.contact || '—'}}</td>
      <td class="${{emailClass}}">${{emailText}}</td>
      <td>${{l.industry}}</td>
      <td>${{l.country}}</td>
      <td>${{source}}</td>
      <td>${{l.personalization || '—'}}</td>
    </tr>`;
  }}).join('');
}}
renderTable(DATA);

// Search
document.getElementById('searchBox').addEventListener('input', function() {{
  const q = this.value.toLowerCase();
  const filtered = DATA.filter(l =>
    (l.name + l.contact + l.email + l.industry + l.country + l.source + l.personalization)
      .toLowerCase().includes(q)
  );
  renderTable(filtered);
}});

// Sort
let sortDir = {{}};
function sortTable(col) {{
  const keys = ['name','contact','email','industry','country','source','personalization'];
  const key = keys[col];
  sortDir[key] = !sortDir[key];
  DATA.sort((a, b) => {{
    let va = (a[key]||'').toLowerCase(), vb = (b[key]||'').toLowerCase();
    return sortDir[key] ? va.localeCompare(vb) : vb.localeCompare(va);
  }});
  renderTable(DATA);
}}

// Charts
const industries = {json.dumps(industries)};
const apolloData = {json.dumps([apollo_by_ind.get(i, 0) for i in industries])};
const googleData = {json.dumps([google_by_ind.get(i, 0) for i in industries])};

new Chart(document.getElementById('industryChart'), {{
  type: 'bar',
  data: {{
    labels: industries,
    datasets: [
      {{ label: 'Apollo', data: apolloData, backgroundColor: '#27ae60' }},
      {{ label: 'Google Places', data: googleData, backgroundColor: '#3498db' }}
    ]
  }},
  options: {{ responsive: true, scales: {{ x: {{ stacked: false }}, y: {{ beginAtZero: true }} }} }}
}});

new Chart(document.getElementById('emailChart'), {{
  type: 'doughnut',
  data: {{
    labels: ['Verificado (Apollo)', 'Email Persona', 'Email Genérico', 'Sin Email'],
    datasets: [{{
      data: [{verified}, {person}, {generic}, {no_email}],
      backgroundColor: ['#27ae60', '#2ecc71', '#f39c12', '#e74c3c']
    }}]
  }},
  options: {{ responsive: true }}
}});
</script>
</body>
</html>"""

    DASHBOARD_OUTPUT.parent.mkdir(exist_ok=True)
    with open(DASHBOARD_OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[Dashboard] Guardado en {DASHBOARD_OUTPUT}")


if __name__ == "__main__":
    run()
