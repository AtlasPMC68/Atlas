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

Après avoir exécuté un cas de test, `best_report.json` sert de référence complète
pour les métriques de couverture des zones. Un nouveau rapport peut le remplacer
uniquement si aucune métrique ne régresse et qu'au moins une métrique s'améliore.
La promotion remplace aussi les GeoJSON associés.

```bash
python scripts/promote_georef_baseline.py \
   tests/assets/georef/test_cases/<test-id>/<case-id>/config.json \
   tests/assets/georef/test_cases/<test-id>/<case-id>/report.json
```

## Mode Celery local

Redis est le mode par défaut et doit être disponible pour l'API et le worker.
Pour exécuter des tâches en processus, sans Redis ni worker, définir explicitement
`CELERY_MODE=eager`. Ce mode ne doit pas être utilisé avec un worker distant.

```bash
CELERY_MODE=eager pytest tests/test_georef_cases.py -q
```

Docker et GitHub Actions utilisent le mode Redis via `REDIS_URL` ; l'API et le
worker doivent donc démarrer avec le même environnement.
