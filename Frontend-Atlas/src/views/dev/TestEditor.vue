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

      <div class="flex-none">
        <button class="btn btn-secondary btn-sm" type="button" @click="goToTestImport">
          Ajouter un test case
        </button>
      </div>
    </div>

    <div class="flex flex-1">
      <!-- Feature controls -->
      <div class="w-96 bg-base-200 border-r border-base-300 p-4">
        <FeatureVisibilityControls
          :features="features"
          :feature-visibility="featureVisibility"
          :is-dev-test-creation="true"
          @toggle-feature="toggleFeatureVisibility"
          @rename-feature="renameFeature"
          @delete-feature="deleteFeature"
        />
      </div>

      <!-- Leaflet map with zones and dev tools -->
      <div class="flex-1 flex">
        <div class="flex-1 flex flex-col">
          <div class="flex-1">
            <MapTestGeoJSON
              v-if="mapId"
              :map-id="mapId"
              :features="features"
              :feature-visibility="featureVisibility"
              :is-create-mode="isCreateMode"
              :reset-create-key="resetCreateKey"
              :is-frontier-mode="isFrontierMode"
              :is-geo-border-mode="isGeoBorderMode"
              :undo-create-key="undoCreateKey"
              :sub-geometries="subGeometries"
              @create-updated="handleCreateUpdated"
            />
          </div>
        </div>

    <div class="w-80 border-l border-base-300 bg-base-200 p-4 space-y-6">
      <!-- Create zone -->
      <CreateZonePanel
        :is-create-mode="isCreateMode"
        v-model:zone-name="newZoneName"
        :pending-create-geometry="pendingCreateGeometry"
        :is-frontier-mode="isFrontierMode"
        :is-geo-border-mode="isGeoBorderMode"
        :subzone-count="subGeometries.length"
        @start-create="startCreateMode"
        @cancel-create="cancelCreateMode"
        @undo-last-stroke="undoLastStroke"
        @toggle-frontier="toggleFrontierMode"
        @toggle-geo-border="toggleGeoBorderMode"
        @save-zone="saveCreatedZone"
        @add-subzone="addSubzone"
      />

      <!-- Test cases list -->
      <div class="bg-base-100 rounded-box border border-base-300 p-3">
        <div class="flex items-center justify-between gap-2">
          <h2 class="text-sm font-semibold">Test cases</h2>
          <span class="text-xs text-base-content/60">{{ testCases.length }}</span>
        </div>

        <div v-if="isLoadingTestCases" class="text-sm text-base-content/60 mt-2">
          Chargement…
        </div>

        <div
          v-else-if="testCases.length === 0"
          class="text-sm text-base-content/60 mt-2"
        >
          Aucun test case pour ce test.
        </div>

        <div v-else class="mt-2 space-y-2">
          <button
            v-for="tc in testCases"
            :key="tc"
            type="button"
            class="btn btn-sm btn-outline w-full justify-start"
            @click="openTestCaseResult(tc)"
          >
            {{ tc }}
          </button>
        </div>
      </div>

      </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import MapTestGeoJSON from "../../components/dev/MapTestGeoJSON.vue";
import FeatureVisibilityControls from "../../components/FeatureVisibilityControls.vue";
import CreateZonePanel from "../../components/dev/CreateZonePanel.vue";
import type { Feature } from "../../typescript/feature";
import keycloak from "../../keycloak";

const route = useRoute();
const router = useRouter();
const mapId = ref<string | null>(null);
const features = ref<Feature[]>([]);
const featureVisibility = ref(new Map<string, boolean>());

const isCreateMode = ref(false);
const pendingCreateGeometry = ref<any | null>(null);
const resetCreateKey = ref(0);
const newZoneName = ref("");
const undoCreateKey = ref(0);
const isFrontierMode = ref(false);
const isGeoBorderMode = ref(false);
const subGeometries = ref<any[]>([]);

const testCases = ref<string[]>([]);
const isLoadingTestCases = ref(false);

