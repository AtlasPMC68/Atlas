import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import Legend from "../../src/components/legend/Legend.vue";
import type { Feature } from "../../src/typescript/feature";

describe("Legend interactions", () => {
  const zone: Feature = {
    type: "Feature",
    id: "zone-1",
    projectId: "project-1",
    mapId: "map-1",
    name: "Zone Québec",
    geometry: {
      type: "Polygon",
      coordinates: [[
        [-71.3, 46.7],
        [-71.1, 46.7],
        [-71.1, 46.9],
        [-71.3, 46.9],
        [-71.3, 46.7],
      ]],
    },
    properties: {
      name: "Zone Québec",
      mapElementType: "zone",
      colorRgb: [255, 0, 0],
    },
  };

  it("selects a legend item on click and requests editing on double click", async () => {
    const wrapper = mount(Legend, {
      props: {
        zoneFeatures: [zone],
        featureVisibility: new Map(),
      },
    });

    const item = wrapper.find("li");
    await item.trigger("click");
    expect(wrapper.emitted("select-feature")?.[0]).toEqual(["zone-1"]);

    await item.trigger("dblclick");
    expect(wrapper.emitted("select-feature")?.[1]).toEqual(["zone-1"]);
    expect(wrapper.emitted("edit-feature")?.[0]).toEqual([zone]);
  });
});
