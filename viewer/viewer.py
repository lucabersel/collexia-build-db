"""
viewer/viewer.py
================
Server Flask locale per esplorare dex.db e cards.db.

Usage:
  python viewer/viewer.py
  python viewer/viewer.py --port 8080

Apri: http://localhost:5000
"""

import sqlite3
import argparse
from pathlib import Path
from flask import Flask, render_template_string, request, g, redirect
from dotenv import load_dotenv
import os

load_dotenv()

ROOT       = Path(__file__).parent.parent
DEX_DB     = ROOT / "output" / "dex.db"
CARDS_DB   = ROOT / "output" / "cards.db"

app = Flask(__name__)

# ─── DB helpers ──────────────────────────────────────────────────────────────

def get_db(path: str):
    key = f"db_{path}"
    if key not in g:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        setattr(g, key, conn)
    return getattr(g, key)

@app.teardown_appcontext
def close_dbs(error):
    for key in list(vars(g)):
        if key.startswith("db_"):
            getattr(g, key).close()

def dex(sql, params=()):
    return get_db(str(DEX_DB)).execute(sql, params).fetchall()

def dex1(sql, params=()):
    return get_db(str(DEX_DB)).execute(sql, params).fetchone()

def cards(sql, params=()):
    return get_db(str(CARDS_DB)).execute(sql, params).fetchall()

def cards1(sql, params=()):
    return get_db(str(CARDS_DB)).execute(sql, params).fetchone()

# ─── UI helpers ──────────────────────────────────────────────────────────────

TYPE_COLORS = {
    "normal":"#A8A878","fire":"#F08030","water":"#6890F0","electric":"#F8D030",
    "grass":"#78C850","ice":"#98D8D8","fighting":"#C03028","poison":"#A040A0",
    "ground":"#E0C068","flying":"#A890F0","psychic":"#F85888","bug":"#A8B820",
    "rock":"#B8A038","ghost":"#705898","dragon":"#7038F8","dark":"#705848",
    "steel":"#B8B8D0","fairy":"#EE99AC",
}

RARITY_COLORS = {
    "Common":           "#888",
    "Uncommon":         "#2a9d8f",
    "Rare":             "#e9c46a",
    "Rare Holo":        "#e9a020",
    "Rare Holo EX":     "#e87040",
    "Rare Holo GX":     "#c050d0",
    "Rare Holo V":      "#5080e0",
    "Rare Holo VMAX":   "#e04060",
    "Rare Holo VSTAR":  "#f0b030",
    "Rare Ultra":       "#e05020",
    "Rare Secret":      "#c0a000",
    "Rare Rainbow":     "#a060d0",
    "Rare Shining":     "#50b050",
    "Amazing Rare":     "#40c0c0",
    "Illustration Rare":"#8060d0",
    "Special Illustration Rare": "#c04090",
    "Hyper Rare":       "#d03050",
    "Promo":            "#3090c0",
}

def tbadge(t):
    c = TYPE_COLORS.get(t, "#aaa")
    return f'<span style="background:{c};color:white;padding:2px 9px;border-radius:20px;font-size:.72rem;font-weight:600;text-transform:capitalize">{t}</span>'

def rbadge(r):
    if not r: return ""
    c = RARITY_COLORS.get(r, "#888")
    return f'<span style="background:{c};color:white;padding:2px 8px;border-radius:6px;font-size:.68rem;font-weight:600">{r}</span>'

def fbadge(ft):
    labels = {"base":"base","mega":"Mega","gmax":"G-Max","regional":"Regionale","other":"Forma"}
    colors = {"base":"#6c757d","mega":"#7b2fbe","gmax":"#e63946","regional":"#2a9d8f","other":"#b5943a"}
    return f'<span style="background:{colors.get(ft,"#aaa")};color:white;padding:1px 7px;border-radius:8px;font-size:.68rem">{labels.get(ft,ft)}</span>'

app.jinja_env.globals.update(tbadge=tbadge, rbadge=rbadge, fbadge=fbadge)

# ─── Template shell ───────────────────────────────────────────────────────────

