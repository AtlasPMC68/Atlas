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
        à extraire. Sautez cette étape pour utiliser la détection automatique.
      </p>

      <div class="border rounded-md overflow-hidden">
        <h3 class="px-3 py-2 text-sm font-medium bg-base-200 border-b">
          Carte importée — cliquez pour échantillonner une couleur
        </h3>

        <div
          ref="container"
          class="relative h-[28rem] bg-base-200 select-none"
          :class="isLoading ? 'cursor-wait' : 'cursor-crosshair'"
          @click="onContainerClick"
        >
          <img
            v-if="imageUrl"
            ref="imageEl"
            :src="imageUrl"
            class="w-full h-full object-contain pointer-events-none"
            alt="Carte importée"
            @load="onImageLoad"
          />

          <!-- Pending click dots (loading) -->
          <div
            v-for="pending in pendingClicks"
            :key="pending.id"
            class="absolute w-5 h-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-base-300 animate-pulse pointer-events-none"
            :style="{ left: `${pending.displayX}px`, top: `${pending.displayY}px` }"
          />

          <!-- Confirmed click dots -->
          <div
            v-for="(color, index) in pickedColors"
            :key="`dot-${index}`"
            class="absolute w-5 h-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white pointer-events-none shadow"
            :style="{
              left: `${color.displayX}px`,
              top: `${color.displayY}px`,
              backgroundColor: color.hex,
            }"
          />
        </div>
      </div>

      <!-- Picked color list with editable names -->
      <div v-if="pickedColors.length > 0" class="flex flex-col gap-2">
        <span class="text-sm font-medium">Couleurs sélectionnées :</span>
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

      <p v-else class="text-sm text-base-content/50 italic">
        Aucune couleur sélectionnée — la détection automatique sera utilisée si vous sautez l'étape.
      </p>

      <p v-if="sampleError" class="text-sm text-error">{{ sampleError }}</p>

      <div class="modal-action">
        <button class="btn btn-ghost" type="button" @click="requestClose">
          Annuler
        </button>
        <button class="btn btn-outline" type="button" @click="onSkip">
          Sauter l'étape
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
import { ref, watch, onMounted } from "vue";
import keycloak from "../../keycloak";

interface PickedColor {
  hex: string;
  rgb: [number, number, number];
  name: string;
  displayX: number;
  displayY: number;
}

interface PendingClick {
  id: number;
  displayX: number;
  displayY: number;
}

interface SampleColorResponse {
  hex: string;
  rgb: [number, number, number];
  lab: [number, number, number];
  name: string;
}

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
  (e: "skip"): void;
  (e: "confirmed", colors: { rgb: [number, number, number]; name: string }[]): void;
}>();

const modalRef = ref<HTMLDialogElement | null>(null);
const container = ref<HTMLDivElement | null>(null);
const imageEl = ref<HTMLImageElement | null>(null);

const pickedColors = ref<PickedColor[]>([]);
const pendingClicks = ref<PendingClick[]>([]);
const isLoading = ref(false);
const sampleError = ref<string | null>(null);
let pendingIdCounter = 0;

type DialogCloseReason = "cancel" | "success" | "programmatic";
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
      if (modalRef.value && !modalRef.value.open) {
        modalRef.value.showModal();
      }
      return;
    }
    if (modalRef.value?.open) {
      closeReason = "programmatic";
      modalRef.value.close();
    }
  },
);

function onImageLoad() {
  // nothing needed — naturalWidth/Height are read on click
}

function onDialogClose() {
  if (closeReason !== "success" && closeReason !== "programmatic") {
    emit("close");
  }
  closeReason = "programmatic";
}

function requestClose() {
  closeReason = "cancel";
  emit("close");
  if (modalRef.value?.open) modalRef.value.close();
}

/** Compute normalized [0,1] coordinates and display pixel position for a click,
 *  accounting for object-contain letterboxing inside the container. */
function getClickPosition(event: MouseEvent): {
  normalized: { x: number; y: number };
  display: { x: number; y: number };
} | null {
  if (!imageEl.value || !container.value) return null;

  const containerRect = container.value.getBoundingClientRect();
  const naturalW = imageEl.value.naturalWidth;
  const naturalH = imageEl.value.naturalHeight;
  if (!naturalW || !naturalH) return null;

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

  const clickX = event.clientX - containerRect.left - offsetX;
  const clickY = event.clientY - containerRect.top - offsetY;

  const nx = clickX / renderedW;
  const ny = clickY / renderedH;

  // Ignore clicks in the letterbox area
  if (nx < 0 || nx > 1 || ny < 0 || ny > 1) return null;

  return {
    normalized: { x: nx, y: ny },
    display: {
      x: event.clientX - containerRect.left,
      y: event.clientY - containerRect.top,
    },
  };
}

async function onContainerClick(event: MouseEvent) {
  if (isLoading.value) return;

  const pos = getClickPosition(event);
  if (!pos) return;

  sampleError.value = null;
  isLoading.value = true;

  const pendingId = ++pendingIdCounter;
  pendingClicks.value.push({
    id: pendingId,
    displayX: pos.display.x,
    displayY: pos.display.y,
  });

  try {
    const formData = new FormData();
    formData.append("file", props.imageFile);
    formData.append("x", String(pos.normalized.x));
    formData.append("y", String(pos.normalized.y));
    formData.append("radius", "20");

    const response = await fetch(
      `${import.meta.env.VITE_API_URL}/projects/sample-color`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${keycloak.token}` },
        body: formData,
      },
    );

    if (!response.ok) {
      throw new Error("Échec de l'échantillonnage de la couleur");
    }

    const data: SampleColorResponse = await response.json();

    pickedColors.value.push({
      hex: data.hex,
      rgb: data.rgb,
      name: data.name,
      displayX: pos.display.x,
      displayY: pos.display.y,
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

function onSkip() {
  closeReason = "success";
  emit("skip");
  if (modalRef.value?.open) modalRef.value.close();
}

function onConfirm() {
  if (pickedColors.value.length === 0) return;
  closeReason = "success";
  emit(
    "confirmed",
    pickedColors.value.map((c) => ({ rgb: c.rgb, name: c.name })),
  );
  if (modalRef.value?.open) modalRef.value.close();
}
</script>
