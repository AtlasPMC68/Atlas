<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-[2000] flex items-center justify-center bg-black/60 backdrop-blur-xs p-3"
  >
    <div
      class="bg-base-100 rounded-2xl shadow-2xl w-full max-w-[96vw] h-[92vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200"
    >
      <!-- Header -->
      <div class="px-6 py-3 border-b border-base-200 flex items-center justify-between bg-base-100 shrink-0">
        <div class="flex items-center gap-6">
          <div class="flex items-center gap-2.5">
            <div class="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
              </svg>
            </div>
            <div>
              <h2 class="text-base font-bold text-black leading-tight">Validation des textes non reconnus</h2>
              <p class="text-xs text-black/70">
                Comparez avec l'image originale et validez les textes détectés.
              </p>
            </div>
          </div>

          <!-- Status legend -->
          <div class="hidden md:flex items-center gap-4 px-3 py-1 bg-base-200/50 rounded-lg border border-base-300 text-xs">
            <div class="flex items-center gap-1.5">
              <span class="w-2.5 h-2.5 rounded-full bg-blue-500 inline-block border border-blue-600" />
              <span class="font-medium text-black">Position estimée image</span>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block border border-emerald-600" />
              <span class="font-medium text-black">Ville suggérée adoptée</span>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="w-3.5 h-3.5 rounded-full bg-amber-500 text-white font-bold text-[9px] flex items-center justify-center border border-amber-600">!</span>
              <span class="font-medium text-black">Suggestion disponible (150 km)</span>
            </div>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <!-- Undo / Redo controls -->
          <div class="flex items-center gap-1 bg-base-200/80 rounded-lg p-0.5 border border-base-300">
            <button
              type="button"
              class="btn btn-ghost btn-xs text-black h-7 px-2 font-medium flex items-center gap-1 hover:bg-base-100 disabled:opacity-30 disabled:hover:bg-transparent"
              :disabled="!canUndo"
              title="Annuler (Ctrl+Z)"
              data-testid="modal-undo-button"
              @click="undo"
            >
              <ArrowUturnLeftIcon class="w-3.5 h-3.5" />
              <span class="hidden sm:inline text-xs">Annuler</span>
            </button>
            <button
              type="button"
              class="btn btn-ghost btn-xs text-black h-7 px-2 font-medium flex items-center gap-1 hover:bg-base-100 disabled:opacity-30 disabled:hover:bg-transparent"
              :disabled="!canRedo"
              title="Rétablir (Ctrl+Y)"
              data-testid="modal-redo-button"
              @click="redo"
            >
              <ArrowUturnRightIcon class="w-3.5 h-3.5" />
              <span class="hidden sm:inline text-xs">Rétablir</span>
            </button>
          </div>

          <button
            type="button"
            class="btn btn-ghost btn-sm btn-circle text-black hover:bg-base-200"
            :disabled="isSubmitting"
            @click="emit('cancel')"
          >
            ✕
          </button>
        </div>
      </div>

      <!-- Main Body: 3 columns with draggable dividers -->
      <div
        class="flex-1 min-h-0 flex overflow-hidden select-none"
        :class="{ 'cursor-col-resize': isDraggingLeft || isDraggingRight }"
      >
        <!-- 1. Left: Original Image Viewer -->
        <div
          class="flex flex-col bg-gray-900 min-h-0 relative shrink-0 overflow-hidden"
          :style="{ width: `${leftColWidth}px` }"
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
                  @click="zoomImg(-0.1)"
                >
                  −
                </button>
                <button
                  type="button"
                  class="btn btn-xs btn-ghost text-white px-2 min-h-0 h-6 text-xs"
                  title="Réinitialiser"
                  @click="resetImgZoom"
                >
                  {{ Math.round(imgZoom * 100) }}%
                </button>
                <button
                  type="button"
                  class="btn btn-xs btn-ghost text-white px-1.5 min-h-0 h-6 text-xs"
                  title="Zoomer"
                  @click="zoomImg(0.1)"
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
                  @change="onLocalImageSelected"
                />
              </label>
              <button
                v-if="displayImageUrl"
                type="button"
                class="btn btn-xs btn-ghost btn-square text-white hover:bg-error/80 px-1 min-h-0 h-6"
                title="Supprimer l'image de référence associée à cette carte"
                aria-label="Supprimer l'image de référence"
                @click="removeReferenceImage"
              >
                <XMarkIcon class="w-4 h-4" />
              </button>
            </div>
          </div>

          <div
            class="flex-1 min-h-0 overflow-auto flex items-center justify-center p-2 bg-gray-950"
            @wheel="onImageWheel"
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
                  @change="onLocalImageSelected"
                />
              </label>
            </div>
          </div>
        </div>

        <!-- Left Resizer Divider -->
        <div
          class="w-1.5 bg-base-300 hover:bg-primary active:bg-primary transition-colors cursor-col-resize shrink-0 z-10"
          title="Glisser pour redimensionner la colonne"
          @mousedown="startColResize(true, $event)"
        />

        <!-- 2. Center: Leaflet Map -->
        <div class="flex-1 min-w-[200px] relative flex flex-col overflow-hidden" data-testid="map-container">
          <div class="px-3 py-2 bg-base-200/70 border-b border-base-300 text-xs shrink-0 flex items-center justify-between">
            <span class="text-black font-semibold">Positionnement géographique</span>
            <span class="text-[11px] text-primary font-medium">Glissez les points ou cliquez sur la carte pour ajuster leur position</span>
          </div>
          <div class="flex-1 min-h-0 relative">
            <div ref="mapContainer" class="w-full h-full bg-[#cfe8ff]" />
          </div>
        </div>

        <!-- Right Resizer Divider -->
        <div
          class="w-1.5 bg-base-300 hover:bg-primary active:bg-primary transition-colors cursor-col-resize shrink-0 z-10"
          title="Glisser pour redimensionner la colonne"
          @mousedown="startColResize(false, $event)"
        />

        <!-- 3. Right: Validation List -->
        <div
          class="shrink-0 flex flex-col bg-base-100 overflow-hidden border-l border-base-200"
          :style="{ width: `${rightColWidth}px` }"
        >
          <!-- List Header -->
          <div class="px-3.5 py-2.5 border-b border-base-200 shrink-0 bg-base-200/50 flex items-center justify-between text-sm">
            <span class="font-bold text-black flex items-center gap-1.5">
              <span>✕</span>
              <span>Non localisés</span>
            </span>
            <span class="badge badge-sm badge-neutral font-semibold text-black bg-base-300 border-0">
              {{ allItems.length }}
            </span>
          </div>

          <!-- Select All Controls -->
          <div class="px-3.5 py-2.5 border-b border-base-200 flex items-center justify-between shrink-0 bg-base-100 text-xs">
            <label class="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                data-testid="select-all-checkbox"
                class="checkbox checkbox-sm checkbox-primary rounded cursor-pointer"
                :checked="isAllSelected"
                :indeterminate.prop="isPartiallySelected"
                @change="onToggleSelectAll"
              />
              <span class="font-bold text-black text-sm">
                Tout sélectionner
              </span>
            </label>
            <span class="font-semibold text-black">
              {{ toKeepCount }} / {{ allItems.length }} conservé(s)
            </span>
          </div>
          <!-- Items list -->
          <div class="flex-1 overflow-y-auto p-2 flex flex-col gap-2">
            <div
              v-if="allItems.length === 0"
              class="text-xs text-black italic text-center py-8"
            >
              Aucun texte dans cette catégorie.
            </div>

            <div
              v-for="item in allItems"
              :key="item.id"
              data-validation-item="true"
              class="flex flex-col p-2 gap-1.5 rounded-lg border transition-all cursor-pointer bg-base-100 hover:border-primary/50"
              :class="[
                item.id === highlightedId ? 'ring-2 ring-primary border-primary bg-primary/5' : '',
                itemBorderClass(item),
              ]"
              @click="focusItem(item)"
              @mouseenter="onItemHover(item)"
              @mouseleave="onItemLeave"
            >
              <!-- Checkbox + Input + Trash -->
              <div class="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  data-testid="item-checkbox"
                  class="checkbox checkbox-sm checkbox-primary rounded shrink-0 cursor-pointer"
                  :checked="item.selected"
                  :title="item.selected ? 'Décocher pour ne pas conserver ce texte' : 'Cocher pour conserver ce texte'"
                  @click.stop
                  @change="toggleItemSelection(item)"
                />

                <div class="relative flex-1 flex items-center">
                  <input
                    v-model="item.text"
                    type="text"
                    class="input input-bordered input-sm w-full h-8 text-sm font-medium bg-base-100 text-black border-base-300 focus:border-primary placeholder:text-gray-400 px-2"
                    :style="itemRightInputStyle(item)"
                    :placeholder="item.originalText"
                    @click.stop
                    @focus="onInputFocus(item)"
                    @blur="onInputBlur"
                    @input="onTextInput(item)"
                  />
                  <!-- Amber badge if suggestion available -->
                  <span
                    v-if="item.suggestedPlace && !item.useSuggestedPlace"
                    class="absolute right-2 px-1.5 py-0.5 rounded-full bg-amber-500 text-white font-extrabold text-[10px] pointer-events-none shadow-xs"
                    title="Suggestion de lieu à proximité disponible"
                  >
                    !
                  </span>
                </div>

                <button
                  type="button"
                  :disabled="isUpdatingReferenceImage"
                  class="btn btn-ghost btn-xs btn-square w-7 h-7 text-error hover:bg-error/10 shrink-0"
                  title="Supprimer ce texte de la carte"
                  @click.stop="toggleSupprimer(item)"
                >
                  <TrashIcon class="w-4 h-4 text-error" />
                </button>
              </div>

              <!-- Word type selector -->
              <div
                v-if="item.selected"
                class="flex items-center justify-between gap-2 pt-0.5"
                @click.stop
              >
                <span class="text-xs font-semibold text-gray-700 shrink-0">Type de mot :</span>
                <select
                  v-model="item.labelStyleSelection"
                  class="select select-bordered select-xs flex-1 h-7 text-xs bg-base-100 text-black border-base-300 font-medium focus:border-primary"
                  data-testid="item-word-type-select"
                  @click.stop
                  @change="onItemLabelStyleChange(item)"
                >
                  <option
                    v-for="style in availableCustomLabelStyles"
                    :key="style.id"
                    :value="`custom:${style.id}`"
                    :style="getCustomStyleObject(style)"
                  >
                    {{ style.name }}
                  </option>                
                  <option
                    v-for="(_, typeKey) in WORD_TYPE_STYLES"
                    :key="typeKey"
                    :value="typeKey"
                    :style="getWordTypeOptionStyle(typeKey)"
                  >
                    {{ getWordTypeOptionLabel(typeKey) }}
                  </option>

                    </select>

                    <button
                      type="button"
                      class="btn btn-outline btn-xs h-7 shrink-0 text-[10px] px-2"
                      data-testid="manage-custom-label-styles"
                      @click.stop="labelStyleManagerRef?.open()"
                    >
                      Personnaliser
                    </button>
                  </div>
              <!-- Suggested place pill button -->
              <div
                v-if="item.suggestedPlace"
                class="flex items-center pt-0.5"
                @click.stop
              >
                <button
                  type="button"
                  class="btn btn-xs h-7 flex-1 justify-between normal-case font-medium transition-all text-xs text-black px-2"
                  :class="item.selected && item.useSuggestedPlace
                    ? 'btn-success bg-emerald-600 hover:bg-emerald-700 text-white font-bold shadow-xs border-emerald-600'
                    : 'btn-outline border-emerald-400 text-black hover:bg-emerald-50 bg-base-100'"
                  @click="toggleSuggestion(item)"
                  :title="item.useSuggestedPlace ? 'Cliquer pour revenir au texte libre' : `Accepter la suggestion ${item.suggestedPlace.name}`"
                >
                  <span class="truncate">
                    Lieu suggéré : <strong>{{ item.suggestedPlace.name }}</strong>
                  </span>
                  <span class="font-semibold shrink-0 text-[11px] flex items-center gap-1">
                    <span v-if="item.useSuggestedPlace" class="font-bold">✓ Adoptée</span>
                    <span v-else class="underline">Accepter la suggestion</span>
                  </span>
                </button>
              </div>
            </div>
            <CustomLabelStyleManager
              ref="labelStyleManagerRef"
              :styles="availableCustomLabelStyles"
              @save="onSaveCustomLabelStyles"
            />
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="px-6 py-3 border-t border-base-200 flex items-center justify-between bg-base-100 shrink-0">
        <div class="text-xs text-black font-medium">Carte sélectionnée : {{ mapTitle }}</div>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="btn btn-ghost btn-sm text-black hover:bg-base-200"
            :disabled="isSubmitting"
            @click="emit('cancel')"
          >
            Passer
          </button>
          <button
            type="button"
            class="btn btn-primary btn-sm text-white font-semibold shadow-xs"
            :disabled="isSubmitting"
            @click="onConfirm"
          >
            <span v-if="isSubmitting" class="loading loading-spinner loading-xs" />
            Confirmer et afficher sur la carte
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount, nextTick } from "vue";
import type { CSSProperties } from "vue";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { FeatureCollection } from "geojson";
import CustomLabelStyleManager from "../CustomLabelStyleManager.vue";
import {
  getCustomStyleObject,
  getEntryTypography,
  getWordTypeOptionLabel,
  getWordTypeOptionStyle,
  type CustomLabelStyle,
} from "../../utils/labelPresentation";
import { resolveClusteredTooltipDirections } from "../../utils/labelCollision";
import {
  TrashIcon,
  PhotoIcon,
  ArrowUpTrayIcon,
  XMarkIcon,
  ArrowUturnLeftIcon,
  ArrowUturnRightIcon,
} from "@heroicons/vue/24/outline";
import type { TextValidationEntry } from "../../utils/textValidation";
import {
  WORD_TYPE_STYLES,
  formatWordText,
  normalizeWordType,
} from "../../utils/wordStyles";
import { removeOriginalMapImage } from "../../composables/useMapImageCache";
import { useMapReferenceImage } from "../../composables/useMapReferenceImage";
import { showAlert } from "../../composables/useAlert";

