# Guide de développement

Comment faire tourner Atlas sur votre ordinateur, lancer les tests et modifier la base de données. Pour mettre Atlas en ligne sur un serveur, voir le [guide de déploiement](deploiement/README.md).

## Prérequis

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (ou Docker Engine avec le plugin Compose sur Linux).
- De l'espace disque : les images Docker et le modèle de lecture de texte sont volumineux.
- Une clé API [CARTO](https://carto.com/) pour les fonds de carte (facultative : sans elle, les fonds de carte peuvent ne pas s'afficher).

Tout se fait dans Docker : il n'y a rien à installer en Python ou en Node sur votre machine.

## Lancer Atlas en local

1. **Configurer l'environnement (facultatif).** Sans fichier `.env`, `docker-compose.yml` utilise des valeurs par défaut pour le développement local (`postgres`/`postgres`, Keycloak `admin`/`admin`). Pour ajouter la clé CARTO :

   ```bash
   cp .env.example .env
   ```

   puis remplissez `VITE_CARTO_API_KEY` dans `.env`. Si `Backend-Atlas/.env.dev` existe, il est lu aussi ; le `.env` à la racine a priorité.

2. **Construire et démarrer les services :**

   ```bash
   docker compose up -d --build
   ```

   Le premier démarrage prend plusieurs minutes. Le service `migrate` crée la base de données, puis le backend et les workers démarrent.

3. **Ouvrir Atlas :**

   | Service | Adresse |
   |---|---|
   | Application | http://localhost |
   | API | http://localhost/api |
   | Keycloak | http://localhost/auth |
   | Flower (suivi des tâches) | http://localhost:5555 |
   | PostgreSQL | `localhost:5432` |
   | Redis | `localhost:6379` |

   Flower, PostgreSQL et Redis n'écoutent que sur `127.0.0.1` : ils ne sont pas accessibles depuis une autre machine.

4. **Vérifier que tout répond :**

   ```bash
   curl http://localhost/api/ping
   ```

   La réponse doit être `{"message": "pong"}`.

### Rechargement automatique

Le code est monté dans les conteneurs :

- **Backend** : toute modification du code Python redémarre le serveur automatiquement.
- **Frontend** : le serveur Vite recharge la page dès qu'un fichier change.

### Arrêter les services

```bash
docker compose down
```

> [!CAUTION]
> N'ajoutez pas `-v` : cette option supprime les volumes, donc la base de données et les comptes Keycloak.

Pour tout reconstruire de zéro (sans perdre les données) :

```bash
docker compose down; docker compose build --no-cache; docker compose up -d
```

## Tests

Les tests se lancent dans Docker, où l'environnement est déjà configuré. Les lancer directement sur votre machine mène souvent à des erreurs de dépendances sans rapport avec le code testé.

### Backend (pytest)

```bash
docker compose run --rm test-backend pytest -q
```

Un seul fichier, avec plus de détails :

```bash
docker compose run --rm test-backend pytest tests/test_extraction_text.py -vv
```

### Frontend (Vitest)

```bash
docker compose exec frontend npm run test -- --run
```

### Cas de géoréférencement

Les cas de test de géoréférencement comparent le résultat du pipeline à des cartes de référence ([`Backend-Atlas/tests/assets/georef/`](../Backend-Atlas/tests/assets/georef/)). Après une modification de l'extraction ou du géoréférencement :

```bash
python scripts/run_georef_tests.py
```

Pour un seul cas :

```bash
python scripts/run_georef_tests.py --test-id "<test_id>" --case-id "<case_id>"
```

Le script lance simplement `docker compose run --rm test-backend pytest tests/test_georef_cases.py -v`, avec un filtre `-k` si vous donnez un cas. L'outil qui sert à créer et explorer ces cas est décrit dans [`dev-docs/dev-test-tool.md`](../dev-docs/dev-test-tool.md).

### Ajouter un test

- **Backend** : un fichier `test_*.py` dans [`Backend-Atlas/tests/`](../Backend-Atlas/tests/), avec pytest.
- **Frontend** : un fichier `*.test.ts` dans [`Frontend-Atlas/tests/`](../Frontend-Atlas/tests/), avec Vitest.

Une nouvelle dépendance de test va dans `Backend-Atlas/requirements.txt` ou dans les `devDependencies` de `Frontend-Atlas/package.json`, puis `docker compose build`.

### Intégration continue

GitHub Actions ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) construit les images et lance les tests backend et frontend à chaque pull request vers `main` et à chaque push sur `main`. Une pull request dont les tests échouent ne peut pas être fusionnée. Les résultats apparaissent dans l'onglet **Checks** de la pull request.

## Modifier la base de données

Les changements de schéma sont des fichiers SQL dans [`Backend-Atlas/db/`](../Backend-Atlas/db/). Le service `migrate` les applique à chaque `docker compose up`, en local comme sur le serveur. Chaque fichier ne s'exécute qu'une fois, dans l'ordre des noms, et est noté dans la table `schema_migrations`.

1. Créez un fichier avec le numéro suivant, par exemple `Backend-Atlas/db/07_ajout_colonne.sql`.
2. Écrivez le changement, par exemple `ALTER TABLE users ADD COLUMN display_name TEXT;`
3. Lancez `docker compose up -d` : seul le nouveau fichier est appliqué. En cas d'erreur, `docker compose logs migrate` l'affiche.

> [!IMPORTANT]
> - Ne modifiez jamais un fichier déjà appliqué : les bases qui l'ont déjà exécuté ne verront pas le changement. Créez un nouveau fichier.
> - Ne supprimez jamais le volume pour changer le schéma.

## Mettre à jour le répertoire géographique

La reconnaissance des noms de lieux utilise un répertoire hors ligne, [`Backend-Atlas/app/data/geographic_entities.json`](../Backend-Atlas/app/data/geographic_entities.json) : pays, continents, provinces, États, territoires, lacs, rivières, mers et océans. Pour le régénérer à partir de `geonamescache` et de Natural Earth, avec les services démarrés :

```bash
docker exec -i atlas-backend python < Backend-Atlas/scripts/update_geographic_entities.py
```

Sous Windows (PowerShell) :

```powershell
Get-Content Backend-Atlas\scripts\update_geographic_entities.py | docker exec -i atlas-backend python -
```

Le script fusionne les nouvelles données avec le fichier existant, avec une écriture atomique pour ne pas le corrompre.
