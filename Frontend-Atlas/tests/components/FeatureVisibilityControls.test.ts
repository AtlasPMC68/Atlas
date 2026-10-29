import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import FeatureVisibilityControls from "../../src/components/FeatureVisibilityControls.vue";
import type { Feature } from "../../src/typescript/feature";
import type { MapPeriod } from "../../src/typescript/map";

// Mock alert
vi.mock("../../src/composables/useAlert", () => ({
  showAlert: vi.fn(),
  clearAlert: vi.fn(),
}));

describe("FeatureVisibilityControls - Text Validation Button", () => {
  const mapPeriods: MapPeriod[] = [
    {
      id: "map-1",
      title: "Carte Québec 1900",
      description: "",
      startDate: "1900-01-01",
      endDate: "1910-01-01",
      visible: true,
      center: [46.8, -71.2],
      zoom: 10,
    },
    {
      id: "map-2",
      title: "Carte Montréal 1950",
      description: "",
      startDate: "1950-01-01",
      endDate: "1960-01-01",
      visible: true,
      center: [45.5, -73.5],
      zoom: 10,
    },
  ];

  const features: Feature[] = [
    {
      type: "Feature",
      id: "feat-1",
      projectId: "proj-1",
      mapId: "map-1",
      name: "Québec",
      geometry: { type: "Point", coordinates: [-71.2, 46.8] },
      properties: { name: "Québec", isOcrText: true },
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
    },
    {
      type: "Feature",
      id: "feat-2",
      projectId: "proj-1",
      mapId: "map-2",
      name: "Montréal",
      geometry: { type: "Point", coordinates: [-73.5, 45.5] },
      properties: { name: "Montréal", isOcrText: true },
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
    },
  ];

  const featureVisibility = new Map<string, boolean>([
    ["feat-1", true],
    ["feat-2", true],
  ]);

  it("shows text validation button when text tab is active", () => {
    const wrapper = mount(FeatureVisibilityControls, {
      props: {
        features,
        featureVisibility,
        mapPeriods,
      },
    });

    expect(wrapper.text()).toContain("Textes non reconnus");
    expect(wrapper.text()).toContain("Examiner les rejets");
  });

  it("shows map selection dialog with available maps when multiple maps contain texts", async () => {
    const wrapper = mount(FeatureVisibilityControls, {
      props: {
        features,
        featureVisibility,
        mapPeriods,
      },
    });

    const dialog = wrapper.find('[data-testid="select-map-validation-dialog"]');
    expect(dialog.exists()).toBe(true);
    expect(dialog.text()).toContain("Carte Québec 1900");
    expect(dialog.text()).toContain("Carte Montréal 1950");
  });

  it("emits validate-texts with map ID when a map is chosen in the selection dialog", async () => {
    const wrapper = mount(FeatureVisibilityControls, {
      props: {
        features,
        featureVisibility,
        mapPeriods,
      },
    });

    // Find and click the map button in the validation dialog
    const dialog = wrapper.find('[data-testid="select-map-validation-dialog"]');
    const mapBtn = dialog
      .findAll("button")
      .find((b) => b.text().includes("Carte Montréal 1950"));
    expect(mapBtn).toBeDefined();

    await mapBtn!.trigger("click");

    expect(wrapper.emitted("validate-texts")).toBeDefined();
    expect(wrapper.emitted("validate-texts")![0]).toEqual(["map-2"]);
  });

  it("allows collapsing and expanding map groups individually using the arrow button", async () => {
    const wrapper = mount(FeatureVisibilityControls, {
      props: {
        features,
        featureVisibility,
        mapPeriods,
      },
    });

    const collapseBtn = wrapper.find(
      'button[title*="Réduire Carte Québec 1900"]',
    );
    expect(collapseBtn.exists()).toBe(true);

    // Initial state: Québec text feature is visible
    expect(wrapper.text()).toContain("Québec");

    // Click collapse
    await collapseBtn.trigger("click");

    // The collapse button title changes to Développer
    const expandBtn = wrapper.find(
      'button[title*="Développer Carte Québec 1900"]',
    );
    expect(expandBtn.exists()).toBe(true);
  });
});