export type { TextValidationEntry };

/** GeoJSON coordinates convention: [longitude, latitude] */
export type GeoJsonCoordinates = [longitude: number, latitude: number];
/** Leaflet coordinates convention: [latitude, longitude] */
export type LeafletLatLng = [latitude: number, longitude: number];

const props = withDefaults(
  defineProps<{
    isOpen: boolean;
    mapId?: string | null;
    imageUrl?: string | null;
    mapTitle?: string;
    initialItems?: TextValidationEntry[];
    isSubmitting?: boolean;
    customLabelStyles?: CustomLabelStyle[];
  }>(),
  {
    mapId: null,
    imageUrl: null,
    mapTitle: "Carte sélectionnée",
    initialItems: () => [],
    isSubmitting: false,
    customLabelStyles: () => [],
  },
);

const emit = defineEmits<{
  (e: "confirm", items: TextValidationEntry[]): void;
  (e: "cancel"): void;
  (e: "save-label-styles", styles: CustomLabelStyle[]): void;
}>();

const mapContainer = ref<HTMLElement | null>(null);
const highlightedId = ref<string | null>(null);
const hoveredId = ref<string | null>(null);
const isDraggingId = ref<string | null>(null);
const allItems = ref<TextValidationEntry[]>([]);
const labelStyleManagerRef = ref<InstanceType<typeof CustomLabelStyleManager> | null>(null);

