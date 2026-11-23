import { afterEach, describe, it, expect, vi, beforeEach } from "vitest";
import { mount, type VueWrapper } from "@vue/test-utils";
import FeatureVisibilityControls from "../../src/components/FeatureVisibilityControls.vue";
import type { Feature } from "../../src/typescript/feature";
import type { MapPeriod } from "../../src/typescript/map";
import type { CustomLabelStyle } from "../../src/utils/labelPresentation";

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
      startDate: "1900-01-01",
      endDate: "1910-01-01",
      exactDate: false,
      color: "#0ea5e9",
    },
    {
      id: "map-2",
      title: "Carte Montréal 1950",
      startDate: "1950-01-01",
      endDate: "1960-01-01",
      exactDate: false,
      color: "#10b981",
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
      properties: { name: "Québec", isOcrText: true, recognized: true, show: true },
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
      properties: { name: "Montréal", isOcrText: true, recognized: true, show: true },
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
    },
  ];

  const reviewFeatures: Feature[] = [
    {
      ...features[0],
      id: "review-1",
      properties: {
        ...features[0].properties,
        recognized: false,
        show: false,
      },
    },
    {
      ...features[1],
      id: "review-2",
      properties: {
        ...features[1].properties,
        recognized: false,
        show: false,
      },
    },
  ];

  const zoneFeature: Feature = {
    type: "Feature",
    id: "zone-1",
    projectId: "proj-1",
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
    properties: { name: "Zone Québec", mapElementType: "zone" },
    createdAt: "2026-01-01",
    updatedAt: "2026-01-01",
  };

  const featureVisibility = new Map<string, boolean>([
    ["feat-1", true],
    ["feat-2", true],
  ]);

  it("shows text validation button when text tab is active", () => {
    const wrapper = mount(FeatureVisibilityControls, {
      props: {
        features: [...features, ...reviewFeatures],
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
        features: [...features, ...reviewFeatures],
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
        features: [...features, ...reviewFeatures],
        featureVisibility,
        mapPeriods,
      },
    });

    // Find and click the map button in the validation dialog
    const dialog = wrapper.find('[data-testid="select-map-validation-dialog"]');
    const mapBtn = dialog
      .findAll("button")
      .find((b: any) => b.text().includes("Carte Montréal 1950"));
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

  it("opens map period editing when its title is clicked", async () => {
    const wrapper = mount(FeatureVisibilityControls, {
      props: {
        features,
        featureVisibility,
        mapPeriods,
      },
    });

    await wrapper.find('button[title="Modifier Carte Québec 1900"]').trigger("click");

    expect(wrapper.emitted("edit-map")).toEqual([["map-1"]]);
  });

  it("switches to the selected feature's tab and displays it", async () => {
    const wrapper = mount(FeatureVisibilityControls, {
      props: {
        features: [...features, zoneFeature],
        featureVisibility,
        mapPeriods,
        selectedFeatureId: null,
      },
    });

    await wrapper.setProps({ selectedFeatureId: "zone-1" });
    await wrapper.vm.$nextTick();

    expect(
      wrapper.find('[data-testid="feature-tab-zone"]').attributes("aria-selected"),
    ).toBe("true");
    expect(wrapper.find('[data-feature-item-id="zone-1"]').exists()).toBe(true);
  });

  it("does not list unrecognized OCR texts (recognized: false) in the page", () => {
    const unrecFeature: Feature = {
      type: "Feature",
      id: "feat-unrec-1",
      projectId: "proj-1",
      mapId: "map-1",
      name: "Fort moose",
      geometry: { type: "Point", coordinates: [-80.5, 51.2] },
      properties: {
        name: "Fort moose",
        isOcrText: true,
        recognized: false,
        show: false,
      },
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
    };

    const wrapper = mount(FeatureVisibilityControls, {
      props: {
        features: [...features, unrecFeature],
        featureVisibility,
        mapPeriods,
      },
    });

    // Unrecognized text should NOT be listed in the page
    expect(wrapper.text()).not.toContain("Fort moose");
    // Recognized text is listed
    expect(wrapper.text()).toContain("Québec");
    // Rejected OCR remains available through the validation workflow.
    expect(wrapper.text()).toContain("Examiner les rejets");
    expect(wrapper.find('[data-testid="select-map-validation-dialog"]').text()).toContain(
      "Carte Québec 1900",
    );
  });

  it("only shows the reject review button in the text group", async () => {
    const shapeFeature: Feature = {
      ...features[0],
      id: "shape-feature",
      geometry: {
        type: "Polygon",
        coordinates: [[
          [-71.2, 46.8],
          [-71.1, 46.8],
          [-71.1, 46.9],
          [-71.2, 46.9],
          [-71.2, 46.8],
        ]],
      },
      properties: { name: "Zone", mapElementType: "shape" },
    };
    const wrapper = mount(FeatureVisibilityControls, {
      props: {
        features: [...features, ...reviewFeatures, shapeFeature],
        featureVisibility,
        mapPeriods,
      },
    });

    expect(wrapper.text()).toContain("Examiner les rejets");
    const shapesTab = wrapper.findAll('[role="tab"]').find((tab: any) =>
      tab.attributes("title")?.includes("Forme"),
    );
    expect(shapesTab).toBeDefined();
    await shapesTab!.trigger("click");
    expect(wrapper.text()).not.toContain("Examiner les rejets");
  });

  it("lists accepted OCR texts (recognized: true) in the page", () => {
    const acceptedFeature: Feature = {
      type: "Feature",
      id: "feat-acc-1",
      projectId: "proj-1",
      mapId: "map-1",
      name: "Fort moose",
      geometry: { type: "Point", coordinates: [-80.5, 51.2] },
      properties: {
        name: "Fort moose",
        isOcrText: true,
        recognized: true,
        show: true,
      },
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
    };

    const wrapper = mount(FeatureVisibilityControls, {
      props: {
        features: [...features, acceptedFeature],
        featureVisibility,
        mapPeriods,
      },
    });

    // Accepted text should now be listed in the page
    expect(wrapper.text()).toContain("Fort moose");
  });
});

