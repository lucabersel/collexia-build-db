"""
cards/build_cards_db.py
=======================
Genera output/cards.db scaricando dati da TCG API (https://pokemontcg.io).

L'API è gratuita. Con TCG_API_KEY nel .env il limite sale da 1.000 a 10.000 req/giorno.

Tabelle:
  - sets    → tutti i set pubblicati
  - cards   → tutte le carte di ogni set

Usage:
  python cards/build_cards_db.py              # Build completo
  python cards/build_cards_db.py --reset      # Cancella e ricostruisce
  python cards/build_cards_db.py --no-cache   # Ignora la cache
  python cards/build_cards_db.py --limit 5    # Solo i primi N set (test)
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
CACHE_DIR = ROOT / "cache" / "cards"
DB_PATH   = OUTPUT / "cards.db"
API_BASE  = "https://api.pokemontcg.io/v2"
DELAY     = 0.1   # secondi tra richieste — aumenta se ricevi errori 429
API_KEY   = ""    # imposta via --api-key oppure modifica qui

# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS sets (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    series          TEXT,
    printed_total   INTEGER,
    total           INTEGER,
    release_date    TEXT,
    logo_url        TEXT,
    symbol_url      TEXT
);

CREATE TABLE IF NOT EXISTS cards (
    id          TEXT PRIMARY KEY,
    set_id      TEXT NOT NULL,
    number      TEXT NOT NULL,
    name        TEXT NOT NULL,
    rarity      TEXT,
    supertype   TEXT,
    subtype     TEXT,
    type1       TEXT,
    hp          INTEGER,
    artist      TEXT,
    image_small TEXT,
    image_large TEXT,
    FOREIGN KEY (set_id) REFERENCES sets(id)
);

CREATE INDEX IF NOT EXISTS idx_cards_set    ON cards(set_id);
CREATE INDEX IF NOT EXISTS idx_cards_name   ON cards(name);
CREATE INDEX IF NOT EXISTS idx_cards_rarity ON cards(rarity);
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_filename(s: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "_", s)


def fetch(url: str, params: dict = None, use_cache: bool = True) -> dict:
    cache_key  = safe_filename(url + json.dumps(params or {}, sort_keys=True))
    cache_file = CACHE_DIR / f"{cache_key}.json"

    if use_cache and cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    headers = {"X-Api-Key": API_KEY} if API_KEY else {}
    time.sleep(DELAY)
    resp = requests.get(url, params=params, headers=headers, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    if use_cache:
        cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    return data


def fetch_set_cards(set_id: str, use_cache: bool) -> list:
    """Scarica tutte le carte di un set, gestendo la paginazione."""
    results   = []
    page      = 1
    page_size = 250

    while True:
        data  = fetch(
            f"{API_BASE}/cards",
            params={"q": f"set.id:{set_id}", "pageSize": page_size, "page": page},
            use_cache=use_cache,
        )
        batch = data.get("data", [])
        results.extend(batch)

        total = data.get("totalCount", 0)
        if len(results) >= total or not batch:
            break
        page += 1

    return results

# ── Build ─────────────────────────────────────────────────────────────────────

def build(use_cache: bool = True, reset: bool = False, limit: int = None):

    OUTPUT.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not API_KEY:
        print("  Suggerimento: aggiungi TCG_API_KEY nel .env per un rate limit più alto.")

    if reset and DB_PATH.exists():
        DB_PATH.unlink()
        print("  DB esistente rimosso")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()
    cur.executescript(SCHEMA)
    conn.commit()

    print("\n[1/2] Fetching lista set...")
    data     = fetch(f"{API_BASE}/sets", params={"pageSize": 250}, use_cache=use_cache)
    all_sets = sorted(data.get("data", []), key=lambda s: s.get("releaseDate", ""))

    if limit:
        all_sets = all_sets[:limit]
        print(f"      Modalità test: {limit} set")

    print(f"      {len(all_sets)} set trovati\n")

    sets_ok, cards_ok, errors = 0, 0, []

    print("[2/2] Build set e carte...")
    for s in tqdm(all_sets, desc="Set", unit="set", ncols=80):
        try:
            cur.execute(
                "INSERT OR REPLACE INTO sets VALUES (?,?,?,?,?,?,?,?)",
                (
                    s["id"], s["name"],
                    s.get("series"),
                    s.get("printedTotal"),
                    s.get("total"),
                    s.get("releaseDate"),
                    s.get("images", {}).get("logo"),
                    s.get("images", {}).get("symbol"),
                ),
            )
            sets_ok += 1

            for card in fetch_set_cards(s["id"], use_cache):
                try:
                    types    = card.get("types", [])
                    subtypes = card.get("subtypes", [])
                    hp_raw   = card.get("hp")

                    cur.execute(
                        "INSERT OR REPLACE INTO cards VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            card["id"],
                            s["id"],
                            card.get("number", ""),
                            card["name"],
                            card.get("rarity"),
                            card.get("supertype"),
                            subtypes[0] if subtypes else None,
                            types[0]    if types    else None,
                            int(hp_raw) if hp_raw and str(hp_raw).isdigit() else None,
                            card.get("artist"),
                            card.get("images", {}).get("small"),
                            card.get("images", {}).get("large"),
                        ),
                    )
                    cards_ok += 1

                except Exception as e:
                    msg = f"  carta '{card.get('id','?')}': {e}"
                    errors.append(msg)
                    tqdm.write(msg)

            conn.commit()

        except Exception as e:
            msg = f"  set '{s.get('id','?')}': {e}"
            errors.append(msg)
            tqdm.write(msg)

    conn.close()

    print("\n" + "─" * 50)
    print("  CARDS DB COMPLETATO")
    print("─" * 50)
    print(f"  Output  : {DB_PATH}")
    print(f"  Set     : {sets_ok}")
    print(f"  Carte   : {cards_ok}")
    print(f"  Errori  : {len(errors)}")
    if errors:
        for e in errors: print(f"    {e}")
    print("─" * 50 + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Build cards.db")
    p.add_argument("--reset",    action="store_true", help="Cancella e ricostruisce")
    p.add_argument("--no-cache", action="store_true", help="Ignora la cache")
    p.add_argument("--limit",    type=int, default=None, metavar="N",
                   help="Solo i primi N set (test)")
    a = p.parse_args()
    build(use_cache=not a.no_cache, reset=a.reset, limit=a.limit)