const localCustomStyles = ref<CustomLabelStyle[]>([]);

watch(
  () => props.customLabelStyles,
  (styles: CustomLabelStyle[] | undefined) => {
    if (styles) {
      localCustomStyles.value = [...styles];
      applyUpdatedCustomStylesToItems(styles);
    }
  },
  { immediate: true },
);

const availableCustomLabelStyles = computed(() => {
  return localCustomStyles.value.length > 0
    ? localCustomStyles.value
    : props.customLabelStyles ?? [];
});

function applyUpdatedCustomStylesToItems(styles: CustomLabelStyle[]) {
  const stylesById = new Map(styles.map((s) => [s.id, s]));
  for (const item of allItems.value) {
    if (!item.customLabelStyleId) continue;
    const style = stylesById.get(item.customLabelStyleId);
    if (style) {
      item.customLabelStyle = style;
      if (style.textTransform === "uppercase" && item.text) {
        item.text = item.text.toUpperCase();
      }
    } else {
      item.customLabelStyleId = undefined;
      item.customLabelStyle = undefined;
      item.labelStyleSelection = item.wordType ?? "city";
    }
    updateMarkerStyle(item);
  }
}

function onSaveCustomLabelStyles(styles: CustomLabelStyle[]) {
  localCustomStyles.value = [...styles];
  applyUpdatedCustomStylesToItems(styles);
  emit("save-label-styles", styles);
}

const leftColWidth = ref(420);
const rightColWidth = ref(380);
const isDraggingLeft = ref(false);
const isDraggingRight = ref(false);

const imgZoom = ref(1);

let leafletMap: L.Map | null = null;
let landLayer: L.GeoJSON | null = null;
let cachedBasemapGeoJSON: FeatureCollection | null = null;
const markerMap = new Map<string, L.Marker>();

let radiusCircle: L.Circle | null = null;
let suggestionPreviewMarker: L.Marker | null = null;
let connectionLine: L.Polyline | null = null;

const localImageMap = ref<Record<string, string>>({});
const removedImageMap = ref<Record<string, boolean>>({});
const loadedReferenceImageMap = new Set<string>();
const { fetchReferenceImage, saveReferenceImage, deleteReferenceImage } =
  useMapReferenceImage();
const isUpdatingReferenceImage = ref(false);

const displayImageUrl = computed(() => {
  const currentKey = props.mapId ?? "_default";
  if (removedImageMap.value[currentKey]) return null;
  return localImageMap.value[currentKey] || props.imageUrl || null;
});

const toKeepCount = computed(() =>
  allItems.value.filter((i: TextValidationEntry) => i.selected).length,
);

const isAllSelected = computed(
  () => allItems.value.length > 0 && allItems.value.every((i: TextValidationEntry) => i.selected),
);

const isPartiallySelected = computed(() => {
  const selectedCount = toKeepCount.value;
  return selectedCount > 0 && selectedCount < allItems.value.length;
});

// ── Undo / Redo History Management ──────────────────────────────────────────
const undoStack = ref<TextValidationEntry[][]>([]);
const redoStack = ref<TextValidationEntry[][]>([]);
const canUndo = computed(() => undoStack.value.length > 0);
const canRedo = computed(() => redoStack.value.length > 0);

function cloneEntries(entries: TextValidationEntry[]): TextValidationEntry[] {
  return entries.map((item) => ({
    ...item,
    coordinates: item.coordinates ? [item.coordinates[0], item.coordinates[1]] : undefined,
    originalCoordinates: item.originalCoordinates
      ? [item.originalCoordinates[0], item.originalCoordinates[1]]
      : undefined,
  }));
}

function resetHistory() {
  undoStack.value = [];
  redoStack.value = [];
}

function saveHistorySnapshot() {
  undoStack.value.push(cloneEntries(allItems.value));
  if (undoStack.value.length > 30) {
    undoStack.value.shift();
  }
  redoStack.value = [];
}

function undo() {
  if (!canUndo.value) return;
  const currentSnapshot = cloneEntries(allItems.value);
  redoStack.value.push(currentSnapshot);

  const previous = undoStack.value.pop()!;
  allItems.value = cloneEntries(previous);

  hideToleranceRadius();
  renderMapMarkers(false);
  adjustTooltipsAntiCollision();
}

