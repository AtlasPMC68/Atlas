<template>
  <div class="min-h-screen w-full bg-base-100 flex flex-col">
    <div class="navbar bg-base-100 shadow-lg">
      <div class="flex justify-end gap-2 items-center">
        <button
          class="btn btn-outline"
          :disabled="!canUndo"
          title="Undo (Ctrl+Z)"
          @click="undoLastAction"
        >
          Undo
        </button>
        <button
          class="btn btn-outline"
          :disabled="!canRedo"
          title="Redo (Ctrl+Y / Ctrl+Shift+Z)"
          @click="redoLastAction"
        >
          Redo
        </button>
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
          ref="mapGeoJsonRef"
          :features="features"
          :feature-visibility="featureVisibility"
          @features-loaded="handleFeaturesLoaded"
          @draw-create="handleDrawChange"
          @draw-update="handleDrawChange"
          @draw-delete="handleDrawChange"
          @draw-delete-id="handleFeatureDelete"
        />
      </div>
    </div>
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onBeforeUnmount, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import MapGeoJSON from "../components/MapGeoJSON.vue";
import SaveDropdown from "../components/save/Dropdown.vue";
import FeatureVisibilityControls from "../components/FeatureVisibilityControls.vue";
import { Feature } from "../typescript/feature";
import { FeatureHistoryService } from "../services/FeatureHistoryService";
import type {
  AtomicHistoryAction,
  BatchHistoryAction,
  HistoryAction,
} from "../typescript/history";
import {
  camelToSnake,
  prepareFeaturesForSave,
  snakeToCamel,
} from "../utils/utils";
import { useCurrentUser } from "../composables/useCurrentUser";
import keycloak from "../keycloak";

const route = useRoute();
const router = useRouter();
const mapId = ref(route.params.mapId as string).value;
const mapGeoJsonRef = ref<{
  syncFeaturesFromMapLayers: () => Feature[];
  clearDraftLayers: () => void;
} | null>(null);
const features = ref<Feature[]>([]);
const featureVisibility = ref<Map<string, boolean>>(new Map());
const { currentUser, fetchCurrentUser } = useCurrentUser();
const featureHistory = new FeatureHistoryService({ limit: 20 });
const isApplyingHistory = ref(false);
const canUndo = ref(false);
const canRedo = ref(false);
const pendingDeleteFeatureIds = ref<Set<string>>(new Set());

function syncHistoryAvailability() {
  canUndo.value = featureHistory.canUndo;
  canRedo.value = featureHistory.canRedo;
}

function areFeaturesEqual(a: Feature, b: Feature): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function buildFeatureHistoryAction(
  previousFeatures: Feature[],
  nextFeatures: Feature[],
): HistoryAction | null {
  const now = Date.now();
  const previousById = new Map(
    previousFeatures.map((feature) => [feature.id, feature]),
  );
  const nextById = new Map(
    nextFeatures.map((feature) => [feature.id, feature]),
  );
  const actions: AtomicHistoryAction[] = [];

  previousById.forEach((previousFeature, featureId) => {
    if (!nextById.has(featureId)) {
      actions.push({
        type: "delete",
        timestamp: now,
        feature: previousFeature,
      });
    }
  });

  previousById.forEach((previousFeature, featureId) => {
    const nextFeature = nextById.get(featureId);
    if (!nextFeature || areFeaturesEqual(previousFeature, nextFeature)) {
      return;
    }

    actions.push({
      type: "update",
      timestamp: now,
      featureId,
      before: previousFeature,
      after: nextFeature,
    });
  });

  nextById.forEach((nextFeature, featureId) => {
    if (!previousById.has(featureId)) {
      actions.push({
        type: "create",
        timestamp: now,
        feature: nextFeature,
      });
    }
  });

  if (actions.length === 0) {
    return null;
  }

  if (actions.length === 1) {
    return actions[0];
  }

  const batchAction: BatchHistoryAction = {
    type: "batch",
    timestamp: now,
    actions,
  };

  return batchAction;
}

function getAtomicActionsFromHistory(action: HistoryAction): AtomicHistoryAction[] {
  if (action.type === "batch") {
    return action.actions;
  }

  return [action];
}

function enqueueDeleteByFeatureId(featureId: string) {
  if (!isUuid(featureId)) return;
  const next = new Set(pendingDeleteFeatureIds.value);
  next.add(featureId);
  pendingDeleteFeatureIds.value = next;
}

function dequeueDeleteByFeatureId(featureId: string) {
  const next = new Set(pendingDeleteFeatureIds.value);
  next.delete(featureId);
  pendingDeleteFeatureIds.value = next;
}

function syncPendingDeletesFromUndoAction(action: HistoryAction) {
  const atomicActions = getAtomicActionsFromHistory(action);
  atomicActions.forEach((atomicAction) => {
    if (atomicAction.type === "delete") {
      dequeueDeleteByFeatureId(atomicAction.feature.id);
    }
  });
}

