# Leaflet.pm Drawing Mode - Testing Guide

**Environment:** http://localhost:5173 (Vite dev server running)
**Date:** December 2024
**Target Audience:** QA/Developers testing drawing functionality after migration

---

## 🚀 Quick Start

### Prerequisites

- [ ] Dev server running: `npm run dev` (already running)
- [ ] Browser window open: http://localhost:5173
- [ ] Browser console open: F12 → Console tab
- [ ] Map editor mode enabled (if required by authentication)

---

## 📋 Manual Test Matrix

### Test Set 1: Drawing Modes Activation

| Test #  | Action                           | Expected Result                                  | Pass/Fail | Notes                       |
| ------- | -------------------------------- | ------------------------------------------------ | --------- | --------------------------- |
| **1.1** | Click "Ajouter un point" button  | Leaflet.pm marker tool activates, cursor changes | ⚪        | Listen for console messages |
| **1.2** | Click "Ligne droite" button      | Leaflet.pm polyline tool activates               | ⚪        |                             |
| **1.3** | Click "Créer un polygone" button | Leaflet.pm polygon tool activates                | ⚪        |                             |
| **1.4** | Click "Formes" → "Rectangle"     | Leaflet.pm rectangle tool activates              | ⚪        |                             |
| **1.5** | Click "Formes" → "Cercle"        | Leaflet.pm circle tool activates                 | ⚪        |                             |
| **1.6** | Click same mode twice            | Mode toggles off, drawing disabled               | ⚪        |                             |

### Test Set 2: Feature Creation

| Test #  | Action                                      | Expected Result                                  | Pass/Fail | Notes                   |
| ------- | ------------------------------------------- | ------------------------------------------------ | --------- | ----------------------- |
| **2.1** | (Mode: Point) Click on map                  | Marker appears, "feature-created" in console     | ⚪        | Check console for event |
| **2.2** | (Mode: Line) Click 2 points                 | Polyline appears between points                  | ⚪        |                         |
| **2.3** | (Mode: Line) Right-click or Escape          | Polyline finalized, saved                        | ⚪        | Check console log       |
| **2.4** | (Mode: Polygon) Click 3+ points, close ring | Polygon appears, "feature-created" emitted       | ⚪        |                         |
| **2.5** | (Mode: Rectangle) Drag rectangle            | Rectangle drawn, "feature-created" emitted       | ⚪        |                         |
| **2.6** | (Mode: Circle) Click center + drag          | Circle drawn, "feature-created" emitted          | ⚪        |                         |
| **2.7** | (Mode: Freehand) Draw freely                | Freehand line appears, "feature-created" emitted | ⚪        |                         |

### Test Set 3: GeoJSON Output Verification

| Test #  | Feature Type | Expected GeoJSON Type | Expected Properties                                                                      | Pass/Fail |
| ------- | ------------ | --------------------- | ---------------------------------------------------------------------------------------- | --------- |
| **3.1** | Point/Marker | Point                 | `{ type: "point", geometry: { type: "Point", coordinates: [lng, lat] } }`                | ⚪        |
| **3.2** | Line         | LineString            | `{ type: "polyline", geometry: { type: "LineString", coordinates: [[lng, lat], ...] } }` | ⚪        |
| **3.3** | Polygon      | Polygon               | `{ type: "zone", geometry: { type: "Polygon", coordinates: [[[lng, lat], ...]] } }`      | ⚪        |
| **3.4** | Rectangle    | Polygon               | `{ type: "zone", geometry: { type: "Polygon", coordinates: [[[lng, lat], ...]] } }`      | ⚪        |
| **3.5** | Circle       | Polygon (32 pts)      | `{ type: "zone", geometry: { type: "Polygon", coordinates: [...] } }`                    | ⚪        |

**How to verify GeoJSON:**

1. Open browser console (F12)
2. When feature is created, event data is logged
3. Paste this in console to see last feature: `console.log(window.lastFeature)`

### Test Set 4: Layer Management

| Test #  | Action                      | Expected Result                   | Pass/Fail | Notes                     |
| ------- | --------------------------- | --------------------------------- | --------- | ------------------------- |
| **4.1** | Create 5 different features | All appear on map, clickable      | ⚪        | Verify drawing layer      |
| **4.2** | Hover over feature          | Highlight or cursor change        | ⚪        | Depends on styling        |
| **4.3** | Click on drawn feature      | Feature selectable?               | ⚪        | Depends on implementation |
| **4.4** | Zoom in/out                 | All features scale correctly      | ⚪        | Check for scaling bugs    |
| **4.5** | Pan map                     | Features stay in correct position | ⚪        |                           |

---

## 🔍 Console Debugging

### What to look for:

**Success indicators:**

```javascript
// In browser console, you should see:
✓ [Leaflet.pm] Initialized on map
✓ pm:create event triggered
✓ feature-created emitted: { type: "point", geometry: {...} }
✓ Layer added to drawnItems FeatureGroup
```

**Error indicators:**

```javascript
// Errors to watch for:
✗ "Leaflet.pm not properly initialized"
  → Leaflet.pm library not loaded
✗ ReferenceError: Cannot read property 'pm' of undefined
  → Map object not initialized
✗ "TypeError: Cannot read property 'getLatLng' of null"
  → Layer creation failed
```

### Adding debug logging:

**Add to browser console to trace events:**

