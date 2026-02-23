# 🎨 How to Use Leaflet.pm Drawing in Atlas

**Dev Server:** http://localhost:5173  
**Status:** Ready for testing  
**Time to first draw:** ~2 minutes

---

## 🚀 Quick Start (Fastest Path)

### These steps should get you drawing within 2 minutes:

1. **Server is already running**
   - Dev server started via `npm run dev`
   - Access: http://localhost:5173

2. **Open the map page**
   - Navigate to Map view (should be default)
   - You should see a world map with timeline slider

3. **Enable editing mode** (if needed)
   - Look for toggle button "Mode édition" or similar
   - Toggle ON to activate editing controls

4. **Select a drawing mode**
   - **Point:** Click "➕ Ajouter un point" or "🔵 Marker"
   - **Line:** Click "➖ Ligne droite" or "📐 Polyline"
   - **Polygon:** Click "🔶 Créer un polygone"
   - **Shapes:** Click "▭ Formes" then:
     - "🟪 Rectangle" for rectangles
     - "⭕ Cercle" for circles

5. **Draw on the map**
   - **For Points:** Click once on the map
   - **For Lines:** Click multiple points, right-click or Escape to finish
   - **For Polygons:** Click 3+ points to form shape, close ring to complete
   - **For Rectangles:** Click and drag to create rectangle
   - **For Circles:** Click center, then drag to expand radius

6. **Check the result**
   - Feature appears on map
   - Open browser console (F12)
   - Look for "feature-created" message with GeoJSON data
   - ✅ Success!

---

## 🎯 Drawing Mode Details

### Creating a Point

```
1. Click "Ajouter un point" button (top-left toolbar)
2. Cursor changes to crosshair
3. Click anywhere on map
4. Circle marker appears → Success! ✅
```

### Creating a Line

```
1. Click "Ligne droite" button
2. Click first point on map
3. Click second point
4. (Optional) Click more points to add segments
5. Right-click or press Escape to finish
6. Line appears → Success! ✅
```

### Creating a Polygon

```
1. Click "Créer un polygone" button
2. Click points to form polygon outline
3. Click close to the first point (within 20px) to close ring
4. Polygon appears filled → Success! ✅
```

### Creating a Rectangle

```
1. Click "Formes" menu
2. Select "Rectangle"
3. Click and drag corner to corner
4. Rectangle appears → Success! ✅
```

### Creating a Circle

```
1. Click "Formes" menu
2. Select "Cercle"
3. Click center point
4. Drag outward to set radius
5. Circle appears (stored as 32-point polygon) → Success! ✅
```

---

## 🔍 Verifying It Works

### In Browser Console (F12 → Console tab)

**You should see logs like this:**

```javascript
// When you create a feature:
"Leaflet.pm Drawing initialized"
[Object] {
  type: "point",
  geometry: { type: "Point", coordinates: [-73.5491, 52.9399] },
  color: "#000000",
  opacity: 0.5,
  stroke_width: 2,
  properties: { mapElementType: "point" }
}
```

**If there are problems, check for these errors:**

```javascript
// ❌ If you see this:
"Leaflet.pm not properly initialized";
// → Fix: Hard refresh (Ctrl+Shift+R)

// ❌ If you see this:
"Cannot read property 'pm' of undefined";
// → Fix: Map not loaded yet, wait a second

// ❌ If you see this:
"TypeError: drawing.setDrawingMode is not a function";
// → Fix: Check that useMapDrawing is imported correctly
```

---

## 📊 Understanding the Output

### Point Feature Example

```json
{
  "type": "point",
  "geometry": {
    "type": "Point",
    "coordinates": [-73.5491, 52.9399]
  },
  "color": "#000000",
  "opacity": 0.5,
  "stroke_width": 2,
  "properties": {
    "mapElementType": "point"
  }
}
```

### Line Feature Example

```json
{
  "type": "polyline",
  "geometry": {
    "type": "LineString",
    "coordinates": [
      [-73.5, 52.0],
      [-73.0, 52.5],
      [-72.5, 53.0]
    ]
  },
  "color": "#000000",
  "opacity": 0.5,
  "stroke_width": 2,
  "properties": {
    "mapElementType": "polyline"
  }
}
```

### Polygon/Zone Feature Example

```json
{
  "type": "zone",
  "geometry": {
    "type": "Polygon",
    "coordinates": [
      [
        [-73.0, 52.0],
        [-73.0, 53.0],
        [-72.0, 53.0],
        [-72.0, 52.0],
        [-73.0, 52.0] /* always closes ring */
      ]
    ]
  },
  "color": "#000000",
  "opacity": 0.5,
  "stroke_width": 2,
  "properties": {
    "mapElementType": "zone"
  }
}
```

