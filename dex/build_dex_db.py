"""
dex/build_dex_db.py
===================
Genera output/dex.db.

Il DB salva SEMPRE gli URL originali delle immagini.
I percorsi locali vengono popolati solo se si usa --download-images.
L'app usa il percorso locale se disponibile, altrimenti l'URL.

Tabelle:
  - generations  → generazioni di gioco
  - games        → titoli principali della serie
  - types        → tipi elementali
  - species      → una riga per specie (es. #006)
  - creatures    → una riga per forma/variante (es. #006 forma mega-x)
  - game_species → quali specie appaiono in quale gioco (da pokedex regionale)

Usage:
  python dex/build_dex_db.py                        # Solo dati + URL
  python dex/build_dex_db.py --download-images      # Dati + URL + immagini locali
  python dex/build_dex_db.py --limit 20             # Solo i primi N (test)
  python dex/build_dex_db.py --reset                # Cancella e ricostruisce
  python dex/build_dex_db.py --no-cache             # Ignora cache JSON

Ctrl+C o chiusura terminale → uscita pulita, DB sempre consistente.
"""

import re
import os
import sys
import signal
import sqlite3
import requests
import json
import time
import argparse
from pathlib import Path
from tqdm import tqdm
from dotenv import load_dotenv

# ── Env ───────────────────────────────────────────────────────────────────────
load_dotenv()

ROOT      = Path(__file__).parent.parent
OUTPUT    = ROOT / "output"
CACHE_DIR = ROOT / "cache" / "dex"
DB_PATH   = OUTPUT / "dex.db"
IMG_ROOT  = OUTPUT / "images" / "dex"
API_BASE  = "https://pokeapi.co/api/v2"
DELAY     = float(os.getenv("DEX_REQUEST_DELAY", "0.05"))

# ── Graceful shutdown ─────────────────────────────────────────────────────────

_stop = False

def _on_signal(sig, frame):
    global _stop
    _stop = True

signal.signal(signal.SIGTERM, _on_signal)

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
    id                      INTEGER PRIMARY KEY,
    species_id              INTEGER NOT NULL,
    name                    TEXT    NOT NULL,
    form_name               TEXT,
    form_type               TEXT    NOT NULL DEFAULT 'base',
    is_default              INTEGER DEFAULT 1,
    type1                   TEXT,
    type2                   TEXT,
    sprite_front            TEXT,
    sprite_front_url        TEXT,
    sprite_front_shiny      TEXT,
    sprite_front_shiny_url  TEXT,
    sprite_official         TEXT,
    sprite_official_url     TEXT,
    FOREIGN KEY (species_id) REFERENCES species(id)
);

CREATE TABLE IF NOT EXISTS game_species (
    game_id    INTEGER NOT NULL,
    species_id INTEGER NOT NULL,
    PRIMARY KEY (game_id, species_id),
    FOREIGN KEY (game_id)    REFERENCES games(id),
    FOREIGN KEY (species_id) REFERENCES species(id)
);

CREATE INDEX IF NOT EXISTS idx_creatures_species  ON creatures(species_id);
CREATE INDEX IF NOT EXISTS idx_species_generation ON species(generation_id);
CREATE INDEX IF NOT EXISTS idx_game_species_game  ON game_species(game_id);
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

# ── Mappa gioco → pokédex regionali PokeAPI ───────────────────────────────────
#
# Ogni gioco può avere uno o più pokédex regionali su PokeAPI.
# Per X/Y ci sono 3 pokédex separati (central, coastal, mountain).
# Per Sword/Shield includiamo i DLC (isle-of-armor, crown-tundra).
# Per Scarlet/Violet includiamo i DLC (kitakami, blueberry).
# FireRed/LeafGreen usano il pokédex di Kanto ma con accesso a Johto post-game:
#   usiamo "kanto" che copre i 151 base; il post-game Johto
#   è coperto da chi seleziona entrambi i giochi.

