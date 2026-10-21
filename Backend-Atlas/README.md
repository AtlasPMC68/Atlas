# Backend - Maps Processing API

## Installation

1. Créer l'environnement virtuel :
   python -m venv .venv

2. Activer l'environnement :
   .venv\Scripts\activate

3. Installer les dépendances :
   pip install -r requirements.txt

4. uvicorn app.main:app --reload

# Dans autre terminal :

curl http://localhost:8000/ping

La reponse recue devrait etre "pong"

# Test bd

curl http://localhost:8000/db-test

La reponse reçu devrait être {"db_status":"connected","result":[1]}

# Tests de géoréférencement

L'outil de tests (régression et exploration) est décrit dans
[`dev-docs/dev-test-tool.md`](../dev-docs/dev-test-tool.md). Pour remplacer volontairement
le meilleur résultat (`best`) d'un cas par son dernier run, même moins bon, voir la
section 5 : `scripts/force_promote_georef_best.py`.