def shell(content: str, active: str) -> str:
    return f"""<!DOCTYPE html><html lang="it"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Collexia — DB Viewer</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
body{{background:#f5f5f5}}
.navbar{{background:#0d1117!important}}
.navbar-brand,.nav-link{{color:white!important;font-weight:500}}
.nav-link.active{{border-bottom:2px solid #58a6ff}}
.nav-link:hover{{opacity:.8}}
.section-label{{font-size:.65rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;
               color:#8b949e;padding:4px 12px 2px;margin-top:4px}}
.stat-card{{background:white;border:1px solid #dee2e6;border-radius:10px;
           padding:1.2rem;text-align:center}}
.stat-num{{font-size:1.8rem;font-weight:700;color:#0d1117}}
.stat-lbl{{font-size:.82rem;color:#6c757d;margin-top:2px}}
.sprite{{width:64px;height:64px;image-rendering:pixelated}}
.entry-card{{background:white;border:1px solid #dee2e6;border-radius:10px;
            padding:.75rem;text-align:center;transition:box-shadow .15s;cursor:pointer}}
.entry-card:hover{{box-shadow:0 4px 12px rgba(0,0,0,.1)}}
.entry-card a{{text-decoration:none;color:inherit}}
.card-thumb{{background:white;border:1px solid #dee2e6;border-radius:8px;
            padding:.5rem;text-align:center;transition:box-shadow .15s}}
.card-thumb:hover{{box-shadow:0 4px 12px rgba(0,0,0,.12)}}
.card-thumb a{{text-decoration:none;color:inherit}}
.card-img{{width:100%;border-radius:6px;object-fit:contain;height:140px}}
.dex-num{{font-size:.72rem;color:#aaa}}
.entry-name{{font-size:.88rem;font-weight:600;text-transform:capitalize;
            white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.no-img{{height:140px;background:#f1f3f5;border-radius:6px;display:flex;
        align-items:center;justify-content:center;font-size:2rem;color:#ccc}}
.no-sprite{{width:64px;height:64px;background:#f1f3f5;border-radius:8px;
           display:flex;align-items:center;justify-content:center;
           font-size:1.5rem;margin:0 auto;color:#ccc}}
.search-bar{{position:sticky;top:0;z-index:100;background:#f5f5f5;
            padding:.75rem 0;border-bottom:1px solid #dee2e6;margin-bottom:1rem}}
pre{{background:#f1f3f5;border-radius:8px;padding:1rem;font-size:.8rem}}
</style></head><body>
<nav class="navbar navbar-expand-lg mb-4"><div class="container-fluid px-4">
<a class="navbar-brand fw-bold" href="/">Collexia — DB Viewer</a>
<div class="navbar-nav ms-auto flex-row gap-1 align-items-center">
  <div class="section-label" style="color:#8b949e">DEX</div>
  <a class="nav-link px-2 {'active' if active=='home' else ''}" href="/">Dashboard</a>
  <a class="nav-link px-2 {'active' if active=='entries' else ''}" href="/entries">Entries</a>
  <div class="section-label ms-3" style="color:#8b949e">CARDS</div>
  <a class="nav-link px-2 {'active' if active=='sets' else ''}" href="/sets">Set</a>
  <a class="nav-link px-2 {'active' if active=='card-list' else ''}" href="/cards">Carte</a>
  <div class="section-label ms-3" style="color:#8b949e">DEV</div>
  <a class="nav-link px-2 {'active' if active=='debug' else ''}" href="/debug">SQL</a>
</div></div></nav>
<div class="container-fluid px-4 pb-5">{content}</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body></html>"""

