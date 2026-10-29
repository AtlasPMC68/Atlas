import { describe, it, expect, vi } from "vitest";
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
