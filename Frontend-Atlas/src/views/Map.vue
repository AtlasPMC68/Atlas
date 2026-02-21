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

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRoute } from "vue-router";
import MapGeoJSON from "../components/MapGeoJSON.vue";
import SaveDropdown from "../components/save/Dropdown.vue";
import SaveAsModal from "../components/save/SaveAsModal.vue";
import FeatureVisibilityControls from "../components/FeatureVisibilityControls.vue";
import { Feature } from "../typescript/feature";
import { MapData } from "../typescript/map";
import { camelToSnake } from "../utils/utils";
import { useCurrentUser } from "../composables/useCurrentUser";
import keycloak from "../keycloak";

const route = useRoute();
const mapId = ref(route.params.mapId as string);
const features = ref<Feature[]>([]);
const featureVisibility = ref<Map<string, boolean>>(new Map());
const showSaveAsModal = ref(false);

const { currentUser, fetchCurrentUser } = useCurrentUser();

async function loadInitialFeatures() {
  try {
    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/maps/features/${mapId.value}`,
    );
    if (!res.ok) throw new Error("Failed to fetch features");

    const allFeatures = await res.json();
    features.value = allFeatures;

    const newVisibility = new Map();
    allFeatures.forEach((feature: Feature) => {
      newVisibility.set(feature.id, true);
    });
    featureVisibility.value = newVisibility;
  } catch (error) {
    console.error("Erreur lors du chargement des features:", error);
  }
}

function toggleFeatureVisibility(featureId: string, visible: boolean) {
  featureVisibility.value.set(featureId, visible);
  featureVisibility.value = new Map(featureVisibility.value);
}

function handleFeaturesLoaded(loadedFeatures: Feature[]) {}

onMounted(async () => {
  await fetchCurrentUser();
  await loadInitialFeatures();
});

function saveCarte() {
  console.log("Quick save");
  // appel API ou logique de sauvegarde ici
}

function saveCarteAs() {
  showSaveAsModal.value = true;
}

async function handleSaveAs(map: MapData) {
  if (!keycloak.token || !currentUser.value) {
    throw new Error("No authentication token or user available");
  }

  const userId = currentUser.value.id;

  try {
    const response = await fetch(`${import.meta.env.VITE_API_URL}/maps/save`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${keycloak.token}`,
      },
      body: JSON.stringify(
        camelToSnake({
          userId: userId,
          title: map.title,
          description: map.description ? map.description : "",
          isPrivate: map.isPrivate,
        }),
      ),
    });

    if (!response.ok) {
      throw new Error("Error while saving the map");
    }

    const result = await response.json();
    console.log("Map saved successfuly:", result);
  } catch (err) {
    console.error("Error while saving map:", err);
  }
}
</script>