function redo() {
  if (!canRedo.value) return;
  const currentSnapshot = cloneEntries(allItems.value);
  undoStack.value.push(currentSnapshot);

  const next = redoStack.value.pop()!;
  allItems.value = cloneEntries(next);

  hideToleranceRadius();
  renderMapMarkers(false);
  adjustTooltipsAntiCollision();
}

let isTypingSession = false;
let typingTimeout: ReturnType<typeof setTimeout> | null = null;

function onInputFocus(_item: TextValidationEntry) {
  if (!isTypingSession) {
    saveHistorySnapshot();
    isTypingSession = true;
  }
}

function onInputBlur() {
  isTypingSession = false;
  if (typingTimeout) {
    clearTimeout(typingTimeout);
    typingTimeout = null;
  }
}

function handleKeyDown(e: KeyboardEvent) {
  if (!props.isOpen) return;

  const isMod = e.ctrlKey || e.metaKey;
  const key = e.key.toLowerCase();

  if (isMod && !e.shiftKey && key === "z") {
    e.preventDefault();
    e.stopPropagation();
    undo();
    return;
  }

  if ((isMod && key === "y") || (isMod && e.shiftKey && key === "z")) {
    e.preventDefault();
    e.stopPropagation();
    redo();
    return;
  }
}

function startColResize(isLeft: boolean, e: MouseEvent) {
  const isDragging = isLeft ? isDraggingLeft : isDraggingRight;
  const colWidth = isLeft ? leftColWidth : rightColWidth;
  const minWidth = isLeft ? 220 : 260;

  isDragging.value = true;
  const startX = e.clientX;
  const startW = colWidth.value;

  const onMouseMove = (ev: MouseEvent) => {
    if (!isDragging.value) return;
    const delta = isLeft ? ev.clientX - startX : startX - ev.clientX;
    colWidth.value = Math.max(minWidth, Math.min(800, startW + delta));
    leafletMap?.invalidateSize();
  };

  const onMouseUp = () => {
    isDragging.value = false;
    window.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("mouseup", onMouseUp);
    leafletMap?.invalidateSize();
  };

  window.addEventListener("mousemove", onMouseMove);
  window.addEventListener("mouseup", onMouseUp);
}

function zoomImg(delta: number) {
  imgZoom.value = Math.max(0.2, Math.min(4, Number((imgZoom.value + delta).toFixed(2))));
}

function resetImgZoom() {
  imgZoom.value = 1;
}

function onImageWheel(event: WheelEvent) {
  if (!displayImageUrl.value) return;
  event.preventDefault();
  zoomImg(event.deltaY < 0 ? 0.1 : -0.1);
}

async function onLocalImageSelected(event: Event) {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0];
  if (!file) return;

  target.value = "";
  const mapId = props.mapId;
  const currentKey = mapId ?? "_default";
  isUpdatingReferenceImage.value = true;
  try {
    if (mapId) {
      const result = await saveReferenceImage(mapId, file);
      if (!result.success) {
        showAlert("error", result.error);
        return;
      }
    }
    const oldUrl = localImageMap.value[currentKey];
    if (oldUrl?.startsWith("blob:")) URL.revokeObjectURL(oldUrl);
    localImageMap.value = {
      ...localImageMap.value,
      [currentKey]: URL.createObjectURL(file),
    };
    removedImageMap.value = { ...removedImageMap.value, [currentKey]: false };
    if (mapId) loadedReferenceImageMap.add(mapId);
    imgZoom.value = 1;
  } finally {
    isUpdatingReferenceImage.value = false;
  }
}

async function removeReferenceImage() {
  const mapId = props.mapId;
  const currentKey = mapId ?? "_default";
  isUpdatingReferenceImage.value = true;
  try {
    if (mapId) {
      const result = await deleteReferenceImage(mapId);
      if (!result.success) {
        showAlert("error", result.error);
        return;
      }
    }
    const localUrl = localImageMap.value[currentKey];
    if (localUrl?.startsWith("blob:")) {
      URL.revokeObjectURL(localUrl);
    }
    localImageMap.value = { ...localImageMap.value, [currentKey]: "" };
    removedImageMap.value = { ...removedImageMap.value, [currentKey]: true };
    removeOriginalMapImage(mapId);
    if (mapId) loadedReferenceImageMap.add(mapId);
    imgZoom.value = 1;
  } finally {
    isUpdatingReferenceImage.value = false;
  }
}

function itemBorderClass(item: TextValidationEntry): string {
  if (item.useSuggestedPlace) {
    return "border-emerald-500 bg-emerald-50/30 ring-1 ring-emerald-400";
  }
  if (item.suggestedPlace) {
    return "border-amber-300 bg-amber-50/20";
  }
  return "border-base-200";
}

function getItemCoords(item: TextValidationEntry): [number, number] | undefined {
  return item.coordinates;
}

function focusItem(item: TextValidationEntry, minZoom = 5) {
  highlightedId.value = item.id;
  const marker = markerMap.get(item.id);
  if (marker && leafletMap) {
    leafletMap.setView(marker.getLatLng(), Math.max(leafletMap.getZoom(), minZoom), {
      animate: true,
    });
    marker.openTooltip();
  }
  showToleranceRadius(item);
}

function onItemHover(item: TextValidationEntry) {
  hoveredId.value = item.id;
  showToleranceRadius(item);
}

function onItemLeave() {
  hoveredId.value = null;
  if (highlightedId.value) {
    const activeItem = allItems.value.find((i: TextValidationEntry) => i.id === highlightedId.value);
    if (activeItem) {
      showToleranceRadius(activeItem);
      return;
    }
  }
  hideToleranceRadius();
}

function onToggleSelectAll(e: Event) {
  const target = e.target as HTMLInputElement;
  setAll(target.checked);
}

function setAll(selected: boolean) {
  saveHistorySnapshot();
  for (const item of allItems.value) {
    item.selected = selected;
    item.validationStatus = selected ? "accepted" : "rejected";
    updateMarkerStyle(item);
  }
}

function toggleItemSelection(item: TextValidationEntry) {
  saveHistorySnapshot();
  item.selected = !item.selected;
  item.validationStatus = item.selected ? "accepted" : "rejected";
  updateMarkerStyle(item);
}

