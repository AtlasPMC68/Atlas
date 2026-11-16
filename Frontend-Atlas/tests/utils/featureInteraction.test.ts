import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createFeatureDoubleClickHandler } from "../../src/utils/featureInteraction";
import type { Feature } from "../../src/typescript/feature";

describe("createFeatureDoubleClickHandler", () => {
  const featureA: Feature = {
    type: "Feature",
    id: "feat-a",
    name: "Floride",
    geometry: { type: "Point", coordinates: [-81.5, 27.5] },
    properties: { name: "Floride" },
  };

  const featureB: Feature = {
    type: "Feature",
    id: "feat-b",
    name: "Québec",
    geometry: { type: "Point", coordinates: [-71.2, 46.8] },
    properties: { name: "Québec" },
  };

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("triggers onSelect on a single click", () => {
    const onSelect = vi.fn();
    const onEdit = vi.fn();

    const handler = createFeatureDoubleClickHandler({
      onSelect,
      onEdit,
    });

    handler.handleClick(featureA);

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(featureA);
    expect(onEdit).not.toHaveBeenCalled();
  });

  it("triggers onEdit when clicked twice in a row within threshold", () => {
    const onSelect = vi.fn();
    const onEdit = vi.fn();

    const handler = createFeatureDoubleClickHandler({
      thresholdMs: 400,
      onSelect,
      onEdit,
    });

    handler.handleClick(featureA);
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onEdit).not.toHaveBeenCalled();

    vi.advanceTimersByTime(250);

    handler.handleClick(featureA);
    expect(onSelect).toHaveBeenCalledTimes(2);
    expect(onEdit).toHaveBeenCalledTimes(1);
    expect(onEdit).toHaveBeenCalledWith(featureA);
  });

  it("does not trigger onEdit if second click is on a different feature", () => {
    const onSelect = vi.fn();
    const onEdit = vi.fn();

    const handler = createFeatureDoubleClickHandler({
      thresholdMs: 400,
      onSelect,
      onEdit,
    });

    handler.handleClick(featureA);
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(featureA);

    vi.advanceTimersByTime(200);

    handler.handleClick(featureB);
    expect(onSelect).toHaveBeenCalledTimes(2);
    expect(onSelect).toHaveBeenCalledWith(featureB);
    expect(onEdit).not.toHaveBeenCalled();
  });

  it("does not trigger onEdit if clicks exceed threshold", () => {
    const onSelect = vi.fn();
    const onEdit = vi.fn();

    const handler = createFeatureDoubleClickHandler({
      thresholdMs: 400,
      onSelect,
      onEdit,
    });

    handler.handleClick(featureA);
    vi.advanceTimersByTime(500);
    handler.handleClick(featureA);

    expect(onSelect).toHaveBeenCalledTimes(2);
    expect(onEdit).not.toHaveBeenCalled();
  });

  it("triggers onEdit on handleDblClick", () => {
    const onSelect = vi.fn();
    const onEdit = vi.fn();

    const handler = createFeatureDoubleClickHandler({
      onSelect,
      onEdit,
    });

    handler.handleDblClick(featureA);

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onEdit).toHaveBeenCalledTimes(1);
    expect(onEdit).toHaveBeenCalledWith(featureA);
  });

  it("deduplicates edit triggers if native dblclick immediately follows consecutive clicks", () => {
    const onSelect = vi.fn();
    const onEdit = vi.fn();

    const handler = createFeatureDoubleClickHandler({
      thresholdMs: 400,
      onSelect,
      onEdit,
    });

    handler.handleClick(featureA);
    vi.advanceTimersByTime(200);
    handler.handleClick(featureA); // consecutive click -> triggers edit
    expect(onEdit).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(10);
    handler.handleDblClick(featureA); // native dblclick right after -> should be deduplicated
    expect(onEdit).toHaveBeenCalledTimes(1);
  });
});
