<template>
  <div class="h-full w-full bg-base-100 flex flex-col">
    <div class="flex flex-1 min-h-0">
      <div class="w-80 bg-base-200 border-r border-base-300 min-h-0">
        <FeatureVisibilityControls
          :features="features"
          :feature-visibility="featureVisibility"
          @toggle-feature="toggleFeatureVisibility"
        />
      </div>

      <div class="flex-1 min-h-0 flex flex-col">
        <div class="flex-1 min-h-0">
          <MapGeoJSON
            class="h-full w-full"
            :features="features"
            :feature-visibility="featureVisibility"
            :selected-year="selectedYear"
            @features-loaded="handleFeaturesLoaded"
            @draw-create="handleDrawChange"
            @draw-update="handleDrawChange"
            @draw-delete="handleDrawChange"
          />
        </div>

        <TimelineSlider v-model:year="selectedYear" />
      </div>
    </div>

    <SaveAsModal
      v-if="showSaveAsModal"
      @save="handleSaveAs"
      @cancel="showSaveAsModal = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import MapGeoJSON from "../components/MapGeoJSON.vue";
import TimelineSlider from "../components/TimelineSlider.vue";
import SaveAsModal from "../components/save/SaveAsModal.vue";
import FeatureVisibilityControls from "../components/FeatureVisibilityControls.vue";
import { Feature } from "../typescript/feature";
import type { MapSaveAsPayload } from "../typescript/map";
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
const showSaveAsModal = ref(false);
const selectedYear = ref(1740);
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

function saveMap() {
  console.log("Quick save");
  // appel API ou logique de sauvegarde ici
}

function saveMapAs() {
  showSaveAsModal.value = true;
}

async function handleSaveAs(map: MapSaveAsPayload) {
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

    await response.json();
    showSaveAsModal.value = false;
  } catch (err) {
    throw new Error(
      `Error while saving map: ${err instanceof Error ? err.message : String(err)}`,
    );
  }
}
</script>
