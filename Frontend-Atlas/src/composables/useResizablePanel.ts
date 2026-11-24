import { ref, nextTick } from "vue";
import type { Ref } from "vue";

export interface ResizablePanelOptions {
  dimension: "width" | "height";
  initial: number | null;
  min: number;
  max: number | (() => number);
  cursor: "col-resize" | "row-resize";
  direction?: "normal" | "reverse";
  elementSelector?: string;
  defaultFallback?: number;
  onResize?: () => void;
  onResizeEnd?: () => void;
}

export function useResizablePanel(options: ResizablePanelOptions) {
  const size: Ref<any> = ref(options.initial);
  let isResizing = false;
  let startPos = 0;
  let startSize = 0;
  let prevCursor = "";
  let prevUserSelect = "";
  let rafId: number | null = null;

  function getMax(): number {
    return typeof options.max === "function" ? options.max() : options.max;
  }

  function resizeBy(delta: number) {
    const el = options.elementSelector
      ? (document.querySelector(options.elementSelector) as HTMLElement | null)
      : null;
    const current =
      size.value ??
      el?.[options.dimension === "width" ? "offsetWidth" : "offsetHeight"] ??
      options.defaultFallback ??
      options.min;
    size.value = Math.max(options.min, Math.min(getMax(), current + delta));
    nextTick(() => options.onResize?.());
  }

  function onMouseMove(event: MouseEvent) {
    const currentPos = options.dimension === "width" ? event.clientX : event.clientY;
    const delta = options.direction === "reverse" ? startPos - currentPos : currentPos - startPos;
    size.value = Math.max(options.min, Math.min(getMax(), startSize + delta));

    if (rafId === null) {
      rafId = window.requestAnimationFrame(() => {
        rafId = null;
        options.onResize?.();
      });
    }
  }

  function stopResize() {
    window.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("mouseup", stopResize);
    if (isResizing) {
      document.body.style.cursor = prevCursor;
      document.body.style.userSelect = prevUserSelect;
      isResizing = false;
      if (rafId !== null) {
        window.cancelAnimationFrame(rafId);
        rafId = null;
      }
      nextTick(() => options.onResizeEnd?.());
    }
  }

  function startResize(event: MouseEvent) {
    const el = options.elementSelector
      ? (document.querySelector(options.elementSelector) as HTMLElement | null)
      : null;
    startPos = options.dimension === "width" ? event.clientX : event.clientY;
    startSize =
      size.value ??
      el?.[options.dimension === "width" ? "offsetWidth" : "offsetHeight"] ??
      options.defaultFallback ??
      options.min;
    size.value = startSize;
    prevCursor = document.body.style.cursor;
    prevUserSelect = document.body.style.userSelect;
    isResizing = true;
    document.body.style.cursor = options.cursor;
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", stopResize);
  }

  return {
    size,
    startResize,
    resizeBy,
    stopResize,
  };
}
