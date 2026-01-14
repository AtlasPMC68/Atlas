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

    <!-- Save modal -->
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
import { useRouter } from "vue-router";

const mapId = ref("11111111-1111-1111-1111-111111111111");
const features = ref([]);
const featureVisibility = ref(new Map());
const error = ref("");
const router = useRouter();

const showSaveAsModal = ref(false);

const title = ref("");
const description = ref("");
const access_level = ref("");

async function loadInitialFeatures() {
  try {
    const res = await fetch(
      `http://localhost:8000/maps/features/${mapId.value}`,
    );
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
  console.log("Quick save");
  // appel API ou logique de sauvegarde ici
}

function saveCarteAs() {
  showSaveAsModal.value = true;
}

async function handleSaveAs(data) {
  title.value = data.title;
  description.value = data.description;
  access_level.value = data.access_level;

  const token = localStorage.getItem("access_token");

  if (!token) {
    console.error("No token found in the localStorage.");
    return;
  }

  let userData;

  try {
    const res = await fetch(`http://localhost:8000/me`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
    });

    if (!res.ok) {
      throw new Error(`Error while getting the user : ${res.status}`);
    }

    userData = await res.json();
  } catch (err) {
    console.error("Error while fetching user :", err);
    return;
  }

  const userId = userData.id;

  try {
    const response = await fetch("http://localhost:8000/maps/save", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        owner_id: userId,
        title: title.value,
        description: description.value,
        access_level: access_level.value,
      }),
    });

    if (!response.ok) {
      const result = await response.json();
      throw new Error(result.detail || "Error while loading the maps.");
    }

    const result = await response.json();
    console.log("Map saved successfuly:", result);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Unknown error.";
  }

  showSaveAsModal.value = false;
}
</script>
