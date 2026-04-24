<template>
  <dialog ref="modalRef" class="modal" @close="onDialogClose">
    <div class="modal-box max-w-5xl w-full flex flex-col gap-4">
      <form method="dialog">
        <button
          value="cancel"
          class="btn btn-sm btn-circle btn-ghost absolute right-2 top-2"
        >
          ✕
        </button>
      </form>

      <h2 class="text-xl font-semibold">Sélectionner les couleurs à extraire</h2>

      <p class="text-sm text-base-content/70">
        Cliquez sur les zones colorées de la carte pour sélectionner les couleurs
        à extraire. Vous devez sélectionner au moins une couleur pour continuer.
      </p>

      <div class="border rounded-md overflow-hidden">
        <div class="px-3 py-2 text-xs font-medium bg-base-200 border-b flex items-center justify-between gap-3">
          <span class="text-xs text-base-content/80">
            Carte importée — cliquez pour échantillonner une couleur
          </span>
          <div class="flex items-center gap-2">
            <span class="text-xs text-base-content/60 whitespace-nowrap">
              {{ Math.round(zoom * 100) }}%
            </span>
            <button
              class="btn btn-xs"
              type="button"
              :disabled="isLoading || zoom <= ZOOM_MIN"
              @click="zoomOut"
            >
              −
            </button>
            <button
              class="btn btn-xs"
              type="button"
              :disabled="isLoading || zoom === 1"
              @click="resetZoom"
            >
              100%
            </button>
            <button
              class="btn btn-xs"
              type="button"
              :disabled="isLoading || zoom >= ZOOM_MAX"
              @click="zoomIn"
            >
              +
            </button>
          </div>
        </div>

        <div
          ref="container"
          class="relative h-[28rem] bg-base-200 select-none overflow-hidden"
          :class="containerCursorClass"
          @mousedown.left="onPointerDown"
          @mousemove="onPointerMove"
          @mouseup.left="onPointerUp"
          @mouseleave="onPointerLeave"
          @wheel.prevent="onWheel"
        >
          <div v-if="imageUrl" class="absolute" :style="stageStyle">
            <img
              ref="imageEl"
              :src="imageUrl"
              class="w-full h-full object-contain pointer-events-none select-none"
              alt="Carte importée"
              @load="onImageLoad"
            />
          </div>

          <!-- Pending click markers (loading) -->
          <div
            v-if="baseStage"
            v-for="pending in pendingClicks"
            :key="pending.id"
            class="absolute rounded-full border-2 border-white bg-base-300 animate-pulse pointer-events-none"
            :style="{
              width: `${markerDiameterFromRadius(pending.sampleRadiusPx) * zoom}px`,
              height: `${markerDiameterFromRadius(pending.sampleRadiusPx) * zoom}px`,
              left: `${stageToContainerX(pending.stageX)}px`,
              top: `${stageToContainerY(pending.stageY)}px`,
              transform: 'translate(-50%, -50%)',
            }"
          />

          <!-- Confirmed click markers -->
          <div
            v-if="baseStage"
            v-for="(color, index) in pickedColors"
            :key="`dot-${index}`"
            class="absolute rounded-full border-2 border-white pointer-events-none shadow"
            :style="{
              width: `${markerDiameterFromRadius(color.sampleRadiusPx) * zoom}px`,
              height: `${markerDiameterFromRadius(color.sampleRadiusPx) * zoom}px`,
              left: `${stageToContainerX(color.stageX)}px`,
              top: `${stageToContainerY(color.stageY)}px`,
              backgroundColor: color.hex,
              transform: 'translate(-50%, -50%)',
            }"
          />
        </div>
      </div>

      <!-- Picked color list with editable names -->
      <div v-if="pickedColors.length > 0" class="flex flex-col gap-2 min-h-0">
        <span class="text-sm font-medium">Couleurs sélectionnées :</span>
        <div class="flex flex-col gap-2 max-h-56 overflow-y-auto pr-1">
          <div
            v-for="(color, index) in pickedColors"
            :key="`row-${index}`"
            class="flex items-center gap-3 bg-base-200 rounded-lg px-3 py-2"
          >
            <!-- Color dot -->
            <div
              class="w-8 h-8 rounded-full border border-base-300 shrink-0 shadow-sm"
              :style="{ backgroundColor: color.hex }"
            />
            <!-- Hex label -->
            <span class="text-xs font-mono text-base-content/50 w-16 shrink-0">{{ color.hex }}</span>
            <!-- Editable name -->
            <input
              v-model="color.name"
              type="text"
              class="input input-sm input-bordered flex-1 min-w-0"
              placeholder="Nom de la zone…"
            />
            <!-- Remove -->
            <button
              class="btn btn-sm btn-ghost btn-circle shrink-0"
              type="button"
              @click="removeColor(index)"
            >
              ✕
            </button>
          </div>
        </div>
      </div>

      <p v-else class="text-sm text-base-content/50 italic">
        Aucune couleur sélectionnée — sélectionnez au moins une couleur pour continuer.
      </p>

      <p v-if="sampleError" class="text-sm text-error">{{ sampleError }}</p>

      <div class="modal-action">
        <button class="btn btn-ghost" type="button" @click="requestClose">
          Annuler
        </button>
        <button
          class="btn btn-primary"
          type="button"
          :disabled="pickedColors.length === 0 || isLoading"
          @click="onConfirm"
        >
          Confirmer les couleurs ({{ pickedColors.length }})
        </button>
      </div>
    </div>
  </dialog>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed, nextTick } from "vue";
