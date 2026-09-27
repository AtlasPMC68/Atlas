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

      <h2 class="text-xl font-semibold">{{ title }}</h2>

      <p class="text-sm text-base-content/70">
        {{ description }}
      </p>

      <div class="border rounded-md overflow-hidden">
        <h3 class="px-3 py-2 text-sm font-medium bg-base-200 border-b">
          Carte importée (sélection)
        </h3>

        <div
          ref="container"
          class="relative h-[28rem] bg-base-200 select-none"
          @mousedown="onMouseDown"
          @mousemove="onMouseMove"
          @mouseup="onMouseUp"
          @mouseleave="onMouseUp"
        >
          <img
            v-if="imageUrl"
            ref="imageEl"
            :src="imageUrl"
            class="w-full h-full object-contain pointer-events-none"
            alt="Carte importée"
            @load="onImageLoad"
          />

          <div
            v-if="selectionStyle"
            class="absolute border-2 border-[#2563eb] bg-[#2563eb]/15 pointer-events-none"
            :style="selectionStyle"
          />
        </div>
      </div>

      <div class="modal-action">
        <button class="btn btn-ghost" type="button" @click="requestClose">
          Annuler
        </button>
        <button class="btn btn-outline" @click="onSkip">Sauter l'étape</button>
        <button
          class="btn btn-primary"
          @click="onConfirm"
          :disabled="!bounds"
        >
          {{ confirmText }}
        </button>
      </div>
    </div>
  </dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import type { LegendBounds } from "../../typescript/legend";

const props = withDefaults(
  defineProps<{
    isOpen: boolean;
    imageUrl: string;
    initialBounds: LegendBounds | null;
    title?: string;
    description?: string;
    confirmText?: string;
  }>(),
  {
    isOpen: false,
    initialBounds: null,
    title: "Délimiter la zone",
    description: "Tracez un rectangle sur l'image pour indiquer la zone. Vous pouvez sauter cette étape si elle n'est pas présente.",
    confirmText: "Confirmer",
  },
);

const emit = defineEmits<{
  (e: "close"): void;
  (e: "skip"): void;
  (e: "confirmed", payload: LegendBounds): void;
}>();

const modalRef = ref<HTMLDialogElement | null>(null);

type DialogCloseReason = "cancel" | "success" | "programmatic";

const container = ref<HTMLDivElement | null>(null);
const imageEl = ref<HTMLImageElement | null>(null);

const imageNaturalWidth = ref<number>(0);
const imageNaturalHeight = ref<number>(0);

const isDrawing = ref<boolean>(false);
const dragStart = ref<{ x: number; y: number } | null>(null);
const bounds = ref<LegendBounds | null>(props.initialBounds);

watch(
  () => props.initialBounds,
  (value) => {
    bounds.value = value;
  },
);

watch(
  () => props.isOpen,
  (opened) => {
    if (opened) {
      bounds.value = props.initialBounds;
      if (modalRef.value && !modalRef.value.open) {
        modalRef.value.showModal();
      }
      return;
    }
    if (modalRef.value?.open) {
      closeDialog("programmatic");
    }
  },
  { immediate: true },
);

onMounted(() => {
  if (props.isOpen && modalRef.value && !modalRef.value.open) {
    modalRef.value.showModal();
  }
});

function requestClose(): void {
  if (modalRef.value?.open) {
    closeDialog("cancel");
    return;
  }
  emit("close");
}

function closeDialog(reason: DialogCloseReason): void {
  if (!modalRef.value?.open) return;
  modalRef.value.close(reason);
}

const displayRect = computed(() => {
  if (
    !container.value ||
    !imageNaturalWidth.value ||
    !imageNaturalHeight.value
  ) {
    return null;
  }

  const rect = container.value.getBoundingClientRect();
  const cw = rect.width;
  const ch = rect.height;

  const baseScale = Math.min(
    cw / imageNaturalWidth.value,
    ch / imageNaturalHeight.value,
  );
  const displayW = imageNaturalWidth.value * baseScale;
  const displayH = imageNaturalHeight.value * baseScale;
  const offsetX = (cw - displayW) / 2;
  const offsetY = (ch - displayH) / 2;

  return {
    offsetX,
    offsetY,
    displayW,
    displayH,
    baseScale,
  };
});

const selectionStyle = computed(() => {
  if (!bounds.value || !displayRect.value) return null;

  const { offsetX, offsetY, baseScale } = displayRect.value;

  return {
    left: `${offsetX + bounds.value.x * baseScale}px`,
    top: `${offsetY + bounds.value.y * baseScale}px`,
    width: `${bounds.value.width * baseScale}px`,
    height: `${bounds.value.height * baseScale}px`,
  };
});

function onImageLoad(): void {
  if (!imageEl.value) return;
  imageNaturalWidth.value = imageEl.value.naturalWidth || 0;
  imageNaturalHeight.value = imageEl.value.naturalHeight || 0;
}

function getImageLocalPoint(
  event: MouseEvent,
): { x: number; y: number } | null {
  if (!container.value || !displayRect.value) return null;

  const containerRect = container.value.getBoundingClientRect();
  const px = event.clientX - containerRect.left;
  const py = event.clientY - containerRect.top;

  const { offsetX, offsetY, displayW, displayH, baseScale } = displayRect.value;
  const ix = px - offsetX;
  const iy = py - offsetY;

  if (ix < 0 || iy < 0 || ix > displayW || iy > displayH) {
    return null;
  }

  return {
    x: ix / baseScale,
    y: iy / baseScale,
  };
}

function onMouseDown(event: MouseEvent): void {
  const point = getImageLocalPoint(event);
  if (!point) return;

  isDrawing.value = true;
  dragStart.value = point;
  bounds.value = {
    x: point.x,
    y: point.y,
    width: 0,
    height: 0,
  };
}

function onMouseMove(event: MouseEvent): void {
  if (!isDrawing.value || !dragStart.value) return;

  const point = getImageLocalPoint(event);
  if (!point) return;

  const x1 = Math.min(dragStart.value.x, point.x);
  const y1 = Math.min(dragStart.value.y, point.y);
  const x2 = Math.max(dragStart.value.x, point.x);
  const y2 = Math.max(dragStart.value.y, point.y);

  bounds.value = {
    x: x1,
    y: y1,
    width: x2 - x1,
    height: y2 - y1,
  };
}

function onMouseUp(): void {
  isDrawing.value = false;
  dragStart.value = null;

  if (!bounds.value) return;
  if (bounds.value.width < 2 || bounds.value.height < 2) {
    bounds.value = null;
  }
}

function onDialogClose() {
  const reason = modalRef.value?.returnValue;
  if (reason !== "success" && reason !== "programmatic") {
    emit("close");
  }

  if (modalRef.value) {
    modalRef.value.returnValue = "";
  }
}

function onSkip(): void {
  bounds.value = null;
  closeDialog("success");
  emit("skip");
}

function onConfirm(): void {
  if (!bounds.value) return;
  closeDialog("success");
  emit("confirmed", bounds.value);
}
</script>
