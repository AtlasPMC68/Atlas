<template>
  <dialog ref="dialogRef" class="modal" data-testid="delete-feature-dialog">
    <div class="modal-box max-w-lg relative">
      <button
        type="button"
        class="btn btn-sm btn-circle btn-ghost absolute right-4 top-4 z-10"
        :disabled="isDeleting"
        @click="close"
      >
        ✕
      </button>

      <h3 class="text-xl font-bold flex items-center gap-2 pr-10">
        <ExclamationTriangleIcon
          v-if="hasMultiMapFeature"
          class="w-5 h-5 text-warning shrink-0"
        />
        {{ hasMultiMapFeature ? "Élément partagé sur plusieurs cartes" : "Supprimer l'élément" }}
      </h3>

      <!-- Multi-map deletion view -->
      <div v-if="hasMultiMapFeature" class="py-3 flex flex-col gap-3">
        <p class="text-sm">
          <span class="font-semibold break-words">{{ featureDisplayName }}</span>
          est présent sur <span class="font-bold">{{ targetMaps.length }} cartes</span> :
        </p>

        <div class="flex items-center justify-between text-xs text-base-content/70 px-1">
          <span>Sélectionnez les cartes d'où retirer cet élément :</span>
          <button
            type="button"
            class="btn btn-ghost btn-xs text-primary hover:bg-base-200"
            @click="toggleSelectAllMaps"
          >
            {{ allMapsSelected ? "Tout décocher" : "Tout cocher" }}
          </button>
        </div>

        <!-- Scrollable list of maps with checkboxes, colors, titles and dates -->
        <div class="max-h-48 overflow-y-auto rounded-lg bg-base-200/70 border border-base-300 divide-y divide-base-300 text-xs">
          <label
            v-for="mapItem in targetMaps"
            :key="mapItem.id"
            class="flex items-center gap-3 px-3 py-2 cursor-pointer hover:bg-base-200 transition-colors"
          >
            <input
              type="checkbox"
              class="checkbox checkbox-primary checkbox-sm shrink-0"
              :value="mapItem.id"
              :checked="selectedMapIds.has(mapItem.id)"
              @change="toggleMapSelection(mapItem.id)"
            />
            <span
              v-if="mapItem.color"
              class="w-3 h-3 rounded-full shrink-0 border border-base-content/20"
              :style="{ backgroundColor: mapItem.color }"
            ></span>
            <div class="flex flex-col flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="font-semibold truncate" :title="mapItem.title">
                  {{ mapItem.title }}
                </span>
                <span
                  v-if="mapItem.isCurrent"
                  class="badge badge-primary badge-xs shrink-0"
                >
                  Carte actuelle
                </span>
              </div>
              <span v-if="mapItem.dateLabel" class="text-[11px] text-base-content/60">
                Période : {{ mapItem.dateLabel }}
              </span>
            </div>
          </label>
        </div>

        <p class="text-xs text-base-content/70">
          Souhaitez-vous le <strong>retirer des cartes sélectionnées</strong> ci-dessus ou le <strong>supprimer définitivement du projet</strong> ?
        </p>
      </div>

      <!-- Single map deletion view -->
      <p v-else class="py-4 text-sm">
        Êtes-vous sûr de vouloir supprimer
        <span class="font-semibold break-words">{{ featureDisplayName }}</span> ?
        Cette action est irréversible.
      </p>

      <div class="modal-action mt-6 flex flex-col-reverse sm:flex-row sm:items-center gap-2">
        <button
          type="button"
          class="modal-secondary-btn sm:mr-auto"
          :disabled="isDeleting"
          @click="close"
        >
          Annuler
        </button>

        <button
          v-if="hasMultiMapFeature"
          type="button"
          class="btn btn-primary rounded-lg whitespace-nowrap"
          data-testid="remove-from-map-btn"
          :disabled="isDeleting || selectedMapIds.size === 0"
          @click="confirmRemoveFromSelectedMaps"
        >
          <span v-if="isDeleting" class="loading loading-spinner loading-xs"></span>
          <span v-else>
            {{ removeButtonLabel }}
          </span>
        </button>

        <button
          type="button"
          class="btn btn-error rounded-lg whitespace-nowrap"
          :class="
            hasMultiMapFeature
              ? 'btn-outline text-error hover:!text-white'
              : 'text-white min-w-32'
          "
          data-testid="confirm-delete-feature-btn"
          :disabled="isDeleting"
          @click="confirmDeleteEverywhere"
        >
          <span v-if="isDeleting" class="loading loading-spinner loading-xs"></span>
          <span v-else>
            {{ hasMultiMapFeature ? "Supprimer partout" : "Supprimer" }}
          </span>
        </button>
      </div>
    </div>

    <form method="dialog" class="modal-backdrop">
      <button :disabled="isDeleting" @click="close">close</button>
    </form>
  </dialog>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { ExclamationTriangleIcon } from "@heroicons/vue/24/outline";
