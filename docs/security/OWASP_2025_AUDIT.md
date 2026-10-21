# Audit de sécurité Atlas — OWASP Top 10:2025

## Résumé

Audit statique de phase 1 réalisé sur le backend FastAPI, le frontend, Keycloak,
la configuration Docker Compose, Celery/Redis/PostgreSQL, les dépendances et les
scripts présents dans le dépôt. Cette phase documente les risques sans corriger
la logique applicative, les dépendances ou la configuration d'exécution.

Six causes regroupées et deux points à valider ont été documentés par vingt-et-un
TODO OWASP dans neuf fichiers source.
Les valeurs sensibles ne sont pas reproduites dans ce rapport. Toute valeur
d'identifiant ou de secret actuellement suivie dans le dépôt doit être considérée
comme exposée et tournée avant un déploiement public.

## Constats et TODO

| Référence | Catégorie | Priorité | État | Emplacement | Risque et correctif phase 2 |
|---|---|---|---|---|---|
| F1 | A07:2025, A02:2025 | ÉLEVÉE | Confirmé | `docker-compose.yml` environnement PostgreSQL et Keycloak; `keycloak/setdata.sh` | Des identifiants par défaut sont présents dans la configuration suivie. Les injecter par secrets, imposer des valeurs uniques et tourner les valeurs exposées. |
| F2 | A02:2025 | ÉLEVÉE | Confirmé | `docker-compose.yml` services Redis, Flower, PostgreSQL et Keycloak | Des services internes sont publiés sans isolation réseau ou authentification démontrée. Ne pas les publier en production, limiter le développement à localhost et ajouter authentification/TLS lorsque nécessaire. |
| F3 | A01:2025, A06:2025 | ÉLEVÉE | Confirmé | `Backend-Atlas/app/main.py`, `Backend-Atlas/app/routers/dev_test.py` | Les outils dev-test sont activés par défaut et leurs mutations exigent seulement une authentification. Désactiver par défaut, séparer l'environnement et imposer un rôle administrateur. |
| F4 | A01:2025 | MOYENNE | Confirmé | `Backend-Atlas/app/routers/celery_router.py`, `Backend-Atlas/app/routers/projects.py` | Les statuts, résultats, erreurs et tâches actives sont accessibles sans contrôle d'identité/propriété démontré. Authentifier les routes et lier chaque tâche à l'utilisateur et au projet. |
| F5 | A04:2025, A02:2025 | ÉLEVÉE | Confirmé pour la configuration fournie; exposition dépendante de l'environnement | `docker-compose.yml`, `keycloak/setdata.sh` | HTTP est explicitement activé et le realm n'impose pas TLS. Exiger HTTPS, une configuration de proxy stricte et une politique SSL adaptée en production. |
| F6 | A03:2025 | MOYENNE | Confirmé | `docker-compose.yml`, `Backend-Atlas/requirements.txt` | `postgis/postgis:latest`, `torch` et `torchvision` rendent le build mutable. Épingler versions/digests/hashes et contrôler les index, SBOM et scans CI. |
| F7 | A07:2025 | MOYENNE | À vérifier | `Backend-Atlas/app/keycloak.py` | La validation d'audience JWT est désactivée; le contrôle `azp` peut être intentionnel mais n'est pas équivalent. Valider issuer, audience, azp, exp, nbf, signature et type de jeton avec des tests. |
| F8 | A02:2025 | MOYENNE | Confirmé | `Backend-Atlas/Dockerfile` | `uvicorn --reload` est le mode par défaut de l'image. Utiliser une commande de production séparée sans reload et avec un profil explicite. |

Les TODO sont placés immédiatement au-dessus du code concerné. Les positions
exactes peuvent évoluer d'une ligne après une future modification; rechercher
`TODO OWASP` dans les fichiers indiqués constitue la référence stable.

## Évaluation par catégorie

### A01:2025 — Broken Access Control

Les routes dev-test et les routes de suivi Celery constituent les risques
confirmés. Les routes de projet examinées utilisent généralement l'utilisateur
authentifié et les opérations d'importation s'appuient sur le contrôle du
propriétaire de la carte. Il faut néanmoins tester explicitement les projets
publics/privés, les identifiants de projet, carte, tâche et fichier.

### A02:2025 — Security Misconfiguration

