import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import FeatureVisibilityControls from "../../src/components/FeatureVisibilityControls.vue";
import type { Feature } from "../../src/typescript/feature";

function createPointFeature(params: {
  id: string;
  name: string;
  coords: [number, number];
  mapId?: string;
  show?: boolean;
}): Feature {
  return {
    type: "Feature",
    id: params.id,
    projectId: "project-1",
    mapId: params.mapId ?? "map-1",
    name: params.name,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    geometry: {
      type: "Point",
      coordinates: params.coords,
    },
    properties: {
      name: params.name,
      mapElementType: "point",
      show: params.show,
      isVisible: true,
    } as any,
  };
}

describe("FeatureVisibilityControls - City Visibility and Deduplication", () => {
  it("does not display unaccepted or unmapped cities in Ville(s)", () => {
    const validCity = createPointFeature({
      id: "f-1",
      name: "Québec",
      coords: [-71.2082, 46.8139],
      show: true,
    });
    const rejectedCityWithNullIsland = createPointFeature({
      id: "f-2",
      name: "Aissouil",
      coords: [0, 0],
      show: false,
    });
    const rejectedCityWithCoords = createPointFeature({
      id: "f-3",
      name: "5",
      coords: [-72.0, 46.0],
      show: false,
    });
    const unmappedCity = createPointFeature({
      id: "f-4",
      name: "Invalide",
      coords: [0, 0],
    });

    const wrapper = mount(FeatureVisibilityControls, {
      props: {
        features: [validCity, rejectedCityWithNullIsland, rejectedCityWithCoords, unmappedCity],
        featureVisibility: new Map(),
      },
    });

    const text = wrapper.text();
    expect(text).toContain("Québec");
    expect(text).not.toContain("Aissouil");
    expect(text).not.toContain("5");
    expect(text).not.toContain("Invalide");
  });

  it("deduplicates cities having the same name or coordinates on the same map", () => {
    const quebec1 = createPointFeature({
      id: "f-1",
      name: "Québec",
      coords: [-71.2082, 46.8139],
      mapId: "map-1",
      show: true,
    });
    const quebec2Duplicate = createPointFeature({
      id: "f-2",
      name: "Québec",
      coords: [-71.2082, 46.8139],
      mapId: "map-1",
      show: true,
    });
    const montreal = createPointFeature({
      id: "f-3",
      name: "Montréal",
      coords: [-73.5673, 45.5017],
      mapId: "map-1",
      show: true,
    });

    const wrapper = mount(FeatureVisibilityControls, {
      props: {
        features: [quebec1, quebec2Duplicate, montreal],
        featureVisibility: new Map(),
      },
    });

    const renderedQuebecLabels = wrapper
      .findAll("span")
      .filter((w) => w.text().trim() === "Québec");

    // Only one "Québec" should be rendered in the list
    expect(renderedQuebecLabels).toHaveLength(1);

    const renderedMontrealLabels = wrapper
      .findAll("span")
      .filter((w) => w.text().trim() === "Montréal");
    expect(renderedMontrealLabels).toHaveLength(1);
  });

  it("does not deduplicate cities that belong to different maps", () => {
    // Two different maps: map-1 and map-2, both having a city named "Québec"
    const quebecMap1 = createPointFeature({
      id: "f-1",
      name: "Québec",
      coords: [-71.2082, 46.8139],
      mapId: "map-1",
      show: true,
    });
    const quebecMap2 = createPointFeature({
      id: "f-2",
      name: "Québec",
      coords: [-71.2082, 46.8139],
      mapId: "map-2",
      show: true,
    });
    // And an actual duplicate on map-1 that SHOULD be deduplicated
    const quebecMap1Duplicate = createPointFeature({
      id: "f-3",
      name: "Québec",
      coords: [-71.2082, 46.8139],
      mapId: "map-1",
      show: true,
    });

    const wrapper = mount(FeatureVisibilityControls, {
      props: {
        features: [quebecMap1, quebecMap2, quebecMap1Duplicate],
        featureVisibility: new Map(),
        mapPeriods: [
          {
            id: "map-1",
            title: "Carte 1763",
            color: "#ff0000",
            exactDate: false,
            startDate: "1763-01-01",
            endDate: "1763-12-31",
          },
          {
            id: "map-2",
            title: "Carte 1783",
            color: "#00ff00",
            exactDate: false,
            startDate: "1783-01-01",
            endDate: "1783-12-31",
          },
        ],
      },
    });

    const renderedQuebecLabels = wrapper
      .findAll("span")
      .filter((w) => w.text().trim() === "Québec");

    // Must have exactly 2 "Québec" entries: one under Carte 1763, one under Carte 1783
    expect(renderedQuebecLabels).toHaveLength(2);

    const fullText = wrapper.text();
    expect(fullText).toContain("Carte 1763");
    expect(fullText).toContain("Carte 1783");
  });
});