import type { Feature } from "../typescript/feature";
import type { MapPeriod } from "../typescript/map";
import { getFeatureMapIds } from "../utils/featureHelpers";

export interface MapDeletionItem {
  id: string;
  title: string;
  dateLabel: string;
  color?: string;
  isCurrent: boolean;
}

const props = withDefaults(
  defineProps<{
    features?: Feature[];
    mapPeriods?: MapPeriod[];
    activeMapId?: string | null;
    isDeleting?: boolean;
  }>(),
  {
    features: () => [],
    mapPeriods: () => [],
    activeMapId: null,
    isDeleting: false,
  },
);

const emit = defineEmits<{
  (event: "delete-features", featureIds: string[]): void;
  (event: "remove-from-maps", payload: { featureIds: string[]; mapIdsToRemove: string[] }): void;
  (event: "cancel"): void;
}>();

const dialogRef = ref<HTMLDialogElement | null>(null);
const targetFeatures = ref<Feature[]>([]);
const featureDisplayName = ref("Élément");
const selectedMapIds = ref<Set<string>>(new Set());

function formatPeriodDates(p?: MapPeriod | null): string {
  if (!p) return "";
  const start = p.startDate ? (p.startDate.match(/^-?\d+/)?.[0] ?? p.startDate) : null;
  const end = p.endDate ? (p.endDate.match(/^-?\d+/)?.[0] ?? p.endDate) : null;
  if (start && end && start !== end) return `${start} - ${end}`;
  if (start) return `${start}`;
  if (end) return `${end}`;
  return "";
}

const hasMultiMapFeature = computed(() => {
  return targetFeatures.value.some((f) => getFeatureMapIds(f).length > 1);
});

const targetMaps = computed<MapDeletionItem[]>(() => {
  if (!hasMultiMapFeature.value || targetFeatures.value.length === 0) return [];

  const mapIdsSet = new Set<string>();
  targetFeatures.value.forEach((f) => {
    getFeatureMapIds(f).forEach((id) => mapIdsSet.add(String(id)));
  });

  const periodByNormalizedId = new Map<string, MapPeriod>();
  const periodByTitle = new Map<string, MapPeriod>();

  props.mapPeriods?.forEach((p) => {
    if (p.id != null) {
      periodByNormalizedId.set(String(p.id).trim().toLowerCase(), p);
      periodByNormalizedId.set(String(p.id), p);
    }
    if (p.title) {
      periodByTitle.set(p.title.trim().toLowerCase(), p);
    }
  });

  return Array.from(mapIdsSet).map((mapId) => {
    const normKey = mapId.trim().toLowerCase();
    const period = periodByNormalizedId.get(normKey) ?? periodByTitle.get(normKey);

    let title = period?.title;
    if (!title) {
      // Check if feature itself has a custom mapTitle attached
      for (const f of targetFeatures.value) {
        const customTitle = ("mapTitle" in f ? (f as { mapTitle?: string }).mapTitle : undefined) || f.properties?.mapTitle;
        if (customTitle) {
          title = customTitle;
          break;
        }
      }
    }
    if (!title) {
      title = `Carte ${mapId}`;
    }

    const isCurrent = Boolean(
      props.activeMapId &&
      (String(props.activeMapId).trim().toLowerCase() === normKey ||
        (period && String(props.activeMapId).trim().toLowerCase() === String(period.id).trim().toLowerCase()))
    );

    return {
      id: mapId,
      title,
      dateLabel: formatPeriodDates(period),
      color: period?.color,
      isCurrent,
    };
  });
});

