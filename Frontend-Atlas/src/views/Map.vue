<template>
  <div class="min-h-screen w-full bg-base-100 flex flex-col">
    <div class="navbar bg-base-100 shadow-lg">
      <div class="flex justify-end">
        <SaveDropdown @save="saveCarte" @save-as="saveCarteAs" />
      </div>
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
    <SaveAsModal
      v-if="showSaveAsModal"
      @save="handleSaveAs"
      @cancel="showSaveAsModal = false"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import MapGeoJSON from "../components/MapGeoJSON.vue";
import FeatureVisibilityControls from "../components/FeatureVisibilityControls.vue";
import SaveDropdown from "../components/save/Dropdown.vue";
import SaveAsModal from "../components/save/SaveAsModal.vue";

const mapId = ref("11111111-1111-1111-1111-111111111111");
const features = ref([]);
const featureVisibility = ref(new Map());

const showSaveAsModal = ref(false);

async function loadInitialFeatures() {
  try {
    const res = await fetch(`http://localhost:8000/maps/features/${mapId.value}`);
    if (!res.ok) throw new Error("Failed to fetch features");

    const allFeatures = await res.json();
    features.value = allFeatures;

    const newVisibility = new Map();
    allFeatures.forEach((feature) => {
      newVisibility.set(feature.id, true);
    });
    featureVisibility.value = newVisibility;
  } catch (error) {
    console.error("Erreur lors du chargement des features:", error);
  }
}

function toggleFeatureVisibility(featureId, visible) {
  featureVisibility.value.set(featureId, visible);
  featureVisibility.value = new Map(featureVisibility.value);
}

function handleFeaturesLoaded(loadedFeatures) {
  console.log("Features chargées dans la map:", loadedFeatures);
}

onMounted(() => {
  loadInitialFeatures();
});

function saveCarte() {
  console.log("Sauvegarde rapide");
  // appel API ou logique de sauvegarde ici
}

function saveCarteAs() {
  showSaveAsModal.value = true;
}

function handleSaveAs(data) {
  console.log("Sauvegarde personnalisée :", data);
  // appel API ici avec data.title, data.description, data.visibility
  showSaveAsModal.value = false;
}
</script>