describe("FeatureVisibilityControls - edit recovery", () => {
  const wrappers: VueWrapper[] = [];
  const feature: Feature = {
    type: "Feature", id: "draft-feature", projectId: "project", mapId: "map-1",
    name: "Québec", geometry: { type: "Point", coordinates: [-71, 46] },
    properties: { name: "Québec", labelText: "Québec", rawType: "city", mapElementType: "point" },
    createdAt: "2026-01-01", updatedAt: "2026-01-01",
  };
  const mapPeriods: MapPeriod[] = ["map-1", "map-2"].map((id) => ({
    id, title: id, startDate: "1900-01-01", endDate: "1910-01-01",
    exactDate: false, color: "#112233",
  }));

  beforeEach(() => {
    HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
      this.open = true;
    });
    HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
      this.open = false;
      this.dispatchEvent(new Event("close"));
    });
  });

  afterEach(() => {
    wrappers.splice(0).forEach((wrapper) => wrapper.unmount());
  });

  function mountEditor(item = feature, options: { busy?: boolean; customLabelStyles?: CustomLabelStyle[] } = {}) {
    const wrapper = mount(FeatureVisibilityControls, {
      props: { features: [item], featureVisibility: new Map([[item.id, true]]), mapPeriods, ...options },
    });
    wrappers.push(wrapper);
    return wrapper;
  }

  it("captures an independent snapshot and restores unfinished text, symbol and map-assignment fields", async () => {
    const original = mountEditor();
    expect(original.vm.getDraft()).toBeNull();
    await original.vm.showEditFeatureDialog(feature);
    await original.get('dialog input[type="text"]').setValue("Capitale");
    await original.get('[data-testid="label-text-input"]').setValue("Québec\nCapitale");
    await original.get('[data-testid="color-input"]').setValue("#ffee00");
    await original.get('[data-testid="text-color-input"]').setValue("#112233");
    await original.get('[data-testid="text-size-input"]').setValue("24");
    await original.get('[data-testid="point-fill-opacity-input"]').setValue("0.4");
    await original.get('#edit-point-stroke-opacity').setValue("0.7");
    await original.get('#edit-point-stroke-width').setValue("3");
    await original.get('[data-testid="map-checkbox-map-2"]').setValue(true);
    const saved = original.vm.getDraft()!;
    expect(saved.draft).toMatchObject({
      name: "Capitale", labelText: "Québec\nCapitale", wordType: "city",
      colorHex: "#ffee00", textColorHex: "#112233", textSizePx: 24,
      fillOpacity: 0.4, strokeOpacity: 0.7, strokeWidth: 3,
      selectedMapIds: ["map-1", "map-2"],
    });
    expect(original.emitted("draft-change")!.length).toBeGreaterThan(1);
    const detached = original.vm.getDraft()!;
    detached.draft!.selectedMapIds!.push("not-in-the-form");
    expect(original.vm.getDraft()!.draft!.selectedMapIds).toEqual(["map-1", "map-2"]);

    const countBeforeClose = original.emitted("draft-change")!.length;
    (original.get('dialog[open]').element as HTMLDialogElement).close();
    expect(original.vm.getDraft()).toBeNull();
    expect(original.emitted("draft-change")!.length).toBe(countBeforeClose + 1);

    // Recovery is programmatic and must work while the parent locks user input.
    const recovered = mountEditor(feature, { busy: true });
    await recovered.vm.restoreDraft(saved);
    expect(recovered.vm.getDraft()).toEqual(saved);
    expect((recovered.get('[data-testid="label-text-input"]').element as HTMLTextAreaElement).value).toBe("Québec\nCapitale");
    expect((recovered.get('[data-testid="map-checkbox-map-2"]').element as HTMLInputElement).checked).toBe(true);
    expect(recovered.get('fieldset').attributes("disabled")).toBeDefined();
  });

  it("preserves custom label style selection and snapshots its style values", async () => {
    const style: CustomLabelStyle = {
      id: "historical", name: "Historique", sizePx: 18, fontStyle: "italic",
      textTransform: "uppercase", color: "#445566", priority: 1, minZoom: 2,
    };
    const original = mountEditor(feature, { customLabelStyles: [style] });
    await original.vm.showEditFeatureDialog(feature);
    await original.get('[data-testid="word-type-select"]').setValue("custom:historical");
    const saved = original.vm.getDraft()!;
    expect(saved.draft).toMatchObject({
      labelStyleSelection: "custom:historical", customLabelStyleId: "historical",
      customLabelStyle: style,
    });
    const detached = original.vm.getDraft()!;
    detached.draft!.customLabelStyle!.color = "#000000";
    expect(original.vm.getDraft()!.draft!.customLabelStyle!.color).toBe("#445566");
    const recovered = mountEditor(feature, { customLabelStyles: [style] });
    await recovered.vm.restoreDraft(saved);
    expect(recovered.vm.getDraft()).toEqual(saved);
    expect((recovered.get('[data-testid="word-type-select"]').element as HTMLSelectElement).value).toBe("custom:historical");
  });

  it("restores shape opacity and stroke fields, including legacy flat drafts", async () => {
    const zone: Feature = {
      ...feature, id: "zone-draft", name: "Zone",
      geometry: { type: "Polygon", coordinates: [[[-71, 46], [-70, 46], [-70, 47], [-71, 46]]] },
      properties: { name: "Zone", mapElementType: "zone" },
    };
    const original = mountEditor(zone);
    await original.vm.restoreDraft({
      featureId: zone.id, name: "Zone modifiée", color: "#778899",
      strokeColor: "#112233", opacity: "0.3", strokeOpacity: "0.8", strokeWidth: "4",
    });
    const saved = original.vm.getDraft()!;
    expect(saved.draft).toMatchObject({
      name: "Zone modifiée", colorHex: "#778899", strokeColorHex: "#112233",
      fillOpacity: 0.3, strokeOpacity: 0.8, strokeWidth: 4,
    });
    const recovered = mountEditor(zone);
    await recovered.vm.restoreDraft(saved);
    expect(recovered.vm.getDraft()).toEqual(saved);
    expect((recovered.get('[data-testid="fill-opacity-input"]').element as HTMLInputElement).value).toBe("0.3");
    await expect(recovered.vm.restoreDraft({ featureId: "missing", name: "Deleted" })).rejects.toThrow("introuvable");
  });

  it("blocks user mutations and cancelling an open edit while busy", async () => {
    const wrapper = mountEditor();
    expect(wrapper.props("busy")).toBe(false);
    await wrapper.vm.showEditFeatureDialog(feature);
    const saved = wrapper.vm.getDraft();
    await wrapper.setProps({ busy: true });
    const dialog = wrapper.get('dialog[open]');
    const cancel = new Event("cancel", { cancelable: true });
    dialog.element.dispatchEvent(cancel);
    expect(cancel.defaultPrevented).toBe(true);
    const modify = dialog.findAll("button").find((button) => button.text() === "Modifier")!;
    expect(modify.attributes("disabled")).toBeDefined();
    await modify.trigger("click");
    const hideAll = wrapper.findAll("button").find((button) => button.text() === "Tout masquer")!;
    await hideAll.trigger("click");
    await wrapper.vm.showEditFeatureDialog({ ...feature, properties: { ...feature.properties, name: "Ignored" } });
    expect(wrapper.vm.getDraft()).toEqual(saved);
    expect(wrapper.emitted("update-feature")).toBeUndefined();
    expect(wrapper.emitted("toggle-feature")).toBeUndefined();
    wrapper.vm.closeEditFeatureDialog();
    expect(wrapper.vm.getDraft()).toBeNull();
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

    const textInput = wrapper.find('[data-testid="label-text-input"]');
    expect((textInput.element as HTMLTextAreaElement).value).toBe("QUÉBEC");
    expect(textInput.attributes("style")).toContain("font-size: 14px");

    // Click modifier button
    const modifyBtn = wrapper.findAll("button").find((b: any) => b.text().includes("Modifier"));
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

  it("preserves the entered text while switching word types before saving", async () => {
    const feature: Feature = {
      ...textFeature,
      name: "mCGuIlL",
      properties: {
        ...textFeature.properties,
        name: "mCGuIlL",
        labelText: "mCGuIlL",
      },
    };
    const wrapper = mount(FeatureVisibilityControls, {
      props: {
        features: [feature],
        featureVisibility: new Map([[feature.id, true]]),
      },
    });

    await (wrapper.vm as any).showEditFeatureDialog(feature);
    const select = wrapper.find('[data-testid="word-type-select"]');
    const textInput = wrapper.findAll("input").find((input: any) => input.element.value === "mCGuIlL");
    expect(textInput).toBeDefined();

    await select.setValue("province");
    await select.setValue("city");

    expect(textInput!.element.value).toBe("mCGuIlL");
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

    const modifyBtn = wrapper.findAll("button").find((b: any) => b.text().includes("Modifier"));
    await modifyBtn!.trigger("click");

    const emittedFeature = wrapper.emitted("update-feature")![0][0] as Feature;
    expect(emittedFeature.properties.rawType).toBe("city");
    expect(emittedFeature.properties.mapElementType).toBe("point");
    expect(emittedFeature.properties.sizePx).toBe(12);
    expect(emittedFeature.properties.fontStyle).toBe("normal");
    expect(emittedFeature.properties.labelText).toBe("Québec");
  });

  it("preserves text when changing province to city and formats it on save", async () => {
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

    const textInput = wrapper.findAll("input").find((i: any) => i.element.value === "SASKATCHEWAN");
    expect(textInput).toBeDefined();

    const modifyBtn = wrapper.findAll("button").find((b: any) => b.text().includes("Modifier"));
    await modifyBtn!.trigger("click");

    const emittedFeature = wrapper.emitted("update-feature")![0][0] as Feature;
    expect(textInput!.element.value).toBe("SASKATCHEWAN");
    expect(emittedFeature.name).toBe("Saskatchewan");
    expect(emittedFeature.properties.name).toBe("Saskatchewan");
    expect(emittedFeature.properties.labelText).toBe("Saskatchewan");
    expect(emittedFeature.properties.rawType).toBe("city");
    expect(emittedFeature.properties.mapElementType).toBe("point");
    expect(emittedFeature.properties.fontStyle).toBe("normal");
    expect(emittedFeature.properties.sizePx).toBe(12);
  });

  it("updates Texte (Aperçu) dynamically when typing the element name", async () => {
    const wrapper = mount(FeatureVisibilityControls, {
      props: {
        features: [textFeature],
        featureVisibility: new Map([[textFeature.id, true]]),
      },
    });

    await (wrapper.vm as any).showEditFeatureDialog(textFeature);

    // Find the Nom de l'élément input (first text input without style)
    const nameInput = wrapper
      .findAll("input")
      .find((i: any) => i.element.value === "Québec" && !i.attributes("style"));
    expect(nameInput).toBeDefined();

    await nameInput!.setValue("Trois-Rivières");
    await nameInput!.trigger("input");

    // The preview input should be updated
    const previewInput = wrapper.find('[data-testid="label-text-input"]');
    expect(previewInput.attributes("style")).toContain("font-size");
    expect((previewInput.element as HTMLTextAreaElement).value).toBe("Trois-Rivières");
  });

  it("keeps the opacity of a point between 0 and 1", async () => {
    const wrapper = mount(FeatureVisibilityControls, {
      props: {
        features: [textFeature],
        featureVisibility: new Map([[textFeature.id, true]]),
      },
    });

    await (wrapper.vm as any).showEditFeatureDialog(textFeature);

    const opacityInput = wrapper.find('[data-testid="point-fill-opacity-input"]');
    expect(opacityInput.attributes("min")).toBe("0");
    expect(opacityInput.attributes("max")).toBe("1");

    await opacityInput.setValue("7");
    await opacityInput.trigger("change");
    expect((opacityInput.element as HTMLInputElement).value).toBe("1");

    // Saved without leaving the field: the stored value is clamped all the same.
    await opacityInput.setValue("-3");
    const modifyBtn = wrapper.findAll("button").find((b: any) => b.text().includes("Modifier"));
    await modifyBtn!.trigger("click");

    const emittedFeature = wrapper.emitted("update-feature")![0][0] as Feature;
    expect(emittedFeature.properties.fillOpacity).toBe(0);
  });

  it("colours and sizes the text of a point apart from its symbol, with line breaks", async () => {
    const wrapper = mount(FeatureVisibilityControls, {
      props: {
        features: [textFeature],
        featureVisibility: new Map([[textFeature.id, true]]),
      },
    });

    await (wrapper.vm as any).showEditFeatureDialog(textFeature);

    await wrapper.find('[data-testid="color-input"]').setValue("#ffee00");
    await wrapper.find('[data-testid="text-color-input"]').setValue("#112233");
    await wrapper.find('[data-testid="text-size-input"]').setValue("22");
    await wrapper.find('[data-testid="label-text-input"]').setValue("Québec\nla capitale");

    const modifyBtn = wrapper.findAll("button").find((b: any) => b.text().includes("Modifier"));
    await modifyBtn!.trigger("click");

    const emittedFeature = wrapper.emitted("update-feature")![0][0] as Feature;
    expect(emittedFeature.properties.colorRgb).toEqual([255, 238, 0]);
    expect(emittedFeature.properties.textColorRgb).toEqual([17, 34, 51]);
    expect(emittedFeature.properties.textSizePx).toBe(22);
    expect(emittedFeature.properties.labelText).toBe("Québec\nla Capitale");
  });

  it("displays shape controls (opacity, stroke) when editing a non-text feature", async () => {
    const wrapper = mount(FeatureVisibilityControls, {
      props: {
        features: [zoneFeature],
        featureVisibility: new Map([[zoneFeature.id, true]]),
      },
    });

    await (wrapper.vm as any).showEditFeatureDialog(zoneFeature);

    // Should display labels for shape opacity and stroke
    expect(wrapper.text()).toContain("Opacité");
    expect(wrapper.text()).toContain("Opacité du contour");
    expect(wrapper.text()).toContain("Épaisseur du contour");
    expect(wrapper.text()).toContain("Couleur du contour :");

    // Click modifier button
    const modifyBtn = wrapper.findAll("button").find((b: any) => b.text().includes("Modifier"));
    expect(modifyBtn).toBeDefined();
    await modifyBtn!.trigger("click");

    expect(wrapper.emitted("update-feature")).toBeDefined();
    const emittedFeature = wrapper.emitted("update-feature")![0][0] as Feature;
    expect(emittedFeature.id).toBe(zoneFeature.id);
    expect(emittedFeature.properties.fillOpacity).toBe(0.5);
    expect(emittedFeature.properties.strokeWidth).toBe(2);
  });

  describe("Map Assignment for General and Map Elements", () => {
    const localMapPeriods: MapPeriod[] = [
      {
        id: "map-1",
        title: "Carte Québec 1900",
        startDate: "1900-01-01",
        endDate: "1910-01-01",
        exactDate: false,
        color: "#0ea5e9",
      },
      {
        id: "map-2",
        title: "Carte Montréal 1950",
        startDate: "1950-01-01",
        endDate: "1960-01-01",
        exactDate: false,
        color: "#10b981",
      },
    ];

    const generalTextFeature: Feature = {
      type: "Feature",
      id: "feat-gen-1",
      projectId: "proj-1",
      mapId: null,
      name: "FLORIDE",
      geometry: { type: "Point", coordinates: [-81.5, 27.5] },
      properties: {
        name: "FLORIDE",
        labelText: "FLORIDE",
        mapElementType: "label",
        rawType: "province",
      },
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
    };

    const generalShapeFeature: Feature = {
      type: "Feature",
      id: "feat-gen-shape-1",
      projectId: "proj-1",
      mapId: null,
      name: "Zone Floride",
      geometry: {
        type: "Polygon",
        coordinates: [[[-82, 27], [-81, 27], [-81, 28], [-82, 28], [-82, 27]]],
      },
      properties: {
        name: "Zone Floride",
        mapElementType: "zone",
      },
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
    };

    it("displays map assignment checkboxes in the edit dialog when mapPeriods are provided", async () => {
      const wrapper = mount(FeatureVisibilityControls, {
        props: {
          features: [generalTextFeature],
          featureVisibility: new Map([[generalTextFeature.id, true]]),
          mapPeriods: localMapPeriods,
        },
      });

      await (wrapper.vm as any).showEditFeatureDialog(generalTextFeature);

      const section = wrapper.find('[data-testid="map-assignment-section"]');
      expect(section.exists()).toBe(true);
      expect(section.text()).toContain("Cartes associées");
      expect(section.text()).toContain("Carte Québec 1900");
      expect(section.text()).toContain("Carte Montréal 1950");
    });

    it("assigns a general element to a chosen map upon selection", async () => {
      const wrapper = mount(FeatureVisibilityControls, {
        props: {
          features: [generalTextFeature],
          featureVisibility: new Map([[generalTextFeature.id, true]]),
          mapPeriods: localMapPeriods,
        },
      });

      await (wrapper.vm as any).showEditFeatureDialog(generalTextFeature);

      // Check map-1
      const checkboxMap1 = wrapper.find('[data-testid="map-checkbox-map-1"]');
      expect(checkboxMap1.exists()).toBe(true);
      await checkboxMap1.setValue(true);

      const modifyBtn = wrapper.findAll("button").find((b: any) => b.text().includes("Modifier"));
      await modifyBtn!.trigger("click");

      expect(wrapper.emitted("update-feature")).toBeDefined();
      const emitted = wrapper.emitted("update-feature")![0][0] as Feature;
      expect(emitted.mapId).toBe("map-1");
      expect(emitted.properties.mapId).toBe("map-1");
    });

    it("assigns a general shape to a map and emits the updated shape", async () => {
      const wrapper = mount(FeatureVisibilityControls, {
        props: {
          features: [generalShapeFeature],
          featureVisibility: new Map([[generalShapeFeature.id, true]]),
          mapPeriods: localMapPeriods,
        },
      });

      await (wrapper.vm as any).showEditFeatureDialog(generalShapeFeature);

      const checkboxMap2 = wrapper.find('[data-testid="map-checkbox-map-2"]');
      expect(checkboxMap2.exists()).toBe(true);
      await checkboxMap2.setValue(true);

      const modifyBtn = wrapper.findAll("button").find((b: any) => b.text().includes("Modifier"));
      await modifyBtn!.trigger("click");

      expect(wrapper.emitted("update-feature")).toBeDefined();
      const emitted = wrapper.emitted("update-feature")![0][0] as Feature;
      expect(emitted.mapId).toBe("map-2");
      expect(emitted.properties.mapElementType).toBe("zone");
    });

    it("clones feature across multiple maps when multiple map checkboxes are checked", async () => {
      const wrapper = mount(FeatureVisibilityControls, {
        props: {
          features: [generalTextFeature],
          featureVisibility: new Map([[generalTextFeature.id, true]]),
          mapPeriods: localMapPeriods,
        },
      });

      await (wrapper.vm as any).showEditFeatureDialog(generalTextFeature);

      const checkboxMap1 = wrapper.find('[data-testid="map-checkbox-map-1"]');
      const checkboxMap2 = wrapper.find('[data-testid="map-checkbox-map-2"]');

      await checkboxMap1.setValue(true);
      await checkboxMap2.setValue(true);

      const modifyBtn = wrapper.findAll("button").find((b: any) => b.text().includes("Modifier"));
      await modifyBtn!.trigger("click");

      expect(wrapper.emitted("update-feature")).toBeDefined();
      const emitted = wrapper.emitted("update-feature")![0][0] as Feature[];
      expect(Array.isArray(emitted)).toBe(true);
      expect(emitted).toHaveLength(2);
      expect(emitted[0].mapId).toBe("map-1");
      expect(emitted[1].mapId).toBe("map-2");
      expect(emitted[0].id).not.toBe(emitted[1].id);
    });

    it("unassigns an element to become general (null mapId) when all map checkboxes are unchecked", async () => {
      const featureInMap1: Feature = {
        ...generalTextFeature,
        id: "feat-map-1",
        mapId: "map-1",
      };

      const wrapper = mount(FeatureVisibilityControls, {
        props: {
          features: [featureInMap1],
          featureVisibility: new Map([[featureInMap1.id, true]]),
          mapPeriods: localMapPeriods,
        },
      });

      await (wrapper.vm as any).showEditFeatureDialog(featureInMap1);

      const checkboxMap1 = wrapper.find('[data-testid="map-checkbox-map-1"]');
      expect((checkboxMap1.element as HTMLInputElement).checked).toBe(true);

      // Uncheck map-1
      await checkboxMap1.setValue(false);

      const modifyBtn = wrapper.findAll("button").find((b: any) => b.text().includes("Modifier"));
      await modifyBtn!.trigger("click");

      expect(wrapper.emitted("update-feature")).toBeDefined();
      const emitted = wrapper.emitted("update-feature")![0][0] as Feature;
      expect(emitted.mapId).toBeNull();
    });
  });

  describe("Feature item click and double click interactions", () => {
    beforeEach(() => {
      HTMLDialogElement.prototype.showModal = vi.fn();
    });

    const florideFeature: Feature = {
      type: "Feature",
      id: "feat-floride-1",
      projectId: "proj-1",
      mapId: null,
      name: "FLORIDE",
      geometry: { type: "Point", coordinates: [-81.5, 27.5] },
      properties: {
        name: "FLORIDE",
        labelText: "FLORIDE",
        mapElementType: "label",
        rawType: "province",
      },
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
    };

    it("selects feature on single click and opens edit dialog on double click", async () => {
      const wrapper = mount(FeatureVisibilityControls, {
        props: {
          features: [florideFeature],
          featureVisibility: new Map([[florideFeature.id, true]]),
        },
      });

      const textTab = wrapper.findAll('[role="tab"]').find((tab: any) =>
        tab.attributes("title")?.includes("Texte") || tab.attributes("data-testid") === "feature-tab-label",
      );
      if (textTab) {
        await textTab.trigger("click");
      }

      const item = wrapper.find(`[data-feature-item-id="${florideFeature.id}"]`);
      expect(item.exists()).toBe(true);

      // Single click selects feature
      await item.trigger("click");
      expect(wrapper.emitted("select-feature")?.[0]).toEqual(["feat-floride-1"]);

      // Double click opens edit modal
      const showModalSpy = vi.spyOn(HTMLDialogElement.prototype, "showModal");
      await item.trigger("dblclick");
      expect(wrapper.emitted("select-feature")?.[1]).toEqual(["feat-floride-1"]);
      expect(showModalSpy).toHaveBeenCalled();
    });
  });
});