---

## ⚙️ Technical Details (For Developers)

### Where features are stored

- **Drawing layer:** `L.FeatureGroup` in Map component
- **Event forwarding:** MapGeoJSON emits "feature-created" event
- **Parent component:** Handles storage in state/DB

### Coordinate system

- **Format:** GeoJSON (longitude, latitude) = [lng, lat]
- **Map projection:** Web Mercator (EPSG:3857)
- **For circles:** Converted to 32-point polygon approximation

### Event flow

```
User draws → Leaflet.pm pm:create event
  → useMapDrawing captures layer
  → layerToFeature() converts to GeoJSON
  → emit("feature-created", feature)
  → MapGeoJSON emits to parent
  → Parent stores in state/API
```

### Coordinate transformation example

```javascript
// User clicks at visual position
// Leaflet converts to WGS84 lat/lng: {lat: 52.9399, lng: -73.5491}
// GeoJSON converts to [lng, lat]: [-73.5491, 52.9399]
// Database stores: {"type": "Point", "coordinates": [-73.5491, 52.9399]}
```

---

## 🐛 Common Issues & Fixes

### Issue: "Drawing tools not visible"

**Solution:**

- Check if edit mode is enabled
- Hard refresh browser (Ctrl+Shift+R)
- Check DevTools console for errors

### Issue: "Can draw but features don't appear"

**Solution:**

- Features ARE created (check console output)
- They might not be styled/rendered properly
- Check if drawnItems FeatureGroup is added to map
- Verify CSS/styling is loaded

### Issue: "Mode keeps resetting"

**Solution:**

- This is expected - UI may trigger mode changes
- Try clicking button again to enable
- Check parent component state management

### Issue: "Circle tool not creating circles"

**Solution:**

- This is EXPECTED! Circles are stored as polygons
- GeoJSON doesn't support circle geometry natively
- 32-point polygon approximation is intentional
- Looks like circle on map, stores as polygon in DB

### Issue: "Getting strange GeoJSON structure"

**Solution:**

- Check `mapElementType` property - tells you feature type
- Polygon `coordinates` are always nested: `[[[lng, lat], ...]]`
- LineString coordinates: `[[lng, lat], [lng, lat], ...]`
- Point coordinates: `[lng, lat]`

---

## ✅ Success Checklist

After drawing a few features, you should see:

- [ ] Leaflet.pm controls visible in top-left corner
- [ ] Drawing mode can be activated by clicking buttons
- [ ] Features appear on map when created
- [ ] Browser console shows "feature-created" events
- [ ] Each feature has valid GeoJSON structure
- [ ] Features are colored (default black)
- [ ] Multiple features can coexist on map

If all boxes ✅, you're ready for Phase 2 testing!

---

## 📋 Testing Checklist

Use TESTING_GUIDE.md for comprehensive testing, but here's a quick version:

```
Quick Test (5 min):
☐ Create 1 point → check console
☐ Create 1 line → verify GeoJSON
☐ Create 1 polygon → check features visible
☐ Create 1 rectangle → verify shape
☐ Create 1 circle → verify it's actually polygon

If all work → ✅ System operational
If any fails → 🔍 Check console errors
```

---

## 🎯 What's NOT Implemented Yet

These features are coming in Phase 2-3:

- ❌ Editing drawn features (move points)
- ❌ Deleting features via UI
- ❌ Resizing/rotating shapes
- ❌ Loading existing features from database
- ❌ Saving to backend API
- ❌ Undo/redo functionality

For now, focus on : **Can I draw and see valid GeoJSON?**

---

## 💡 Pro Tips

**Display last feature in console:**

```javascript
// You can manually check the last feature:
window.lastCreatedFeature;
```

**Monitor all drawing events:**

```javascript
// In console, add this to watch all events:
L.map("map").on("pm:create pm:edit pm:remove", (e) => {
  console.log("Drawing event:", e.type, e);
});
```

**Identify feature types:**

- Look at `feature.geometry.type` in GeoJSON
- Or check `feature.properties.mapElementType`

**Save feature to file:**

```javascript
// Copy entire feature object:
JSON.stringify(window.lastCreatedFeature, null, 2);
// Then paste into .json file or send to API
```

---

**Happy drawing! 🎨**

_Questions? Check TESTING_GUIDE.md or MIGRATION_STATUS_2024.md for more details._