```javascript
// Monitor drawing events
const originalEmit = map.pm.Toolbar || window;
window.addEventListener("feature-created", (e) => {
  console.log("✓ feature-created:", e.detail);
});

// Check Leaflet.pm status
console.log("Leaflet.pm loaded:", !!L.PM);
console.log("Map has pm:", !!map.pm);
console.log("Drawing mode:", map.pm.Draw?._enabled);
```

---

## 🐛 Troubleshooting

### Issue 1: "drawing.initializeDrawing is not a function"

**Cause:** useMapDrawing composable not properly exported
**Fix:** Check MapGeoJSON.vue line 27 for import, line 273 for initialization

### Issue 2: Drawing tools don't appear in UI

**Cause:** Leaflet.pm controls not rendered
**Fix:** Open browser DevTools, check if control elements exist in DOM

### Issue 3: Features created but not visible

**Cause:** drawnItems FeatureGroup not added to map
**Fix:** Check useMapDrawing.ts line 50: `map.addLayer(drawnItems.value)`

### Issue 4: Console shows "Leaflet.pm not properly initialized"

**Cause:** @geoman-io/leaflet-geoman-free not loaded in browser
**Fix:** Hard refresh (Ctrl+Shift+R) to clear cache, check network tab for CSS/JS loading

### Issue 5: Circle tool creates polygon instead of circle

**Expected behavior:** This is intentional! Circles are stored as 32-point polygons for GeoJSON compatibility

---

## 📊 Test Coverage Checklist

### Core Functionality

- [ ] All 6 drawing modes can be activated
- [ ] Each mode successfully creates a feature
- [ ] Features emit correct GeoJSON
- [ ] Features are visually represented on map
- [ ] Multiple features can coexist
- [ ] Features survive map pan/zoom

### Edge Cases

- [ ] Creating zero-area shapes (edge of map)
- [ ] Creating very large shapes (world bounds)
- [ ] Rapid mode switching
- [ ] Drawing on zoomed-out map (< zoom 2)
- [ ] Drawing on zoomed-in map (> zoom 18)
- [ ] Network latency (test with DevTools throttling)

### Browser Compatibility

- [ ] Chrome/Edge (Chromium)
- [ ] Firefox
- [ ] Safari (if applicable)
- [ ] Mobile browser (if applicable)

---

## 📈 Performance Benchmarks

| Metric              | Target     | Actual | Status |
| ------------------- | ---------- | ------ | ------ |
| Mode activation     | < 100ms    | ⏱️     | ⚪     |
| Feature creation    | < 200ms    | ⏱️     | ⚪     |
| Feature rendering   | < 500ms    | ⏱️     | ⚪     |
| 10 features on map  | < 1s total | ⏱️     | ⚪     |
| 100 features on map | < 3s total | ⏱️     | ⚪     |

**How to measure:**

```javascript
// In console:
console.time("draw-point");
// [click draw button and click on map]
console.timeEnd("draw-point");
// Expected: ~50-150ms
```

---

## ✅ Sign-Off Checklist

### Phase 1: Basic Functionality (MVP)

- [ ] All 6 drawing modes work
- [ ] Feature creation events fire
- [ ] GeoJSON export is valid
- [ ] No console errors

### Phase 2: Integration (Ready for Prod)

- [ ] Edit mode works (when implemented)
- [ ] Delete mode works (when implemented)
- [ ] Existing features load correctly
- [ ] Multi-feature operations work

### Phase 3: Polish (Optional)

- [ ] Performance acceptable with 1000+ features
- [ ] Mobile gesture support (touch drawing)
- [ ] Accessibility compliance
- [ ] Resize/rotate features (if needed)

---

## 📝 Test Log Template

```markdown
### Test Run - [Date] [Tester Name]

**Environment:** [Browser/Version], [OS], [Zoom Level]
**Features Created:** [e.g., 3 points, 2 lines, 1 polygon]
**Pass Rate:** [X]/[Y] tests passed

#### Issues Found:

1. [Issue 1]: [Description] [Severity: Low/Medium/High]
2. [Issue 2]: [Description] [Severity: Low/Medium/High]

#### Notes:

- [Any observations about behavior]
- [Recommendations for improvement]

**Overall Status:** ✅ Ready / ⚠️ Minor Issues / ❌ Blocking Issues
```

---

## 🎯 Next Steps After Testing

1. **If tests PASS:**
   - Proceed to Phase 3: Edit & Delete modes
   - Begin cleanup of legacy composables
   - Prepare for production deployment

2. **If tests FAIL:**
   - Document errors with steps to reproduce
   - Check console logs for root causes
   - Review integration points in MapGeoJSON.vue
   - Fix and re-test affected feature

3. **If tests INCONCLUSIVE:**
   - Add more debug logging
   - Test in different browser/environment
   - Check network requests to backend
   - Isolate the failing component

---

## 📞 Support References

**Files Modified:**

- [MapGeoJSON.vue](src/components/MapGeoJSON.vue) - Drawing mode watcher logic
- [useMapDrawing.ts](src/composables/useMapDrawing.ts) - Leaflet.pm wrapper

**Documentation:**

- [Leaflet.pm Docs](https://geoman.io/docs/) - Full Leaflet.pm API reference
- [GeoJSON Spec](https://tools.ietf.org/html/rfc7946) - GeoJSON format reference

**Dependencies:**

- [leaflet](https://leafletjs.com/) v1.9.4
- [@geoman-io/leaflet-geoman-free](https://www.npmjs.com/package/@geoman-io/leaflet-geoman-free) v2.19.2