function syncPendingDeletesFromRedoAction(action: HistoryAction) {
  const atomicActions = getAtomicActionsFromHistory(action);
  atomicActions.forEach((atomicAction) => {
    if (atomicAction.type === "delete") {
      enqueueDeleteByFeatureId(atomicAction.feature.id);
    }
  });
}

const handleDrawChange = (updatedFeatures: Feature[]) => {
  const previousFeatures = features.value;
  const historyAction = buildFeatureHistoryAction(
    previousFeatures,
    updatedFeatures,
  );

  features.value = updatedFeatures;
  reconcileVisibility(updatedFeatures);

  if (historyAction && !isApplyingHistory.value) {
    featureHistory.record(historyAction);
    syncHistoryAvailability();
  }
};

function undoLastAction() {
  if (!featureHistory.canUndo) return;

  isApplyingHistory.value = true;
  try {
    const result = featureHistory.undo(features.value);
    if (result.appliedAction) {
      features.value = result.features;
      reconcileVisibility(result.features);
      syncPendingDeletesFromUndoAction(result.appliedAction);
    }
    syncHistoryAvailability();
  } finally {
    isApplyingHistory.value = false;
  }
}

function redoLastAction() {
  if (!featureHistory.canRedo) return;

  isApplyingHistory.value = true;
  try {
    const result = featureHistory.redo(features.value);
    if (result.appliedAction) {
      features.value = result.features;
      reconcileVisibility(result.features);
      syncPendingDeletesFromRedoAction(result.appliedAction);
    }
    syncHistoryAvailability();
  } finally {
    isApplyingHistory.value = false;
  }
}

function isTextInputTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;

  if (target.isContentEditable) {
    return true;
  }

  const tagName = target.tagName.toLowerCase();
  return tagName === "input" || tagName === "textarea" || tagName === "select";
}

function handleUndoRedoShortcuts(event: KeyboardEvent) {
  if (isTextInputTarget(event.target)) return;

  const isModifierPressed = event.ctrlKey || event.metaKey;
  if (!isModifierPressed) return;

  const key = event.key.toLowerCase();
  const isUndo = key === "z" && !event.shiftKey;
  const isRedo = key === "y" || (key === "z" && event.shiftKey);

  if (isUndo) {
    event.preventDefault();
    undoLastAction();
    return;
  }

  if (isRedo) {
    event.preventDefault();
    redoLastAction();
  }
}

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
    value,
  );
}

async function deleteFeatureFromApi(featureId: string) {
  if (!isUuid(featureId)) return; // Check if the featureId is a valid UUID (it could be a temporary ID for unsaved features)

  if (!currentUser.value) {
    throw new Error("No user signed in");
  }

  const response = await fetch(
    `${import.meta.env.VITE_API_URL}/maps/features/${mapId}/${featureId}`,
    {
      method: "DELETE",
      headers: {
        Authorization: `Bearer ${keycloak.token}`,
      },
    },
  );

  if (!response.ok) {
    throw new Error(`Error deleting feature ${featureId}: ${response.status}`);
  }
}

function handleFeatureDelete(featureId: string) {
  if (isApplyingHistory.value) {
    return;
  }

  enqueueDeleteByFeatureId(featureId);
}

async function flushPendingDeletes() {
  const idsToDelete = Array.from(pendingDeleteFeatureIds.value);

  for (const featureId of idsToDelete) {
    await deleteFeatureFromApi(featureId);
    dequeueDeleteByFeatureId(featureId);
  }
}

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
    featureHistory.clear();
    pendingDeleteFeatureIds.value = new Set();
    syncHistoryAvailability();
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
  window.addEventListener("keydown", handleUndoRedoShortcuts);
  await fetchCurrentUser();
  await loadInitialFeatures();
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleUndoRedoShortcuts);
});

async function saveFeatures() {
  if (!currentUser.value) {
    throw new Error("No authentication token or user available");
  }

  try {
    const syncedFeatures = mapGeoJsonRef.value?.syncFeaturesFromMapLayers();
    if (syncedFeatures) {
      features.value = syncedFeatures;
      reconcileVisibility(syncedFeatures);
    }

    await flushPendingDeletes();

    const payload = camelToSnake(prepareFeaturesForSave(features.value));

    const response = await fetch(
      `${import.meta.env.VITE_API_URL}/maps/features/${mapId}`,
      {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${keycloak.token}`,
        },
        body: JSON.stringify(payload),
      },
    );
    if (!response.ok) {
      throw new Error(`Error saving features: ${response.status}`);
    }

    mapGeoJsonRef.value?.clearDraftLayers();
  } catch (err) {
    throw new Error(
      `Error while saving features: ${err instanceof Error ? err.message : String(err)}`,
    );
  }
}
</script>