const allMapsSelected = computed(() => {
  return targetMaps.value.length > 0 && selectedMapIds.value.size === targetMaps.value.length;
});

const removeButtonLabel = computed(() => {
  const count = selectedMapIds.value.size;
  if (count <= 1) {
    const firstSelectedId = Array.from(selectedMapIds.value)[0];
    const match = targetMaps.value.find((m) => m.id === firstSelectedId);
    if (match?.isCurrent) {
      return "Retirer de cette carte";
    }
    return "Retirer de la carte sélectionnée";
  }
  return `Retirer des cartes sélectionnées (${count})`;
});

function toggleMapSelection(mapId: string) {
  const next = new Set(selectedMapIds.value);
  if (next.has(mapId)) {
    next.delete(mapId);
  } else {
    next.add(mapId);
  }
  selectedMapIds.value = next;
}

function toggleSelectAllMaps() {
  if (allMapsSelected.value) {
    selectedMapIds.value = new Set();
  } else {
    selectedMapIds.value = new Set(targetMaps.value.map((m) => m.id));
  }
}

function open(featureOrFeatures: Feature | Feature[] | string | string[]) {
  let resolved: Feature[] = [];

  if (Array.isArray(featureOrFeatures)) {
    if (featureOrFeatures.length > 0 && typeof featureOrFeatures[0] === "string") {
      const idsSet = new Set((featureOrFeatures as string[]).map(String));
      resolved = props.features.filter((f) => idsSet.has(String(f.id)));
    } else {
      resolved = featureOrFeatures as Feature[];
    }
  } else if (typeof featureOrFeatures === "string") {
    const f = props.features.find((feat) => String(feat.id) === String(featureOrFeatures));
    if (f) resolved = [f];
  } else if (featureOrFeatures) {
    resolved = [featureOrFeatures as Feature];
  }

  if (resolved.length === 0) return;

  targetFeatures.value = resolved;
  if (resolved.length > 1) {
    featureDisplayName.value = `${resolved.length} éléments sélectionnés`;
  } else {
    featureDisplayName.value = resolved[0].properties?.name || "Élément sans nom";
  }

  // Pre-select current active map if present, or all maps
  const newSelection = new Set<string>();
  const allMapIds = new Set<string>();
  resolved.forEach((f) => {
    getFeatureMapIds(f).forEach((id) => allMapIds.add(String(id)));
  });

  if (props.activeMapId && allMapIds.has(String(props.activeMapId))) {
    newSelection.add(String(props.activeMapId));
  } else if (allMapIds.size > 0) {
    newSelection.add(Array.from(allMapIds)[0]);
  }
  selectedMapIds.value = newSelection;

  if (typeof dialogRef.value?.showModal === "function") {
    dialogRef.value.showModal();
  } else if (dialogRef.value) {
    dialogRef.value.setAttribute("open", "");
  }
}

function close() {
  if (typeof dialogRef.value?.close === "function") {
    dialogRef.value.close();
  } else if (dialogRef.value) {
    dialogRef.value.removeAttribute("open");
  }
  emit("cancel");
}

function confirmRemoveFromSelectedMaps() {
  const featureIds = targetFeatures.value.map((f) => String(f.id));
  const mapIdsToRemove = Array.from(selectedMapIds.value);
  emit("remove-from-maps", { featureIds, mapIdsToRemove });
}

function confirmDeleteEverywhere() {
  const featureIds = targetFeatures.value.map((f) => String(f.id));
  emit("delete-features", featureIds);
}

defineExpose({
  open,
  close,
  showModal: (feats?: Feature | Feature[]) => feats && open(feats),
});
</script>