# ─── Routes: dashboard ───────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    dex_ok    = DEX_DB.exists()
    cards_ok  = CARDS_DB.exists()

    dex_stats = {}
    if dex_ok:
        dex_stats = {
            "species":   dex1("SELECT COUNT(*) c FROM species")["c"],
            "entries":   dex1("SELECT COUNT(*) c FROM creatures")["c"],
            "legendary": dex1("SELECT COUNT(*) c FROM species WHERE is_legendary=1")["c"],
            "mythical":  dex1("SELECT COUNT(*) c FROM species WHERE is_mythical=1")["c"],
            "mega":      dex1("SELECT COUNT(*) c FROM creatures WHERE form_type='mega'")["c"],
            "gmax":      dex1("SELECT COUNT(*) c FROM creatures WHERE form_type='gmax'")["c"],
            "regional":  dex1("SELECT COUNT(*) c FROM creatures WHERE form_type='regional'")["c"],
        }

    cards_stats = {}
    if cards_ok:
        cards_stats = {
            "sets":   cards1("SELECT COUNT(*) c FROM sets")["c"],
            "cards":  cards1("SELECT COUNT(*) c FROM cards")["c"],
            "common": cards1("SELECT COUNT(*) c FROM cards WHERE rarity='Common'")["c"],
            "rare":   cards1("SELECT COUNT(*) c FROM cards WHERE rarity LIKE 'Rare%'")["c"],
        }

    gen_stats = dex("SELECT g.name, g.region, COUNT(DISTINCT s.id) sc, COUNT(c.id) ec FROM generations g LEFT JOIN species s ON s.generation_id=g.id LEFT JOIN creatures c ON c.species_id=s.id GROUP BY g.id ORDER BY g.id") if dex_ok else []

    t = render_template_string("""
<h4 class="mb-4 fw-bold">Dashboard</h4>

{% if not dex_ok and not cards_ok %}
<div class="alert alert-warning">
  Nessun DB trovato in <code>output/</code>.
  Esegui <code>python dex/build_dex_db.py --limit 20</code> per iniziare.
</div>
{% endif %}

{% if dex_ok %}
<h5 class="mb-3 text-muted fw-normal" style="font-size:.9rem;text-transform:uppercase;letter-spacing:.05em">Dex DB</h5>
<div class="row g-3 mb-4">
  <div class="col-6 col-md-2"><div class="stat-card"><div class="stat-num">{{d.species}}</div><div class="stat-lbl">Specie</div></div></div>
  <div class="col-6 col-md-2"><div class="stat-card"><div class="stat-num">{{d.entries}}</div><div class="stat-lbl">Entries</div></div></div>
  <div class="col-6 col-md-2"><div class="stat-card"><div class="stat-num" style="color:#f8d030">{{d.legendary}}</div><div class="stat-lbl">Leggendari</div></div></div>
  <div class="col-6 col-md-2"><div class="stat-card"><div class="stat-num" style="color:#f85888">{{d.mythical}}</div><div class="stat-lbl">Mitici</div></div></div>
  <div class="col-6 col-md-2"><div class="stat-card"><div class="stat-num" style="color:#7b2fbe">{{d.mega}}</div><div class="stat-lbl">Mega</div></div></div>
  <div class="col-6 col-md-2"><div class="stat-card"><div class="stat-num" style="color:#2a9d8f">{{d.regional}}</div><div class="stat-lbl">Regionali</div></div></div>
</div>
<div class="table-responsive mb-5">
<table class="table table-bordered table-hover bg-white rounded" style="font-size:.88rem">
<thead class="table-dark"><tr><th>Generazione</th><th>Regione</th><th class="text-center">Specie</th><th class="text-center">Entries totali</th><th></th></tr></thead>
<tbody>
{% for g in gs %}<tr>
  <td class="fw-semibold">{{g.name}}</td><td>{{g.region}}</td>
  <td class="text-center">{{g.sc}}</td><td class="text-center">{{g.ec}}</td>
  <td><a href="/entries?gen={{loop.index}}" class="btn btn-sm btn-outline-dark">Vedi</a></td>
</tr>{% endfor %}
</tbody></table></div>
{% endif %}

{% if cards_ok %}
<h5 class="mb-3 text-muted fw-normal" style="font-size:.9rem;text-transform:uppercase;letter-spacing:.05em">Cards DB</h5>
<div class="row g-3 mb-4">
  <div class="col-6 col-md-3"><div class="stat-card"><div class="stat-num">{{c.sets}}</div><div class="stat-lbl">Set</div></div></div>
  <div class="col-6 col-md-3"><div class="stat-card"><div class="stat-num">{{c.cards}}</div><div class="stat-lbl">Carte totali</div></div></div>
  <div class="col-6 col-md-3"><div class="stat-card"><div class="stat-num" style="color:#888">{{c.common}}</div><div class="stat-lbl">Common</div></div></div>
  <div class="col-6 col-md-3"><div class="stat-card"><div class="stat-num" style="color:#e9a020">{{c.rare}}</div><div class="stat-lbl">Rare (tutte)</div></div></div>
</div>
{% endif %}
""", dex_ok=dex_ok, cards_ok=cards_ok, d=dex_stats, c=cards_stats, gs=gen_stats)
    return shell(t, "home")

# ─── Routes: dex entries ─────────────────────────────────────────────────────