import { showAlert } from "../../composables/useAlert";
import { useZoomableStage } from "../../composables/useZoomableStage";
import { apiFetch } from "../../utils/api";
import type {
  PendingClick,
  PickedColor,
  SampleColorResponse,
  DialogCloseReason,
} from "../../typescript/colorPicker";

const props = withDefaults(
  defineProps<{
    isOpen: boolean;
    imageUrl: string;
    imageFile: File;
  }>(),
  { isOpen: false },
);

const emit = defineEmits<{
  (e: "close"): void;
  (e: "confirmed", colors: { x: number; y: number; name: string; radius: number }[]): void;
}>();

const modalRef = ref<HTMLDialogElement | null>(null);

const container = ref<HTMLDivElement | null>(null);
const imageEl = ref<HTMLImageElement | null>(null);

const {
  baseStage,
  stagePxPerImagePx,
  stageStyle,
  zoom,
  panX,
  panY,
  zoomMin: ZOOM_MIN,
  zoomMax: ZOOM_MAX,
  updateBaseStage,
  clampPan,
  getLocalPointer,
  getStagePositionFromEvent,
  zoomIn,
  zoomOut,
  resetView,
  onWheel,
} = useZoomableStage({
  containerRef: container,
  imageRef: imageEl,
  zoomMin: 1,
  zoomMax: 8,
  zoomStepFactor: 1.25,
});

const pickedColors = ref<PickedColor[]>([]);
const pendingClicks = ref<PendingClick[]>([]);
const isLoading = ref(false);
const sampleError = ref<string | null>(null);
let pendingIdCounter = 0;

const BASE_SAMPLE_RADIUS_PX = 20;
const sampleRadiusPx = computed(() =>
  Math.max(3, Math.min(200, Math.round(BASE_SAMPLE_RADIUS_PX / zoom.value))),
);

function markerDiameterFromRadius(radiusImagePx: number) {
  const r = Number(radiusImagePx);
  if (!Number.isFinite(r)) return 6;
  const diameterStagePx = 2 * Math.max(1, Math.min(200, r)) * stagePxPerImagePx.value;
  return Math.max(6, Math.round(diameterStagePx));
}

function stageToContainerX(stageX: number) {
  if (!baseStage.value) return 0;
  return baseStage.value.offsetX + panX.value + stageX * zoom.value;
}

function stageToContainerY(stageY: number) {
  if (!baseStage.value) return 0;
  return baseStage.value.offsetY + panY.value + stageY * zoom.value;
}

const isPointerDown = ref(false);
const hasDragged = ref(false);
const pointerStart = ref({ x: 0, y: 0 });
const panStart = ref({ x: 0, y: 0 });

const containerCursorClass = computed(() => {
  if (isLoading.value) return "cursor-wait";
  if (zoom.value > 1) {
    return isPointerDown.value ? "cursor-grabbing" : "cursor-grab";
  }
  return "cursor-crosshair";
});

let closeReason: DialogCloseReason = "programmatic";

onMounted(() => {
  if (props.isOpen && modalRef.value && !modalRef.value.open) {
    modalRef.value.showModal();
  }
});

watch(
  () => props.isOpen,
  (opened) => {
    if (opened) {
      pickedColors.value = [];
      pendingClicks.value = [];
      sampleError.value = null;
      resetView();
      if (modalRef.value && !modalRef.value.open) {
        modalRef.value.showModal();
      }
      nextTick(() => updateBaseStage());
      return;
    }
    if (modalRef.value?.open) {
      closeReason = "programmatic";
      modalRef.value.close();
    }
  },
);

