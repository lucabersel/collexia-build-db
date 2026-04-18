# collexia-build-db

Script di build per i database interni di **Collexia**.

Genera i due file SQLite distribuiti con l'app:

| File                | Contenuto                                     |
|---------------------|-----------------------------------------------|
| `output/dex.db`     | Specie, varianti, generazioni, giochi         |
| `output/cards.db`   | Set e carte del gioco di carte collezionabili |

I file in `output/` **vengono committati** — sono gli artefatti che
l'app Collexia legge in locale, senza mai contattare internet.

---

## Struttura del repo

```
collexia-build-db/
├── dex/
│   └── build_dex_db.py       # Genera output/dex.db
├── cards/
│   └── build_cards_db.py     # Genera output/cards.db
├── viewer/
│   └── viewer.py             # Viewer Flask per debug
├── output/
│   ├── dex.db                # Committato
│   └── cards.db              # Committato
├── cache/                    # Ignorato da git (JSON temporanei)
├── .venv/                    # Ignorato da git (virtual env)
├── .env                      # Ignorato da git ← da creare
├── .env.example              # Template committato
├── setup.bat                 # Setup one-click Windows
├── setup.sh                  # Setup one-click Mac/Linux
├── .gitignore
├── README.md
└── requirements.txt
```

---

## Setup

### Windows

```bat
setup.bat
```

### Mac / Linux

```bash
chmod +x setup.sh
./setup.sh
```

Gli script fanno tutto in automatico:
1. Creano il virtual env `.venv`
2. Installano le dipendenze in isolamento
3. Copiano `.env.example` in `.env`

### Setup manuale (alternativa)

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate
# Mac / Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

> **Importante** — ricorda di attivare il virtual env prima di usare
> qualsiasi script: `.venv\Scripts\activate` (Windows)
> o `source .venv/bin/activate` (Mac/Linux).

---

## Configurazione `.env`

Apri il file `.env` creato dal setup e compila i valori:

```env
# Chiave API opzionale — aumenta il rate limit da 1.000 a 10.000 req/giorno
# Registrazione gratuita: https://dev.pokemontcg.io
TCG_API_KEY=

# Delay tra richieste (secondi) — aumenta se ricevi errori 429
DEX_REQUEST_DELAY=0.05
CARDS_REQUEST_DELAY=0.1

# Porta del viewer
VIEWER_PORT=5000
```

Il file `.env` non viene mai committato.

---

## Build dei database

### dex.db

```bash
# Test rapido — solo i primi 20
python dex/build_dex_db.py --limit 20

# Build completo (~20–30 min, prima run)
python dex/build_dex_db.py

# Ricostruisce da zero
python dex/build_dex_db.py --reset

# Ignora la cache su disco
python dex/build_dex_db.py --no-cache
```

### cards.db

```bash
# Test rapido — solo i primi 5 set
python cards/build_cards_db.py --limit 5

# Build completo
python cards/build_cards_db.py

# Ricostruisce da zero
python cards/build_cards_db.py --reset
```

> **Cache** — le risposte API vengono salvate in `cache/dex/` e
> `cache/cards/`. La cache è ignorata da git ma rimane sul disco.
> Le run successive al primo build sono istantanee.

---

## Viewer (debug)

```bash
python viewer/viewer.py
# → http://localhost:5000
```

Il viewer mostra:
- **Dashboard** — statistiche su entrambi i DB
- **Entries** — griglia con sprite, filtri per generazione / tipo / forma
- **Set** — tutti i set con logo, filtro per serie
- **Carte** — browser con filtri rarità e tipo
- **SQL** — terminale SQL diretto su dex.db o cards.db

---

## Commit dopo il build

```bash
git add output/dex.db output/cards.db
git commit -m "chore: rebuild db"
git push
```

---

## Quando rieseguire

| Evento                     | Comando                               |
|----------------------------|---------------------------------------|
| Nuova generazione          | `python dex/build_dex_db.py --reset`  |
| Nuovo set di carte         | `python cards/build_cards_db.py`      |
| Bug nei dati               | Correggi lo script + `--reset`        |

---

## Sorgenti dati

| DB        | API                                    | Auth       |
|-----------|----------------------------------------|------------|
| dex.db    | https://pokeapi.co (pubblica)          | Non serve  |
| cards.db  | https://pokemontcg.io (pubblica)       | Opzionale  |