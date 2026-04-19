"""
cards/build_cards_db.py
=======================
Genera output/cards.db.

Il DB salva SEMPRE gli URL originali delle immagini.
I percorsi locali vengono popolati solo se si usa --download-images.
L'app usa il percorso locale se disponibile, altrimenti l'URL.

Tabelle:
  - sets    → tutti i set pubblicati
  - cards   → tutte le carte di ogni set

Usage:
  python cards/build_cards_db.py                        # Solo dati + URL
  python cards/build_cards_db.py --download-images      # + immagini small locali
  python cards/build_cards_db.py --download-images --large  # + anche large
  python cards/build_cards_db.py --limit 5              # Solo i primi N set (test)
  python cards/build_cards_db.py --reset                # Cancella e ricostruisce
  python cards/build_cards_db.py --no-cache             # Ignora cache JSON

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
CACHE_DIR = ROOT / "cache" / "cards"
DB_PATH   = OUTPUT / "cards.db"
IMG_ROOT  = OUTPUT / "images" / "cards"
API_BASE  = "https://api.pokemontcg.io/v2"
DELAY     = float(os.getenv("CARDS_REQUEST_DELAY", "0.1"))
API_KEY   = os.getenv("TCG_API_KEY", "")

# ── Graceful shutdown ─────────────────────────────────────────────────────────

_stop = False

def _on_signal(sig, frame):
    global _stop
    _stop = True

signal.signal(signal.SIGTERM, _on_signal)

# ── Schema ────────────────────────────────────────────────────────────────────
# Ogni immagine ha due colonne:
#   image_*      → percorso locale relativo a output/  (NULL se non scaricato)
#   image_*_url  → URL originale                       (sempre presente)

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
    id              TEXT PRIMARY KEY,
    set_id          TEXT NOT NULL,
    number          TEXT NOT NULL,
    name            TEXT NOT NULL,
    rarity          TEXT,
    supertype       TEXT,
    subtype         TEXT,
    type1           TEXT,
    hp              INTEGER,
    artist          TEXT,
    image_small     TEXT,
    image_small_url TEXT,
    image_large     TEXT,
    image_large_url TEXT,
    FOREIGN KEY (set_id) REFERENCES sets(id)
);

CREATE INDEX IF NOT EXISTS idx_cards_set    ON cards(set_id);
CREATE INDEX IF NOT EXISTS idx_cards_name   ON cards(name);
CREATE INDEX IF NOT EXISTS idx_cards_rarity ON cards(rarity);
"""

# ── Helpers API ───────────────────────────────────────────────────────────────

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
    results, page = [], 1
    while True:
        data  = fetch(f"{API_BASE}/cards",
                      params={"q": f"set.id:{set_id}", "pageSize": 250, "page": page},
                      use_cache=use_cache)
        batch = data.get("data", [])
        results.extend(batch)
        if len(results) >= data.get("totalCount", 0) or not batch:
            break
        page += 1
    return results

# ── Helpers immagini ──────────────────────────────────────────────────────────

def download_image(url: str, dest: Path) -> bool:
    """Scarica un'immagine. Salta se già presente."""
    if not url or dest.exists():
        return False
    try:
        time.sleep(DELAY)
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        return True
    except Exception as e:
        tqdm.write(f"  img error {dest.name}: {e}")
        return False


def card_img_path(size: str, card_id: str) -> Path:
    return IMG_ROOT / size / f"{safe_filename(card_id)}.jpg"


def card_img_rel(size: str, card_id: str) -> str:
    return f"images/cards/{size}/{safe_filename(card_id)}.jpg"

# ── Riepilogo ─────────────────────────────────────────────────────────────────

def print_summary(sets_ok, cards_ok, imgs_ok, errors,
                  download_images, large, interrupted):
    status = "INTERROTTO" if interrupted else "COMPLETATO"
    print("\n" + "─" * 50)
    print(f"  CARDS DB {status}")
    print("─" * 50)
    print(f"  Output     : {DB_PATH}")
    print(f"  Set        : {sets_ok}")
    print(f"  Carte      : {cards_ok}")
    if download_images:
        sizes = "small + large" if large else "small"
        print(f"  Immagini   : {imgs_ok} scaricate ({sizes}) in {IMG_ROOT}")
    else:
        print(f"  Immagini   : solo URL salvati (usa --download-images per scaricare)")
    print(f"  Errori     : {len(errors)}")
    if errors:
        for e in errors:
            print(f"    {e}")
    if interrupted:
        print("\n  Il DB è consistente — riprendi senza --reset.")
    print("─" * 50 + "\n")

