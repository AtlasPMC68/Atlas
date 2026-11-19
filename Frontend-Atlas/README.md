# Frontend Atlas

Application web d'Atlas : Vue 3, TypeScript, Vite, Tailwind CSS / DaisyUI et Leaflet.

Le frontend se lance avec le reste d'Atlas, dans Docker : voir le [guide de développement](../docs/developpement.md). Le serveur Vite recharge la page dès qu'un fichier change.

| Dossier | Contenu |
|---|---|
| [`src/views/`](src/views/) | Pages : accueil, mes projets, explorer, éditeur de carte, import |
| [`src/components/`](src/components/) | Composants : import, géoréférencement, légende, ligne du temps |
| [`src/router/`](src/router/) | Routes (en français) |
| [`src/composables/`](src/composables/), [`src/stores/`](src/stores/) | État et logique partagés |
| [`tests/`](tests/) | Tests Vitest |

Lancer les tests :

```bash
docker compose exec frontend npm run test -- --run
```
