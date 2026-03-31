<template>
  <div class="min-h-screen w-full bg-base-100 flex flex-col">
    <div class="navbar bg-base-100 shadow-lg">
      <div class="flex justify-end gap-4">
        <SaveDropdown @save="saveMap" @save-as="saveMapAs" />
        <button @click="openAddMapDialog" class="btn btn-primary">
          Ajouter une carte
        </button>
        <button
          @click="addFeatureImageDialog?.showModal()"
          class="btn btn-primary"
          :disabled="!hasActiveMap"
        >
          Ajouter une image
        </button>
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
          :features="features"
          :feature-visibility="featureVisibility"
          @features-loaded="handleFeaturesLoaded"
          @draw-create="handleDrawChange"
          @draw-update="handleDrawChange"
          @draw-delete="handleDrawChange"
          @map-ready="onMapReady"
        />
      </div>
    </div>

    <SaveAsModal
      v-if="showSaveAsModal"
      @save="handleSaveAs"
      @cancel="showSaveAsModal = false"
    />
  </div>

  <dialog id="addFeatureImageDialog" ref="addFeatureImageDialog" class="modal">
    <div class="modal-box">
      <h3 class="text-lg font-bold mb-4">Ajouter une image</h3>

      <fieldset class="fieldset">
        <input
          ref="fileInputRef"
          type="file"
          class="file-input file-input-ghost"
          accept="image/*"
          @change="onFileChange"
        />
        <label class="label">Taille maximale de 10MB</label>
      </fieldset>
      <div class="modal-action">
        <button
          class="btn"
          :disabled="isAdding"
          @click="onCloseAddFeatureImageDialog"
        >
          Annuler
        </button>
        <button
          class="btn btn-primary"
          :disabled="isAdding || !selectedFile"
          @click="onAddFeatureImage"
        >
          <span
            v-if="isAdding"
            class="loading loading-spinner loading-xs"
          ></span>
          <span v-else class="text-white">Ajouter</span>
        </button>
      </div>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button :disabled="isAdding">close</button>
    </form>
  </dialog>

  <dialog ref="addMapDialogRef" class="modal">
    <div class="modal-box p-0">
      <form @submit.prevent="createMapForProject">
        <div class="card-body">
          <h3 class="text-lg font-bold">Ajouter une carte au projet</h3>

          <fieldset class="fieldset" :disabled="isCreatingMap">
            <label class="label">Nom de la carte</label>
            <input
              v-model="newMapTitle"
              type="text"
              class="input"
              placeholder="Ex: Carte politique de 1850"
              required
            />

            <label class="label">Annee</label>
            <input
              v-model.number="newMapYear"
              type="number"
              min="1"
              max="9999"
              class="input"
              placeholder="Ex: 1850"
              required
            />
          </fieldset>

          <div class="flex justify-end gap-2 mt-6">
            <button
              type="button"
              class="btn btn-ghost"
              :disabled="isCreatingMap"
              @click="addMapDialogRef?.close()"
            >
              Annuler
            </button>
            <button
              type="submit"
              class="btn btn-primary"
              :disabled="!newMapTitle.trim() || !newMapYear || isCreatingMap"
            >
              <span
                v-if="isCreatingMap"
                class="loading loading-spinner loading-xs"
              ></span>
              <span v-else>Creer et importer</span>
            </button>
          </div>
        </div>
      </form>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button :disabled="isCreatingMap">close</button>
    </form>
  </dialog>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import MapGeoJSON from "../components/MapGeoJSON.vue";
import SaveDropdown from "../components/save/Dropdown.vue";
import SaveAsModal from "../components/save/SaveAsModal.vue";
import FeatureVisibilityControls from "../components/FeatureVisibilityControls.vue";
import { Feature } from "../typescript/feature";
import type { MapSaveAsPayload } from "../typescript/map";
import { camelToSnake, snakeToCamel } from "../utils/utils";
import { useCurrentUser } from "../composables/useCurrentUser";
import keycloak from "../keycloak";
import leafletImage from "leaflet-image";
import type { Map as LeafletMap } from "leaflet";

const handleDrawChange = (updatedFeatures: Feature[]) => {
  features.value = updatedFeatures;
  reconcileVisibility(updatedFeatures);
};

const route = useRoute();
const router = useRouter();
const mapRouteId = ref((route.params.mapId as string | undefined) ?? null).value;
const projectRouteId = ref((route.params.projectId as string | undefined) ?? null).value;
const activeMapId = ref<string | null>(null);
const projectId = ref<string | null>(null);
const features = ref<Feature[]>([]);
const featureVisibility = ref<Map<string, boolean>>(new Map());
const showSaveAsModal = ref(false);
const { currentUser, fetchCurrentUser } = useCurrentUser();
const leafletMap = ref<LeafletMap | null>(null);
const addFeatureImageDialog = ref<HTMLDialogElement | null>(null);
const addMapDialogRef = ref<HTMLDialogElement | null>(null);
const isAdding = ref(false);
const isCreatingMap = ref(false);
const newMapTitle = ref("");
const newMapYear = ref<number | null>(null);
const selectedFile = ref<File | null>(null);
const fileInputRef = ref<HTMLInputElement | null>(null);
const hasActiveMap = computed(() => Boolean(activeMapId.value));

