# Migration vers Leaflet.pm - Guide de Conversion

## État d'avancement

### ✅ Implémenté - Phase 1

**Composable `useMapDrawing.ts` créé avec support pour:**

- Points/Markers
- Polylines (lignes)
- Polygones (polygones custom)
- Rectangles
- Cercles
- Freehand (dessin libre)

**Intégration dans MapGeoJSON.vue:**

- Initialisation de Leaflet.pm au montage
- Mappage des modes d'édition (`activeEditMode`) → modes Leaflet.pm
- Gestion des formes spéciales (`CREATE_SHAPES` → rectangle/circle)
- Événements: `feature-created`, `feature-updated`, `feature-deleted`

### 🚧 À faire - Phase 2

**Fonctionnalités à intégrer graduellement:**

1. **Suppression des features** (DELETE_FEATURE)
   - Utiliser le mode "remove" de Leaflet.pm
   - Connecter aux événements `pm:remove`

2. **Édition/Move des features existantes** (MOVE_FEATURE)
   - Activer le mode edit de Leaflet.pm pour les objects existants
   - Gérer les événements `pm:edit`

3. **Multi-sélection et overlays personnalisés**
   - À faire seulement si nécessaire (optionnel pour MVP)
   - Peut rester en code custom pour l'instant

4. **Rotation et Resize avancés** (RESIZE_SHAPE)
   - À faire seulement si nécessaire (optionnel pour MVP)
   - Peut rester en code custom pour l'instant

5. **Formes spéciales** (optionnel)
   - Triangles, ovals, carrés: à faire après MVP
   - Leaflet.pm ne supporte pas nativement, nécessite custom shapes

### ⚙️ Configuration actuelle

**Modes supportés:**

```
CREATE_POINT → marker
CREATE_LINE → polyline
CREATE_POLYGON → polygon
CREATE_SHAPES:
  - rectangle → rectangle
  - circle → circle
```

**Éléments non migrés à Leaflet.pm (encore actifs):**

- Résizing en mètres/km
- Rotation d'objets avec handles custom
- Multi-sélection avec overlays
- Delete mode avancé

### 📋 Prochaines étapes

1. **Tester les draws basiques** avec Leaflet.pm (points, lignes, polygones, rectangles, cercles)
2. **Valider la conversion** et l'émission des events
3. **Nettoyer graduellement** les composables non utilisés (`useMapEvents.ts`, `useMapEditing.ts` partiellement)
4. **Ajouter suppression** (DELETE_FEATURE mode)
5. **Décider** si on migre resize/rotation ou on les garde en custom

### 🔧 Installation requise

```bash
npm install @geoman-io/leaflet-geoman-free
```

**Déjà fait ✓**

---

## Mapping des anciennes fonctionnalités → Leaflet.pm

| Ancienne fonction   | Nouvelle approche                     | Composable         |
| ------------------- | ------------------------------------- | ------------------ |
| `createPoint()`     | `drawing.setDrawingMode("marker")`    | `useMapDrawing.ts` |
| `createLine()`      | `drawing.setDrawingMode("polyline")`  | `useMapDrawing.ts` |
| `createPolygon()`   | `drawing.setDrawingMode("polygon")`   | `useMapDrawing.ts` |
| `createRectangle()` | `drawing.setDrawingMode("rectangle")` | `useMapDrawing.ts` |
| `createCircle()`    | `drawing.setDrawingMode("circle")`    | `useMapDrawing.ts` |
| Freehand drawing    | `drawing.setDrawingMode("freehand")`  | `useMapDrawing.ts` |
| Delete features     | TODO: pm remove mode                  | `useMapDrawing.ts` |
| Edit/Move           | TODO: pm edit mode                    | `useMapDrawing.ts` |
| Resize + Rotation   | CUSTOM (optionnel ultérieurement)     | -                  |

---

**Fichiers modifiés:**

- ✅ `src/composables/useMapDrawing.ts` (nouveau)
- ✅ `src/components/MapGeoJSON.vue` (intégration)

**Fichiers non utilisés (à nettoyer plus tard):**

- `useMapEvents.ts` (partiellement remplacé)
- `useMapEditing.ts` (partiellement remplacé)
- `useMapInit.ts` (peut être allégé)
