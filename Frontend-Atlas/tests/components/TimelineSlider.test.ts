import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import TimelineSlider from "../../src/components/TimelineSlider.vue";

function mountSlider(
  markerYears: number[],
  year = markerYears[0],
) {
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
    .find((label : { text: () => string }) => label.text().includes(String(year)))!;
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

describe("TimelineSlider filter modes", () => {
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

  it("positions each period track on its own row one above the other when they overlap", () => {
    const wrapper = mount(TimelineSlider, {
      props: {
        year: 1700,
        min: 1600,
        max: 1800,
        mapPeriods: [
          { id: "p1", title: "Map 1", startYear: 1650, endYear: 1700, color: "#10b981", exactDate: false },
          { id: "p2", title: "Map 2", startYear: 1680, endYear: 1750, color: "#f59e0b", exactDate: false },
        ],
      },
    });
    const tracks = wrapper.findAll(".period-track");
    expect(tracks.length).toBe(2);
    const bottom1 = parseFloat(tracks[0].attributes("style")?.match(/bottom:\s*([\d.]+)rem/)?.[1] || "0");
    const bottom2 = parseFloat(tracks[1].attributes("style")?.match(/bottom:\s*([\d.]+)rem/)?.[1] || "0");
    expect(bottom2).toBeGreaterThan(bottom1);
  });

  it("shares the same row when periods do not overlap and space is free", () => {
    const wrapper = mount(TimelineSlider, {
      props: {
        year: 1700,
        min: 1600,
        max: 1800,
        mapPeriods: [
          { id: "p1", title: "Map 1", startYear: 1610, endYear: 1630, color: "#10b981", exactDate: false },
          { id: "p2", title: "Map 2", startYear: 1660, endYear: 1690, color: "#f59e0b", exactDate: false },
        ],
      },
    });
    const tracks = wrapper.findAll(".period-track");
    expect(tracks.length).toBe(2);
    const bottom1 = parseFloat(tracks[0].attributes("style")?.match(/bottom:\s*([\d.]+)rem/)?.[1] || "0");
    const bottom2 = parseFloat(tracks[1].attributes("style")?.match(/bottom:\s*([\d.]+)rem/)?.[1] || "0");
    expect(bottom2).toBe(bottom1);
  });
});