@app.route("/entries")
def entries_list():
    if not DEX_DB.exists():
        return redirect("/")

    search  = request.args.get("q","").strip()
    gen_f   = request.args.get("gen","")
    type_f  = request.args.get("type","")
    form_f  = request.args.get("form","")
    page    = max(1, int(request.args.get("page",1)))
    per_page= 60

    conds, params = [], []
    if search:
        conds.append("(c.name LIKE ? OR CAST(s.id AS TEXT) LIKE ?)")
        params += [f"%{search}%", f"%{search}%"]
    if gen_f:
        conds.append("s.generation_id=?"); params.append(int(gen_f))
    if type_f:
        conds.append("(c.type1=? OR c.type2=?)"); params += [type_f, type_f]
    if form_f:
        conds.append("c.form_type=?"); params.append(form_f)

    where  = ("WHERE " + " AND ".join(conds)) if conds else ""
    total  = dex1(f"SELECT COUNT(*) c FROM creatures c JOIN species s ON c.species_id=s.id {where}", tuple(params))["c"]
    rows   = dex(f"""SELECT c.id, c.name, c.form_type, c.type1, c.type2,
                            c.sprite_front, s.id AS dn, s.is_legendary, s.is_mythical
                     FROM creatures c JOIN species s ON c.species_id=s.id
                     {where}
                     ORDER BY s.id, c.is_default DESC, c.id
                     LIMIT ? OFFSET ?""",
                 tuple(params) + (per_page, (page-1)*per_page))
    tl  = dex("SELECT name FROM types ORDER BY name")
    gl  = dex("SELECT id, name FROM generations ORDER BY id")
    tp  = max(1,(total+per_page-1)//per_page)

    t = render_template_string("""
<div class="search-bar">
<form method="get" class="row g-2 align-items-center">
  <div class="col-12 col-md-3"><input name="q" class="form-control" placeholder="Nome o numero..." value="{{q}}"></div>
  <div class="col-6 col-md-2"><select name="gen" class="form-select"><option value="">Tutte le gen</option>
    {% for g in gl %}<option value="{{g.id}}" {%if gf==g.id|string%}selected{%endif%}>Gen {{g.id}}</option>{% endfor %}
  </select></div>
  <div class="col-6 col-md-2"><select name="type" class="form-select"><option value="">Tutti i tipi</option>
    {% for t in tl %}<option value="{{t.name}}" {%if tf==t.name%}selected{%endif%}>{{t.name|capitalize}}</option>{% endfor %}
  </select></div>
  <div class="col-6 col-md-2"><select name="form" class="form-select"><option value="">Tutte le forme</option>
    <option value="base" {%if ff=='base'%}selected{%endif%}>Base</option>
    <option value="mega" {%if ff=='mega'%}selected{%endif%}>Mega</option>
    <option value="gmax" {%if ff=='gmax'%}selected{%endif%}>G-Max</option>
    <option value="regional" {%if ff=='regional'%}selected{%endif%}>Regionale</option>
    <option value="other" {%if ff=='other'%}selected{%endif%}>Altra</option>
  </select></div>
  <div class="col-auto"><button class="btn btn-dark">Cerca</button></div>
  {%if q or gf or tf or ff%}<div class="col-auto"><a href="/entries" class="btn btn-outline-secondary">Reset</a></div>{%endif%}
</form>
<div class="mt-2 text-muted small">{{total}} entries — pagina {{page}}/{{tp}}</div>
</div>

<div class="row row-cols-2 row-cols-sm-3 row-cols-md-5 row-cols-lg-8 g-2">
{% for e in rows %}<div class="col"><div class="entry-card"><a href="/entries/{{e.id}}">
  <div class="dex-num">#{{"%04d"|format(e.dn)}}</div>
  {%if e.sprite_front%}<img src="{{e.sprite_front}}" class="sprite" onerror="this.style.display='none'">{%else%}<div class="no-sprite">?</div>{%endif%}
  <div class="entry-name mt-1">{{e.name}}</div>
  <div class="mt-1">{{tbadge(e.type1)|safe}}{%if e.type2%} {{tbadge(e.type2)|safe}}{%endif%}</div>
  {%if e.form_type!='base'%}<div class="mt-1">{{fbadge(e.form_type)|safe}}</div>{%endif%}
</a></div></div>{% endfor %}
</div>

{%if tp>1%}<nav class="mt-4"><ul class="pagination justify-content-center">
{% for i in range(1,tp+1) %}
{%if i==page%}<li class="page-item active"><span class="page-link">{{i}}</span></li>
{%elif i<=2 or i>=tp-1 or (i>=page-2 and i<=page+2)%}
<li class="page-item"><a class="page-link" href="?q={{q}}&gen={{gf}}&type={{tf}}&form={{ff}}&page={{i}}">{{i}}</a></li>
{%elif i==3 or i==tp-2%}<li class="page-item disabled"><span class="page-link">…</span></li>{%endif%}
{% endfor %}</ul></nav>{%endif%}
""", rows=rows, q=search, gf=gen_f, tf=type_f, ff=form_f,
     page=page, total=total, tp=tp, tl=tl, gl=gl)
    return shell(t, "entries")


@app.route("/entries/<int:eid>")
def entry_detail(eid):
    e = dex1("""SELECT c.*, s.id AS dn, s.name AS sn, s.is_legendary, s.is_mythical,
                       g.name AS gn, g.region
               FROM creatures c
               JOIN species s ON c.species_id=s.id
               JOIN generations g ON g.id=s.generation_id
               WHERE c.id=?""", (eid,))
    if not e: return "Non trovato", 404

    forms = dex("""SELECT id, name, form_name, form_type, is_default, type1, type2,
                          sprite_front, sprite_front_shiny, sprite_official
                   FROM creatures WHERE species_id=?
                   ORDER BY is_default DESC, id""", (e["species_id"],))

    t = render_template_string("""
<nav aria-label="breadcrumb" class="mb-3">
<ol class="breadcrumb"><li class="breadcrumb-item"><a href="/entries">Entries</a></li>
<li class="breadcrumb-item active">{{e.name}}</li></ol></nav>
<div class="row g-4">
<div class="col-md-4">
  <div class="stat-card">
    {%if e.sprite_official%}<img src="{{e.sprite_official}}" style="width:180px;height:180px;object-fit:contain">
    {%elif e.sprite_front%}<img src="{{e.sprite_front}}" class="sprite" style="width:96px;height:96px">
    {%else%}<div style="width:96px;height:96px;background:#f1f3f5;border-radius:10px;margin:0 auto;display:flex;align-items:center;justify-content:center;font-size:2.5rem;color:#ccc">?</div>{%endif%}
    <h4 class="mt-3 text-capitalize fw-bold">{{e.name}}</h4>
    <div class="text-muted mb-2">#{{"%04d"|format(e.dn)}} — {{e.gn}} ({{e.region}})</div>
    <div class="mb-2">{{tbadge(e.type1)|safe}}{%if e.type2%} {{tbadge(e.type2)|safe}}{%endif%}</div>
    <div>{{fbadge(e.form_type)|safe}}</div>
    {%if e.is_legendary%}<span class="badge bg-warning text-dark mt-2">Leggendario</span>{%endif%}
    {%if e.is_mythical%}<span class="badge bg-danger mt-2">Mitico</span>{%endif%}
  </div>
  {%if e.sprite_front or e.sprite_front_shiny%}
  <div class="mt-3 stat-card">
    <div class="fw-semibold mb-2 small">Sprite</div>
    <div class="d-flex gap-3 justify-content-center">
      {%if e.sprite_front%}<div class="text-center"><img src="{{e.sprite_front}}" class="sprite"><div class="small text-muted">Normale</div></div>{%endif%}
      {%if e.sprite_front_shiny%}<div class="text-center"><img src="{{e.sprite_front_shiny}}" class="sprite"><div class="small text-muted">Shiny</div></div>{%endif%}
    </div>
  </div>{%endif%}
</div>
<div class="col-md-8">
  {%if forms|length>1%}
  <h5 class="fw-bold mb-3">Varianti ({{forms|length}})</h5>
  <div class="row row-cols-3 row-cols-md-4 g-2 mb-4">
  {% for f in forms %}<div class="col"><div class="entry-card {%if f.id==e.id%}border border-2 border-dark{%endif%}">
    <a href="/entries/{{f.id}}">
      {%if f.sprite_front%}<img src="{{f.sprite_front}}" class="sprite">{%else%}<div class="no-sprite">?</div>{%endif%}
      <div class="entry-name mt-1">{{f.form_name or 'base'}}</div>
      <div class="mt-1">{{fbadge(f.form_type)|safe}}</div>
    </a></div></div>{% endfor %}
  </div>{%endif%}
  <h5 class="fw-bold mb-2">Dati raw</h5>
  <pre>{{raw|tojson(indent=2)}}</pre>
</div></div>
""", e=e, forms=forms, raw=dict(e))
    return shell(t, "entries")

# ─── Routes: sets ────────────────────────────────────────────────────────────

@app.route("/sets")
def sets_list():
    if not CARDS_DB.exists():
        return redirect("/")

    series_f = request.args.get("series","")
    search   = request.args.get("q","").strip()

    conds, params = [], []
    if series_f: conds.append("series=?"); params.append(series_f)
    if search:   conds.append("name LIKE ?"); params.append(f"%{search}%")
    where = ("WHERE " + " AND ".join(conds)) if conds else ""

    rows       = cards(f"SELECT * FROM sets {where} ORDER BY release_date DESC", tuple(params))
    all_series = cards("SELECT DISTINCT series FROM sets WHERE series IS NOT NULL ORDER BY series")

    t = render_template_string("""
<div class="search-bar">
<form method="get" class="row g-2 align-items-center">
  <div class="col-12 col-md-4"><input name="q" class="form-control" placeholder="Cerca set..." value="{{q}}"></div>
  <div class="col-6 col-md-3"><select name="series" class="form-select"><option value="">Tutte le serie</option>
    {% for s in series %}<option value="{{s.series}}" {%if sf==s.series%}selected{%endif%}>{{s.series}}</option>{% endfor %}
  </select></div>
  <div class="col-auto"><button class="btn btn-dark">Cerca</button></div>
  {%if q or sf%}<div class="col-auto"><a href="/sets" class="btn btn-outline-secondary">Reset</a></div>{%endif%}
</form>
<div class="mt-2 text-muted small">{{rows|length}} set</div>
</div>

<div class="row row-cols-2 row-cols-sm-3 row-cols-md-4 row-cols-lg-6 g-3">
{% for s in rows %}<div class="col">
<div class="card-thumb"><a href="/sets/{{s.id}}">
  {%if s.logo_url%}<img src="{{s.logo_url}}" style="width:100%;height:60px;object-fit:contain;margin-bottom:6px" onerror="this.style.display='none'">{%endif%}
  <div style="font-size:.85rem;font-weight:600">{{s.name}}</div>
  <div style="font-size:.75rem;color:#888">{{s.series}}</div>
  <div style="font-size:.75rem;color:#aaa">{{s.release_date}} · {{s.printed_total}} carte</div>
</a></div></div>{% endfor %}
</div>
""", rows=rows, q=search, sf=series_f, series=all_series)
    return shell(t, "sets")


@app.route("/sets/<set_id>")
def set_detail(set_id):
    s = cards1("SELECT * FROM sets WHERE id=?", (set_id,))
    if not s: return "Set non trovato", 404

    card_rows = cards("""SELECT * FROM cards WHERE set_id=?
                         ORDER BY CAST(number AS INTEGER), number""", (set_id,))
    t = render_template_string("""
<nav aria-label="breadcrumb" class="mb-3">
<ol class="breadcrumb"><li class="breadcrumb-item"><a href="/sets">Set</a></li>
<li class="breadcrumb-item active">{{s.name}}</li></ol></nav>

<div class="row g-3 mb-4">
  <div class="col-md-3">
    <div class="stat-card">
      {%if s.logo_url%}<img src="{{s.logo_url}}" style="max-width:180px;max-height:80px;object-fit:contain">{%endif%}
      <h5 class="mt-2 fw-bold">{{s.name}}</h5>
      <div class="text-muted small">{{s.series}}</div>
      <div class="text-muted small mt-1">{{s.release_date}}</div>
      <div class="mt-2">
        <span class="badge bg-secondary">{{s.printed_total}} carte stampate</span>
        <span class="badge bg-dark">{{s.total}} totali</span>
      </div>
      {%if s.symbol_url%}<div class="mt-2"><img src="{{s.symbol_url}}" style="width:32px;height:32px;object-fit:contain"></div>{%endif%}
    </div>
  </div>
  <div class="col-md-9">
    <div class="row row-cols-2 row-cols-sm-3 row-cols-md-4 row-cols-lg-5 g-2">
    {% for c in card_rows %}<div class="col"><div class="card-thumb">
      <a href="/cards/{{c.id}}">
        {%if c.image_small%}<img src="{{c.image_small}}" class="card-img" onerror="this.style.display='none'">{%else%}<div class="no-img">?</div>{%endif%}
        <div style="font-size:.75rem;font-weight:600;margin-top:4px">{{c.name}}</div>
        <div style="font-size:.68rem;color:#888">#{{c.number}}</div>
        <div class="mt-1">{{rbadge(c.rarity)|safe}}</div>
      </a></div></div>{% endfor %}
    </div>
  </div>
</div>
""", s=s, card_rows=card_rows)
    return shell(t, "sets")

# ─── Routes: cards ───────────────────────────────────────────────────────────

@app.route("/cards")
def cards_list():
    if not CARDS_DB.exists():
        return redirect("/")

    search   = request.args.get("q","").strip()
    rarity_f = request.args.get("rarity","")
    type_f   = request.args.get("type","")
    page     = max(1, int(request.args.get("page",1)))
    per_page = 48

    conds, params = [], []
    if search:
        conds.append("c.name LIKE ?"); params.append(f"%{search}%")
    if rarity_f:
        conds.append("c.rarity=?"); params.append(rarity_f)
    if type_f:
        conds.append("c.type1=?"); params.append(type_f)

    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    total = cards1(f"SELECT COUNT(*) c FROM cards c {where}", tuple(params))["c"]
    rows  = cards(f"""SELECT c.id, c.name, c.number, c.rarity, c.type1,
                             c.image_small, s.name AS sn
                      FROM cards c JOIN sets s ON s.id=c.set_id
                      {where}
                      ORDER BY s.release_date DESC, CAST(c.number AS INTEGER), c.number
                      LIMIT ? OFFSET ?""",
                  tuple(params) + (per_page, (page-1)*per_page))

    rarities = cards("SELECT DISTINCT rarity FROM cards WHERE rarity IS NOT NULL ORDER BY rarity")
    types    = cards("SELECT DISTINCT type1 FROM cards WHERE type1 IS NOT NULL ORDER BY type1")
    tp       = max(1,(total+per_page-1)//per_page)

    t = render_template_string("""
<div class="search-bar">
<form method="get" class="row g-2 align-items-center">
  <div class="col-12 col-md-3"><input name="q" class="form-control" placeholder="Nome carta..." value="{{q}}"></div>
  <div class="col-6 col-md-2"><select name="rarity" class="form-select"><option value="">Tutte le rarità</option>
    {% for r in rarities %}<option value="{{r.rarity}}" {%if rf==r.rarity%}selected{%endif%}>{{r.rarity}}</option>{% endfor %}
  </select></div>
  <div class="col-6 col-md-2"><select name="type" class="form-select"><option value="">Tutti i tipi</option>
    {% for t in types %}<option value="{{t.type1}}" {%if tf==t.type1%}selected{%endif%}>{{t.type1}}</option>{% endfor %}
  </select></div>
  <div class="col-auto"><button class="btn btn-dark">Cerca</button></div>
  {%if q or rf or tf%}<div class="col-auto"><a href="/cards" class="btn btn-outline-secondary">Reset</a></div>{%endif%}
</form>
<div class="mt-2 text-muted small">{{total}} carte — pagina {{page}}/{{tp}}</div>
</div>

<div class="row row-cols-2 row-cols-sm-3 row-cols-md-5 row-cols-lg-6 g-2">
{% for c in rows %}<div class="col"><div class="card-thumb">
  <a href="/cards/{{c.id}}">
    {%if c.image_small%}<img src="{{c.image_small}}" class="card-img" onerror="this.style.display='none'">{%else%}<div class="no-img">?</div>{%endif%}
    <div style="font-size:.78rem;font-weight:600;margin-top:4px">{{c.name}}</div>
    <div style="font-size:.68rem;color:#888">{{c.sn}} #{{c.number}}</div>
    <div class="mt-1">{{rbadge(c.rarity)|safe}}</div>
    {%if c.type1%}<div class="mt-1">{{tbadge(c.type1)|safe}}</div>{%endif%}
  </a></div></div>{% endfor %}
</div>

{%if tp>1%}<nav class="mt-4"><ul class="pagination justify-content-center">
{% for i in range(1,tp+1) %}
{%if i==page%}<li class="page-item active"><span class="page-link">{{i}}</span></li>
{%elif i<=2 or i>=tp-1 or (i>=page-2 and i<=page+2)%}
<li class="page-item"><a class="page-link" href="?q={{q}}&rarity={{rf}}&type={{tf}}&page={{i}}">{{i}}</a></li>
{%elif i==3 or i==tp-2%}<li class="page-item disabled"><span class="page-link">…</span></li>{%endif%}
{% endfor %}</ul></nav>{%endif%}
""", rows=rows, q=search, rf=rarity_f, tf=type_f,
     page=page, total=total, tp=tp, rarities=rarities, types=types)
    return shell(t, "card-list")


@app.route("/cards/<card_id>")
def card_detail(card_id):
    c = cards1("SELECT c.*, s.name AS sn, s.series, s.release_date, s.symbol_url FROM cards c JOIN sets s ON s.id=c.set_id WHERE c.id=?", (card_id,))
    if not c: return "Carta non trovata", 404

    t = render_template_string("""
<nav aria-label="breadcrumb" class="mb-3">
<ol class="breadcrumb">
  <li class="breadcrumb-item"><a href="/sets">Set</a></li>
  <li class="breadcrumb-item"><a href="/sets/{{c.set_id}}">{{c.sn}}</a></li>
  <li class="breadcrumb-item active">{{c.name}}</li>
</ol></nav>
<div class="row g-4">
<div class="col-md-4 col-lg-3">
  {%if c.image_large%}<img src="{{c.image_large}}" style="width:100%;border-radius:12px" onerror="this.src='{{c.image_small}}'">
  {%elif c.image_small%}<img src="{{c.image_small}}" style="width:100%;border-radius:12px">
  {%else%}<div style="height:300px;background:#f1f3f5;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:3rem;color:#ccc">?</div>{%endif%}
</div>
<div class="col-md-8 col-lg-9">
  <h4 class="fw-bold mb-1">{{c.name}}</h4>
  <div class="text-muted mb-3">{{c.sn}} — #{{c.number}} — {{c.series}} ({{c.release_date}})</div>
  <div class="d-flex flex-wrap gap-2 mb-3">
    {{rbadge(c.rarity)|safe}}
    {%if c.type1%}{{tbadge(c.type1)|safe}}{%endif%}
    {%if c.supertype%}<span class="badge bg-secondary">{{c.supertype}}</span>{%endif%}
    {%if c.subtype%}<span class="badge bg-light text-dark border">{{c.subtype}}</span>{%endif%}
    {%if c.hp%}<span class="badge bg-danger">{{c.hp}} HP</span>{%endif%}
  </div>
  {%if c.artist%}<div class="text-muted small mb-3">Illustrazione: {{c.artist}}</div>{%endif%}
  <h6 class="fw-bold mb-2">Dati raw</h6>
  <pre>{{raw|tojson(indent=2)}}</pre>
</div></div>
""", c=c, raw=dict(c))
    return shell(t, "sets")

# ─── Routes: debug SQL ───────────────────────────────────────────────────────

@app.route("/debug", methods=["GET","POST"])
def debug_sql():
    target  = request.args.get("db","dex")
    sql     = request.form.get("sql","SELECT * FROM creatures LIMIT 10")
    result, error, columns = None, None, []

    if request.method == "POST":
        try:
            db  = get_db(str(DEX_DB if target=="dex" else CARDS_DB))
            cur = db.execute(sql)
            columns = [d[0] for d in cur.description] if cur.description else []
            result  = cur.fetchall()
        except Exception as e:
            error = str(e)

    def tables_of(path):
        if not path.exists(): return []
        return get_db(str(path)).execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()

    dex_tables   = tables_of(DEX_DB)
    cards_tables = tables_of(CARDS_DB)

    t = render_template_string("""
<h4 class="fw-bold mb-4">Debug SQL</h4>
<div class="row g-3">
<div class="col-md-3">
  <div class="stat-card text-start mb-3">
    <div class="fw-semibold mb-1 small">DB attivo</div>
    <div class="btn-group w-100">
      <a href="?db=dex"   class="btn btn-sm {%if db=='dex'%}btn-dark{%else%}btn-outline-dark{%endif%}">dex.db</a>
      <a href="?db=cards" class="btn btn-sm {%if db=='cards'%}btn-dark{%else%}btn-outline-dark{%endif%}">cards.db</a>
    </div>
  </div>
  {%if db=='dex' and dex_t%}
  <div class="stat-card text-start mb-3">
    <div class="fw-semibold mb-1 small">dex.db</div>
    <ul class="list-unstyled mb-0">{% for t in dex_t %}
      <li><a href="#" onclick="setSql('SELECT * FROM {{t.name}} LIMIT 20');return false" class="text-decoration-none">{{t.name}}</a></li>
    {% endfor %}</ul>
  </div>{%endif%}
  {%if db=='cards' and cards_t%}
  <div class="stat-card text-start mb-3">
    <div class="fw-semibold mb-1 small">cards.db</div>
    <ul class="list-unstyled mb-0">{% for t in cards_t %}
      <li><a href="#" onclick="setSql('SELECT * FROM {{t.name}} LIMIT 20');return false" class="text-decoration-none">{{t.name}}</a></li>
    {% endfor %}</ul>
  </div>{%endif%}
  <div class="stat-card text-start">
    <div class="fw-semibold mb-2 small">Query rapide</div>
    <div class="d-grid gap-1">
      <button class="btn btn-sm btn-outline-secondary text-start" onclick="setSql('SELECT form_type, COUNT(*) n FROM creatures GROUP BY form_type ORDER BY n DESC')">Forme dex</button>
      <button class="btn btn-sm btn-outline-secondary text-start" onclick="setSql('SELECT rarity, COUNT(*) n FROM cards GROUP BY rarity ORDER BY n DESC')">Rarità carte</button>
      <button class="btn btn-sm btn-outline-secondary text-start" onclick="setSql('SELECT series, COUNT(*) n FROM sets GROUP BY series ORDER BY n DESC')">Set per serie</button>
      <button class="btn btn-sm btn-outline-secondary text-start" onclick="setSql('SELECT name FROM creatures WHERE sprite_front IS NULL LIMIT 20')">Senza sprite</button>
      <button class="btn btn-sm btn-outline-secondary text-start" onclick="setSql('SELECT type1, COUNT(*) n FROM cards WHERE type1 IS NOT NULL GROUP BY type1 ORDER BY n DESC')">Tipi nelle carte</button>
    </div>
  </div>
</div>
<div class="col-md-9">
  <form method="post">
    <textarea name="sql" id="sql-input" class="form-control font-monospace mb-2"
              rows="5" style="font-size:.85rem">{{sql}}</textarea>
    <button class="btn btn-dark">Esegui su {{db}}.db</button>
  </form>
  {%if error%}<div class="alert alert-danger mt-3">{{error}}</div>{%endif%}
  {%if result is not none%}
  <div class="mt-3 text-muted small mb-1">{{result|length}} righe</div>
  {%if result%}<div class="table-responsive">
  <table class="table table-bordered table-sm table-hover bg-white" style="font-size:.82rem">
    <thead class="table-dark"><tr>{% for c in columns %}<th>{{c}}</th>{% endfor %}</tr></thead>
    <tbody>{% for row in result %}<tr>{% for v in row %}<td>{{v}}</td>{% endfor %}</tr>{% endfor %}</tbody>
  </table></div>
  {%else%}<div class="text-muted mt-2">Nessun risultato.</div>{%endif%}
  {%endif%}
</div></div>
<script>function setSql(q){document.getElementById('sql-input').value=q}</script>
""", sql=sql, result=result, error=error, columns=columns,
     db=target, dex_t=dex_tables, cards_t=cards_tables)
    return shell(t, "debug")

# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Collexia — DB viewer locale")
    p.add_argument("--port", default=int(os.getenv("VIEWER_PORT", "5000")), type=int)
    a = p.parse_args()

    if not DEX_DB.exists() and not CARDS_DB.exists():
        print("\n  Nessun DB trovato in output/")
        print("  Esegui prima: python dex/build_dex_db.py --limit 20\n")

    print(f"\n  Collexia — DB Viewer")
    print(f"  URL  : http://localhost:{a.port}")
    print(f"  Stop : Ctrl+C\n")
    app.run(debug=True, port=a.port)