import { beforeEach, describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import EditMapPeriodDialog from "../../src/components/add/EditMapPeriodDialog.vue";
import type { MapPeriod } from "../../src/typescript/map";

describe("EditMapPeriodDialog", () => {
  beforeEach(() => {
    HTMLDialogElement.prototype.showModal = HTMLDialogElement.prototype.showModal || function (this: HTMLDialogElement) {
      this.open = true;
    };
    HTMLDialogElement.prototype.close = HTMLDialogElement.prototype.close || function (this: HTMLDialogElement) {
      this.open = false;
    };
  });
  const samplePeriod: MapPeriod = {
    id: "map-123",
    title: "Nouvelle-France 1750",
    startDate: "1750-01-01",
    endDate: "1760-12-31",
    exactDate: false,
    color: "#2563eb",
  };

  it("initializes with period values when open is called", async () => {
    const wrapper = mount(EditMapPeriodDialog);
    const vm = wrapper.vm as any;

    vm.open(samplePeriod);
    await wrapper.vm.$nextTick();

    const titleInput = wrapper.find("input[required]");
    expect((titleInput.element as HTMLInputElement).value).toBe("Nouvelle-France 1750");

    const numberInputs = wrapper.findAll("input[type='number']");
    expect(numberInputs.length).toBe(2);
    expect((numberInputs[0].element as HTMLInputElement).value).toBe("1750");
    expect((numberInputs[1].element as HTMLInputElement).value).toBe("1760");

    const submitBtn = wrapper.find("button[type='submit']");
    expect(submitBtn.attributes("disabled")).toBeUndefined();
  });

  it("disables submit button when start year is strictly greater than end year", async () => {
    const wrapper = mount(EditMapPeriodDialog);
    const vm = wrapper.vm as any;

    vm.open({
      ...samplePeriod,
      startDate: "1770-01-01",
      endDate: "1750-12-31",
    });
    await wrapper.vm.$nextTick();

    const submitBtn = wrapper.find("button[type='submit']");
    expect(submitBtn.attributes("disabled")).toBeDefined();
  });

  it("emits 'save' with year-to-iso strings when exactDate is false", async () => {
    const wrapper = mount(EditMapPeriodDialog);
    const vm = wrapper.vm as any;

    vm.open(samplePeriod);
    await wrapper.vm.$nextTick();

    const form = wrapper.find("form");
    await form.trigger("submit");

    expect(wrapper.emitted("save")).toBeTruthy();
    expect(wrapper.emitted("save")?.[0]).toEqual([
      {
        mapId: "map-123",
        title: "Nouvelle-France 1750",
        startDate: "1750-01-01",
        endDate: "1760-12-31",
        exactDate: false,
      },
    ]);
  });

  it("handles exact dates and emits exact date strings", async () => {
    const wrapper = mount(EditMapPeriodDialog);
    const vm = wrapper.vm as any;

    const exactPeriod: MapPeriod = {
      id: "map-exact",
      title: "Bataille des Plaines",
      startDate: "1759-09-13",
      endDate: "1759-09-13",
      exactDate: true,
      color: "#10b981", // Another color from PERIOD_COLORS
    };

    vm.open(exactPeriod);
    await wrapper.vm.$nextTick();

    const dateInputs = wrapper.findAll("input[type='date']");
    expect(dateInputs.length).toBe(2);

    const form = wrapper.find("form");
    await form.trigger("submit");

    expect(wrapper.emitted("save")?.[0]).toEqual([
      {
        mapId: "map-exact",
        title: "Bataille des Plaines",
        startDate: "1759-09-13",
        endDate: "1759-09-13",
        exactDate: true,
      },
    ]);
  });

  it("displays error message when setError is called", async () => {
    const wrapper = mount(EditMapPeriodDialog);
    const vm = wrapper.vm as any;

    vm.open(samplePeriod);
    vm.setError("La période est invalide");
    await wrapper.vm.$nextTick();

    expect(wrapper.text()).toContain("La période est invalide");
  });
});