Les expositions de ports, les outils dev activés par défaut, HTTP Keycloak,
les secrets par défaut et le mode `--reload` sont documentés. La séparation
effective des réseaux et les règles du pare-feu de l'environnement déployé ne
peuvent pas être confirmées statiquement.

### A03:2025 — Software Supply Chain Failures

Les images et dépendances non immuables sont documentées. Aucun scan actuel,
SBOM, vérification de signature d'image ou politique complète de provenance ne
peut être confirmé à partir du dépôt seul. Ne pas changer les versions dans
cette phase.

### A04:2025 — Cryptographic Failures

Le transport HTTP et `sslRequired=None` sont des risques confirmés pour la
configuration fournie. La vérification JWT utilise RS256; la décision
d'audience doit être validée avant correction. Aucun stockage de mot de passe
applicatif faible n'a été identifié dans le périmètre lu; Keycloak le gère.

### A05:2025 — Injection

Aucune injection SQL, commande, chemin, HTML ou template n'a été confirmée dans
la lecture statique. Les accès SQL observés utilisent des expressions SQLAlchemy
et les tâches Celery acceptent JSON. Des tests adversariaux restent nécessaires
pour les parseurs d'images, OCR, GeoJSON et traitements géospatiaux.

### A06:2025 — Insecure Design

La colocalisation et l'activation par défaut des outils dev-test, ainsi que
l'utilisation d'identifiants de tâche sans liaison de propriété démontrée,
sont couvertes par F3 et F4. Les quotas, limites de débit et ressources
opérationnelles doivent être vérifiés avec les exigences de déploiement.

### A07:2025 — Authentication Failures

Les identifiants par défaut et le transport HTTP sont confirmés. La validation
de l'audience JWT est à vérifier. Les politiques Keycloak de MFA, mots de passe,
anti-brute-force et rotation des secrets ne sont pas entièrement évaluables
statiquement.

### A08:2025 — Software or Data Integrity Failures

Celery est configuré en JSON et aucun pickle n'a été identifié dans le périmètre
lu. La signature des artefacts, des images et des déploiements n'est pas
démontrée; cela recoupe F6 et doit être couvert par la CI en phase 2.

### A09:2025 — Security Logging and Alerting Failures

Aucun risque exploitable confirmé. Des logs existent pour certains échecs, mais
la centralisation, la rétention, les alertes et la détection comportementale
dépendent de l'exploitation et ne sont pas vérifiables statiquement.

### A10:2025 — Mishandling of Exceptional Conditions

Les réponses d'échec Celery peuvent divulguer des détails, mais ce risque est
traité sous A01 dans F4 car les routes sont aussi non authentifiées. Aucun
endpoint de production exposant une stack trace n'a été confirmé. Tester les
erreurs Redis, PostgreSQL, Keycloak, les interruptions Celery et le nettoyage
des fichiers temporaires.

## Tests de sécurité recommandés

- Tester qu'un utilisateur non authentifié ou non propriétaire ne peut lire un
  statut, résultat ou détail d'échec d'une autre tâche.
- Tester qu'un utilisateur standard reçoit `403` sur toutes les mutations
  dev-test et que les routes sont absentes en profil production.
- Scanner les ports publiés et vérifier Redis, Flower et PostgreSQL depuis un
  réseau non fiable.
- Vérifier le rejet des identifiants par défaut et la rotation des secrets.
- Vérifier redirection/rejet HTTP, TLS, issuer, audience, `azp`, `exp` et `nbf`.
- Ajouter un contrôle CI interdisant `latest`, les dépendances non épinglées et
  les secrets suivis; générer un SBOM et exécuter des scans de dépendances,
  images et secrets.
- Fuzzer les imports d'images, GeoJSON, OCR, chemins et propriétés utilisateur.

## Éléments sécurisés ou non évaluables

- Les accès SQL examinés utilisent SQLAlchemy paramétré.
- Les tâches Celery utilisent JSON (`task_serializer` et `accept_content`).
- Le JWT limite l'algorithme à RS256.
- Les autorisations de plusieurs opérations de projet et d'import utilisent
  l'utilisateur courant et/ou le propriétaire.
- La configuration réelle du pare-feu, du reverse proxy, de TLS, des secrets
  runtime, de Keycloak (MFA/anti-brute-force), de la rétention des logs et de
  la provenance des artefacts ne peut pas être établie par cet audit statique.