function onItemLabelStyleChange(item: TextValidationEntry) {
  saveHistorySnapshot();
  const selection = item.labelStyleSelection ?? "";
  if (selection.startsWith("custom:")) {
    const style = availableCustomLabelStyles.value?.find(
      (candidate: CustomLabelStyle) => candidate.id === selection.slice("custom:".length),
    );
    if (!style) return;
    item.customLabelStyleId = style.id;
    item.customLabelStyle = style;
    if (style.textTransform === "uppercase") item.text = item.text.toUpperCase();
  } else {
    item.customLabelStyleId = undefined;
    item.customLabelStyle = undefined;
    item.wordType = normalizeWordType(selection);
    if (item.text) item.text = formatWordText(item.text, item.wordType);
  }
  updateMarkerStyle(item);
}

function itemRightInputStyle(item: TextValidationEntry): CSSProperties {
  const typo = getEntryTypography(item);
  return {
    textTransform: typo.textTransform,
    fontStyle: typo.fontStyle,
  };
}

function onTextInput(item: TextValidationEntry) {
  if (!isTypingSession) {
    saveHistorySnapshot();
    isTypingSession = true;
  }
  item.useSuggestedPlace = false;
  item.selected = true;
  item.validationStatus = "accepted";
  updateMarkerStyle(item, true);
  showToleranceRadius(item);

  if (typingTimeout) clearTimeout(typingTimeout);
  typingTimeout = setTimeout(() => {
    isTypingSession = false;
  }, 800);
}

function toggleSuggestion(item: TextValidationEntry) {
  saveHistorySnapshot();
  if (item.useSuggestedPlace) {
    item.useSuggestedPlace = false;
    item.text = item.originalText;
    if (item.originalCoordinates) {
      item.coordinates = [item.originalCoordinates[0], item.originalCoordinates[1]];
    }
  } else {
    item.useSuggestedPlace = true;
    item.selected = true;
    item.wordType = normalizeWordType(item.suggestedPlace?.type);
    item.labelStyleSelection = item.wordType;
    item.customLabelStyleId = undefined;
    item.customLabelStyle = undefined;
    item.validationStatus = "accepted";
    if (item.suggestedPlace) {
      item.text = formatWordText(item.suggestedPlace.name, item.wordType);
      item.coordinates = [
        item.suggestedPlace.coordinates[0],
        item.suggestedPlace.coordinates[1],
      ];
    }
  }
  hideToleranceRadius();
  updateMarkerStyle(item);
  focusItem(item, 4);
  adjustTooltipsAntiCollision();
}

function toggleSupprimer(item: TextValidationEntry) {
  saveHistorySnapshot();
  const marker = markerMap.get(item.id);
  if (marker && leafletMap) {
    leafletMap.removeLayer(marker);
    markerMap.delete(item.id);
  }
  if (highlightedId.value === item.id) {
    highlightedId.value = null;
    hideToleranceRadius();
  }
  allItems.value = allItems.value.filter((i: TextValidationEntry) => i.id !== item.id);
}

function setItemCoordinates(item: TextValidationEntry, lon: number, lat: number) {
  saveHistorySnapshot();
  item.coordinates = [lon, lat];
  item.useSuggestedPlace = false;
  item.suggestedPlace = undefined;
  item.selected = true;
  item.validationStatus = "accepted";

  hideToleranceRadius();
  updateMarkerStyle(item);
  adjustTooltipsAntiCollision();
}

function getMarkerHtml(item: TextValidationEntry): string {
  const isSuggested = Boolean(item.useSuggestedPlace);
  const isMovingOrSelected =
    highlightedId.value === item.id || isDraggingId.value === item.id;

  const fillColor = isSuggested ? "#059669" : "#2563eb";
  const strokeColor = isMovingOrSelected
    ? "#f59e0b"
    : isSuggested
      ? "#047857"
      : "#1d4ed8";
  const strokeWidth = isMovingOrSelected ? "3px" : "2px";
  const opacity = item.selected || isMovingOrSelected ? "1" : "0.45";

  const hasSuggestion = Boolean(item.suggestedPlace) && !item.useSuggestedPlace;
  const badgeHtml = hasSuggestion
    ? `<div style="position: absolute; top: -7px; right: -7px; width: 14px; height: 14px; border-radius: 50%; background-color: #f59e0b; color: #ffffff; font-size: 10px; font-weight: 800; display: flex; align-items: center; justify-content: center; border: 1.5px solid #ffffff; box-shadow: 0 1px 3px rgba(0,0,0,0.35); pointer-events: none;">!</div>`
    : "";

  return `<div class="relative validation-point-dot" style="width: 18px; height: 18px; border-radius: 50%; background-color: ${fillColor}; border: ${strokeWidth} solid ${strokeColor}; opacity: ${opacity}; box-shadow: 0 2px 5px rgba(0,0,0,0.35); cursor: grab; transition: transform 0.1s ease;">${badgeHtml}</div>`;
}

function createMarkerIcon(item: TextValidationEntry) {
  return L.divIcon({
    className: "custom-validation-marker",
    html: getMarkerHtml(item),
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });
}

function getOptimalSuggestionTooltipPlacement(
  lat: number,
  lon: number,
  sLat: number,
  sLon: number,
): { direction: "top" | "bottom" | "left" | "right"; offset: [number, number] } {
  if (!leafletMap) {
    const dLon = sLon - lon;
    const dLat = sLat - lat;
    if (dLon < 0) return { direction: "left", offset: [-12, 0] };
    if (dLon > 0) return { direction: "right", offset: [12, 0] };
    if (dLat < 0) return { direction: "bottom", offset: [0, 12] };
    return { direction: "top", offset: [0, -14] };
  }

  try {
    const pOrig = leafletMap.latLngToContainerPoint([lat, lon]);
    const pSugg = leafletMap.latLngToContainerPoint([sLat, sLon]);

    const dx = pSugg.x - pOrig.x; // > 0 if suggestion is to the right
    const dy = pSugg.y - pOrig.y; // > 0 if suggestion is below

    if (dx < -15) {
      return { direction: "left", offset: [-12, 0] };
    }
    if (dx > 15) {
      return { direction: "right", offset: [12, 0] };
    }
    if (dy > 0) {
      return { direction: "bottom", offset: [0, 12] };
    }
    return { direction: "top", offset: [0, -18] };
  } catch {
    return { direction: "left", offset: [-12, 0] };
  }
}