GAME_POKEDEX_MAP: dict[int, list[str]] = {
    1:  ["kanto"],                                          # Red
    2:  ["kanto"],                                          # Blue
    3:  ["kanto"],                                          # Yellow
    4:  ["original-johto"],                                 # Gold
    5:  ["original-johto"],                                 # Silver
    6:  ["original-johto"],                                 # Crystal
    7:  ["hoenn"],                                          # Ruby
    8:  ["hoenn"],                                          # Sapphire
    9:  ["kanto"],                                          # FireRed
    10: ["kanto"],                                          # LeafGreen
    11: ["hoenn"],                                          # Emerald
    12: ["original-sinnoh"],                                # Diamond
    13: ["original-sinnoh"],                                # Pearl
    14: ["extended-sinnoh"],                                # Platinum (più specie di D/P)
    15: ["updated-johto"],                                  # HeartGold
    16: ["updated-johto"],                                  # SoulSilver
    17: ["original-unova"],                                 # Black
    18: ["original-unova"],                                 # White
    19: ["updated-unova"],                                  # Black 2
    20: ["updated-unova"],                                  # White 2
    21: ["kalos-central", "kalos-coastal", "kalos-mountain"], # X
    22: ["kalos-central", "kalos-coastal", "kalos-mountain"], # Y
    23: ["updated-hoenn"],                                  # Omega Ruby
    24: ["updated-hoenn"],                                  # Alpha Sapphire
    25: ["original-alola"],                                 # Sun
    26: ["original-alola"],                                 # Moon
    27: ["updated-alola"],                                  # Ultra Sun
    28: ["updated-alola"],                                  # Ultra Moon
    29: ["letsgo-kanto"],                                   # Let's Go Pikachu
    30: ["letsgo-kanto"],                                   # Let's Go Eevee
    31: ["galar", "isle-of-armor", "crown-tundra"],         # Sword (+ DLC)
    32: ["galar", "isle-of-armor", "crown-tundra"],         # Shield (+ DLC)
    33: ["original-sinnoh"],                                # Brilliant Diamond
    34: ["original-sinnoh"],                                # Shining Pearl
    35: ["hisui"],                                          # Legends: Arceus
    36: ["paldea", "kitakami", "blueberry"],                # Scarlet (+ DLC)
    37: ["paldea", "kitakami", "blueberry"],                # Violet (+ DLC)
}

# ── Helpers API ───────────────────────────────────────────────────────────────

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

# ── Helpers immagini ──────────────────────────────────────────────────────────

def download_image(url: str, dest: Path) -> bool:
    if not url or dest.exists():
        return False
    try:
        time.sleep(DELAY)
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        return True
    except Exception as e:
        tqdm.write(f"  img error {dest.name}: {e}")
        return False


def img_local_path(subfolder: str, creature_id: int) -> Path:
    return IMG_ROOT / subfolder / f"{creature_id}.png"


def img_local_rel(subfolder: str, creature_id: int) -> str:
    return f"images/dex/{subfolder}/{creature_id}.png"

# ── Form classifier ───────────────────────────────────────────────────────────

def classify_form(form_name: str, is_default: bool) -> str:
    if not form_name or is_default:
        return "base"
    n = form_name.lower()
    if "mega" in n:                               return "mega"
    if "gmax" in n or "gigantamax" in n:          return "gmax"
    if any(x in n for x in ("alola", "alolan")):  return "regional"
    if any(x in n for x in ("galar", "galarian")): return "regional"
    if any(x in n for x in ("hisui", "hisuian")):  return "regional"
    if any(x in n for x in ("paldea", "paldean")): return "regional"
    return "other"

# ── Riepilogo ─────────────────────────────────────────────────────────────────

def print_summary(species_ok, entries_ok, game_species_ok, imgs_ok,
                  errors, download_images, interrupted):
    status = "INTERROTTO" if interrupted else "COMPLETATO"
    print("\n" + "─" * 50)
    print(f"  DEX DB {status}")
    print("─" * 50)
    print(f"  Output          : {DB_PATH}")
    print(f"  Specie          : {species_ok}")
    print(f"  Varianti        : {entries_ok}")
    print(f"  Mapping giochi  : {game_species_ok} righe in game_species")
    if download_images:
        print(f"  Immagini        : {imgs_ok} scaricate in {IMG_ROOT}")
    else:
        print(f"  Immagini        : solo URL salvati (usa --download-images)")
    print(f"  Errori          : {len(errors)}")
    if errors:
        for e in errors:
            print(f"    {e}")
    if interrupted:
        print("\n  Il DB è consistente — riprendi senza --reset.")
    print("─" * 50 + "\n")

# ── Build ─────────────────────────────────────────────────────────────────────

