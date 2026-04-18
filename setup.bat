@echo off
echo Collexia — build-db setup
echo.

if exist .venv (
    echo Virtual env gia presente, skip creazione.
) else (
    echo Creo virtual env...
    python -m venv .venv
)

echo Attivo virtual env...
call .venv\Scripts\activate.bat

echo Installo dipendenze...
pip install -r requirements.txt

if not exist .env (
    echo Copio .env.example in .env...
    copy .env.example .env
    echo Apri .env e aggiungi la TCG_API_KEY se vuoi un rate limit piu alto.
) else (
    echo .env gia presente, skip.
)

echo.
echo Setup completato.
echo.
echo Prossimi passi:
echo   1. Apri .env e controlla i valori
echo   2. python dex\build_dex_db.py --limit 20
echo   3. python cards\build_cards_db.py --limit 5
echo   4. python viewer\viewer.py
echo.
pause
