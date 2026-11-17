# Contribuer à Atlas

Merci de votre intérêt pour Atlas ! Toute contribution est la bienvenue : signaler un bogue, proposer une idée, améliorer la documentation ou le code.

## Signaler un problème

1. Vérifiez dans les [issues](https://github.com/AtlasPMC68/Atlas/issues) que le problème n'a pas déjà été signalé.
2. Sinon, [ouvrez une nouvelle issue](https://github.com/AtlasPMC68/Atlas/issues/new/choose) et décrivez :
   - ce que vous faisiez (les étapes pour reproduire le problème) ;
   - ce qui s'est passé, et ce que vous attendiez ;
   - votre navigateur, et une capture d'écran si possible.

Une carte qui donne un mauvais résultat d'extraction ou de placement est très utile : joignez l'image si vous pouvez la partager.

## Proposer une fonctionnalité

Ouvrez une issue qui explique le besoin (ce que vous essayez de faire en classe, par exemple) avant la solution. C'est l'occasion d'en discuter avant que quelqu'un commence à coder.

## Contribuer au code

### Mettre en place l'environnement

Suivez le [guide de développement](docs/developpement.md) : tout tourne dans Docker.

### Le processus

1. Créez une branche à partir de `main`, nommée d'après l'issue : `<numéro>-<description-courte>`, par exemple `42-export-png`.
2. Faites vos changements, avec des tests si possible.
3. Vérifiez que les tests passent :

   ```bash
   docker compose run --rm test-backend pytest -q
   docker compose exec frontend npm run test -- --run
   ```

4. Ouvrez une pull request vers `main`. Dans la description, expliquez ce qui change et pourquoi, et liez l'issue (`Closes #42`).
5. L'intégration continue relance les tests. Une pull request est fusionnée quand les tests passent et qu'elle a été relue.

Ne poussez jamais directement sur `main`.

### Conventions

- **Langue.** Le code, les noms de variables et l'API sont en anglais. Tout ce que l'utilisateur voit (interface, URL, messages d'erreur) est en français.
- **Base de données.** Un changement de schéma est un nouveau fichier SQL numéroté dans `Backend-Atlas/db/`. Ne modifiez jamais un fichier déjà appliqué ([détails](docs/developpement.md#modifier-la-base-de-données)).
- **Géoréférencement.** Avant de modifier le pipeline de placement, lisez [`dev-docs/georeferencing.md`](dev-docs/georeferencing.md) et relancez les cas de test ([détails](docs/developpement.md#cas-de-géoréférencement)).
- **Secrets.** Ne commitez jamais de fichier `.env`, de clé API ou de mot de passe.

## Licence

En contribuant, vous acceptez que votre contribution soit distribuée sous la [licence MIT](LICENSE) du projet.
