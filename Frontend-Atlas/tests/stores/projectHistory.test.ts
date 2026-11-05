import { describe, it, expect, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { useProjectHistoryStore } from "../../src/stores/projectHistory";
import type { Feature } from "../../src/typescript/feature";

describe("useProjectHistoryStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  const featA: Feature = {
    type: "Feature",
    id: "feat-1",
    projectId: "p1",
    name: "Québec",
    geometry: { type: "Point", coordinates: [-71.2, 46.8] },
    properties: { name: "Québec", colorName: "blue" },
    createdAt: "2026-01-01",
    updatedAt: "2026-01-01",
  };

  const featB: Feature = {
    type: "Feature",
    id: "feat-2",
    projectId: "p1",
    name: "Montréal",
    geometry: { type: "Point", coordinates: [-73.5, 45.5] },
    properties: { name: "Montréal", colorName: "red" },
    createdAt: "2026-01-01",
    updatedAt: "2026-01-01",
  };

  it("initializes with empty stacks and canUndo/canRedo as false", () => {
    const store = useProjectHistoryStore();
    expect(store.undoStack).toHaveLength(0);
    expect(store.redoStack).toHaveLength(0);
    expect(store.canUndo).toBe(false);
    expect(store.canRedo).toBe(false);
    expect(store.undoCount).toBe(0);
    expect(store.redoCount).toBe(0);
    expect(store.lastActionLabel).toBeNull();
  });

  it("commits a change, updates canUndo and records action label", () => {
    const store = useProjectHistoryStore();
    const state0: Feature[] = [];
    const state1: Feature[] = [featA];

    const result = store.commit(state0, state1, "Ajout Québec");

    expect(result).toHaveLength(1);
    expect(result[0].name).toBe("Québec");
    expect(store.canUndo).toBe(true);
    expect(store.canRedo).toBe(false);
    expect(store.undoCount).toBe(1);
    expect(store.lastActionLabel).toBe("Ajout Québec");
    expect(store.undoStack[0].features).toHaveLength(0);
  });

  it("ignores commits when state signature has not changed (prevents empty undo spam)", () => {
    const store = useProjectHistoryStore();
    const state1: Feature[] = [featA];
    const state1Clone: Feature[] = [{ ...featA, properties: { ...featA.properties } }];

    store.commit([], state1, "Action 1");
    expect(store.undoCount).toBe(1);

    // Commit identical state
    store.commit(state1, state1Clone, "Action redundante");
    expect(store.undoCount).toBe(1); // stack should not grow
  });

  it("handles undo and redo correctly", () => {
    const store = useProjectHistoryStore();
    const s0: Feature[] = [];
    const s1: Feature[] = [featA];
    const s2: Feature[] = [featA, featB];

    store.commit(s0, s1, "Ajout 1");
    store.commit(s1, s2, "Ajout 2");

    expect(store.undoCount).toBe(2);
    expect(store.canUndo).toBe(true);
    expect(store.canRedo).toBe(false);

    // Undo s2 -> s1
    const restored1 = store.undo(s2);
    expect(restored1).toHaveLength(1);
    expect(restored1[0].id).toBe("feat-1");
    expect(store.canUndo).toBe(true);
    expect(store.canRedo).toBe(true);
    expect(store.undoCount).toBe(1);
    expect(store.redoCount).toBe(1);

    // Redo s1 -> s2
    const restored2 = store.redo(restored1);
    expect(restored2).toHaveLength(2);
    expect(restored2.map((f) => f.id)).toEqual(["feat-1", "feat-2"]);
    expect(store.canUndo).toBe(true);
    expect(store.canRedo).toBe(false);
    expect(store.undoCount).toBe(2);
    expect(store.redoCount).toBe(0);
  });

  it("enforces maxLimit on undo stack to prevent memory bloat", () => {
    const store = useProjectHistoryStore();
    store.setMaxLimit(3);

    for (let i = 0; i < 6; i++) {
      const current: Feature[] = [{ ...featA, name: `Nom ${i}` }];
      const next: Feature[] = [{ ...featA, name: `Nom ${i + 1}` }];
      store.commit(current, next, `Action ${i}`);
    }

    expect(store.undoStack.length).toBeLessThanOrEqual(3);
  });

  it("resets undo and redo stacks when reset is called", () => {
    const store = useProjectHistoryStore();
    store.commit([], [featA], "Action");
    expect(store.canUndo).toBe(true);

    store.reset([featA]);
    expect(store.canUndo).toBe(false);
    expect(store.canRedo).toBe(false);
    expect(store.undoStack).toHaveLength(0);
    expect(store.redoStack).toHaveLength(0);
  });

  it("supports withoutTracking to perform silent updates", () => {
    const store = useProjectHistoryStore();

    store.withoutTracking(() => {
      expect(store.trackingEnabled).toBe(false);
      store.commit([], [featA], "Silent Action");
    });

    expect(store.undoCount).toBe(0);
  });
});
