import { beforeEach, describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import DuplicateMapDialog from "../../src/components/add/DuplicateMapDialog.vue";
import type { MapPeriod } from "../../src/typescript/map";

describe("DuplicateMapDialog", () => {
  beforeEach(() => {
    HTMLDialogElement.prototype.showModal =
      HTMLDialogElement.prototype.showModal ||
      function (this: HTMLDialogElement) {
        this.open = true;
      };
    HTMLDialogElement.prototype.close =
      HTMLDialogElement.prototype.close ||
      function (this: HTMLDialogElement) {
        this.open = false;
      };
  });

  const samplePeriods: MapPeriod[] = [
    {
      id: "map-1",
      title: "Nouvelle-France",
      startDate: "1750-01-01",
      endDate: "1760-12-31",
      exactDate: false,
    },
    {
      id: "map-2",
      title: "Bas-Canada",
      startDate: "1791-05-10",
      endDate: "1840-02-15",
      exactDate: true,
    },
  ];

  it("initializes and selects source map with auto-generated title on open", async () => {
    const wrapper = mount(DuplicateMapDialog, {
      props: {
        mapPeriods: samplePeriods,
      },
    });
    const vm = wrapper.vm as any;

    vm.open("map-1");
    await wrapper.vm.$nextTick();

    const titleInput = wrapper.find("[data-testid='duplicate-map-title-input']");
    expect((titleInput.element as HTMLInputElement).value).toBe("Nouvelle-France (copie)");

    const startYearInput = wrapper.find("[data-testid='duplicate-map-start-year']");
    expect((startYearInput.element as HTMLInputElement).value).toBe("1750");

    const endYearInput = wrapper.find("[data-testid='duplicate-map-end-year']");
    expect((endYearInput.element as HTMLInputElement).value).toBe("1760");

    const submitBtn = wrapper.find("[data-testid='duplicate-map-submit-button']");
    expect(submitBtn.attributes("disabled")).toBeUndefined();
  });

  it("switches to exact date fields when an exact date map is selected", async () => {
    const wrapper = mount(DuplicateMapDialog, {
      props: {
        mapPeriods: samplePeriods,
      },
    });
    const vm = wrapper.vm as any;

    vm.open("map-2");
    await wrapper.vm.$nextTick();

    const titleInput = wrapper.find("[data-testid='duplicate-map-title-input']");
    expect((titleInput.element as HTMLInputElement).value).toBe("Bas-Canada (copie)");

    const startDateInput = wrapper.find("[data-testid='duplicate-map-start-date']");
    expect((startDateInput.element as HTMLInputElement).value).toBe("1791-05-10");

    const endDateInput = wrapper.find("[data-testid='duplicate-map-end-date']");
    expect((endDateInput.element as HTMLInputElement).value).toBe("1840-02-15");
  });

  it("disables submit button when start year is greater than end year", async () => {
    const wrapper = mount(DuplicateMapDialog, {
      props: {
        mapPeriods: samplePeriods,
      },
    });
    const vm = wrapper.vm as any;

    vm.open("map-1");
    await wrapper.vm.$nextTick();

    const startYearInput = wrapper.find("[data-testid='duplicate-map-start-year']");
    const endYearInput = wrapper.find("[data-testid='duplicate-map-end-year']");

    await endYearInput.setValue(1700);
    await startYearInput.setValue(1750);
    await wrapper.vm.$nextTick();

    const submitBtn = wrapper.find("[data-testid='duplicate-map-submit-button']");
    expect(submitBtn.attributes("disabled")).toBeDefined();
  });

  it("emits submit with payload on form submission", async () => {
    const wrapper = mount(DuplicateMapDialog, {
      props: {
        mapPeriods: samplePeriods,
      },
    });
    const vm = wrapper.vm as any;

    vm.open("map-1");
    await wrapper.vm.$nextTick();

    const form = wrapper.find("form");
    await form.trigger("submit");

    expect(wrapper.emitted("submit")).toBeTruthy();
    expect(wrapper.emitted("submit")?.[0]).toEqual([
      {
        sourceMapId: "map-1",
        newTitle: "Nouvelle-France (copie)",
        startDate: "1750-01-01",
        endDate: "1760-12-31",
        exactDate: false,
      },
    ]);
  });
});
