import { ref, computed } from "vue";

export function useHistory<T>(limit = 30) {
  const undoStack = ref<T[]>([]);
  const redoStack = ref<T[]>([]);

  const canUndo = computed(() => undoStack.value.length > 0);
  const canRedo = computed(() => redoStack.value.length > 0);

  function resetHistory() {
    undoStack.value = [];
    redoStack.value = [];
  }

  function pushHistory(snapshot: T) {
    undoStack.value.push(JSON.parse(JSON.stringify(snapshot)));
    if (undoStack.value.length > limit) {
      undoStack.value.shift();
    }
    redoStack.value = [];
  }

  function undo(current: T): T | null {
    if (!canUndo.value) return null;
    redoStack.value.push(JSON.parse(JSON.stringify(current)));
    if (redoStack.value.length > limit) {
      redoStack.value.shift();
    }
    return undoStack.value.pop() ?? null;
  }

  function redo(current: T): T | null {
    if (!canRedo.value) return null;
    undoStack.value.push(JSON.parse(JSON.stringify(current)));
    if (undoStack.value.length > limit) {
      undoStack.value.shift();
    }
    return redoStack.value.pop() ?? null;
  }

  return {
    undoStack,
    redoStack,
    canUndo,
    canRedo,
    resetHistory,
    pushHistory,
    undo,
    redo,
  };
}
