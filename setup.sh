#!/bin/bash
set -e

echo "Collexia — build-db setup"
echo ""

if [ -d ".venv" ]; then
    echo "Virtual env già presente, skip creazione."
else
    echo "Creo virtual env..."
    python3 -m venv .venv
fi

echo "Attivo virtual env..."
source .venv/bin/activate

echo "Installo dipendenze..."
pip install -r requirements.txt

if [ ! -f ".env" ]; then
    echo "Copio .env.example in .env..."
    cp .env.example .env
    echo "Apri .env e aggiungi TCG_API_KEY se vuoi un rate limit più alto."
else
    echo ".env già presente, skip."
fi

echo ""
echo "Setup completato."
echo ""
echo "Prossimi passi:"
echo "  1. Apri .env e controlla i valori"
echo "  2. python dex/build_dex_db.py --limit 20"
echo "  3. python cards/build_cards_db.py --limit 5"
echo "  4. python viewer/viewer.py"
echo ""