describe("FeatureVisibilityControls - Word Type Selection and Font Modification", () => {
  beforeEach(() => {
    HTMLDialogElement.prototype.showModal = vi.fn();
    HTMLDialogElement.prototype.close = vi.fn();
  });

  const textFeature: Feature = {
    type: "Feature",
    id: "feat-text-1",
    projectId: "proj-1",
    mapId: "map-1",
    name: "Québec",
    geometry: { type: "Point", coordinates: [-71.2, 46.8] },
    properties: {
      name: "Québec",
      labelText: "Québec",
      mapElementType: "point",
      rawType: "city",
      sizePx: 12,
      fontStyle: "normal",
    },
    createdAt: "2026-01-01",
    updatedAt: "2026-01-01",
  };

  const zoneFeature: Feature = {
    type: "Feature",
    id: "feat-zone-1",
    projectId: "proj-1",
    mapId: "map-1",
    name: "Zone Québec",
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [-71.0, 46.0],
          [-71.0, 47.0],
          [-70.0, 47.0],
          [-70.0, 46.0],
          [-71.0, 46.0],
        ],
      ],
    },
    properties: {
      name: "Zone Québec",
      mapElementType: "zone",
      fillOpacity: 0.5,
      strokeWidth: 2,
    },
    createdAt: "2026-01-01",
    updatedAt: "2026-01-01",
  };

  it("displays word type selector when editing a word/text feature", async () => {
    const wrapper = mount(FeatureVisibilityControls, {
      props: {
        features: [textFeature],
        featureVisibility: new Map([[textFeature.id, true]]),
      },
    });

    await (wrapper.vm as any).showEditFeatureDialog(textFeature);

    const select = wrapper.find('[data-testid="word-type-select"]');
    expect(select.exists()).toBe(true);
    expect((select.element as HTMLSelectElement).value).toBe("city");
  });

  it("does not display word type selector when editing a non-text feature (e.g. zone)", async () => {
    const wrapper = mount(FeatureVisibilityControls, {
      props: {
        features: [zoneFeature],
        featureVisibility: new Map([[zoneFeature.id, true]]),
      },
    });

    await (wrapper.vm as any).showEditFeatureDialog(zoneFeature);

    const select = wrapper.find('[data-testid="word-type-select"]');
    expect(select.exists()).toBe(false);
  });

  it("updates font police and style when changing type from city to province", async () => {
    const wrapper = mount(FeatureVisibilityControls, {
      props: {
        features: [textFeature],
        featureVisibility: new Map([[textFeature.id, true]]),
      },
    });

    await (wrapper.vm as any).showEditFeatureDialog(textFeature);

    const select = wrapper.find('[data-testid="word-type-select"]');
    expect(select.exists()).toBe(true);

    // Change type to province
    await select.setValue("province");
    await select.trigger("change");

    // The text input should automatically be capitalized to uppercase
    const textInput = wrapper.findAll("input").find((i) => i.element.value === "QUÉBEC");
    expect(textInput?.element.value).toBe("QUÉBEC");

    // Click modifier button
    const modifyBtn = wrapper.findAll("button").find((b) => b.text().includes("Modifier"));
    expect(modifyBtn).toBeDefined();
    await modifyBtn!.trigger("click");

    // Verify emitted update-feature contains province styles
    expect(wrapper.emitted("update-feature")).toBeDefined();
    const emittedFeature = wrapper.emitted("update-feature")![0][0] as Feature;
    expect(emittedFeature.properties.rawType).toBe("province");
    expect(emittedFeature.properties.mapElementType).toBe("label");
    expect(emittedFeature.properties.sizePx).toBe(14);
    expect(emittedFeature.properties.fontStyle).toBe("uppercase");
    expect(emittedFeature.properties.labelText).toBe("QUÉBEC");
  });

  it("updates font police and style when changing type from province to city", async () => {
    const provinceFeature: Feature = {
      type: "Feature",
      id: "feat-prov-1",
      projectId: "proj-1",
      mapId: "map-1",
      name: "QUÉBEC",
      geometry: { type: "Point", coordinates: [-71.2, 46.8] },
      properties: {
        name: "QUÉBEC",
        labelText: "QUÉBEC",
        mapElementType: "label",
        rawType: "province",
        sizePx: 14,
        fontStyle: "uppercase",
      },
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
    };

    const wrapper = mount(FeatureVisibilityControls, {
      props: {
        features: [provinceFeature],
        featureVisibility: new Map([[provinceFeature.id, true]]),
      },
    });

    await (wrapper.vm as any).showEditFeatureDialog(provinceFeature);

    const select = wrapper.find('[data-testid="word-type-select"]');
    expect(select.exists()).toBe(true);
    expect((select.element as HTMLSelectElement).value).toBe("province");

    // Change type to city
    await select.setValue("city");
    await select.trigger("change");

    const modifyBtn = wrapper.findAll("button").find((b) => b.text().includes("Modifier"));
    await modifyBtn!.trigger("click");

    const emittedFeature = wrapper.emitted("update-feature")![0][0] as Feature;
    expect(emittedFeature.properties.rawType).toBe("city");
    expect(emittedFeature.properties.mapElementType).toBe("point");
    expect(emittedFeature.properties.sizePx).toBe(12);
    expect(emittedFeature.properties.fontStyle).toBe("normal");
    expect(emittedFeature.properties.labelText).toBe("Québec");
  });

  it("formats SASKATCHEWAN with only the first letter capitalized when changed from province to city", async () => {
    const saskatchewanFeature: Feature = {
      type: "Feature",
      id: "feat-sask-1",
      projectId: "proj-1",
      mapId: "map-1",
      name: "SASKATCHEWAN",
      geometry: { type: "Point", coordinates: [-105.0, 52.0] },
      properties: {
        name: "SASKATCHEWAN",
        labelText: "SASKATCHEWAN",
        mapElementType: "label",
        rawType: "province",
        sizePx: 14,
        fontStyle: "uppercase",
      },
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
    };

    const wrapper = mount(FeatureVisibilityControls, {
      props: {
        features: [saskatchewanFeature],
        featureVisibility: new Map([[saskatchewanFeature.id, true]]),
      },
    });

    await (wrapper.vm as any).showEditFeatureDialog(saskatchewanFeature);

    const select = wrapper.find('[data-testid="word-type-select"]');
    expect(select.exists()).toBe(true);

    // Switch from province to city
    await select.setValue("city");
    await select.trigger("change");

    // The text inputs should now have only the first letter in uppercase: "Saskatchewan"
    const textInput = wrapper.findAll("input").find((i) => i.element.value === "Saskatchewan");
    expect(textInput).toBeDefined();

    const modifyBtn = wrapper.findAll("button").find((b) => b.text().includes("Modifier"));
    await modifyBtn!.trigger("click");

    const emittedFeature = wrapper.emitted("update-feature")![0][0] as Feature;
    expect(emittedFeature.name).toBe("Saskatchewan");
    expect(emittedFeature.properties.name).toBe("Saskatchewan");
    expect(emittedFeature.properties.labelText).toBe("Saskatchewan");
    expect(emittedFeature.properties.rawType).toBe("city");
    expect(emittedFeature.properties.mapElementType).toBe("point");
    expect(emittedFeature.properties.fontStyle).toBe("normal");
    expect(emittedFeature.properties.sizePx).toBe(12);
  });
});
