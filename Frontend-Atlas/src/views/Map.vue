<template>
  <div class="min-h-screen w-full bg-base-100 flex flex-col">
    <div class="navbar bg-base-100 shadow-lg">
      <div class="flex-1">
        <h1 class="text-xl font-bold">Carte démo</h1>
      </div>
    </div>
    
    <div class="flex flex-1">
      <!-- Panneau de contrôle des features -->
      <div class="w-80 bg-base-200 border-r border-base-300 p-4">
        <FeatureVisibilityControls 
          :features="features"
          :feature-visibility="featureVisibility"
          @toggle-feature="toggleFeatureVisibility"
        />
      </div>
      
      <!-- Map avec timeline intégrée -->
      <div class="flex-1">
        <MapGeoJSON 
          :map-id="mapId"
          :features="features"
          :feature-visibility="featureVisibility"
          @features-loaded="handleFeaturesLoaded"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import MapGeoJSON from '../components/MapGeoJSON.vue';
import FeatureVisibilityControls from '../components/FeatureVisibilityControls.vue';

// État global de la vue
const mapId = ref("11111111-1111-1111-1111-111111111111");
const features = ref([]);
const featureVisibility = ref(new Map());

// Fonction pour charger les features initiales
async function loadInitialFeatures() {
  try {
    const res = await fetch(`http://localhost:8000/maps/features/${mapId.value}`);
    if (!res.ok) throw new Error("Failed to fetch features");
    
    const allFeatures = await res.json();
    console.log("we got this for the features my friend", allFeatures);
    features.value = allFeatures;
    
    // Initialiser la visibilité (toutes visibles par défaut)
    const newVisibility = new Map();
    allFeatures.forEach(feature => {
      newVisibility.set(feature.id, true);
    });
    featureVisibility.value = newVisibility;
    
  } catch (error) {
    console.error("Erreur lors du chargement des features:", error);
  }
}

// Fonction pour toggle la visibilité d'une feature
function toggleFeatureVisibility(featureId, visible) {
  featureVisibility.value.set(featureId, visible);
  featureVisibility.value = new Map(featureVisibility.value);
}

// Handler quand les features sont chargées dans la map
function handleFeaturesLoaded(loadedFeatures) {
  console.log("Features chargées dans la map:", loadedFeatures);
}

// Charger les features au montage
onMounted(() => {
  loadInitialFeatures();
});
</script>