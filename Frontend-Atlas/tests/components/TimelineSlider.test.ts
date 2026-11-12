import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import TimelineSlider from "../../src/components/TimelineSlider.vue";

function mountSlider(markerYears: number[], year = markerYears[0]) {
  return mount(TimelineSlider, {
    props: {
      year,
      min: Math.min(...markerYears),
      max: Math.max(...markerYears),
      markerYears,
    },
  });
}

function labelFor(wrapper: ReturnType<typeof mountSlider>, year: number) {
  return wrapper
    .findAll("button.tick-label")
    .find((label) => label.text() === String(year))!;
}

describe("TimelineSlider year labels", () => {
  it("keeps well-spaced years on one line", () => {
    const wrapper = mountSlider([1700, 1800, 1925]);
    for (const year of [1700, 1800, 1925]) {
      expect(labelFor(wrapper, year).attributes("style")).toContain("top: 0rem");
    }
  });

  it("moves a year that would overlap the previous one to the next line", () => {
    const wrapper = mountSlider([1700, 1800, 1899, 1900, 1925]);
    expect(labelFor(wrapper, 1899).attributes("style")).toContain("top: 0rem");
    expect(labelFor(wrapper, 1900).attributes("style")).toContain("top: 1rem");
    expect(wrapper.find(".labels-row").attributes("style")).toContain("height: 2rem");
  });

  it("selects a year from its label", async () => {
    const wrapper = mountSlider([1700, 1800, 1899, 1900, 1925]);
    await labelFor(wrapper, 1900).trigger("click");
    expect(wrapper.emitted("update:year")?.at(-1)).toEqual([1900]);
    expect(labelFor(wrapper, 1900).classes()).toContain("tick-label-active");
  });
});
