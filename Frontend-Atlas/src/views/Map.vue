<template>
  <div class="min-h-screen w-full bg-base-100 flex flex-col">
    <div class="navbar bg-base-100 shadow-lg">
      <div class="flex justify-end">
        <SaveDropdown @save="saveFeatures" />
      </div>

      <button @click="upload(mapId)" class="btn btn-primary">
        Ajouter une carte
      </button>
    </div>

    <div class="flex flex-1">
      <div class="w-80 bg-base-200 border-r border-base-300 p-4">
        <FeatureVisibilityControls
          :features="features"
          :feature-visibility="featureVisibility"
          @toggle-feature="toggleFeatureVisibility"
        />
      </div>

      <div class="flex-1">
        <MapGeoJSON
          :features="features"
          :feature-visibility="featureVisibility"
          @features-loaded="handleFeaturesLoaded"
          @draw-create="handleDrawChange"
          @draw-update="handleDrawChange"
          @draw-delete="handleDrawChange"
        />
      </div>
    </div>
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import MapGeoJSON from "../components/MapGeoJSON.vue";
import SaveDropdown from "../components/save/Dropdown.vue";
import FeatureVisibilityControls from "../components/FeatureVisibilityControls.vue";
import { Feature } from "../typescript/feature";
import { camelToSnake, snakeToCamel } from "../utils/utils";
import { useCurrentUser } from "../composables/useCurrentUser";
import keycloak from "../keycloak";

const handleDrawChange = (updatedFeatures: Feature[]) => {
  features.value = updatedFeatures;
  reconcileVisibility(updatedFeatures);
};

const route = useRoute();
const router = useRouter();
const mapId = ref(route.params.mapId as string).value;
const features = ref<Feature[]>([]);
const featureVisibility = ref<Map<string, boolean>>(new Map());
const { currentUser, fetchCurrentUser } = useCurrentUser();

function reconcileVisibility(list: Feature[]) {
  const next = new Map(featureVisibility.value);
  for (const f of list) {
    const id = f?.id;
    if (id != null && next.get(id) === undefined) {
      next.set(id, true);
    }
  }
  const ids = new Set(list.map((f) => f.id));
  for (const k of next.keys()) {
    if (!ids.has(k)) next.delete(k);
  }
  featureVisibility.value = next;
}

async function loadInitialFeatures() {
  try {
    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/maps/features/${mapId}`,
    );
    if (!res.ok) throw new Error("Failed to fetch features");

    const allFeatures = snakeToCamel(await res.json()) as Feature[];

    features.value = allFeatures;
    reconcileVisibility(allFeatures);
  } catch (e) {
    console.error("Failed to load initial map features:", e);
  }
}

function upload(mapId: string) {
  router.push(`/televersement/${mapId}`);
}

function toggleFeatureVisibility(featureId: string, visible: boolean) {
  const next = new Map(featureVisibility.value);
  next.set(featureId, visible);
  featureVisibility.value = next;
}

function handleFeaturesLoaded(_loadedFeatures: Feature[]) {}

onMounted(async () => {
  await fetchCurrentUser();
  await loadInitialFeatures();
});

async function saveFeatures() {
  if (!currentUser.value) {
    throw new Error("No authentication token or user available");
  }

  try {
    const response = await fetch(
      `${import.meta.env.VITE_API_URL}/maps/features/${mapId}`,
      {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${keycloak.token}`,
        },
        body: JSON.stringify(camelToSnake(features.value)),
      },
    );
    if (!response.ok) {
      throw new Error(`Error saving features: ${response.status}`);
    }
  } catch (err) {
    throw new Error(
      `Error while saving features: ${err instanceof Error ? err.message : String(err)}`,
    );
  }
}
</script>
