<template>
  <div v-if="isOpen" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
    <div class="bg-base-100 rounded-lg shadow-xl max-w-6xl w-full mx-4 p-6 flex flex-col gap-4">
      <div class="flex justify-between items-center mb-2">
        <h2 class="text-xl font-semibold">Géoréférencement de la carte</h2>
        <button class="btn btn-ghost btn-sm" @click="emit('close')">✕</button>
      </div>

      <p class="text-sm text-base-content/70 mb-2">
        Dessinez la même ligne de référence sur les deux cartes :
        à gauche sur la carte du monde (coordonnées réelles) et à droite
        sur l'image importée (pixels). Cliquez pour ajouter des points.
      </p>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 flex-1 min-h-[320px]">
        <div class="border rounded-md overflow-hidden">
          <h3 class="px-3 py-2 text-sm font-medium bg-base-200 border-b">
            Carte de référence (Leaflet)
          </h3>
          <GeoRefBaseMap v-model="worldPolyline" class="h-80" />
        </div>

        <div class="border rounded-md overflow-hidden">
          <h3 class="px-3 py-2 text-sm font-medium bg-base-200 border-b">
            Image importée (pixels)
          </h3>
          <GeoRefImageMap
            v-model="imagePolyline"
            :image-url="imageUrl"
            class="h-80"
          />
        </div>
      </div>

      <div class="flex justify-end gap-2 pt-2">
        <button class="btn btn-ghost" @click="resetPolylines">Réinitialiser</button>
        <button class="btn" @click="onConfirm" :disabled="!canConfirm">
          Valider les lignes
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from "vue";
import GeoRefBaseMap from "./GeoRefBaseMap.vue";
import GeoRefImageMap from "./GeoRefImageMap.vue";

const props = defineProps({
  isOpen: { type: Boolean, default: false },
  imageUrl: { type: String, required: true },
});

const emit = defineEmits(["close", "confirmed"]);

const worldPolyline = ref([]); // [ [lat,lng], ... ]
const imagePolyline = ref([]); // [ [x,y], ... ]

const canConfirm = computed(
  () => worldPolyline.value.length >= 2 && imagePolyline.value.length >= 2,
);

function resetPolylines() {
  worldPolyline.value = [];
  imagePolyline.value = [];
}

function onConfirm() {
  if (!canConfirm.value) return;
  
  const world = worldPolyline.value || [];
  const image = imagePolyline.value || [];

  // Resample both polylines to exactly 20 evenly-spaced points
  const resampledWorld = resamplePolyline(world, 20);
  const resampledImage = resamplePolyline(image, 20);

  console.log("Resampled polylines:", {
    originalWorld: world.length,
    resampledWorld: resampledWorld.length,
    originalImage: image.length,
    resampledImage: resampledImage.length
  });

  emit("confirmed", {
    worldPolyline: resampledWorld,
    imagePolyline: resampledImage,
  });
}

function resamplePolyline(points, targetCount) {
  if (points.length <= targetCount) {
    return [...points];
  }
  
  const resampled = [];
  for (let i = 0; i < targetCount; i++) {
    const index = Math.round((i / (targetCount - 1)) * (points.length - 1));
    resampled.push(points[index]);
  }
  return resampled;
}

watch(
  () => props.isOpen,
  (open) => {
    if (!open) {
      resetPolylines();
    }
  },
);
</script>
