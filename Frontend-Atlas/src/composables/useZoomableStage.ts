import { onBeforeUnmount, onMounted } from "vue";
import { ZoomableStageService } from "../services/ZoomableStageService";
import type { ZoomableStageOptions } from "../typescript/zoomableStage";

export function useZoomableStage(options: ZoomableStageOptions = {}) {
  const service = new ZoomableStageService(options);
  const tools = service.createTools();

  onMounted(() => {
    window.addEventListener("resize", tools.updateBaseStage);
  });

  onBeforeUnmount(() => {
    window.removeEventListener("resize", tools.updateBaseStage);
  });

  return tools;
}