async function onAddFeatureImage() {
  if (!selectedFile.value || !keycloak.token || !activeMapId.value) {
    onCloseAddFeatureImageDialog();
    return;
  }

  isAdding.value = true;
  try {
    const formData = new FormData();
    formData.append("image", selectedFile.value);
    formData.append("map_id", activeMapId.value);

    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/maps/${activeMapId.value}/features/image`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${keycloak.token}` },
        body: formData,
      },
    );

    if (!res.ok) {
      throw new Error(`HTTP error : ${res.status}`);
    }

    await loadInitialFeatures();
    selectedFile.value = null;
    onCloseAddFeatureImageDialog();
  } catch (e) {
    console.error("Upload image failed:", e);
  } finally {
    isAdding.value = false;
  }
}

function onMapReady(map: LeafletMap) {
  leafletMap.value = map;
}

function onCloseAddFeatureImageDialog() {
  isAdding.value = false;
  selectedFile.value = null;
  if (fileInputRef.value) {
    fileInputRef.value.value = "";
  }
  addFeatureImageDialog.value?.close();
}

function onFileChange() {
  const input = fileInputRef.value;
  selectedFile.value = input?.files?.[0] ?? null;
}

async function uploadMapThumbnail(): Promise<boolean> {
  if (!leafletMap.value || !activeMapId.value || !keycloak.token) return false;

  if (!projectId.value) {
    const resolved = await resolveRouteContext();
    if (!resolved) return false;
  }

  await new Promise<void>((resolve) =>
    requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
  );

  return await new Promise<boolean>((resolve) => {
    leafletImage(leafletMap.value as LeafletMap, async (err, canvas) => {
      if (err || !canvas) return resolve(false);

      const blob = await new Promise<Blob | null>((r) =>
        canvas.toBlob(r, "image/png"),
      );
      if (!blob) return resolve(false);

      const formData = new FormData();
      formData.append("image", blob);

      const res = await fetch(
        `${import.meta.env.VITE_API_URL}/maps/${projectId.value}/thumbnail`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${keycloak.token}` },
          body: formData,
        },
      );

      resolve(res.ok);
    });
  });
}

async function loadProjectIdForMap(): Promise<boolean> {
  if (!keycloak.token) return false;

  if (projectRouteId) {
    projectId.value = projectRouteId;
    activeMapId.value = null;
    return true;
  }

  if (!mapRouteId) return false;

  try {
    const res = await fetch(
      `${import.meta.env.VITE_API_URL}/maps/map-project/${mapRouteId}`,
      {
        method: "GET",
        headers: { Authorization: `Bearer ${keycloak.token}` },
      },
    );

    if (!res.ok) return false;

    const payload = snakeToCamel(await res.json()) as { projectId: string };
    projectId.value = payload.projectId;
    activeMapId.value = mapRouteId;
    return Boolean(projectId.value);
  } catch {
    return false;
  }
}

async function resolveRouteContext(): Promise<boolean> {
  return loadProjectIdForMap();
}

function openAddMapDialog() {
  newMapTitle.value = "";
  newMapYear.value = null;
  addMapDialogRef.value?.showModal();
}

async function createMapForProject() {
  if (!keycloak.token) return;
  const targetProjectId = projectId.value || projectRouteId;

  if (!targetProjectId || !newMapTitle.value.trim()) {
    return;
  }
  if (!newMapYear.value || newMapYear.value < 1 || newMapYear.value > 9999) {
    return;
  }

  isCreatingMap.value = true;
  try {
    const res = await fetch(`${import.meta.env.VITE_API_URL}/maps/import`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${keycloak.token}`,
      },
      body: JSON.stringify(
        camelToSnake({
          projectId: targetProjectId,
          title: newMapTitle.value.trim(),
          year: newMapYear.value,
        }),
      ),
    });

    if (!res.ok) {
      throw new Error(`Error creating map for project: ${res.status}`);
    }

    const payload = snakeToCamel(await res.json()) as { mapId: string };
    addMapDialogRef.value?.close();
    router.push(`/televersement/${payload.mapId}`);
  } catch (e) {
    console.error("Failed to create map for project:", e);
  } finally {
    isCreatingMap.value = false;
  }
}

function reconcileVisibility(list: Feature[]) {
  const next = new Map<string, boolean>(featureVisibility.value);
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
  if (!keycloak.token) {
    return;
  }

  if (!activeMapId.value && !projectId.value) {
    features.value = [];
    featureVisibility.value = new Map();
    return;
  }

  try {
    const endpoint = activeMapId.value
      ? `${import.meta.env.VITE_API_URL}/maps/features/${activeMapId.value}`
      : `${import.meta.env.VITE_API_URL}/maps/projects/${projectId.value}/features`;

    const res = await fetch(endpoint, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${keycloak.token}`,
      },
    });
    if (!res.ok) throw new Error("Failed to fetch features");

    const allFeatures = snakeToCamel(await res.json()) as Feature[];

    features.value = allFeatures;
    reconcileVisibility(allFeatures);
  } catch (e) {
    console.error("Failed to load initial map features:", e);
  }
}

function toggleFeatureVisibility(featureId: string, visible: boolean) {
  const next = new Map<string, boolean>(featureVisibility.value);
  next.set(featureId, visible);
  featureVisibility.value = next;
}

function handleFeaturesLoaded(_loadedFeatures: Feature[]) {
  if (!activeMapId.value) return;
  uploadMapThumbnail();
}

onMounted(async () => {
  await fetchCurrentUser();
  await resolveRouteContext();
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