function onDialogClose() {
  const returnValue = modalRef.value?.returnValue;

  // We emit "close" for user-driven closes (✕ / ESC / native cancel),
  // but not when we close programmatically in response to prop changes.
  const isProgrammaticClose = returnValue === "programmatic";
  const isSuccessClose = closeReason === "success" || returnValue === "success";

  if (!isProgrammaticClose && !isSuccessClose) {
    emit("close");
  }

  closeReason = "programmatic";
}

function requestClose() {
  closeReason = "cancel";
  if (modalRef.value?.open) modalRef.value.close("cancel");
}

function onImageLoad() {
  updateBaseStage();
}

function resetZoom() {
  resetView();
}

function onPointerDown(event: MouseEvent) {
  if (isLoading.value) return;
  if (event.button !== 0) return;
  isPointerDown.value = true;
  hasDragged.value = false;
  const local = getLocalPointer(event);
  if (!local) return;
  pointerStart.value = local;
  panStart.value = { x: panX.value, y: panY.value };
}

function onPointerMove(event: MouseEvent) {
  if (!isPointerDown.value) return;
  if (zoom.value <= 1) return;
  const local = getLocalPointer(event);
  if (!local) return;

  const dx = local.x - pointerStart.value.x;
  const dy = local.y - pointerStart.value.y;
  if (!hasDragged.value && (Math.abs(dx) > 3 || Math.abs(dy) > 3)) {
    hasDragged.value = true;
  }

  if (!hasDragged.value) return;

  const clamped = clampPan(panStart.value.x + dx, panStart.value.y + dy);
  panX.value = clamped.x;
  panY.value = clamped.y;
}

function onPointerUp(event: MouseEvent) {
  if (!isPointerDown.value) return;
  isPointerDown.value = false;
  if (hasDragged.value) return;
  void sampleAtEvent(event);
}

function onPointerLeave() {
  isPointerDown.value = false;
}

async function sampleAtEvent(event: MouseEvent) {
  if (isLoading.value) return;
  const pos = getStagePositionFromEvent(event);
  if (!pos) return;

  sampleError.value = null;
  isLoading.value = true;

  const pendingId = ++pendingIdCounter;
  pendingClicks.value.push({
    id: pendingId,
    stageX: pos.stage.x,
    stageY: pos.stage.y,
    sampleRadiusPx: sampleRadiusPx.value,
  });

  try {
    const formData = new FormData();
    formData.append("file", props.imageFile);
    formData.append("x", String(pos.normalized.x));
    formData.append("y", String(pos.normalized.y));
    formData.append("radius", String(sampleRadiusPx.value));

    const response = await apiFetch("/projects/sample-color", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      throw new Error("Échec de l'échantillonnage de la couleur");
    }

    const data: SampleColorResponse = await response.json();

    const normalizedReturnedName = (data.name ?? "").trim().toLowerCase();
    const normalizedReturnedHex = (data.hex ?? "").trim().toLowerCase();
    const alreadyPicked = pickedColors.value.some((c) => {
      const normalizedExistingName = (c.name ?? "").trim().toLowerCase();
      const normalizedExistingHex = (c.hex ?? "").trim().toLowerCase();
      return (
        (normalizedReturnedName.length > 0 &&
          normalizedExistingName === normalizedReturnedName) ||
        (normalizedReturnedHex.length > 0 &&
          normalizedExistingHex === normalizedReturnedHex)
      );
    });

    if (alreadyPicked) {
      const msg = "Couleur déjà sélectionnée. Cliquez sur une autre zone.";
      sampleError.value = msg;
      showAlert("error", msg);
      return;
    }

    pickedColors.value.push({
      hex: data.hex,
      rgb: data.rgb,
      name: data.name,
      stageX: pos.stage.x,
      stageY: pos.stage.y,
      normalizedX: pos.normalized.x,
      normalizedY: pos.normalized.y,
      sampleRadiusPx: sampleRadiusPx.value,
    });
  } catch (err) {
    sampleError.value =
      err instanceof Error ? err.message : "Erreur lors de l'échantillonnage";
  } finally {
    pendingClicks.value = pendingClicks.value.filter((p) => p.id !== pendingId);
    isLoading.value = pendingClicks.value.length > 0;
  }
}

function removeColor(index: number) {
  pickedColors.value.splice(index, 1);
}

function onConfirm() {
  if (pickedColors.value.length === 0) return;
  closeReason = "success";
  emit(
    "confirmed",
    pickedColors.value.map((c) => ({
      x: c.normalizedX,
      y: c.normalizedY,
      name: c.name,
      radius: c.sampleRadiusPx,
    })),
  );
  if (modalRef.value?.open) modalRef.value.close("success");
}
</script>