function preventSuggestionTooltipOverlap(item: TextValidationEntry) {
  if (!suggestionPreviewMarker || !leafletMap) return;
  const origMarker = markerMap.get(item.id);
  const origTooltipEl = origMarker?.getTooltip()?.getElement();
  const suggTooltipEl = suggestionPreviewMarker.getTooltip()?.getElement();

  if (!origTooltipEl || !suggTooltipEl) return;

  const rOrig = origTooltipEl.getBoundingClientRect();
  const rSugg = suggTooltipEl.getBoundingClientRect();

  const isOverlapping = !(
    rOrig.right + 2 < rSugg.left ||
    rOrig.left > rSugg.right + 2 ||
    rOrig.bottom + 2 < rSugg.top ||
    rOrig.top > rSugg.bottom + 2
  );

  if (isOverlapping) {
    const coords = getItemCoords(item);
    if (!coords || !item.suggestedPlace) return;
    try {
      const pOrig = leafletMap.latLngToContainerPoint([coords[1], coords[0]]);
      const pSugg = leafletMap.latLngToContainerPoint([
        item.suggestedPlace.coordinates[1],
        item.suggestedPlace.coordinates[0],
      ]);
      const dx = pSugg.x - pOrig.x;

      const fallbackDir: "left" | "right" | "bottom" = dx <= 0 ? "left" : "right";
      const offset: [number, number] = fallbackDir === "left" ? [-14, 0] : [14, 0];

      const tooltip = suggestionPreviewMarker.getTooltip();
      if (tooltip) {
        tooltip.options.direction = fallbackDir;
        tooltip.options.offset = L.point(offset[0], offset[1]);
        if (suggestionPreviewMarker.isTooltipOpen?.()) {
          suggestionPreviewMarker.closeTooltip();
          suggestionPreviewMarker.openTooltip();
        }
      }
    } catch {
      // ignore
    }
  }
}

function showToleranceRadius(item: TextValidationEntry) {
  if (!leafletMap || !item.suggestedPlace) return;
  hideToleranceRadius();

  const coords = getItemCoords(item);
  if (!coords || (coords[0] === 0 && coords[1] === 0)) return;
  const [lon, lat] = coords;
  const [sLon, sLat] = item.suggestedPlace.coordinates;

  radiusCircle = L.circle([lat, lon], {
    radius: 150000,
    color: "#2563eb",
    weight: 1.5,
    dashArray: "5, 5",
    fillColor: "#3b82f6",
    fillOpacity: 0.12,
  }).addTo(leafletMap);

  const previewIcon = L.divIcon({
    className: "custom-suggestion-preview-marker",
    html: `<div style="width: 16px; height: 16px; border-radius: 50%; background-color: #059669; border: 2px solid #ffffff; box-shadow: 0 2px 6px rgba(0,0,0,0.4);"></div>`,
    iconSize: [16, 16],
    iconAnchor: [8, 8],
  });

  const placement = getOptimalSuggestionTooltipPlacement(lat, lon, sLat, sLon);

  suggestionPreviewMarker = L.marker([sLat, sLon], { icon: previewIcon }).addTo(leafletMap);
  const suggestionTooltip = document.createElement("span");
  const suggestionName = document.createElement("strong");
  suggestionName.textContent = item.suggestedPlace.name;
  suggestionTooltip.append(suggestionName, document.createTextNode(" (Suggestion)"));
  suggestionPreviewMarker.bindTooltip(suggestionTooltip, {
    permanent: true,
    direction: placement.direction,
    offset: L.point(placement.offset[0], placement.offset[1]),
    className: "leaflet-tooltip-suggestion",
  });

  nextTick(() => preventSuggestionTooltipOverlap(item));

  connectionLine = L.polyline([[lat, lon], [sLat, sLon]], {
    color: "#059669",
    weight: 1.5,
    dashArray: "3, 3",
    opacity: 0.75,
  }).addTo(leafletMap);
}

function hideToleranceRadius() {
  if (!leafletMap) return;
  if (radiusCircle) {
    leafletMap.removeLayer(radiusCircle);
    radiusCircle = null;
  }
  if (suggestionPreviewMarker) {
    leafletMap.removeLayer(suggestionPreviewMarker);
    suggestionPreviewMarker = null;
  }
  if (connectionLine) {
    leafletMap.removeLayer(connectionLine);
    connectionLine = null;
  }
}

function makeDraggableMarker(item: TextValidationEntry): L.Marker {
  const [lon, lat] = getItemCoords(item) ?? [0, 0];

  const marker = L.marker([lat, lon], {
    draggable: true,
    icon: createMarkerIcon(item),
  });

  const isFocused = item.id === highlightedId.value;
  marker.bindTooltip(createTextTooltip(item), {
    permanent: true,
    direction: "top",
    offset: [0, -12],
    interactive: true,
    className: isFocused
      ? "leaflet-tooltip-validation validation-tooltip-focused"
      : "leaflet-tooltip-validation",
  });

  marker.on("click", (e: L.LeafletMouseEvent) => {
    L.DomEvent.stopPropagation(e as any);
    focusItem(item);
  });

  marker.on("tooltipopen", () => {
    const el = marker.getTooltip()?.getElement();
    if (el) {
      el.style.pointerEvents = "auto";
      el.style.cursor = "pointer";
      el.onclick = (e) => {
        e.stopPropagation();
        focusItem(item);
      };
    }
  });

  marker.on("mouseover", () => showToleranceRadius(item));
  marker.on("mouseout", () => {
    if (highlightedId.value !== item.id) {
      const active = allItems.value.find((i: TextValidationEntry) => i.id === highlightedId.value);
      if (active) showToleranceRadius(active);
      else hideToleranceRadius();
    }
  });

  marker.on("dragstart", () => {
    isDraggingId.value = item.id;
    highlightedId.value = item.id;
    hideToleranceRadius();
    updateMarkerStyle(item);
  });

  marker.on("dragend", (event: L.DragEndEvent) => {
    isDraggingId.value = null;
    const latlng = event.target.getLatLng();
    setItemCoordinates(
      item,
      Number(latlng.lng.toFixed(5)),
      Number(latlng.lat.toFixed(5)),
    );
    updateMarkerStyle(item);
  });

  return marker;
}

function updateMarkerStyle(item: TextValidationEntry, textOnly = false) {
  const marker = markerMap.get(item.id);
  if (!marker) return;

  const coords = getItemCoords(item);
  if (!textOnly && coords && (coords[0] !== 0 || coords[1] !== 0)) {
    marker.setLatLng([coords[1], coords[0]]);
  }

  const markerEl = typeof marker.getElement === "function" ? marker.getElement() : null;
  if (!textOnly || !markerEl) {
    marker.setIcon(createMarkerIcon(item));
  } else {
    const dotEl = markerEl.querySelector(".validation-point-dot") as HTMLElement | null;
    if (dotEl) {
      const isSuggested = Boolean(item.useSuggestedPlace);
      const isMovingOrSelected =
        highlightedId.value === item.id || isDraggingId.value === item.id;
      dotEl.style.backgroundColor = isSuggested ? "#059669" : "#2563eb";
      dotEl.style.borderColor = isMovingOrSelected
        ? "#f59e0b"
        : isSuggested
          ? "#047857"
          : "#1d4ed8";
      dotEl.style.borderWidth = isMovingOrSelected ? "3px" : "2px";
      dotEl.style.opacity = item.selected || isMovingOrSelected ? "1" : "0.45";
    }
  }

  marker.setTooltipContent(createTextTooltip(item));

  const isFocused = item.id === highlightedId.value;
  const tooltip = marker.getTooltip();
  const tooltipEl = tooltip?.getElement();
  if (tooltipEl) {
    if (isFocused) {
      tooltipEl.classList.add("validation-tooltip-focused");
    } else {
      tooltipEl.classList.remove("validation-tooltip-focused");
    }
  }
}

