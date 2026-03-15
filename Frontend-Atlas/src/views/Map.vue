<template>
  <div class="min-h-screen w-full bg-base-100 flex flex-col">
    <div class="navbar bg-base-100 shadow-lg">
      <div class="flex justify-end">
        <SaveDropdown @save="saveMap" @save-as="saveMapAs" />
      </div>
      <div class="flex-1">
        <h1 class="text-xl font-bold">Carte démo</h1>
      </div>
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
          :map-id="mapId"
          :features="features"
          :feature-visibility="featureVisibility"
          :resize-feature-id="resizeFeatureId"
          @features-loaded="handleFeaturesLoaded"
        />
      </div>
    </div>

    <SaveAsModal v-if="showSaveAsModal" @save="handleSaveAs" @cancel="showSaveAsModal = false" />
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
import { MapData} from "../typescript/map";
import { camelToSnake } from "../utils/utils";
import { useCurrentUser } from "../composables/useCurrentUser";
import { normalizeFeatures } from "../utils/featureTypes";
import keycloak from "../keycloak";

const route = useRoute();
const mapId = ref(route.params.mapId as string);
const features = ref<Feature[]>([]);
const featureVisibility = ref<Map<string, boolean>>(new Map());
const showSaveAsModal = ref(false);
const { currentUser, fetchCurrentUser } = useCurrentUser();

const resizeFeatureId = ref<string | null>(null);

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
    const res = await fetch(`${import.meta.env.VITE_API_URL}/maps/features/${mapId.value}`);
    if (!res.ok) throw new Error("Failed to fetch features");

    const allFeatures = await res.json();
    const normalized = normalizeFeatures(allFeatures) as Feature[];

    features.value = normalized;
    reconcileVisibility(normalized);
  } catch (e) {
    console.error("Failed to load initial map features:", e);
  }
}

function toggleFeatureVisibility(featureId: string, visible: boolean) {
  const next = new Map(featureVisibility.value);
  next.set(featureId, visible);
  featureVisibility.value = next;
}

function handleFeaturesLoaded(updated: unknown) {
  if (!Array.isArray(updated)) return;

  const normalized = normalizeFeatures(updated) as Feature[];
  features.value = normalized;
  reconcileVisibility(normalized);
}

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

    await response.json();
  } catch (err) {
    console.error("Error while saving map:", err);
  }
}
</script>
