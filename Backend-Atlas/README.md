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

## Baseline de non-régression georef

Après avoir exécuté un cas de test, une baseline peut être promue uniquement si
le nouveau rapport est globalement meilleur : aucune métrique ne régresse et au
moins une métrique s'améliore. La promotion remplace toutes les métriques de la
baseline, y compris les erreurs individuelles des checkpoints.

```bash
python scripts/promote_georef_baseline.py \
   tests/assets/georef/test_cases/<test-id>/<case-id>/config.json \
   tests/assets/georef/test_cases/<test-id>/<case-id>/report.json
```
