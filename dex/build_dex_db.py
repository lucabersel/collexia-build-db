"""
dex/build_dex_db.py
===================
Genera output/dex.db scaricando dati da PokeAPI (https://pokeapi.co).

Tabelle:
  - generations  → generazioni di gioco
  - games        → titoli principali della serie
  - types        → tipi elementali
  - species      → una riga per specie (es. #006)
  - creatures    → una riga per forma/variante (es. #006 forma mega-x)

Usage:
  python dex/build_dex_db.py              # Build con cache
  python dex/build_dex_db.py --reset      # Cancella e ricostruisce
  python dex/build_dex_db.py --no-cache   # Ignora la cache
  python dex/build_dex_db.py --limit 151  # Solo i primi N (test)
"""

import re
import sqlite3
import requests
import json
import time
import argparse
from pathlib import Path
from tqdm import tqdm

ROOT      = Path(__file__).parent.parent
OUTPUT    = ROOT / "output"
CACHE_DIR = ROOT / "cache" / "dex"
DB_PATH   = OUTPUT / "dex.db"
API_BASE  = "https://pokeapi.co/api/v2"
DELAY     = 0.05  # secondi tra richieste — aumenta se ricevi errori 429

# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS generations (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL,
    region  TEXT
);

CREATE TABLE IF NOT EXISTS games (
    id              INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL,
    generation_id   INTEGER NOT NULL,
    platform        TEXT,
    release_year    INTEGER,
    FOREIGN KEY (generation_id) REFERENCES generations(id)
);

