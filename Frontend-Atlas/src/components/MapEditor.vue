<template>
    <div class="map-editor">
      <!-- Toolbar d'édition -->
      <div class="edit-toolbar absolute top-4 left-4 z-10 bg-white rounded-lg shadow-lg p-2">
        <div class="flex gap-2">
          <button 
            v-for="mode in editModes" 
            :key="mode.id"
            @click="setEditMode(mode.id)"
            :class="[
              'px-3 py-2 rounded text-sm font-medium transition-colors',
              activeMode === mode.id 
                ? 'bg-blue-600 text-white' 
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            ]"
          >
            <i :class="mode.icon" class="mr-1"></i>
            {{ mode.label }}
          </button>
        </div>
        
        <!-- Boutons d'action -->
        <div class="flex gap-2 mt-2 pt-2 border-t border-gray-200">
          <button 
            @click="saveChanges"
            class="px-3 py-2 bg-green-600 text-white rounded text-sm font-medium hover:bg-green-700 transition-colors"
            :disabled="!hasUnsavedChanges"
          >
            <i class="fas fa-save mr-1"></i>
            Sauvegarder
          </button>
          <button 
            @click="cancelEdit"
            class="px-3 py-2 bg-red-600 text-white rounded text-sm font-medium hover:bg-red-700 transition-colors"
            :disabled="!activeMode"
          >
            <i class="fas fa-times mr-1"></i>
            Annuler
          </button>
        </div>
      </div>
  
      <!-- Map container -->
      <div id="edit-map" class="h-full w-full"></div>
    </div>
  </template>
  
  <script setup>
  import { ref, onMounted, watch, onUnmounted } from 'vue'
  import L from 'leaflet'
  import 'leaflet-draw'
  import 'leaflet-draw/dist/leaflet.draw.css'
  
  // Props
  const props = defineProps({
    mapId: String,
    features: Array,
    featureVisibility: Map
  })
  
  // Emits
  const emit = defineEmits(['feature-created', 'feature-updated', 'feature-deleted'])
  
  // Modes d'édition
  const editModes = [
    { id: 'CREATE_POINT', label: 'Point', icon: 'fas fa-map-marker-alt' },
    { id: 'CREATE_LINE', label: 'Ligne', icon: 'fas fa-minus' },
    { id: 'CREATE_POLYGON', label: 'Polygone', icon: 'fas fa-draw-polygon' },
    { id: 'MOVE_FEATURE', label: 'Déplacer', icon: 'fas fa-arrows-alt' },
    { id: 'DELETE_FEATURE', label: 'Supprimer', icon: 'fas fa-trash' }
  ]
  
  // État
  const activeMode = ref(null)
  const map = ref(null)
  const drawControl = ref(null)
  const drawnItems = ref(null)
  const hasUnsavedChanges = ref(false)
  const unsavedFeatures = ref([])
  
  // Initialisation de la carte
  onMounted(() => {
    initializeMap()
    initializeDrawControl()
    loadExistingFeatures()
  })
  
  onUnmounted(() => {
    if (map.value) {
      map.value.remove()
    }
  })
  
  // Initialiser la carte
  function initializeMap() {
    map.value = L.map('edit-map').setView([52.9399, -73.5491], 5)
    
    // Fond de carte
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
      subdomains: 'abcd',
      maxZoom: 19
    }).addTo(map.value)
    
    // Layer pour les éléments dessinés
    drawnItems.value = new L.FeatureGroup()
    map.value.addLayer(drawnItems.value)
  }
  
  // Initialiser les contrôles de dessin
  function initializeDrawControl() {
    // Options pour chaque type de dessin
    const drawOptions = {
      position: 'topright',
      draw: {
        polyline: false,
        polygon: false,
        circle: false,
        rectangle: false,
        marker: false,
        circlemarker: false
      },
      edit: {
        featureGroup: drawnItems.value,
        remove: false,
        edit: false
      }
    }
    
    drawControl.value = new L.Control.Draw(drawOptions)
    map.value.addControl(drawControl.value)
  }
  
  // Charger les features existantes
  function loadExistingFeatures() {
    if (!props.features) return
    
    props.features.forEach(feature => {
      if (feature.geometry) {
        const layer = createLayerFromFeature(feature)
        if (layer) {
          drawnItems.value.addLayer(layer)
          layer.featureId = feature.id // Stocker l'ID pour les updates
        }
      }
    })
  }
  
  // Créer un layer Leaflet depuis une feature
  function createLayerFromFeature(feature) {
    const geom = feature.geometry
    
    if (!geom || !geom.coordinates) return null
    
    switch (feature.type) {
      case 'point':
        return L.circleMarker([geom.coordinates[1], geom.coordinates[0]], {
          radius: 6,
          fillColor: feature.color || '#000',
          color: feature.color || '#000',
          weight: 1,
          opacity: feature.opacity ?? 1,
          fillOpacity: feature.opacity ?? 1
        })
        
      case 'polyline':
      case 'arrow':
        const latlngs = geom.coordinates.map(coord => [coord[1], coord[0]])
        return L.polyline(latlngs, {
          color: feature.color || '#000',
          weight: feature.stroke_width ?? 2,
          opacity: feature.opacity ?? 1
        })
        
      case 'polygon':
      case 'zone':
        return L.geoJSON(geom, {
          style: {
            fillColor: feature.color || '#ccc',
            fillOpacity: 0.5,
            color: '#333',
            weight: 1
          }
        })
        
      default:
        return null
    }
  }
  
  // Changer de mode d'édition
  function setEditMode(modeId) {
    if (activeMode.value === modeId) {
      activeMode.value = null
      disableDrawMode()
      return
    }
    
    activeMode.value = modeId
    enableDrawMode(modeId)
  }
  
  // Activer un mode de dessin
  function enableDrawMode(modeId) {
    disableDrawMode() // Désactiver le mode précédent
    
    switch (modeId) {
      case 'CREATE_POINT':
        new L.Draw.Marker(map.value, {
          icon: new L.Icon.Default()
        }).enable()
        break
        
      case 'CREATE_LINE':
        new L.Draw.Polyline(map.value, {
          shapeOptions: {
            color: '#000',
            weight: 2
          }
        }).enable()
        break
        
      case 'CREATE_POLYGON':
        new L.Draw.Polygon(map.value, {
          shapeOptions: {
            color: '#000',
            fillColor: '#ccc',
            fillOpacity: 0.5
          }
        }).enable()
        break
        
      case 'MOVE_FEATURE':
        // Activer l'édition pour tous les layers
        drawnItems.value.eachLayer(layer => {
          layer.editing.enable()
        })
        break
        
      case 'DELETE_FEATURE':
        // Activer la suppression
        new L.Draw.Remove(map.value).enable()
        break
    }
  }
  
  // Désactiver tous les modes de dessin
  function disableDrawMode() {
    map.value.eachLayer(layer => {
      if (layer instanceof L.Draw.Feature) {
        layer.disable()
      }
    })
    
    // Désactiver l'édition
    drawnItems.value.eachLayer(layer => {
      if (layer.editing) {
        layer.editing.disable()
      }
    })
  }
  
  // Écouter les événements de dessin
  map.value.on(L.Draw.Event.CREATED, (event) => {
    const layer = event.layer
    drawnItems.value.addLayer(layer)
    
    // Créer la feature
    const feature = createFeatureFromLayer(layer, event.layerType)
    if (feature) {
      unsavedFeatures.value.push(feature)
      hasUnsavedChanges.value = true
      
      // Marquer le layer comme non sauvegardé
      layer.isUnsaved = true
      layer.featureData = feature
    }
  })
  
  map.value.on(L.Draw.Event.DELETED, (event) => {
    event.layers.eachLayer(layer => {
      if (layer.isUnsaved) {
        // Retirer des features non sauvegardées
        const index = unsavedFeatures.value.findIndex(f => f === layer.featureData)
        if (index > -1) {
          unsavedFeatures.value.splice(index, 1)
        }
      } else {
        // Marquer pour suppression
        unsavedFeatures.value.push({
          id: layer.featureId,
          action: 'delete'
        })
      }
    })
    hasUnsavedChanges.value = true
  })
  
  // Créer une feature depuis un layer Leaflet
  function createFeatureFromLayer(layer, layerType) {
    const mapId = props.mapId
    
    switch (layerType) {
      case 'marker':
        const latlng = layer.getLatLng()
        return {
          map_id: mapId,
          type: 'point',
          geometry: {
            type: 'Point',
            coordinates: [latlng.lng, latlng.lat]
          },
          color: '#000000',
          opacity: 1.0,
          z_index: 1
        }
        
      case 'polyline':
        const latlngs = layer.getLatLngs()
        return {
          map_id: mapId,
          type: 'polyline',
          geometry: {
            type: 'LineString',
            coordinates: latlngs.map(ll => [ll.lng, ll.lat])
          },
          color: '#000000',
          stroke_width: 2,
          opacity: 1.0,
          z_index: 1
        }
        
      case 'polygon':
        const polygonLatlngs = layer.getLatLngs()[0] // Premier ring
        return {
          map_id: mapId,
          type: 'polygon',
          geometry: {
            type: 'Polygon',
            coordinates: [polygonLatlngs.map(ll => [ll.lng, ll.lat])]
          },
          color: '#cccccc',
          opacity: 0.5,
          z_index: 1
        }
        
      default:
        return null
    }
  }
  
  // Sauvegarder les changements
  async function saveChanges() {
    try {
      for (const feature of unsavedFeatures.value) {
        if (feature.action === 'delete') {
          await deleteFeature(feature.id)
        } else if (feature.id) {
          await updateFeature(feature)
        } else {
          await createFeature(feature)
        }
      }
      
      unsavedFeatures.value = []
      hasUnsavedChanges.value = false
      
      // Recharger les features
      emit('features-updated')
      
    } catch (error) {
      console.error('Erreur lors de la sauvegarde:', error)
      alert('Erreur lors de la sauvegarde des modifications')
    }
  }
  
  // Annuler l'édition
  function cancelEdit() {
    // Recharger les features depuis le serveur
    loadExistingFeatures()
    unsavedFeatures.value = []
    hasUnsavedChanges.value = false
    activeMode.value = null
    disableDrawMode()
  }
  
  // API calls
  async function createFeature(featureData) {
    const response = await fetch('${import.meta.env.VITE_API_URL}/maps/features', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(featureData)
    })
    
    if (!response.ok) {
      throw new Error('Failed to create feature')
    }
    
    return response.json()
  }
  
  async function updateFeature(featureData) {
    const response = await fetch(`${import.meta.env.VITE_API_URL}/maps/features/${featureData.id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(featureData)
    })
    
    if (!response.ok) {
      throw new Error('Failed to update feature')
    }
    
    return response.json()
  }
  
  async function deleteFeature(featureId) {
    const response = await fetch(`${import.meta.env.VITE_API_URL}/maps/features/${featureId}`, {
      method: 'DELETE'
    })
    
    if (!response.ok) {
      throw new Error('Failed to delete feature')
    }
  }
  </script>
  
  <style scoped>
  .edit-toolbar {
    min-width: 300px;
  }
  
  .map-editor {
    position: relative;
    height: 100%;
    width: 100%;
  }
  
  /* Styles pour Leaflet.Draw */
  :deep(.leaflet-draw-toolbar) {
    display: none; /* Cacher la toolbar par défaut */
  }
  </style>
