import { computed, ref } from "vue";
import type { BaseStage, StagePosition, ZoomableStageOptions } from "../typescript/zoomableStage";

export class ZoomableStageService {
  public container;
  public imageEl;

  public zoomMin: number;
  public zoomMax: number;
  private zoomStepFactor: number;

  public zoom = ref(1);
  public panX = ref(0);
  public panY = ref(0);

  public baseStage = ref<BaseStage | null>(null);

  public stagePxPerImagePx = computed(() => {
    if (!this.baseStage.value) return 1;
    return this.baseStage.value.renderedW / Math.max(1, this.baseStage.value.naturalW);
  });

  public stageStyle = computed(() => {
    if (!this.baseStage.value) {
      return {
        left: "0px",
        top: "0px",
        width: "100%",
        height: "100%",
        transform: `translate(${this.panX.value}px, ${this.panY.value}px) scale(${this.zoom.value})`,
        transformOrigin: "0 0",
      } as Record<string, string>;
    }
    return {
      left: `${this.baseStage.value.offsetX}px`,
      top: `${this.baseStage.value.offsetY}px`,
      width: `${this.baseStage.value.renderedW}px`,
      height: `${this.baseStage.value.renderedH}px`,
      transform: `translate(${this.panX.value}px, ${this.panY.value}px) scale(${this.zoom.value})`,
      transformOrigin: "0 0",
    } as Record<string, string>;
  });

  constructor(options: ZoomableStageOptions = {}) {
    this.zoomMin = options.zoomMin ?? 1;
    this.zoomMax = options.zoomMax ?? 8;
    this.zoomStepFactor = options.zoomStepFactor ?? 1.25;

    this.container = options.containerRef ?? ref<HTMLElement | null>(null);
    this.imageEl = options.imageRef ?? ref<HTMLImageElement | null>(null);
  }

  updateBaseStage = () => {
    if (!this.container.value || !this.imageEl.value) return;
    const containerRect = this.container.value.getBoundingClientRect();
    const naturalW = this.imageEl.value.naturalWidth;
    const naturalH = this.imageEl.value.naturalHeight;
    if (!naturalW || !naturalH) return;

    const containerW = containerRect.width;
    const containerH = containerRect.height;
    const containerAspect = containerW / containerH;
    const imageAspect = naturalW / naturalH;

    let renderedW: number, renderedH: number, offsetX: number, offsetY: number;
    if (imageAspect > containerAspect) {
      renderedW = containerW;
      renderedH = containerW / imageAspect;
      offsetX = 0;
      offsetY = (containerH - renderedH) / 2;
    } else {
      renderedH = containerH;
      renderedW = containerH * imageAspect;
      offsetX = (containerW - renderedW) / 2;
      offsetY = 0;
    }

    this.baseStage.value = {
      containerW,
      containerH,
      renderedW,
      renderedH,
      offsetX,
      offsetY,
      naturalW,
      naturalH,
    };

    const clamped = this.clampPan(this.panX.value, this.panY.value);
    this.panX.value = clamped.x;
    this.panY.value = clamped.y;
  };

  clampPan(nextX: number, nextY: number) {
    if (!this.baseStage.value) return { x: 0, y: 0 };
    const { containerW, containerH, offsetX, offsetY, renderedW, renderedH } =
      this.baseStage.value;

    const scaledW = renderedW * this.zoom.value;
    const scaledH = renderedH * this.zoom.value;

    if (scaledW <= containerW) {
      const centeredLeft = (containerW - scaledW) / 2;
      nextX = centeredLeft - offsetX;
    } else {
      const minX = containerW - offsetX - scaledW;
      const maxX = -offsetX;
      nextX = Math.min(maxX, Math.max(minX, nextX));
    }

    if (scaledH <= containerH) {
      const centeredTop = (containerH - scaledH) / 2;
      nextY = centeredTop - offsetY;
    } else {
      const minY = containerH - offsetY - scaledH;
      const maxY = -offsetY;
      nextY = Math.min(maxY, Math.max(minY, nextY));
    }

    return { x: nextX, y: nextY };
  }

