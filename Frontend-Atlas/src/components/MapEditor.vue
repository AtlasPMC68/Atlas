<template>
  <div class="map-editor">
    <div id="edit-map" class="h-full w-full"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import L from 'leaflet'
import 'leaflet-draw'
import 'leaflet-draw/dist/leaflet.draw.css'

const props = defineProps({
  mapId: String,
  features: Array
})

const emit = defineEmits(['features-updated'])

const map = ref(null)
const drawnItems = new L.FeatureGroup()
let activeTool = null

onMounted(() => {
  map.value = L.map('edit-map', {
    zoomControl: false
  }).setView([52.9399, -73.5491], 5)

  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', {
    subdomains: 'abcd',
    maxZoom: 19
  }).addTo(map.value)

  // Zoom control top right
  L.control.zoom({ position: 'topright' }).addTo(map.value)

  map.value.addLayer(drawnItems)

  // Toolbar custom sous le zoom
  const ToolbarControl = L.Control.extend({
    options: { position: 'topright' },
    onAdd: function () {
      const container = L.DomUtil.create('div', 'leaflet-bar')
      const buttons = [
        { icon: 'fa-solid fa-location-dot', type: 'marker' },
        { icon: 'fa-solid fa-route', type: 'polyline' },
        { icon: 'fa-solid fa-draw-polygon', type: 'polygon' },
        { icon: 'fa-solid fa-pen-to-square', type: 'edit' },
        { icon: 'fa-solid fa-trash-can', type: 'delete' },
        { icon: 'fa-solid fa-floppy-disk', type: 'save' }
      ]
      buttons.forEach(btn => {
        const a = L.DomUtil.create('a', '', container)
        a.href = '#'
        a.innerHTML = `<i class="${btn.icon}"></i>`
        a.title = btn.type
        a.style.textAlign = 'center'
        a.onclick = e => {
          e.preventDefault()
          if (btn.type === 'save') save()
          else enable(btn.type)
        }
      })
      return container
    }
  })

  map.value.addControl(new ToolbarControl())

  // Charger les features existantes
  if (props.features?.length) {
    props.features.forEach(f => {
      if (!f.geometry) return
      const layer = L.geoJSON(f.geometry, {
        style: {
          color: f.color || '#000',
          weight: f.stroke_width || 2,
          fillColor: f.color || '#ccc',
          fillOpacity: f.opacity ?? 0.5
        }
      })
      layer.eachLayer(l => drawnItems.addLayer(l))
    })
  }

  // Event création
  map.value.on(L.Draw.Event.CREATED, e => {
    drawnItems.addLayer(e.layer)
  })
})

onUnmounted(() => {
  if (map.value) map.value.remove()
})

function enable(type) {
  if (activeTool) {
    activeTool.disable()
    activeTool = null
  }

  drawnItems.eachLayer(l => {
    if (l.editing && l.editing.enabled()) {
      l.editing.disable()
    }
  })

  if (type === 'marker') {
    activeTool = new L.Draw.Marker(map.value)
    activeTool.enable()
  }

  if (type === 'polyline') {
    activeTool = new L.Draw.Polyline(map.value)
    activeTool.enable()
  }

  if (type === 'polygon') {
    activeTool = new L.Draw.Polygon(map.value)
    activeTool.enable()
  }

  if (type === 'edit') {
    drawnItems.eachLayer(layer => {
      if (layer.editing) {
        layer.editing.enable()
      }

      if (layer.dragging) {
        layer.dragging.enable()
      }
    })
  }
  if (type === 'delete') {
    map.value.once('click', e => {
      let targetLayer = null

      drawnItems.eachLayer(layer => {
        if (layer.getBounds && layer.getBounds().contains(e.latlng)) {
          targetLayer = layer
        }

        if (layer.getLatLng && layer.getLatLng().distanceTo(e.latlng) < 15) {
          targetLayer = layer
        }
      })

      if (targetLayer) {
        drawnItems.removeLayer(targetLayer)
      }
    })
  }
}

async function save() {
  const geojson = drawnItems.toGeoJSON()
  await fetch(`${import.meta.env.VITE_API_URL}/maps/features/${props.mapId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(geojson)
  })
  emit('features-updated')
}
</script>

<style scoped>
.map-editor { height: 100%; width: 100%; }

/* Optionnel : espace sous le zoom */
.leaflet-top.leaflet-right .leaflet-bar + .leaflet-bar {
  margin-top: 6px; /* laisse un petit espace sous le zoom */
}

/* Supprime le gris sur les boutons */
.leaflet-bar a {
  background: white;
  border: none;
  padding: 6px 8px;
  display: flex;
  justify-content: center;
  align-items: center;
  font-size: 16px;
  color: #333;
}

.leaflet-bar a:hover {
  background: #f4f4f4;
}
</style>
