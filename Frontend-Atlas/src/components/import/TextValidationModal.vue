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
              <span class="w-3.5 h-3.5 rounded-full bg-amber-500 text-white font-bold text-[9px] flex items-center justify-center border border-amber-600">!</span>
              <span class="font-medium text-black">Suggestion disponible</span>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block border border-emerald-600" />
              <span class="font-medium text-black">Lieu suggéré</span>
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

      <!-- Main Body: 2 columns with draggable divider -->
      <div
        class="flex-1 min-h-0 flex overflow-hidden select-none"
        :class="{ 'cursor-col-resize': isDragging }"
      >
        <!-- 1. Left: Original Image Viewer -->
        <ValidationImageViewer
          :display-image-url="displayImageUrl"
          :img-zoom="imgZoom"
          :is-updating-reference-image="isUpdatingReferenceImage"
          @zoom="zoomImg"
          @reset-zoom="resetImgZoom"
          @wheel="onImageWheel"
          @select-image="onLocalImageSelected"
          @remove-image="removeReferenceImage"
        />

        <!-- Resizer Divider -->
        <div
          class="w-1.5 bg-base-300 hover:bg-primary active:bg-primary transition-colors cursor-col-resize shrink-0 z-10"
          title="Glisser pour redimensionner la colonne"
          @mousedown="startColResize"
        />

        <!-- 2. Right: Validation List -->
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
                    title="Suggestion de lieu disponible"
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
import { computed, ref, watch, onBeforeUnmount } from "vue";
import { useHistory } from "../../composables/useHistory";
import type { CSSProperties } from "vue";
import CustomLabelStyleManager from "../CustomLabelStyleManager.vue";
import ValidationImageViewer from "./ValidationImageViewer.vue";
import {
  getCustomStyleObject,
  getEntryTypography,
  getWordTypeOptionLabel,
  getWordTypeOptionStyle,
  type CustomLabelStyle,
} from "../../utils/labelPresentation";
import {
  TrashIcon,
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

const highlightedId = ref<string | null>(null);
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
  }
}

function onSaveCustomLabelStyles(styles: CustomLabelStyle[]) {
  localCustomStyles.value = [...styles];
  applyUpdatedCustomStylesToItems(styles);
  emit("save-label-styles", styles);
}

const rightColWidth = ref(450);
const isDragging = ref(false);

const imgZoom = ref(1);

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

// ── Undo / Redo History Management ───────────────────────────────────────────
const {
  canUndo,
  canRedo,
  resetHistory,
  pushHistory,
  undo: historyUndo,
  redo: historyRedo,
} = useHistory<TextValidationEntry[]>(30);

function saveHistorySnapshot() {
  pushHistory(allItems.value);
}

function undo() {
  const previous = historyUndo(allItems.value);
  if (!previous) return;
  allItems.value = previous;
}

function redo() {
  const next = historyRedo(allItems.value);
  if (!next) return;
  allItems.value = next;
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

function startColResize(e: MouseEvent) {
  isDragging.value = true;
  const startX = e.clientX;
  const startW = rightColWidth.value;
  const minWidth = 320;
  const maxWidth = 800;

  const onMouseMove = (ev: MouseEvent) => {
    if (!isDragging.value) return;
    const delta = startX - ev.clientX;
    rightColWidth.value = Math.max(minWidth, Math.min(maxWidth, startW + delta));
  };

  const onMouseUp = () => {
    isDragging.value = false;
    window.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("mouseup", onMouseUp);
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

function focusItem(item: TextValidationEntry) {
  highlightedId.value = item.id;
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
  }
}

function toggleItemSelection(item: TextValidationEntry) {
  saveHistorySnapshot();
  item.selected = !item.selected;
  item.validationStatus = item.selected ? "accepted" : "rejected";
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
    }
  }
}

function toggleSupprimer(item: TextValidationEntry) {
  saveHistorySnapshot();
  if (highlightedId.value === item.id) {
    highlightedId.value = null;
  }
  allItems.value = allItems.value.filter((i: TextValidationEntry) => i.id !== item.id);
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
    if (highlightedId.value) highlightedId.value = null;
    return;
  }

  if (target.closest("[data-validation-item]")) {
    return;
  }

  if (highlightedId.value) {
    highlightedId.value = null;
  }
}

let isListening = false;
function attachGlobalListeners() {
  if (isListening || typeof window === "undefined") return;
  window.addEventListener("keydown", handleKeyDown, true);
  window.addEventListener("click", onDocumentClick, true);
  isListening = true;
}

function removeGlobalListeners() {
  if (!isListening || typeof window === "undefined") return;
  window.removeEventListener("keydown", handleKeyDown, true);
  window.removeEventListener("click", onDocumentClick, true);
  isListening = false;
}

watch(
  () => props.isOpen,
  (open: boolean) => {
    if (!open) {
      removeGlobalListeners();
      return;
    }
    attachGlobalListeners();
    resetHistory();
    imgZoom.value = 1;
    allItems.value = mapInitialItems(props.initialItems);
  },
  { immediate: true },
);

watch(
  () => props.initialItems,
  (newItems: TextValidationEntry[]) => {
    if (props.isOpen && (!allItems.value || allItems.value.length === 0)) {
      allItems.value = mapInitialItems(newItems);
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
  removeGlobalListeners();
  if (typingTimeout) {
    clearTimeout(typingTimeout);
    typingTimeout = null;
  }
  if (typeof URL !== "undefined" && typeof URL.revokeObjectURL === "function" && localImageMap.value) {
    for (const imageUrl of Object.values(localImageMap.value)) {
      if (typeof imageUrl === "string" && imageUrl.startsWith("blob:")) {
        URL.revokeObjectURL(imageUrl);
      }
    }
  }
});

function onConfirm() {
  for (const item of allItems.value) {
    item.validationStatus = item.selected ? "accepted" : "rejected";
  }
  emit("confirm", allItems.value);
}

defineExpose({
  allItems,
  highlightedId,
  focusItem,
  undo,
  redo,
  canUndo,
  canRedo,
});
</script>
