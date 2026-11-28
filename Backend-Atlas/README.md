# Backend Atlas

API FastAPI, workers Celery et worker de lecture de texte (Florence-2) d'Atlas.

Le backend se lance avec le reste d'Atlas, dans Docker : voir le [guide de développement](../docs/developpement.md). Le rôle de chaque service est décrit dans l'[architecture](../docs/architecture.md).

| Dossier | Contenu |
|---|---|
| [`app/routers/`](app/routers/) | Points d'entrée de l'API |
| [`app/services/`](app/services/) | Logique métier |
| [`app/models/`](app/models/), [`app/schemas/`](app/schemas/) | Modèles SQLAlchemy et schémas Pydantic |
| [`app/utils/`](app/utils/) | Extraction des couleurs, des formes et du texte |
| [`app/utils/georeferencing/`](app/utils/georeferencing/) | Géoréférencement ([documentation](../dev-docs/georeferencing.md)) |
| [`app/tasks.py`](app/tasks.py) | Tâches Celery |
| [`db/`](db/) | Migrations SQL |
| [`ocr-florence/`](ocr-florence/) | Worker Florence-2 (image Docker séparée) |
| [`tests/`](tests/) | Tests pytest et cas de géoréférencement |
| [`scripts/`](scripts/) | Outils de développement |

## Outil de test du géoréférencement

L'outil de création et d'évaluation des cas de test est décrit dans [`dev-docs/dev-test-tool.md`](../dev-docs/dev-test-tool.md). Pour remplacer volontairement le meilleur résultat (`best`) d'un cas par sa dernière exécution, même moins bonne, voir la section 5 de ce document (`scripts/force_promote_georef_best.py`)
