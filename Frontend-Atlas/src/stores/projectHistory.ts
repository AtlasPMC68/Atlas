import { defineStore } from "pinia";
import { ref, computed } from "vue";
import type { Feature } from "../typescript/feature";
import {
  cloneFeatureSnapshot,
  buildFeatureSnapshotSignature,
  trimFeatureHistoryStack,
} from "../utils/featureHistory";

export interface ProjectHistoryEntry {
  features: Feature[];
  label?: string;
  timestamp: number;
}

export const useProjectHistoryStore = defineStore("projectHistory", () => {
  const undoStack = ref<ProjectHistoryEntry[]>([]);
  const redoStack = ref<ProjectHistoryEntry[]>([]);
  const trackingEnabled = ref(true);
  const maxLimit = ref(30);
  const currentSignature = ref("");

  const canUndo = computed(() => undoStack.value.length > 0);
  const canRedo = computed(() => redoStack.value.length > 0);
  const undoCount = computed(() => undoStack.value.length);
  const redoCount = computed(() => redoStack.value.length);
  const lastActionLabel = computed<string | null>(() =>
    undoStack.value.length > 0 ? (undoStack.value[0].label ?? null) : null,
  );

  /**
   * Enregistre un nouvel état dans la pile d'historique.
   * Ignore les modifications si le tracking est désactivé ou si le contenu est identique.
   */
  function commit(
    currentFeatures: Feature[],
    nextFeatures: Feature[],
    label?: string,
  ): Feature[] {
    if (!trackingEnabled.value) {
      return cloneFeatureSnapshot(nextFeatures);
    }

    const currentSig = buildFeatureSnapshotSignature(currentFeatures);
    const nextSig = buildFeatureSnapshotSignature(nextFeatures);

    // Si le contenu n'a pas changé, ne pas polluer l'historique
    if (currentSig === nextSig) {
      return cloneFeatureSnapshot(currentFeatures);
    }

    const entry: ProjectHistoryEntry = {
      features: cloneFeatureSnapshot(currentFeatures),
      label,
      timestamp: Date.now(),
    };

    undoStack.value = trimFeatureHistoryStack(
      [entry, ...undoStack.value],
      maxLimit.value,
    );
    redoStack.value = [];
    currentSignature.value = nextSig;

    return cloneFeatureSnapshot(nextFeatures);
  }

  /**
   * Annule la dernière action et renvoie l'état précédent.
   */
  function undo(currentFeatures: Feature[]): Feature[] {
    if (!canUndo.value) {
      return cloneFeatureSnapshot(currentFeatures);
    }

    const previousEntry = undoStack.value[0];
    undoStack.value = undoStack.value.slice(1);

    const currentEntry: ProjectHistoryEntry = {
      features: cloneFeatureSnapshot(currentFeatures),
      label: previousEntry.label,
      timestamp: Date.now(),
    };

    redoStack.value = trimFeatureHistoryStack(
      [currentEntry, ...redoStack.value],
      maxLimit.value,
    );
    currentSignature.value = buildFeatureSnapshotSignature(previousEntry.features);

    return cloneFeatureSnapshot(previousEntry.features);
  }

  /**
   * Rétablit la dernière action annulée et renvoie le nouvel état.
   */
  function redo(currentFeatures: Feature[]): Feature[] {
    if (!canRedo.value) {
      return cloneFeatureSnapshot(currentFeatures);
    }

    const nextEntry = redoStack.value[0];
    redoStack.value = redoStack.value.slice(1);

    const currentEntry: ProjectHistoryEntry = {
      features: cloneFeatureSnapshot(currentFeatures),
      label: nextEntry.label,
      timestamp: Date.now(),
    };

    undoStack.value = trimFeatureHistoryStack(
      [currentEntry, ...undoStack.value],
      maxLimit.value,
    );
    currentSignature.value = buildFeatureSnapshotSignature(nextEntry.features);

    return cloneFeatureSnapshot(nextEntry.features);
  }

  /**
   * Réinitialise les piles d'historique (ex: changement de carte ou de projet).
   */
  function reset(initialFeatures: Feature[] = []): Feature[] {
    undoStack.value = [];
    redoStack.value = [];
    currentSignature.value = buildFeatureSnapshotSignature(initialFeatures);
    return cloneFeatureSnapshot(initialFeatures);
  }

  /**
   * Exécute une opération sans enregistrer d'action dans l'historique.
   */
  function withoutTracking<T>(callback: () => T): T {
    const prev = trackingEnabled.value;
    trackingEnabled.value = false;
    try {
      return callback();
    } finally {
      queueMicrotask(() => {
        trackingEnabled.value = prev;
      });
    }
  }

  function setTrackingEnabled(enabled: boolean) {
    trackingEnabled.value = enabled;
  }

  function setMaxLimit(limit: number) {
    maxLimit.value = Math.max(1, limit);
  }

  return {
    undoStack,
    redoStack,
    trackingEnabled,
    maxLimit,
    currentSignature,
    canUndo,
    canRedo,
    undoCount,
    redoCount,
    lastActionLabel,
    commit,
    undo,
    redo,
    reset,
    withoutTracking,
    setTrackingEnabled,
    setMaxLimit,
  };
});
