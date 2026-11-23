import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import DeleteFeatureDialog from "../../src/components/DeleteFeatureDialog.vue";
import type { Feature } from "../../src/typescript/feature";
import type { MapPeriod } from "../../src/typescript/map";

describe("DeleteFeatureDialog", () => {
  beforeEach(() => {
    HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
      this.setAttribute("open", "");
    });
    HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
      this.removeAttribute("open");
    });
  });
  const map1: MapPeriod = {
    id: "map-1",
    title: "Nouvelle-France 1608",
    startDate: "1608-01-01",
    endDate: "1763-12-31",
    exactDate: false,
    color: "#2563eb",
  };

  const map2: MapPeriod = {
    id: "map-2",
    title: "Amérique du Nord 1608",
    startDate: "1608-01-01",
    endDate: "1763-12-31",
    exactDate: false,
    color: "#dc2626",
  };

  const sharedFeature: Feature = {
    type: "Feature",
    id: "feat-shared",
    projectId: "proj-1",
    mapId: "map-1",
    mapIds: ["map-1", "map-2"],
    properties: {
      name: "Fort Saint-Louis",
      mapId: "map-1",
      mapIds: ["map-1", "map-2"],
    },
    geometry: {
      type: "Point",
      coordinates: [-71.2, 46.8],
    },
  };

  const singleFeature: Feature = {
    type: "Feature",
    id: "feat-single",
    projectId: "proj-1",
    mapId: "map-1",
    mapIds: ["map-1"],
    properties: {
      name: "Québec",
      mapId: "map-1",
      mapIds: ["map-1"],
    },
    geometry: {
      type: "Point",
      coordinates: [-71.2, 46.8],
    },
  };

  it("renders single feature deletion confirmation when feature belongs to only 1 map", async () => {
    const wrapper = mount(DeleteFeatureDialog, {
      props: {
        features: [singleFeature],
        mapPeriods: [map1, map2],
        activeMapId: "map-1",
      },
    });

    wrapper.vm.open(singleFeature);
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).toContain("Supprimer l'élément");
    expect(wrapper.text()).toContain("Êtes-vous sûr de vouloir supprimer");
    expect(wrapper.text()).toContain("Québec");
    expect(wrapper.find('[data-testid="remove-from-map-btn"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="confirm-delete-feature-btn"]').text()).toBe("Supprimer");
  });

  it("displays map titles, dates and checkboxes when feature belongs to multiple maps", async () => {
    const wrapper = mount(DeleteFeatureDialog, {
      props: {
        features: [sharedFeature],
        mapPeriods: [map1, map2],
        activeMapId: "map-1",
      },
    });

    wrapper.vm.open(sharedFeature);
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).toContain("Élément partagé sur plusieurs cartes");
    expect(wrapper.text()).toContain("est présent sur 2 cartes");

    // Both map titles are visible!
    expect(wrapper.text()).toContain("Nouvelle-France 1608");
    expect(wrapper.text()).toContain("Amérique du Nord 1608");

    // Active map badge is shown
    expect(wrapper.text()).toContain("Carte actuelle");

    // Checkboxes are rendered for each map
    const checkboxes = wrapper.findAll('input[type="checkbox"]');
    expect(checkboxes.length).toBe(2);

    // activeMapId 'map-1' is pre-checked
    expect((checkboxes[0].element as HTMLInputElement).checked).toBe(true);
  });

  it("emits remove-from-maps with selected map IDs when clicking remove button", async () => {
    const wrapper = mount(DeleteFeatureDialog, {
      props: {
        features: [sharedFeature],
        mapPeriods: [map1, map2],
        activeMapId: "map-1",
      },
    });

    wrapper.vm.open(sharedFeature);
    await wrapper.vm.$nextTick();

    const removeBtn = wrapper.find('[data-testid="remove-from-map-btn"]');
    await removeBtn.trigger("click");

    expect(wrapper.emitted("remove-from-maps")).toBeDefined();
    expect(wrapper.emitted("remove-from-maps")?.[0][0]).toEqual({
      featureIds: ["feat-shared"],
      mapIdsToRemove: ["map-1"],
    });
  });

  it("emits delete-features when clicking Supprimer partout", async () => {
    const wrapper = mount(DeleteFeatureDialog, {
      props: {
        features: [sharedFeature],
        mapPeriods: [map1, map2],
        activeMapId: "map-1",
      },
    });

    wrapper.vm.open(sharedFeature);
    await wrapper.vm.$nextTick();

    const deleteBtn = wrapper.find('[data-testid="confirm-delete-feature-btn"]');
    await deleteBtn.trigger("click");

    expect(wrapper.emitted("delete-features")).toBeDefined();
    expect(wrapper.emitted("delete-features")?.[0][0]).toEqual(["feat-shared"]);
  });

  it("allows toggling map checkboxes to select which maps to remove from", async () => {
    const wrapper = mount(DeleteFeatureDialog, {
      props: {
        features: [sharedFeature],
        mapPeriods: [map1, map2],
        activeMapId: "map-1",
      },
    });

    wrapper.vm.open(sharedFeature);
    await wrapper.vm.$nextTick();

    const checkboxes = wrapper.findAll('input[type="checkbox"]');
    // Check the second map as well
    await checkboxes[1].setValue(true);

    const removeBtn = wrapper.find('[data-testid="remove-from-map-btn"]');
    await removeBtn.trigger("click");

    expect(wrapper.emitted("remove-from-maps")?.[0][0]).toEqual({
      featureIds: ["feat-shared"],
      mapIdsToRemove: ["map-1", "map-2"],
    });
  });
});