async function loadTestCases(currentMapId: string) {
  isLoadingTestCases.value = true;
  try {
    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/dev-test-api/test-cases/${currentMapId}`,
    );
    if (!res.ok) {
      testCases.value = [];
      return;
    }

    const data = await res.json();
    testCases.value = Array.isArray(data)
      ? data.filter((x) => typeof x === "string")
      : [];
  } catch {
    testCases.value = [];
  } finally {
    isLoadingTestCases.value = false;
  }
}

async function loadTestZones(currentMapId: string) {
  try {
    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/dev-test-api/georef_zones/${currentMapId}`,
    );
    if (!res.ok) {
      // For a brand-new test map, it's normal to have no zones yet.
      if (res.status === 404) {
        features.value = [];
        featureVisibility.value = new Map();
        return;
      }

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

async function renameFeature(featureId: string) {
  const feature = features.value.find((f) => f.id === featureId);
  if (!feature) return;

  const currentName = (feature.properties as any)?.name || "";
  const newName = window.prompt("Nouveau nom de la zone", currentName) ?? "";
  const trimmed = newName.trim();
  if (!trimmed || trimmed === currentName) return;

  if (!feature.properties) {
    (feature as any).properties = {};
  }
  (feature.properties as any).name = trimmed;

  // Reassign array to ensure reactivity
  features.value = [...features.value];

  await persistZonesToBackend();
}

async function deleteFeature(featureId: string) {
  // Only allow deletion of features that actually exist in this test
  const existing = features.value.find((f) => f.id === featureId);
  if (!existing) return;

  const confirmed = window.confirm(
    `Supprimer la zone "${(existing.properties as any)?.name ?? featureId}" ?`,
  );
  if (!confirmed) return;

  features.value = features.value.filter((f) => f.id !== featureId);
  featureVisibility.value.delete(featureId);
  featureVisibility.value = new Map(featureVisibility.value);

  await persistZonesToBackend();
}

function handleCreateUpdated(geometry: any | null) {
  pendingCreateGeometry.value = geometry;
}

async function persistZonesToBackend() {
  if (!mapId.value) return;

  const payload = {
    type: "FeatureCollection",
    features: features.value,
  };

  try {
    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/dev-test-api/georef_zones/${mapId.value}`,
      {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${keycloak.token}`,
        },
        body: JSON.stringify(payload),
      },
    );

    if (res.status === 401 || res.status === 403) {
      console.error("Not authorised to persist test zones", res.status);
      return;
    }

    if (!res.ok) {
      console.error("Failed to persist test zones", res.status);
    }
  } catch (err) {
    console.error("Error persisting test zones:", err);
  }
}

function clearCreateDrawing() {
  pendingCreateGeometry.value = null;
  subGeometries.value = [];
  newZoneName.value = "";
  resetCreateKey.value += 1;
  isFrontierMode.value = false;
  isGeoBorderMode.value = false;
}

function startCreateMode() {
  isCreateMode.value = true;
  clearCreateDrawing();
}

function cancelCreateMode() {
  // If nothing has been drawn, cancel silently
  if (!pendingCreateGeometry.value && subGeometries.value.length === 0) {
    isCreateMode.value = false;
    clearCreateDrawing();
    return;
  }

  const confirmed = window.confirm(
    "Annuler la création de la zone ? Les formes dessinées seront perdues.",
  );
  if (!confirmed) return;

  isCreateMode.value = false;
  clearCreateDrawing();
}

function undoLastStroke() {
  if (!isCreateMode.value) return;
  undoCreateKey.value += 1;
}

function toggleFrontierMode() {
  if (!isCreateMode.value) return;
  isFrontierMode.value = !isFrontierMode.value;
  if (isFrontierMode.value) {
    isGeoBorderMode.value = false;
  }
}

function toggleGeoBorderMode() {
  if (!isCreateMode.value) return;
  isGeoBorderMode.value = !isGeoBorderMode.value;
  if (isGeoBorderMode.value) {
    isFrontierMode.value = false;
  }
}

async function saveCreatedZone() {
  if (!pendingCreateGeometry.value && subGeometries.value.length === 0) {
    console.warn("No geometry to save for new zone");
    return;
  }

  let geometry: any;

  if (subGeometries.value.length === 0) {
    geometry = pendingCreateGeometry.value;
  } else {
    const allPolygons = [
      ...subGeometries.value,
      ...(pendingCreateGeometry.value ? [pendingCreateGeometry.value] : []),
    ];

    const rings = allPolygons
      .filter((g) => g && g.type === "Polygon" && Array.isArray(g.coordinates))
      .map((g) => g.coordinates[0]);

    if (rings.length === 1) {
      geometry = {
        type: "Polygon",
        coordinates: [rings[0]],
      };
    } else {
      geometry = {
        type: "MultiPolygon",
        coordinates: rings.map((ring) => [ring]),
      };
    }
  }

  const id = `dev-zone-${Date.now()}`;
  const feature: Feature = {
    type: "Feature",
    id,
    geometry,
    properties: {
      name: newZoneName.value || id,
      mapElementType: "zone",
    },
  } as any;

  features.value = [...features.value, feature];

  await persistZonesToBackend();

  isCreateMode.value = false;
  clearCreateDrawing();
}

function addSubzone() {
  if (!pendingCreateGeometry.value) return;

  subGeometries.value = [...subGeometries.value, pendingCreateGeometry.value];
  pendingCreateGeometry.value = null;
  resetCreateKey.value += 1;
}

onMounted(() => {
  const idParam = route.params.mapId;
  if (typeof idParam === "string" && idParam.length > 0) {
    mapId.value = idParam;
    loadTestZones(idParam);
    loadTestCases(idParam);
  } else {
    console.error("No mapId route param provided for TestEditor");
  }
});

function goToTestImport() {
  if (!mapId.value) return;
  router.push({ path: `/demo/upload-test/${mapId.value}` });
}

function openTestCaseResult(testCaseId: string) {
  if (!mapId.value) return;
  router.push({
    path: `/test-editor/${mapId.value}/case/${encodeURIComponent(testCaseId)}`,
  });
}
</script>