def build(use_cache: bool = True, reset: bool = False,
          limit: int = None, download_images: bool = False):

    global _stop

    OUTPUT.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if download_images:
        for sub in ("front", "shiny", "official"):
            (IMG_ROOT / sub).mkdir(parents=True, exist_ok=True)

    if reset and DB_PATH.exists():
        DB_PATH.unlink()
        print("  DB esistente rimosso")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()
    cur.executescript(SCHEMA)
    conn.commit()

    species_ok = entries_ok = game_species_ok = imgs_ok = 0
    errors: list[str] = []

    try:
        # ── Step 1: dati statici ──────────────────────────────────────────────
        print("\n[1/5] Generazioni e giochi...")
        cur.executemany("INSERT OR IGNORE INTO generations VALUES (?,?,?)", GENERATIONS)
        cur.executemany("INSERT OR IGNORE INTO games VALUES (?,?,?,?,?)", GAMES)
        conn.commit()
        print(f"      {len(GENERATIONS)} generazioni,  {len(GAMES)} giochi")

        # ── Step 2: tipi ──────────────────────────────────────────────────────
        print("\n[2/5] Tipi elementali...")
        raw   = fetch(f"{API_BASE}/type?limit=100", use_cache)
        types = [
            (i + 1, t["name"])
            for i, t in enumerate(raw["results"])
            if t["name"] not in ("unknown", "shadow")
        ]
        cur.executemany("INSERT OR IGNORE INTO types VALUES (?,?)", types)
        conn.commit()
        print(f"      {len(types)} tipi")

        # ── Step 3: specie + varianti ─────────────────────────────────────────
        print("\n[3/5] Lista specie...")
        all_species = fetch(f"{API_BASE}/pokemon-species?limit=2000", use_cache)["results"]
        if limit:
            all_species = all_species[:limit]
            print(f"      Modalità test: {limit} entries")
        print(f"      {len(all_species)} specie\n")

        print("[3/5] Build specie e varianti...")
        for item in tqdm(all_species, desc="Specie", unit="sp", ncols=80):
            if _stop:
                tqdm.write("\n  Stop richiesto — concludo l'entry corrente...")
                break

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
                        eid       = entry["id"]

                        raw_name  = entry["name"]
                        form_name = (raw_name.replace(sp["name"] + "-", "", 1)
                                     if raw_name != sp["name"] else "")
                        form_type = classify_form(form_name, variety["is_default"])

                        url_front    = spr.get("front_default")
                        url_shiny    = spr.get("front_shiny")
                        url_official = (spr.get("other", {})
                                           .get("official-artwork", {})
                                           .get("front_default"))

                        local_front = local_shiny = local_official = None

                        if download_images:
                            if url_front:
                                p = img_local_path("front", eid)
                                imgs_ok += download_image(url_front, p)
                                if p.exists():
                                    local_front = img_local_rel("front", eid)
                            if url_shiny:
                                p = img_local_path("shiny", eid)
                                imgs_ok += download_image(url_shiny, p)
                                if p.exists():
                                    local_shiny = img_local_rel("shiny", eid)
                            if url_official:
                                p = img_local_path("official", eid)
                                imgs_ok += download_image(url_official, p)
                                if p.exists():
                                    local_official = img_local_rel("official", eid)

                        cur.execute(
                            """INSERT OR REPLACE INTO creatures
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                eid, sp["id"], entry["name"],
                                form_name or None, form_type,
                                int(variety["is_default"]),
                                type1, type2,
                                local_front,    url_front,
                                local_shiny,    url_shiny,
                                local_official, url_official,
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

        if _stop:
            return False

        # ── Step 4: game_species — chi appare in quale gioco ──────────────────
        print("\n[4/5] Mapping specie per gioco (pokédex regionali)...")

        # Recupera tutti gli species_id presenti nel DB (per filtrare quelli
        # che non abbiamo ancora — es. in modalità --limit)
        known_species = {
            row[0] for row in cur.execute("SELECT id FROM species").fetchall()
        }

        for game_id, pokedex_names in tqdm(
            GAME_POKEDEX_MAP.items(), desc="Giochi", unit="game", ncols=80
        ):
            if _stop:
                break

            species_for_game: set[int] = set()

            for dex_name in pokedex_names:
                try:
                    dex_data = fetch(f"{API_BASE}/pokedex/{dex_name}", use_cache)
                    for entry in dex_data.get("pokemon_entries", []):
                        # L'URL della specie contiene l'ID come ultimo segmento
                        url = entry["pokemon_species"]["url"]
                        species_id = int(url.rstrip("/").split("/")[-1])
                        if species_id in known_species:
                            species_for_game.add(species_id)
                except Exception as e:
                    msg = f"  pokédex '{dex_name}' (game {game_id}): {e}"
                    errors.append(msg)
                    tqdm.write(msg)

            rows = [(game_id, sid) for sid in species_for_game]
            cur.executemany(
                "INSERT OR IGNORE INTO game_species VALUES (?,?)", rows
            )
            game_species_ok += len(rows)
            conn.commit()

        # ── Step 5: indici finali ─────────────────────────────────────────────
        print("\n[5/5] Indici finali...")
        conn.execute("ANALYZE")
        conn.commit()
        print("      Fatto.")

    except KeyboardInterrupt:
        _stop = True
        print("\n  Ctrl+C ricevuto.")

    finally:
        try:
            conn.commit()
        except Exception:
            pass
        conn.close()
        print_summary(species_ok, entries_ok, game_species_ok, imgs_ok,
                      errors, download_images, _stop)

    return not _stop


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Build dex.db")
    p.add_argument("--reset",            action="store_true", help="Cancella e ricostruisce")
    p.add_argument("--no-cache",         action="store_true", help="Ignora cache JSON")
    p.add_argument("--download-images",  action="store_true",
                   help="Scarica le immagini in locale (default: solo URL)")
    p.add_argument("--limit",            type=int, default=None, metavar="N",
                   help="Solo i primi N specie (test)")
    a = p.parse_args()
    ok = build(use_cache=not a.no_cache, reset=a.reset,
               limit=a.limit, download_images=a.download_images)
    sys.exit(0 if ok else 1)