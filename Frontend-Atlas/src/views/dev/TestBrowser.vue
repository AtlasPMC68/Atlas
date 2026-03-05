<script setup lang="ts">
import { ref, onMounted, watch } from "vue";
import { useRoute } from "vue-router";
import MapTestGeoJSON from "../../components/MapTestGeoJSON.vue";
import FeatureVisibilityControls from "../../components/FeatureVisibilityControls.vue";
import type { Feature } from "../../typescript/feature";

const route = useRoute();
const mapId = ref<string | null>(null);
const features = ref<Feature[]>([]);
const featureVisibility = ref(new Map<string, boolean>());
const showImage = ref(false);
const mapImageUrl = ref<string | null>(null);

const imageExtCandidates = [".png", ".jpg", ".jpeg"];
const imageExtIndex = ref(0);

function buildImageUrl(id: string, extIndex: number) {
  const ext = imageExtCandidates[extIndex] ?? ".png";
  return `${import.meta.env.VITE_API_URL}/dev-test/maps/${id}${ext}`;
}

async function loadTestZones(currentMapId: string) {
  try {
    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/dev-test/georef_zones/${currentMapId}_zones.geojson`,
    );
    if (!res.ok) {
      console.error("Failed to fetch test zones GeoJSON", res.status);
      return;
    }

    const data = await res.json();
    const rawFeatures: any[] = Array.isArray(data.features) ? data.features : [];

    const withIds: Feature[] = rawFeatures.map((f, idx) => ({
      ...f,
      id: f.id ?? `${currentMapId}-${idx}`,
    }));

    features.value = withIds;

    const vis = new Map<string, boolean>();
    withIds.forEach((f) => {
      if (f.id) vis.set(f.id, true);
    });
    featureVisibility.value = vis;
  } catch (err) {
    console.error("Error loading test zones:", err);
  }
}

function toggleFeatureVisibility(featureId: string, visible: boolean) {
  featureVisibility.value.set(featureId, visible);
  featureVisibility.value = new Map(featureVisibility.value);
}

function handleFeaturesLoaded(_loaded: Feature[]) {
  // Placeholder for future dev tooling if needed
}

function handleImageError() {
  if (!mapId.value) return;

  if (imageExtIndex.value < imageExtCandidates.length - 1) {
    imageExtIndex.value += 1;
    mapImageUrl.value = buildImageUrl(mapId.value, imageExtIndex.value);
  } else {
    console.error("Failed to load test map image for", mapId.value);
    mapImageUrl.value = null;
  }
}

onMounted(() => {
  const idParam = route.params.mapId;
  if (typeof idParam === "string" && idParam.length > 0) {
    mapId.value = idParam;
    loadTestZones(idParam);
  } else {
    console.error("No mapId route param provided for TestBrowser");
  }
});

watch(
  showImage,
  (val) => {
    if (val && mapId.value) {
      imageExtIndex.value = 0;
      mapImageUrl.value = buildImageUrl(mapId.value, imageExtIndex.value);
    } else if (!val) {
      mapImageUrl.value = null;
    }
  },
);
</script>

<template>
  <div class="min-h-screen w-full bg-base-100 flex flex-col">
    <div class="navbar bg-base-100 shadow-lg">
      <div class="flex-1">
        <h1 class="text-xl font-bold">
          Test editor
          <span
            v-if="mapId"
            class="ml-2 text-sm font-normal text-base-content/60"
          >
            ({{ mapId }})
          </span>
        </h1>
      </div>
    </div>

    <div class="flex flex-1">
      <!-- Feature controls -->
      <div class="w-80 bg-base-200 border-r border-base-300 p-4">
        <FeatureVisibilityControls
          :features="features"
          :feature-visibility="featureVisibility"
          @toggle-feature="toggleFeatureVisibility"
        />
      </div>

      <!-- Leaflet map with zones and image overlay + external controls -->
      <div class="flex-1 flex">
        <div class="flex-1">
          <MapTestGeoJSON
            v-if="mapId"
            :map-id="mapId"
            :features="features"
            :feature-visibility="featureVisibility"
            @features-loaded="handleFeaturesLoaded"
          />
        </div>

      <div class="w-80 border-l border-base-300 bg-base-200 p-4 space-y-4">
        <h2 class="text-sm font-semibold mb-2">Image de carte</h2>
        <label class="flex items-center gap-2">
          <input
            type="checkbox"
            v-model="showImage"
            class="checkbox checkbox-xs checkbox-primary"
          />
          <span class="text-sm">Afficher l'image de la carte</span>
        </label>

        <div v-if="showImage" class="mt-2">
          <div
            v-if="mapImageUrl"
            class="w-full h-full flex items-center justify-center"
          >
            <img
              :src="mapImageUrl"
              alt="Test map source"
              class="max-w-full max-h-[70vh] object-contain rounded shadow"
              @error="handleImageError"
            />
          </div>
          <div v-else class="text-xs text-base-content/60 text-center mt-4">
            Aucune image de carte trouvée.
          </div>
        </div>
      </div>
      </div>
    </div>
  </div>
</template>
