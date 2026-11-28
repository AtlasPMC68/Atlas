import { beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import LegendAreaPickerModal from "../../src/components/legend/LegendAreaPickerModal.vue";
import type { LegendBounds } from "../../src/typescript/legend";

describe("LegendAreaPickerModal", () => {
  const dummyImageUrl =
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==";

  beforeEach(() => {
    HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
      this.open = true;
    };
    HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
      this.open = false;
    };
  });

  async function setupModal(props = {}) {
    const wrapper = mount(LegendAreaPickerModal, {
      props: {
        isOpen: true,
        imageUrl: dummyImageUrl,
        ...props,
      },
      attachTo: document.body,
    });

    const container = wrapper.find(".cursor-crosshair").element as HTMLDivElement;
    vi.spyOn(container, "getBoundingClientRect").mockReturnValue({
      left: 0,
      top: 0,
      width: 500,
      height: 400,
      right: 500,
      bottom: 400,
      x: 0,
      y: 0,
      toJSON: () => {},
    });

    const imgWrapper = wrapper.find("img");
    const img = imgWrapper.element as HTMLImageElement;
    Object.defineProperty(img, "naturalWidth", { value: 1000, configurable: true });
    Object.defineProperty(img, "naturalHeight", { value: 800, configurable: true });
    await imgWrapper.trigger("load");

    return { wrapper, container };
  }

  it("renders with initial legend bounds and multiple ignored areas on the same window", async () => {
    const initialBounds: LegendBounds = { x: 10, y: 10, width: 100, height: 80 };
    const initialIgnoredAreas: LegendBounds[] = [
      { x: 50, y: 50, width: 40, height: 30 },
      { x: 150, y: 150, width: 60, height: 40 },
    ];

    const { wrapper } = await setupModal({
      initialBounds,
      initialIgnoredAreas,
    });

    // Check header and tabs
    expect(wrapper.text()).toContain("Légende");
    expect(wrapper.text()).toContain("Zones à ignorer");
    expect(wrapper.text()).toContain("Zone #1");
    expect(wrapper.text()).toContain("Zone #2");

    // Check count in list header
    expect(wrapper.text()).toContain("2");
  });

  it("allows switching between Legend and Exclusion drawing modes", async () => {
    const { wrapper } = await setupModal();

    const buttons = wrapper.findAll("button");
    const legendBtn = buttons.find(
      (b) => b.text().includes("Légende") && b.classes().includes("join-item"),
    );
    const exclusionBtn = buttons.find(
      (b) => b.text().includes("Zones à ignorer") && b.classes().includes("join-item"),
    );

    expect(legendBtn).toBeDefined();
    expect(exclusionBtn).toBeDefined();
    expect(exclusionBtn?.classes()).not.toContain("btn-primary");

    // Switch to exclusion
    await exclusionBtn?.trigger("click");
    expect(exclusionBtn?.classes()).toContain("btn-primary");

    // Switch back to legend
    await legendBtn?.trigger("click");
    expect(legendBtn?.classes()).toContain("btn-primary");
  });

  it("allows selecting multiple exclusion zones independently from the legend", async () => {
    const initialLegend: LegendBounds = { x: 50, y: 50, width: 100, height: 80 };
    const { wrapper, container } = await setupModal({ initialBounds: initialLegend });

    // Switch to exclusion mode
    const buttons = wrapper.findAll("button");
    const exclusionBtn = buttons.find(
      (b) => b.text().includes("Zones à ignorer") && b.classes().includes("join-item"),
    );
    await exclusionBtn?.trigger("click");

    // 1. Draw scale exclusion zone (200, 200 -> 300, 250)
    await container.dispatchEvent(
      new MouseEvent("mousedown", { clientX: 200, clientY: 200, button: 0 }),
    );
    window.dispatchEvent(
      new MouseEvent("mousemove", { clientX: 300, clientY: 250 }),
    );
    window.dispatchEvent(
      new MouseEvent("mouseup", { clientX: 300, clientY: 250 }),
    );
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("Zone #1");

    // 2. Draw compass exclusion zone (350, 50 -> 400, 100)
    await container.dispatchEvent(
      new MouseEvent("mousedown", { clientX: 350, clientY: 50, button: 0 }),
    );
    window.dispatchEvent(
      new MouseEvent("mousemove", { clientX: 400, clientY: 100 }),
    );
    window.dispatchEvent(
      new MouseEvent("mouseup", { clientX: 400, clientY: 100 }),
    );
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("Zone #2");

    // 3. Draw title exclusion zone (100, 10 -> 400, 40)
    await container.dispatchEvent(
      new MouseEvent("mousedown", { clientX: 100, clientY: 10, button: 0 }),
    );
    window.dispatchEvent(
      new MouseEvent("mousemove", { clientX: 400, clientY: 40 }),
    );
    window.dispatchEvent(
      new MouseEvent("mouseup", { clientX: 400, clientY: 40 }),
    );
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain("Zone #3");

    // Confirm and verify payload contains both legend AND the 3 exclusion zones
    const confirmBtn = wrapper
      .findAll("button")
      .find((b) => b.text().startsWith("Confirmer"));
    await confirmBtn?.trigger("click");

    const emitted = wrapper.emitted("confirmed");
    expect(emitted).toBeTruthy();
    const payload = emitted![0][0] as {
      legend: LegendBounds | null;
      ignoredAreas: LegendBounds[];
    };

    expect(payload.legend).toEqual(initialLegend);
    expect(payload.ignoredAreas).toHaveLength(3);
    // Scaled by 2 (1000/500 = 2)
    expect(payload.ignoredAreas[0]).toEqual({
      x: 400,
      y: 400,
      width: 200,
      height: 100,
    });
  });

  it("can delete an exclusion zone from the list or clear all", async () => {
    const initialIgnoredAreas: LegendBounds[] = [
      { x: 10, y: 10, width: 20, height: 20 },
      { x: 40, y: 40, width: 30, height: 30 },
    ];

    const { wrapper } = await setupModal({
      initialBounds: null,
      initialIgnoredAreas,
    });

    expect(wrapper.text()).toContain("Zone #1");
    expect(wrapper.text()).toContain("Zone #2");

    // Delete first zone
    const deleteButtons = wrapper.findAll('button[title="Supprimer cette zone"]');
    expect(deleteButtons.length).toBe(2);
    await deleteButtons[0].trigger("click");

    expect(wrapper.findAll('button[title="Supprimer cette zone"]').length).toBe(1);
    expect(wrapper.text()).toContain("30×30 px (x: 40, y: 40)");

    // Clear all
    const clearAllBtn = wrapper
      .findAll("button")
      .find((b) => b.text() === "Tout effacer");
    expect(clearAllBtn).toBeDefined();
    await clearAllBtn?.trigger("click");

    expect(wrapper.findAll('button[title="Supprimer cette zone"]').length).toBe(0);
    expect(wrapper.text()).toContain("Aucune zone d'exclusion tracée");
  });

  it("can delete the legend independently", async () => {
    const initialBounds: LegendBounds = { x: 10, y: 10, width: 100, height: 80 };
    const { wrapper } = await setupModal({
      initialBounds,
      initialIgnoredAreas: [{ x: 50, y: 50, width: 40, height: 40 }],
    });

    expect(wrapper.text()).toContain("Délimitée");

    const deleteLegendBtn = wrapper
      .findAll("button")
      .find((b) => b.text() === "Supprimer");
    expect(deleteLegendBtn).toBeDefined();
    await deleteLegendBtn?.trigger("click");

    expect(wrapper.text()).toContain("Aucune légende délimitée (optionnelle)");
    // Ignored area is preserved
    expect(wrapper.text()).toContain("Zone #1");
  });

  it("keeps drawing active when mouse leaves image bounds and finishes only on mouseup", async () => {
    const { wrapper, container } = await setupModal();

    // 1. Mouse down inside image
    await container.dispatchEvent(
      new MouseEvent("mousedown", { clientX: 100, clientY: 100, button: 0 }),
    );

    // 2. Drag outside image bounds (1500, 1200)
    window.dispatchEvent(
      new MouseEvent("mousemove", { clientX: 1500, clientY: 1200 }),
    );

    // 3. Move outside in negative direction (-500, -300)
    window.dispatchEvent(
      new MouseEvent("mousemove", { clientX: -500, clientY: -300 }),
    );

    // Drawing stays active (not yet committed)
    expect(wrapper.emitted("confirmed")).toBeFalsy();

    // 4. Finally release mouse on window
    window.dispatchEvent(
      new MouseEvent("mouseup", { clientX: -500, clientY: -300 }),
    );
    await wrapper.vm.$nextTick();

    // Box was committed successfully (from 100,100 clamped to 0,0 -> 200x200 px)
    expect(wrapper.text()).toContain("Délimitée");
  });

  it("handles edge case of micro-drag (< 2px) by ignoring it", async () => {
    const { wrapper, container } = await setupModal();

    await container.dispatchEvent(
      new MouseEvent("mousedown", { clientX: 100, clientY: 100, button: 0 }),
    );
    window.dispatchEvent(
      new MouseEvent("mousemove", { clientX: 100.5, clientY: 100.5 }),
    );
    window.dispatchEvent(
      new MouseEvent("mouseup", { clientX: 100.5, clientY: 100.5 }),
    );

    expect(wrapper.text()).toContain("Aucune légende délimitée");
  });

  it("ignores non-primary mouse button clicks", async () => {
    const { wrapper, container } = await setupModal();

    await container.dispatchEvent(
      new MouseEvent("mousedown", { clientX: 100, clientY: 100, button: 2 }),
    );
    window.dispatchEvent(
      new MouseEvent("mousemove", { clientX: 200, clientY: 200 }),
    );
    window.dispatchEvent(
      new MouseEvent("mouseup", { clientX: 200, clientY: 200 }),
    );

    expect(wrapper.text()).toContain("Aucune légende délimitée");
  });

  it("automatically switches to exclusion mode after tracing the legend", async () => {
    const { wrapper, container } = await setupModal();

    // Starts in legend mode
    const legendBtn = wrapper
      .findAll("button")
      .find((b) => b.text().includes("Légende") && b.classes().includes("join-item"));
    expect(legendBtn?.classes()).toContain("btn-primary");

    // Draw the legend rectangle
    await container.dispatchEvent(
      new MouseEvent("mousedown", { clientX: 50, clientY: 50, button: 0 }),
    );
    window.dispatchEvent(
      new MouseEvent("mousemove", { clientX: 150, clientY: 120 }),
    );
    window.dispatchEvent(
      new MouseEvent("mouseup", { clientX: 150, clientY: 120 }),
    );
    await wrapper.vm.$nextTick();

    // Mode automatically switched to exclusion zones
    const exclusionBtn = wrapper
      .findAll("button")
      .find((b) => b.text().includes("Zones à ignorer") && b.classes().includes("join-item"));
    expect(exclusionBtn?.classes()).toContain("btn-primary");
    expect(wrapper.text()).toContain("Délimitée");
  });
});
