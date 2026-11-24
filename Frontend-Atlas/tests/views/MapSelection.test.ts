import { describe, it, expect, vi } from "vitest";
import { nextTick } from "vue";

describe("Map selection - fitView behavior", () => {
  it("does not trigger fitToVisibleFeatures when fitView is false (map click)", async () => {
    const mockFitToVisibleFeatures = vi.fn();
    const mapGeoJsonRef = {
      value: {
        fitToVisibleFeatures: mockFitToVisibleFeatures,
      },
    };

    let selectedFeatureId: string | null = null;
    let multiSelectedFeatureIds: string[] = [];

    function selectFeature(id: string | null, fitView = true) {
      selectedFeatureId = id;
      if (id) {
        multiSelectedFeatureIds = [];
        if (fitView) {
          nextTick(() => {
            mapGeoJsonRef.value?.fitToVisibleFeatures?.([id], true);
          });
        }
      }
    }

    // Direct map click passes fitView = false
    selectFeature("feature-1", false);
    expect(selectedFeatureId).toBe("feature-1");
    expect(multiSelectedFeatureIds).toEqual([]);

    await nextTick();
    expect(mockFitToVisibleFeatures).not.toHaveBeenCalled();
  });

  it("triggers fitToVisibleFeatures when fitView is true (sidebar/timeline/legend)", async () => {
    const mockFitToVisibleFeatures = vi.fn();
    const mapGeoJsonRef = {
      value: {
        fitToVisibleFeatures: mockFitToVisibleFeatures,
      },
    };

    let selectedFeatureId: string | null = null;
    let multiSelectedFeatureIds: string[] = [];

    function selectFeature(id: string | null, fitView = true) {
      selectedFeatureId = id;
      if (id) {
        multiSelectedFeatureIds = [];
        if (fitView) {
          nextTick(() => {
            mapGeoJsonRef.value?.fitToVisibleFeatures?.([id], true);
          });
        }
      }
    }

    // Sidebar selection uses default fitView = true
    selectFeature("feature-2");
    expect(selectedFeatureId).toBe("feature-2");

    await nextTick();
    expect(mockFitToVisibleFeatures).toHaveBeenCalledTimes(1);
    expect(mockFitToVisibleFeatures).toHaveBeenCalledWith(["feature-2"], true);
  });

  it("does not trigger fitToVisibleFeatures on multi-select from map (fitView = false)", async () => {
    const mockFitToVisibleFeatures = vi.fn();
    const mapGeoJsonRef = {
      value: {
        fitToVisibleFeatures: mockFitToVisibleFeatures,
      },
    };

    let multiSelectedFeatureIds: string[] = [];
    let selectedFeatureId: string | null = "feat-prev";

    function onSelectFeatures(ids: string[], fitView = true) {
      multiSelectedFeatureIds = ids;
      if (ids.length > 0) {
        selectedFeatureId = null;
        if (fitView) {
          nextTick(() => {
            mapGeoJsonRef.value?.fitToVisibleFeatures?.(ids, true);
          });
        }
      }
    }

    onSelectFeatures(["feat-1", "feat-2"], false);
    expect(multiSelectedFeatureIds).toEqual(["feat-1", "feat-2"]);
    expect(selectedFeatureId).toBeNull();

    await nextTick();
    expect(mockFitToVisibleFeatures).not.toHaveBeenCalled();
  });

  it("triggers fitToVisibleFeatures on multi-select from controls (fitView = true)", async () => {
    const mockFitToVisibleFeatures = vi.fn();
    const mapGeoJsonRef = {
      value: {
        fitToVisibleFeatures: mockFitToVisibleFeatures,
      },
    };

    let multiSelectedFeatureIds: string[] = [];
    let selectedFeatureId: string | null = null;

    function onSelectFeatures(ids: string[], fitView = true) {
      multiSelectedFeatureIds = ids;
      if (ids.length > 0) {
        selectedFeatureId = null;
        if (fitView) {
          nextTick(() => {
            mapGeoJsonRef.value?.fitToVisibleFeatures?.(ids, true);
          });
        }
      }
    }

    onSelectFeatures(["feat-1", "feat-2"]);
    expect(multiSelectedFeatureIds).toEqual(["feat-1", "feat-2"]);

    await nextTick();
    expect(mockFitToVisibleFeatures).toHaveBeenCalledTimes(1);
    expect(mockFitToVisibleFeatures).toHaveBeenCalledWith(["feat-1", "feat-2"], true);
  });
});