CREATE TABLE IF NOT EXISTS types (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS species (
    id              INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL,
    generation_id   INTEGER NOT NULL,
    is_legendary    INTEGER DEFAULT 0,
    is_mythical     INTEGER DEFAULT 0,
    FOREIGN KEY (generation_id) REFERENCES generations(id)
);

CREATE TABLE IF NOT EXISTS creatures (
    id                  INTEGER PRIMARY KEY,
    species_id          INTEGER NOT NULL,
    name                TEXT    NOT NULL,
    form_name           TEXT,
    form_type           TEXT    NOT NULL DEFAULT 'base',
    is_default          INTEGER DEFAULT 1,
    type1               TEXT,
    type2               TEXT,
    sprite_front        TEXT,
    sprite_front_shiny  TEXT,
    sprite_official     TEXT,
    FOREIGN KEY (species_id) REFERENCES species(id)
);

CREATE INDEX IF NOT EXISTS idx_creatures_species ON creatures(species_id);
CREATE INDEX IF NOT EXISTS idx_species_generation ON species(generation_id);
"""

# ── Dati statici ──────────────────────────────────────────────────────────────

GENERATIONS = [
    (1, "Generation I",    "Kanto"),
    (2, "Generation II",   "Johto"),
    (3, "Generation III",  "Hoenn"),
    (4, "Generation IV",   "Sinnoh"),
    (5, "Generation V",    "Unova"),
    (6, "Generation VI",   "Kalos"),
    (7, "Generation VII",  "Alola"),
    (8, "Generation VIII", "Galar"),
    (9, "Generation IX",   "Paldea"),
]

GAMES = [
    (1,  "Red",               1, "Game Boy",         1996),
    (2,  "Blue",              1, "Game Boy",         1996),
    (3,  "Yellow",            1, "Game Boy",         1998),
    (4,  "Gold",              2, "Game Boy Color",   1999),
    (5,  "Silver",            2, "Game Boy Color",   1999),
    (6,  "Crystal",           2, "Game Boy Color",   2000),
    (7,  "Ruby",              3, "Game Boy Advance",  2002),
    (8,  "Sapphire",          3, "Game Boy Advance",  2002),
    (9,  "FireRed",           3, "Game Boy Advance",  2004),
    (10, "LeafGreen",         3, "Game Boy Advance",  2004),
    (11, "Emerald",           3, "Game Boy Advance",  2005),
    (12, "Diamond",           4, "Nintendo DS",      2006),
    (13, "Pearl",             4, "Nintendo DS",      2006),
    (14, "Platinum",          4, "Nintendo DS",      2008),
    (15, "HeartGold",         4, "Nintendo DS",      2009),
    (16, "SoulSilver",        4, "Nintendo DS",      2009),
    (17, "Black",             5, "Nintendo DS",      2010),
    (18, "White",             5, "Nintendo DS",      2010),
    (19, "Black 2",           5, "Nintendo DS",      2012),
    (20, "White 2",           5, "Nintendo DS",      2012),
    (21, "X",                 6, "Nintendo 3DS",     2013),
    (22, "Y",                 6, "Nintendo 3DS",     2013),
    (23, "Omega Ruby",        6, "Nintendo 3DS",     2014),
    (24, "Alpha Sapphire",    6, "Nintendo 3DS",     2014),
    (25, "Sun",               7, "Nintendo 3DS",     2016),
    (26, "Moon",              7, "Nintendo 3DS",     2016),
    (27, "Ultra Sun",         7, "Nintendo 3DS",     2017),
    (28, "Ultra Moon",        7, "Nintendo 3DS",     2017),
    (29, "Let's Go Pikachu",  7, "Nintendo Switch",  2018),
    (30, "Let's Go Eevee",    7, "Nintendo Switch",  2018),
    (31, "Sword",             8, "Nintendo Switch",  2019),
    (32, "Shield",            8, "Nintendo Switch",  2019),
    (33, "Brilliant Diamond", 8, "Nintendo Switch",  2021),
    (34, "Shining Pearl",     8, "Nintendo Switch",  2021),
    (35, "Legends: Arceus",   8, "Nintendo Switch",  2022),
    (36, "Scarlet",           9, "Nintendo Switch",  2022),
    (37, "Violet",            9, "Nintendo Switch",  2022),
]

GEN_MAP = {
    "generation-i": 1,    "generation-ii": 2,   "generation-iii": 3,
    "generation-iv": 4,   "generation-v": 5,    "generation-vi": 6,
    "generation-vii": 7,  "generation-viii": 8, "generation-ix": 9,
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_filename(url: str) -> str:
    key = url.replace(API_BASE, "").strip("/")
    return re.sub(r'[\\/*?:"<>|]', "_", key)


def fetch(url: str, use_cache: bool = True) -> dict:
    cache_file = CACHE_DIR / f"{safe_filename(url)}.json"

    if use_cache and cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    time.sleep(DELAY)
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if use_cache:
        cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    return data


def classify_form(form_name: str, is_default: bool) -> str:
    if not form_name or is_default:
        return "base"
    n = form_name.lower()
    if "mega" in n:                             return "mega"
    if "gmax" in n or "gigantamax" in n:        return "gmax"
    if any(x in n for x in ("alola","alolan")): return "regional"
    if any(x in n for x in ("galar","galarian")):return "regional"
    if any(x in n for x in ("hisui","hisuian")): return "regional"
    if any(x in n for x in ("paldea","paldean")):return "regional"
    return "other"

# ── Build ─────────────────────────────────────────────────────────────────────

def build(use_cache: bool = True, reset: bool = False, limit: int = None):

    OUTPUT.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if reset and DB_PATH.exists():
        DB_PATH.unlink()
        print("  DB esistente rimosso")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()
    cur.executescript(SCHEMA)
    conn.commit()

    print("\n[1/4] Generazioni e giochi...")
    cur.executemany("INSERT OR IGNORE INTO generations VALUES (?,?,?)", GENERATIONS)
    cur.executemany("INSERT OR IGNORE INTO games VALUES (?,?,?,?,?)", GAMES)
    conn.commit()
    print(f"      {len(GENERATIONS)} generazioni,  {len(GAMES)} giochi")

    print("\n[2/4] Tipi elementali...")
    raw   = fetch(f"{API_BASE}/type?limit=100", use_cache)
    types = [
        (i + 1, t["name"])
        for i, t in enumerate(raw["results"])
        if t["name"] not in ("unknown", "shadow")
    ]
    cur.executemany("INSERT OR IGNORE INTO types VALUES (?,?)", types)
    conn.commit()
    print(f"      {len(types)} tipi")

    print("\n[3/4] Lista specie...")
    all_species = fetch(f"{API_BASE}/pokemon-species?limit=2000", use_cache)["results"]
    if limit:
        all_species = all_species[:limit]
        print(f"      Modalità test: {limit} entries")
    print(f"      {len(all_species)} specie\n")

    print("[4/4] Build specie e varianti...")
    species_ok, entries_ok, errors = 0, 0, []

    for item in tqdm(all_species, desc="Specie", unit="sp", ncols=80):
        try:
            sp     = fetch(item["url"], use_cache)
            gen_id = GEN_MAP.get(sp["generation"]["name"], 1)

            cur.execute(
                "INSERT OR REPLACE INTO species VALUES (?,?,?,?,?)",
                (sp["id"], sp["name"], gen_id,
                 int(sp["is_legendary"]), int(sp["is_mythical"])),
            )
            species_ok += 1

            for variety in sp["varieties"]:
                try:
                    entry     = fetch(variety["pokemon"]["url"], use_cache)
                    t         = entry["types"]
                    type1     = t[0]["type"]["name"] if t else None
                    type2     = t[1]["type"]["name"] if len(t) > 1 else None
                    spr       = entry["sprites"]
                    raw_name  = entry["name"]
                    form_name = (raw_name.replace(sp["name"] + "-", "", 1)
                                 if raw_name != sp["name"] else "")
                    form_type = classify_form(form_name, variety["is_default"])

                    cur.execute(
                        "INSERT OR REPLACE INTO creatures VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            entry["id"], sp["id"], entry["name"],
                            form_name or None, form_type,
                            int(variety["is_default"]),
                            type1, type2,
                            spr.get("front_default"),
                            spr.get("front_shiny"),
                            spr.get("other", {})
                               .get("official-artwork", {})
                               .get("front_default"),
                        ),
                    )
                    entries_ok += 1

                except Exception as e:
                    msg = f"  variante '{variety['pokemon']['name']}': {e}"
                    errors.append(msg)
                    tqdm.write(msg)

            conn.commit()

        except Exception as e:
            msg = f"  specie '{item['name']}': {e}"
            errors.append(msg)
            tqdm.write(msg)

    conn.close()

    print("\n" + "─" * 50)
    print("  DEX DB COMPLETATO")
    print("─" * 50)
    print(f"  Output   : {DB_PATH}")
    print(f"  Specie   : {species_ok}")
    print(f"  Varianti : {entries_ok}")
    print(f"  Errori   : {len(errors)}")
    if errors:
        for e in errors: print(f"    {e}")
    print("─" * 50 + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Build dex.db")
    p.add_argument("--reset",    action="store_true", help="Cancella e ricostruisce")
    p.add_argument("--no-cache", action="store_true", help="Ignora la cache")
    p.add_argument("--limit",    type=int, default=None, metavar="N",
                   help="Solo i primi N specie (test)")
    a = p.parse_args()
    build(use_cache=not a.no_cache, reset=a.reset, limit=a.limit)