  resetView() {
    this.zoom.value = 1;
    this.panX.value = 0;
    this.panY.value = 0;
    const clamped = this.clampPan(this.panX.value, this.panY.value);
    this.panX.value = clamped.x;
    this.panY.value = clamped.y;
  }

  getLocalPointer(event: MouseEvent) {
    if (!this.container.value) return null;
    const rect = this.container.value.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  getStagePositionFromEvent(event: MouseEvent): StagePosition | null {
    if (!this.baseStage.value) return null;
    const local = this.getLocalPointer(event);
    if (!local) return null;

    const { offsetX, offsetY, renderedW, renderedH } = this.baseStage.value;

    const stageX = (local.x - offsetX - this.panX.value) / this.zoom.value;
    const stageY = (local.y - offsetY - this.panY.value) / this.zoom.value;

    const nx = stageX / renderedW;
    const ny = stageY / renderedH;

    if (nx < 0 || nx > 1 || ny < 0 || ny > 1) return null;

    return {
      normalized: { x: nx, y: ny },
      stage: { x: stageX, y: stageY },
    };
  }

  applyZoom(newZoom: number, anchorX: number, anchorY: number) {
    if (!this.baseStage.value) return;
    const { offsetX, offsetY } = this.baseStage.value;

    const currentZoom = this.zoom.value;
    const stageX = (anchorX - offsetX - this.panX.value) / currentZoom;
    const stageY = (anchorY - offsetY - this.panY.value) / currentZoom;

    this.zoom.value = newZoom;

    const nextPanX = anchorX - offsetX - stageX * newZoom;
    const nextPanY = anchorY - offsetY - stageY * newZoom;
    const clamped = this.clampPan(nextPanX, nextPanY);
    this.panX.value = clamped.x;
    this.panY.value = clamped.y;
  }

  zoomIn() {
    if (!this.container.value) return;
    const rect = this.container.value.getBoundingClientRect();
    const anchorX = rect.width / 2;
    const anchorY = rect.height / 2;
    const next = Math.min(this.zoomMax, Number((this.zoom.value * this.zoomStepFactor).toFixed(4)));
    this.applyZoom(next, anchorX, anchorY);
  }

  zoomOut() {
    if (!this.container.value) return;
    const rect = this.container.value.getBoundingClientRect();
    const anchorX = rect.width / 2;
    const anchorY = rect.height / 2;
    const next = Math.max(this.zoomMin, Number((this.zoom.value / this.zoomStepFactor).toFixed(4)));
    this.applyZoom(next, anchorX, anchorY);
  }

  onWheel(event: WheelEvent) {
    if (!this.baseStage.value) return;

    const local = this.getLocalPointer(event as unknown as MouseEvent);
    if (!local) return;

    const direction = event.deltaY < 0 ? 1 : -1;
    const factor = direction > 0 ? 1.1 : 1 / 1.1;
    const next = Math.min(this.zoomMax, Math.max(this.zoomMin, this.zoom.value * factor));
    this.applyZoom(Number(next.toFixed(4)), local.x, local.y);
  }

  createTools() {
    return {
      container: this.container,
      imageEl: this.imageEl,
      baseStage: this.baseStage,
      stagePxPerImagePx: this.stagePxPerImagePx,
      stageStyle: this.stageStyle,
      zoom: this.zoom,
      panX: this.panX,
      panY: this.panY,
      zoomMin: this.zoomMin,
      zoomMax: this.zoomMax,
      updateBaseStage: this.updateBaseStage,
      clampPan: this.clampPan.bind(this),
      resetView: this.resetView.bind(this),
      getLocalPointer: this.getLocalPointer.bind(this),
      getStagePositionFromEvent: this.getStagePositionFromEvent.bind(this),
      applyZoom: this.applyZoom.bind(this),
      zoomIn: this.zoomIn.bind(this),
      zoomOut: this.zoomOut.bind(this),
      onWheel: this.onWheel.bind(this),
    };
  }
}