function createTextTooltip(item: TextValidationEntry | string): HTMLElement {
  const content = document.createElement("span");
  if (typeof item === "string") {
    content.textContent = item;
    return content;
  }

  const isFocused = item.id === highlightedId.value;
  if (item.selected || isFocused) {
    const typo = getEntryTypography(item);
    const size = Math.min(typo.sizePx, 14);

    content.style.color = typo.color;
    content.style.fontSize = `${size}px`;
    content.style.fontStyle = typo.fontStyle;
    content.style.fontWeight = typo.fontWeight;
    content.style.textTransform = typo.textTransform;
    content.textContent = typo.isUppercase ? item.text.toUpperCase() : item.text;
  } else {
    content.style.color = "#6b7280";
    content.style.fontSize = "11px";
    content.style.fontStyle = "normal";
    content.style.fontWeight = "normal";
    content.style.textTransform = "none";
    content.style.opacity = "0.6";
    content.textContent = item.text;
  }
  return content;
}

watch(highlightedId, (newId: string | null, oldId: string | null) => {
  if (oldId) {
    const oldItem = allItems.value.find((i: TextValidationEntry) => i.id === oldId);
    if (oldItem) updateMarkerStyle(oldItem);
  }
  if (newId) {
    const newItem = allItems.value.find((i: TextValidationEntry) => i.id === newId);
    if (newItem) updateMarkerStyle(newItem);
  }
});

function renderMapMarkers(shouldFitBounds = true) {
  if (!leafletMap) return;

  const currentItemIds = new Set(allItems.value.map((i) => i.id));
  for (const [id, marker] of markerMap.entries()) {
    if (!currentItemIds.has(id)) {
      leafletMap.removeLayer(marker);
      markerMap.delete(id);
    }
  }

  const bounds: [number, number][] = [];

  for (const item of allItems.value) {
    const coords = getItemCoords(item);
    if (!coords) continue;
    const [lon, lat] = coords;
    if (lon === 0 && lat === 0) continue;

    let marker = markerMap.get(item.id);
    if (!marker) {
      marker = makeDraggableMarker(item);
      marker.addTo(leafletMap);
      markerMap.set(item.id, marker);
    } else {
      marker.setLatLng([lat, lon]);
      updateMarkerStyle(item);
    }
    bounds.push([lat, lon]);
  }

  if (shouldFitBounds && bounds.length > 0) {
    leafletMap.fitBounds(bounds as L.LatLngBoundsExpression, {
      padding: [40, 40],
      maxZoom: 8,
    });
  }
  nextTick(() => adjustTooltipsAntiCollision());
}

function adjustTooltipsAntiCollision() {
  const currentMap = leafletMap;
  if (!currentMap) return;

  const validEntries = allItems.value
    .map((item: TextValidationEntry) => {
      const marker = markerMap.get(item.id);
      const latlng = marker?.getLatLng();
      if (!marker || !latlng || (latlng.lat === 0 && latlng.lng === 0)) return null;
      try {
        const pt = currentMap.latLngToContainerPoint(latlng);
        return { id: item.id, marker, x: pt.x, y: pt.y };
      } catch {
        return null;
      }
    })
    .filter(Boolean) as { id: string; marker: L.Marker; x: number; y: number }[];

  const placements = resolveClusteredTooltipDirections(validEntries);
  for (const entry of validEntries) {
    const placement = placements.get(entry.id);
    if (!placement) continue;
    const tooltip = entry.marker.getTooltip();
    if (tooltip) {
      tooltip.options.direction = placement.direction;
      tooltip.options.offset = L.point(placement.offset[0], placement.offset[1]);
      if (entry.marker.isTooltipOpen?.()) {
        entry.marker.closeTooltip();
        entry.marker.openTooltip();
      }
    }
  }
}

async function initMap() {
  if (!mapContainer.value || leafletMap) return;

  const map = L.map(mapContainer.value, {
    center: [20, 0],
    zoom: 2,
    zoomControl: true,
    attributionControl: false,
    maxBoundsViscosity: 1.0,
  });

  leafletMap = map;
  renderMapMarkers();

  map.on("zoomend", () => {
    adjustTooltipsAntiCollision();
    const active = allItems.value.find((i: TextValidationEntry) => i.id === hoveredId.value || i.id === highlightedId.value);
    if (active && suggestionPreviewMarker) {
      showToleranceRadius(active);
    }
  });
  map.on("moveend", () => {
    adjustTooltipsAntiCollision();
    const active = allItems.value.find((i: TextValidationEntry) => i.id === hoveredId.value || i.id === highlightedId.value);
    if (active && suggestionPreviewMarker) {
      showToleranceRadius(active);
    }
  });

  map.on("click", (e: L.LeafletMouseEvent) => {
    if (!highlightedId.value) return;
    const item = allItems.value.find((i: TextValidationEntry) => i.id === highlightedId.value);
    if (!item) return;

    const lon = Number(e.latlng.lng.toFixed(5));
    const lat = Number(e.latlng.lat.toFixed(5));

    let marker = markerMap.get(item.id);
    if (!marker && leafletMap) {
      marker = makeDraggableMarker(item);
      marker.addTo(leafletMap);
      markerMap.set(item.id, marker);
    }
    setItemCoordinates(item, lon, lat);
  });

  // Offline basemap using local GeoJSON (cached in memory)
  try {
    if (!cachedBasemapGeoJSON && typeof fetch === "function") {
      const baseUrl =
        typeof window !== "undefined" && window.location?.origin
          ? window.location.origin
          : "http://localhost";
      const geojsonFiles = [
        "/geojson/ne_coastline.geojson",
        "/geojson/ne_50m_lakes.geojson",
      ];
      const responses = await Promise.all(
        geojsonFiles.map((f) => fetch(new URL(f, baseUrl).toString()).catch(() => null)),
      );
      const geojsonData = await Promise.all(
        responses
          .filter((r): r is Response => Boolean(r && r.ok))
          .map((r) => r.json().catch(() => null)),
      );

      const validData = geojsonData.filter(isFeatureCollection);
      if (validData.length > 0) {
        cachedBasemapGeoJSON = {
          type: "FeatureCollection",
          features: validData.flatMap((data) => data.features),
        };
      }
    }

    if (cachedBasemapGeoJSON) {
      landLayer = L.geoJSON(cachedBasemapGeoJSON, {
        style: {
          fillColor: "#e5e7eb",
          fillOpacity: 0.9,
          color: "#9ca3af",
          weight: 1,
          opacity: 1,
        },
      }).addTo(map);
    }
  } catch {
    // Basemap is optional visual context
  }
}