# ── Build ─────────────────────────────────────────────────────────────────────

def build(use_cache: bool = True, reset: bool = False, limit: int = None,
          download_images: bool = False, large: bool = False):

    global _stop

    OUTPUT.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if download_images:
        (IMG_ROOT / "small").mkdir(parents=True, exist_ok=True)
        if large:
            (IMG_ROOT / "large").mkdir(parents=True, exist_ok=True)

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

    sets_ok = cards_ok = imgs_ok = 0
    errors: list[str] = []

    try:
        print("\n[1/2] Fetching lista set...")
        data     = fetch(f"{API_BASE}/sets", params={"pageSize": 250}, use_cache=use_cache)
        all_sets = sorted(data.get("data", []), key=lambda s: s.get("releaseDate", ""))
        if limit:
            all_sets = all_sets[:limit]
            print(f"      Modalità test: {limit} set")
        print(f"      {len(all_sets)} set trovati\n")

        print("[2/2] Build set, carte" +
              (" e immagini..." if download_images else " e URL..."))

        for s in tqdm(all_sets, desc="Set", unit="set", ncols=80):
            if _stop:
                tqdm.write("\n  Stop richiesto — concludo il set corrente...")
                break

            try:
                cur.execute(
                    "INSERT OR REPLACE INTO sets VALUES (?,?,?,?,?,?,?,?)",
                    (s["id"], s["name"], s.get("series"),
                     s.get("printedTotal"), s.get("total"),
                     s.get("releaseDate"),
                     s.get("images", {}).get("logo"),
                     s.get("images", {}).get("symbol")),
                )
                sets_ok += 1

                for card in fetch_set_cards(s["id"], use_cache):
                    try:
                        types    = card.get("types", [])
                        subtypes = card.get("subtypes", [])
                        hp_raw   = card.get("hp")
                        cid      = card["id"]

                        # URL originali — salvati sempre
                        url_small = card.get("images", {}).get("small")
                        url_large = card.get("images", {}).get("large")

                        # Percorsi locali — popolati solo se si scarica
                        local_small = local_large = None

                        if download_images:
                            if url_small:
                                p = card_img_path("small", cid)
                                imgs_ok += download_image(url_small, p)
                                if p.exists():
                                    local_small = card_img_rel("small", cid)

                            if large and url_large:
                                p = card_img_path("large", cid)
                                imgs_ok += download_image(url_large, p)
                                if p.exists():
                                    local_large = card_img_rel("large", cid)

                        cur.execute(
                            """INSERT OR REPLACE INTO cards
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                cid, s["id"], card.get("number", ""), card["name"],
                                card.get("rarity"), card.get("supertype"),
                                subtypes[0] if subtypes else None,
                                types[0]    if types    else None,
                                int(hp_raw) if hp_raw and str(hp_raw).isdigit() else None,
                                card.get("artist"),
                                local_small, url_small,
                                local_large, url_large,
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

    except KeyboardInterrupt:
        _stop = True
        print("\n  Ctrl+C ricevuto.")

    finally:
        try:
            conn.commit()
        except Exception:
            pass
        conn.close()
        print_summary(sets_ok, cards_ok, imgs_ok, errors,
                      download_images, large, _stop)

    return not _stop


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Build cards.db")
    p.add_argument("--reset",           action="store_true", help="Cancella e ricostruisce")
    p.add_argument("--no-cache",        action="store_true", help="Ignora cache JSON")
    p.add_argument("--download-images", action="store_true",
                   help="Scarica le immagini in locale (default: solo URL)")
    p.add_argument("--large",           action="store_true",
                   help="Con --download-images, scarica anche le large (centinaia di MB)")
    p.add_argument("--limit",           type=int, default=None, metavar="N",
                   help="Solo i primi N set (test)")
    a = p.parse_args()
    ok = build(use_cache=not a.no_cache, reset=a.reset, limit=a.limit,
               download_images=a.download_images, large=a.large)
    sys.exit(0 if ok else 1)