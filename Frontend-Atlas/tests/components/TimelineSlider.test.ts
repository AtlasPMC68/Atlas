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
    expect(labelFor(wrapper, 1900).attributes("style")).toContain("top: 1.05rem");
    expect(wrapper.find(".labels-row").attributes("style")).toContain("height: 2.2rem");
  });

  it("selects a year from its label", async () => {
    const wrapper = mountSlider([1700, 1800, 1899, 1900, 1925]);
    await labelFor(wrapper, 1900).trigger("click");
    expect(wrapper.emitted("update:year")?.at(-1)).toEqual([1900]);
    expect(wrapper.emitted("select-date")?.at(-1)).toEqual([1900]);
    expect(labelFor(wrapper, 1900).classes()).toContain("tick-label-active");
  });

  it("emits select-date when clicking on a period track", async () => {
    const wrapper = mount(TimelineSlider, {
      props: {
        year: 1600,
        min: 1500,
        max: 1900,
        mapPeriods: [
          {
            id: "p1",
            title: "Carte 1",
            startDate: "1800",
            endDate: "1850",
            startYear: 1800,
            endYear: 1850,
            exactDate: false,
            color: "#0ea5e9",
          },
        ],
      },
    });
    const track = wrapper.find(".period-track");
    expect(track.exists()).toBe(true);
    await track.trigger("click");
    expect(wrapper.emitted("update:year")?.at(-1)).toEqual([1800]);
    expect(wrapper.emitted("select-date")?.at(-1)).toEqual([1800]);
    expect(wrapper.emitted("select-map")?.at(-1)).toEqual(["p1"]);

    await track.trigger("dblclick");
    expect(wrapper.emitted("edit-map")?.at(-1)).toEqual(["p1"]);
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

  it("forces grouping under 'Éléments généraux' in popover when item has custom dates or isCustom, ignoring residual mapId/mapTitle", async () => {
    const elementMarkers: TimelineElementMarker[] = [
      {
        id: "feat-custom-1",
        name: "lightseagreen",
        year: 1650,
        startYear: 1650,
        endYear: 1650,
        type: "zone",
        mapId: "map-2",
        mapTitle: "CARTE2 ON EFFACE IDIA",
        isCustom: true,
      },
    ];

    const wrapper = mountSlider([1600, 1650, 1700], 1650, elementMarkers);
    const pin = wrapper.find("[data-testid='timeline-element-marker']");
    await pin.trigger("mouseenter");

    const popover = wrapper.find(".element-marker-popover");
    expect(popover.exists()).toBe(true);
    expect(popover.text()).toContain("Éléments généraux");
    expect(popover.text()).not.toContain("CARTE2 ON EFFACE IDIA");
    expect(popover.text()).toContain("lightseagreen");
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

  it("applies correct track style and classes for specific, cumulative, and global modes", () => {
    const wrapperSpecific = mount(TimelineSlider, {
      props: {
        year: 1700,
        min: 1500,
        max: 1900,
        mode: "specific",
      },
    });
    const sliderSpecific = wrapperSpecific.find("input[type='range']");
    expect(sliderSpecific.classes()).toContain("timeline-range--specific");
    expect(sliderSpecific.attributes("style")).toContain("background: rgb(226, 232, 240)");

    const wrapperCumulative = mount(TimelineSlider, {
      props: {
        year: 1700,
        min: 1500,
        max: 1900,
        mode: "cumulative",
      },
    });
    const sliderCumulative = wrapperCumulative.find("input[type='range']");
    expect(sliderCumulative.classes()).toContain("timeline-range--cumulative");
    expect(sliderCumulative.attributes("style")).toContain("linear-gradient");

    const wrapperGlobal = mount(TimelineSlider, {
      props: {
        year: 1700,
        min: 1500,
        max: 1900,
        mode: "global",
      },
    });
    const sliderGlobal = wrapperGlobal.find("input[type='range']");
    expect(sliderGlobal.classes()).toContain("timeline-range--global");
    expect(sliderGlobal.attributes("style")).toContain("background: var(--color-primary)");
  });

  it("falls back gracefully to filterByDate when mode is not provided", () => {
    const wrapperUnfilled = mount(TimelineSlider, {
      props: {
        year: 1700,
        min: 1500,
        max: 1900,
        filterByDate: true,
      },
    });
    const sliderUnfilled = wrapperUnfilled.find("input[type='range']");
    expect(sliderUnfilled.classes()).toContain("timeline-range--specific");

    const wrapperFilled = mount(TimelineSlider, {
      props: {
        year: 1700,
        min: 1500,
        max: 1900,
        filterByDate: false,
      },
    });
    const sliderFilled = wrapperFilled.find("input[type='range']");
    expect(sliderFilled.classes()).toContain("timeline-range--global");
  });

  it("highlights marker pin with selected class when selectedFeatureId matches an item", () => {
    const wrapper = mount(TimelineSlider, {
      props: {
        year: 1700,
        min: 1500,
        max: 1900,
        elementMarkers: [
          {
            id: "feat-1",
            name: "Québec",
            year: 1608,
            type: "point",
          },
          {
            id: "feat-2",
            name: "Montréal",
            year: 1642,
            type: "point",
          },
        ],
        selectedFeatureId: "feat-1",
      },
    });

    const pins = wrapper.findAll(".element-marker-pin");
    expect(pins).toHaveLength(2);
    expect(pins[0].classes()).toContain("element-marker-selected");
    expect(pins[0].find(".element-marker-badge").classes()).toContain("element-marker-badge-selected");
    expect(pins[1].classes()).not.toContain("element-marker-selected");
  });
});
