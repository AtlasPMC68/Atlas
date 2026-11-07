<template>
  <div
    class="flex flex-col bg-gray-900 min-h-0 relative overflow-hidden"
    :class="width !== undefined ? 'shrink-0' : 'flex-1 min-w-0'"
    :style="width !== undefined ? { width: `${width}px` } : undefined"
  >
    <div class="px-3 py-2 bg-gray-800 text-white font-semibold flex items-center justify-between shrink-0 text-sm">
      <span class="flex items-center gap-1.5">
        <PhotoIcon class="w-4 h-4 text-gray-400" />
        Image de référence
      </span>
      <div class="flex items-center gap-1">
        <template v-if="displayImageUrl">
          <button
            type="button"
            class="btn btn-xs btn-ghost text-white px-1.5 min-h-0 h-6 text-xs"
            title="Dézoomer"
            @click="emit('zoom', -0.1)"
          >
            −
          </button>
          <button
            type="button"
            class="btn btn-xs btn-ghost text-white px-2 min-h-0 h-6 text-xs"
            title="Réinitialiser"
            @click="emit('reset-zoom')"
          >
            {{ Math.round(imgZoom * 100) }}%
          </button>
          <button
            type="button"
            class="btn btn-xs btn-ghost text-white px-1.5 min-h-0 h-6 text-xs"
            title="Zoomer"
            @click="emit('zoom', 0.1)"
          >
            +
          </button>
        </template>

        <label
          class="btn btn-xs btn-ghost text-white px-1.5 min-h-0 h-6 text-xs cursor-pointer"
          title="Charger une image pour visualiser"
        >
          <ArrowUpTrayIcon class="w-3.5 h-3.5" />
          <span class="hidden sm:inline">Changer</span>
          <input
            type="file"
            accept="image/avif,image/gif,image/jpeg,image/png,image/webp"
            class="hidden"
            :disabled="isUpdatingReferenceImage"
            @change="emit('select-image', $event)"
          />
        </label>
        <button
          v-if="displayImageUrl"
          type="button"
          class="btn btn-xs btn-ghost btn-square text-white hover:bg-error/80 px-1 min-h-0 h-6"
          title="Supprimer l'image de référence associée à cette carte"
          aria-label="Supprimer l'image de référence"
          @click="emit('remove-image')"
        >
          <XMarkIcon class="w-4 h-4" />
        </button>
      </div>
    </div>

    <div
      class="flex-1 min-h-0 overflow-auto flex items-center justify-center p-2 bg-gray-950"
      @wheel="emit('wheel', $event)"
    >
      <img
        v-if="displayImageUrl"
        :src="displayImageUrl"
        alt="Image de la carte pour visualisation"
        class="max-w-full max-h-full object-contain transition-transform duration-100 origin-center select-none will-change-transform"
        :style="{ transform: `scale(${imgZoom}) translateZ(0)` }"
      />
      <div v-else class="flex flex-col items-center justify-center p-6 text-center gap-3 max-w-sm">
        <PhotoIcon class="w-12 h-12 text-gray-500" />
        <div class="flex flex-col gap-1">
          <p class="text-sm text-gray-200 font-semibold">
            Aucune image originale disponible pour cette carte.
          </p>
          <p class="text-xs text-gray-400">
            Vous pouvez importer une image depuis votre ordinateur pour vous repérer pendant la validation.
          </p>
        </div>
        <label class="btn btn-primary btn-sm text-white cursor-pointer gap-1.5 font-medium shadow-xs mt-1">
          <ArrowUpTrayIcon class="w-3.5 h-3.5" />
          <span>Importer une image pour visualiser</span>
          <input
            type="file"
            accept="image/avif,image/gif,image/jpeg,image/png,image/webp"
            class="hidden"
            :disabled="isUpdatingReferenceImage"
            @change="emit('select-image', $event)"
          />
        </label>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { PhotoIcon, ArrowUpTrayIcon, XMarkIcon } from "@heroicons/vue/24/outline";

defineProps<{
  width?: number;
  displayImageUrl?: string | null;
  imgZoom: number;
  isUpdatingReferenceImage?: boolean;
}>();

const emit = defineEmits<{
  (e: "zoom", delta: number): void;
  (e: "reset-zoom"): void;
  (e: "wheel", event: WheelEvent): void;
  (e: "select-image", event: Event): void;
  (e: "remove-image"): void;
}>();
</script>

