import { computed, ref } from "vue";
import type { Feature } from "../typescript/feature";
import type {
  FeatureSnapshot,
  FeatureTrackingCallback,
} from "../typescript/featureHistory";
import {
  buildFeatureSnapshotSignature,
  cloneFeatureSnapshot,
  trimFeatureHistoryStack,
} from "../utils/featureHistory";

export class FeatureHistoryService {
  public undoStack = ref<FeatureSnapshot[]>([]);
  public redoStack = ref<FeatureSnapshot[]>([]);
  public trackingEnabled = ref(true);

  public canUndo = computed(() => this.undoStack.value.length > 0);
  public canRedo = computed(() => this.redoStack.value.length > 0);

  constructor(private readonly limit: number = 5) {}

  commit(current: Feature[], next: Feature[]): FeatureSnapshot {
    if (!this.trackingEnabled.value) {
      return cloneFeatureSnapshot(next);
    }

    if (
      buildFeatureSnapshotSignature(current) ===
      buildFeatureSnapshotSignature(next)
    ) {
      return cloneFeatureSnapshot(current);
    }

    this.undoStack.value = trimFeatureHistoryStack(
      [cloneFeatureSnapshot(current), ...this.undoStack.value],
      this.limit,
    );
    this.redoStack.value = [];

    return cloneFeatureSnapshot(next);
  }

  undo(current: Feature[]): FeatureSnapshot {
    const previous = this.undoStack.value[0];
    if (!previous) {
      return cloneFeatureSnapshot(current);
    }

    this.undoStack.value = this.undoStack.value.slice(1);
    this.redoStack.value = trimFeatureHistoryStack(
      [cloneFeatureSnapshot(current), ...this.redoStack.value],
      this.limit,
    );

    return cloneFeatureSnapshot(previous);
  }

  redo(current: Feature[]): FeatureSnapshot {
    const next = this.redoStack.value[0];
    if (!next) {
      return cloneFeatureSnapshot(current);
    }

    this.redoStack.value = this.redoStack.value.slice(1);
    this.undoStack.value = trimFeatureHistoryStack(
      [cloneFeatureSnapshot(current), ...this.undoStack.value],
      this.limit,
    );

    return cloneFeatureSnapshot(next);
  }

  reset(initial: Feature[] = []): FeatureSnapshot {
    this.undoStack.value = [];
    this.redoStack.value = [];

    return cloneFeatureSnapshot(initial);
  }

  withoutTracking<T>(callback: FeatureTrackingCallback<T>): T {
    this.trackingEnabled.value = false;

    try {
      return callback();
    } finally {
      queueMicrotask(() => {
        this.trackingEnabled.value = true;
      });
    }
  }
}