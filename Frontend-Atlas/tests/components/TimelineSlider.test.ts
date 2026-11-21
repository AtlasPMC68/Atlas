import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import TimelineSlider from "../../src/components/TimelineSlider.vue";
import type { TimelineElementMarker } from "../../src/typescript/map";

function mountSlider(
  markerYears: number[],
  year = markerYears[0],
  elementMarkers?: TimelineElementMarker[],
) {
  return mount(TimelineSlider, {
    props: {
      year,
      min: Math.min(...markerYears),
      max: Math.max(...markerYears),
      markerYears,
      elementMarkers,
    },
  });
}

function labelFor(wrapper: ReturnType<typeof mountSlider>, year: number) {
  return wrapper
    .findAll("button.tick-label")
    .find((label) => label.text().includes(String(year)))!;
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

describe("TimelineSlider element markers (pins)", () => {
  it("does not render element markers row when no elementMarkers are provided", () => {
    const wrapper = mountSlider([1500, 1501]);
    expect(wrapper.find("[data-testid='timeline-element-markers-row']").exists()).toBe(false);
  });

  it("renders distinct pin and indicator dot for element at year 1900", () => {
    const elementMarkers: TimelineElementMarker[] = [
      {
        id: "feat-alberta",
        name: "ALBERTA",
        year: 1900,
        type: "Texte",
      },
    ];
    const wrapper = mountSlider([1500, 1501, 1900], 1500, elementMarkers);

    const markersRow = wrapper.find("[data-testid='timeline-element-markers-row']");
    expect(markersRow.exists()).toBe(true);

    const pins = wrapper.findAll("[data-testid='timeline-element-marker']");
    expect(pins).toHaveLength(1);
    expect(pins[0].text()).toContain("1");
    expect(pins[0].attributes("data-tip")).toBe("ALBERTA (1900) - Texte");

    // Year label 1900 should exist in the slider ticks
    const label1900 = labelFor(wrapper, 1900);
    expect(label1900.exists()).toBe(true);
  });

  it("groups multiple elements on the same year into one marker", () => {
    const elementMarkers: TimelineElementMarker[] = [
      { id: "1", name: "ALBERTA", year: 1900, type: "Texte" },
      { id: "2", name: "CALGARY", year: 1900, type: "Texte" },
    ];
    const wrapper = mountSlider([1500, 1900], 1500, elementMarkers);

    const pins = wrapper.findAll("[data-testid='timeline-element-marker']");
    expect(pins).toHaveLength(1);
    expect(pins[0].text()).toContain("2 éléments");
    expect(pins[0].attributes("data-tip")).toContain("2 éléments (1900) : ALBERTA, CALGARY");
  });

  it("displays map title and general elements section in the popover on hover", async () => {
    const elementMarkers: TimelineElementMarker[] = [
      {
        id: "feat-map-1",
        name: "Province De Québec",
        year: 1800,
        type: "Texte",
        mapId: "map-qc",
        mapTitle: "Carte Nouvelle-France",
      },
      {
        id: "feat-gen-1",
        name: "Grand Fleuve",
        year: 1800,
        type: "Texte",
        mapId: null,
        mapTitle: "Éléments généraux",
      },
    ];
    const wrapper = mountSlider([1600, 1800, 1900], 1800, elementMarkers);

    const pin = wrapper.find("[data-testid='timeline-element-marker']");
    expect(pin.exists()).toBe(true);

    // Trigger mouseenter to open the popover
    await pin.trigger("mouseenter");

    const popover = wrapper.find(".element-marker-popover");
    expect(popover.exists()).toBe(true);
    expect(popover.text()).toContain("2 éléments");
    expect(popover.text()).toContain("Carte Nouvelle-France");
    expect(popover.text()).toContain("Éléments généraux");
    expect(popover.text()).toContain("Province De Québec");
    expect(popover.text()).toContain("Grand Fleuve");
  });

  it("clicking an element pin selects the year immediately", async () => {
    const elementMarkers: TimelineElementMarker[] = [
      { id: "feat-1", name: "ALBERTA", year: 1900, type: "Texte" },
    ];
    const wrapper = mountSlider([1500, 1501, 1900], 1500, elementMarkers);

    const pin = wrapper.find("[data-testid='timeline-element-marker']");
    await pin.trigger("click");

    expect(wrapper.emitted("update:year")?.at(-1)).toEqual([1900]);
    expect(pin.classes()).toContain("element-marker-active");
  });
});