function destroyMap() {
  hideToleranceRadius();
  if (landLayer && leafletMap) {
    leafletMap.removeLayer(landLayer);
    landLayer = null;
  }
  if (leafletMap) {
    leafletMap.remove();
    leafletMap = null;
  }
  markerMap.clear();
}

function isFeatureCollection(value: unknown): value is FeatureCollection {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as { type?: unknown; features?: unknown };
  return candidate.type === "FeatureCollection" && Array.isArray(candidate.features);
}

function mapInitialItems(items?: TextValidationEntry[]): TextValidationEntry[] {
  return (items || []).map((item: TextValidationEntry) => {
    const selected = item.selected ?? true;
    const coordinates = item.coordinates
      ? ([item.coordinates[0], item.coordinates[1]] as [number, number])
      : undefined;
    const originalCoordinates = item.originalCoordinates
      ? ([item.originalCoordinates[0], item.originalCoordinates[1]] as [number, number])
      : coordinates
      ? ([coordinates[0], coordinates[1]] as [number, number])
      : undefined;
    return {
      ...item,
      selected,
      coordinates,
      originalCoordinates,
      labelStyleSelection:
        item.labelStyleSelection ??
        (item.customLabelStyleId
          ? `custom:${item.customLabelStyleId}`
          : item.wordType ?? "city"),
      customLabelStyle:
        props.customLabelStyles.find(
          (style: CustomLabelStyle) => style.id === item.customLabelStyleId,
        ) ?? item.customLabelStyle,
      validationStatus: item.validationStatus ?? (selected ? "accepted" : "manual_review"),
      useSuggestedPlace: item.useSuggestedPlace ?? false,
    };
  });
}



function onDocumentClick(e: MouseEvent) {
  if (!props.isOpen) return;
  const target = e.target as HTMLElement | null;
  if (!target || typeof target.closest !== "function") {
    if (highlightedId.value) {
      highlightedId.value = null;
      hideToleranceRadius();
    }
    return;
  }

  if (
    target.closest("[data-testid='map-container']") ||
    target.closest("[data-validation-item]") ||
    target.closest(".leaflet-pane") ||
    target.closest(".leaflet-marker-icon") ||
    target.closest(".leaflet-tooltip")
  ) {
    return;
  }

  if (highlightedId.value) {
    highlightedId.value = null;
    hideToleranceRadius();
  }
}

watch(
  () => props.isOpen,
  (open: boolean) => {
    if (!open) {
      if (typeof window !== "undefined") {
        window.removeEventListener("keydown", handleKeyDown, true);
        window.removeEventListener("click", onDocumentClick, true);
      }
      destroyMap();
      return;
    }
    if (typeof window !== "undefined") {
      window.addEventListener("keydown", handleKeyDown, true);
      window.addEventListener("click", onDocumentClick, true);
    }
    resetHistory();
    imgZoom.value = 1;
    allItems.value = mapInitialItems(props.initialItems);
    nextTick(() => initMap());
  },
  { immediate: true },
);

watch(
  () => props.initialItems,
  (newItems: TextValidationEntry[]) => {
    if (props.isOpen && (!allItems.value || allItems.value.length === 0)) {
      allItems.value = mapInitialItems(newItems);
      renderMapMarkers();
    }
  },
);

watch(
  () => [props.isOpen, props.mapId] as const,
  async ([isOpen, mapId]: readonly [boolean, string | null]) => {
    if (!isOpen || !mapId || loadedReferenceImageMap.has(mapId)) return;
    const result = await fetchReferenceImage(mapId);
    if (!props.isOpen || props.mapId !== mapId) {
      if (result.success) URL.revokeObjectURL(result.data);
      return;
    }

    loadedReferenceImageMap.add(mapId);
    if (result.success) {
      localImageMap.value = { ...localImageMap.value, [mapId]: result.data };
    } else if (result.status !== 404) {
      showAlert("error", result.error);
    }
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  if (typeof window !== "undefined") {
    window.removeEventListener("keydown", handleKeyDown, true);
    window.removeEventListener("click", onDocumentClick, true);
  }
  for (const imageUrl of Object.values<string>(localImageMap.value)) {
    if (imageUrl.startsWith("blob:")) URL.revokeObjectURL(imageUrl);
  }
  destroyMap();
});

function onConfirm() {
  for (const item of allItems.value) {
    item.validationStatus = item.selected ? "accepted" : "rejected";
  }
  emit("confirm", allItems.value);
}

function getSuggestionPreviewMarker(): L.Marker | null {
  return suggestionPreviewMarker;
}

defineExpose({
  allItems,
  setItemCoordinates,
  showToleranceRadius,
  getSuggestionPreviewMarker,
  getOptimalSuggestionTooltipPlacement,
  initMap,
  undo,
  redo,
  canUndo,
  canRedo,
});
</script>

<style>
.custom-validation-marker {
  background: transparent !important;
  border: none !important;
}
.custom-suggestion-preview-marker {
  background: transparent !important;
  border: none !important;
}
.leaflet-tooltip-validation {
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  color: #000000;
  padding: 2px 6px;
  white-space: nowrap;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
  pointer-events: auto;
  cursor: pointer;
  z-index: 1000 !important;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.leaflet-tooltip-validation::before {
  border-top-color: #d1d5db;
}
.leaflet-tooltip-validation.validation-tooltip-focused {
  border: 2px solid #2563eb !important;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.25), 0 2px 6px rgba(0, 0, 0, 0.2) !important;
  background: #ffffff !important;
  z-index: 2000 !important;
}
.leaflet-tooltip-validation.validation-tooltip-focused::before {
  border-top-color: #2563eb !important;
}
.leaflet-tooltip-suggestion {
  background: #ecfdf5;
  border: 1px solid #10b981;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  color: #065f46 !important;
  padding: 2px 6px;
  white-space: nowrap;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
  pointer-events: none;
  z-index: 900 !important;
}
.leaflet-tooltip-suggestion::before {
  border-top-color: #10b981;
}
</style>
