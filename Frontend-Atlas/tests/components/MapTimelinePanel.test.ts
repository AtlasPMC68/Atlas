import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import MapTimelinePanel from "../../src/components/MapTimelinePanel.vue";

describe("MapTimelinePanel.vue", () => {
  const defaultProps = {
    isTimelineVisible: true,
    isLegendVisible: true,
    timelineHeight: 180,
    projectTitle: "Projet de 1850",
    sortedTimelineMilestones: [
      { year: 1800, label: "Carte 1800", type: "map" as const, id: "m1" },
      { year: 1850, label: "Carte 1850", type: "map" as const, id: "m2" },
      { year: 1900, label: "Carte 1900", type: "map" as const, id: "m3" },
    ],
    prevMilestone: { year: 1800, label: "Carte 1800", type: "map" as const, id: "m1" },
    nextMilestone: { year: 1900, label: "Carte 1900", type: "map" as const, id: "m3" },
    hasPrevMilestone: true,
    hasNextMilestone: true,
    year: 1850,
    mode: "specific" as const,
    selectedFeatureId: null,
    multiSelectedFeatureIds: [],
    min: 1800,
    max: 1900,
    markerYears: [1800, 1850, 1900],
    mapPeriods: [],
    elementMarkers: [],
    currentExactDate: null,
  };

  it("renders project title and navigation controls", () => {
    const wrapper = mount(MapTimelinePanel, {
      props: defaultProps,
    });

    expect(wrapper.text()).toContain("Projet de 1850");
    const prevBtn = wrapper.find("[data-testid='prev-map-button']");
    const nextBtn = wrapper.find("[data-testid='next-map-button']");
    expect(prevBtn.exists()).toBe(true);
    expect(nextBtn.exists()).toBe(true);
  });

  it("emits prev-milestone and next-milestone on click", async () => {
    const wrapper = mount(MapTimelinePanel, {
      props: defaultProps,
    });

    await wrapper.find("[data-testid='prev-map-button']").trigger("click");
    expect(wrapper.emitted("prev-milestone")).toBeTruthy();

    await wrapper.find("[data-testid='next-map-button']").trigger("click");
    expect(wrapper.emitted("next-milestone")).toBeTruthy();
  });

  it("emits toggle-legend and toggle-timeline", async () => {
    const wrapper = mount(MapTimelinePanel, {
      props: defaultProps,
    });

    await wrapper.find("[data-testid='hide-legend-button']").trigger("click");
    expect(wrapper.emitted("toggle-legend")).toBeTruthy();

    await wrapper.find("[data-testid='hide-timeline-button']").trigger("click");
    expect(wrapper.emitted("toggle-timeline")).toBeTruthy();
  });
});
