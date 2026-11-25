<template>
  <dialog ref="dialogRef" class="modal">
   <div class="modal-box w-11/12 max-w-7xl h-[90vh] max-h-[92vh] flex flex-col gap-0 p-6 overflow-hidden">
      <!-- Header -->
      <div class="flex items-center justify-between gap-4 pb-3 border-b border-base-200 shrink-0">
        <h3 class="text-xl font-bold truncate">Modification des styles de libellé</h3>
        <button
          type="button"
          class="btn btn-sm btn-circle btn-ghost shrink-0"
          aria-label="Fermer"
          @click="dialogRef?.close()"
        >
          ✕
        </button>
      </div>

      <!-- Row 1: style list (scrolls to typography height) | text settings
           Row 2: preview | point settings -->
      <form
        class="grid grid-cols-1 md:grid-cols-[1fr_1.45fr] md:grid-rows-[auto_auto] flex-1 min-h-0 py-4 gap-y-3 md:gap-y-0 overflow-y-auto"
        @submit.prevent="submitDraft"
      >
        <!-- Style list: height follows first row (Mise en forme), then scrolls -->
        <div
          class="flex flex-col gap-3 min-w-0 min-h-[140px] order-1 md:h-0 md:min-h-full overflow-hidden md:pr-6 md:row-start-1 md:col-start-1"
        >
          <div class="flex items-center justify-between gap-2 min-h-[2rem] shrink-0">
            <h4 class="section-title">Styles personnalisés</h4>
            <button
              type="button"
              class="btn btn-primary btn-xs flex items-center gap-1"
              data-testid="add-new-style-btn"
              title="Ajouter un nouveau style"
              @click="addNewStyle"
            >
              <PlusIcon class="w-3.5 h-3.5" />
              <span>Nouveau style</span>
            </button>
          </div>

          <div class="flex flex-col gap-2 flex-1 min-h-0 overflow-y-auto pr-1 py-0.5">
            <div
              v-for="(style, index) in draftStyles"
              :key="style.id"
              class="flex items-center justify-between gap-2 rounded-lg border px-2.5 py-2 bg-base-100 transition-colors cursor-pointer select-none shrink-0"
              :class="
                editingId === style.id
                  ? 'border-2 border-blue-600 ring-2 ring-inset ring-blue-500/20 bg-blue-50/50 shadow-xs'
                  : 'border-gray-300 hover:border-base-content/40'
              "
              :draggable="true"
              :aria-label="`Modifier le style ${style.name}`"
              @dragstart="onDragStart(index, $event)"
              @dragover.prevent="onDragOver(index)"
              @drop="onDrop(index)"
              @click="editStyle(style)"
            >
              <div class="flex items-center gap-2 min-w-0 flex-1">
                <span
                  class="cursor-grab active:cursor-grabbing text-gray-400 hover:text-gray-600 shrink-0 p-0.5"
                  title="Glisser pour réordonner"
                  @click.stop
                >
                  <Bars3Icon class="w-4 h-4" />
                </span>
                <PointSwatch
                  v-if="hasStylePoint(style)"
                  :fill="style.pointColor || style.color || '#000000'"
                  :fill-opacity="style.pointFillOpacity ?? 1"
                  :stroke="style.pointStrokeColor || '#000000'"
                  :stroke-width="Math.min(style.pointStrokeWidth ?? 1, 2)"
                  :stroke-opacity="style.pointStrokeOpacity ?? 1"
                  title="Map point"
                />
                <span
                  class="truncate font-medium pr-2"
                  :style="previewStyle(style, true)"
                >
                  {{ style.name }}
                </span>
              </div>

              <div class="flex shrink-0 items-center gap-0.5">
                <button
                  type="button"
                  class="icon-action-btn-sm text-error hover:bg-error/10"
                  :aria-label="`Supprimer le style ${style.name}`"
                  @click.stop="removeStyle(style.id)"
                >
                  <TrashIcon class="w-4 h-4 text-error" />
                </button>
              </div>
            </div>

            <p v-if="draftStyles.length === 0" class="field-hint py-2">
              Aucun style personnalisé.
            </p>
          </div>
        </div>

        <div
          class="flex flex-col gap-2.5 min-w-0 shrink-0 pt-3 border-t border-gray-200 order-3 md:order-none md:pr-6 md:row-start-2 md:col-start-1"
        >
            <div class="flex items-center justify-between min-h-[1.75rem]">
              <h4 class="section-title">Aperçu</h4>
            </div>
            <div v-if="isTextStyleActive" class="preview-frame min-h-[108px] flex items-center p-3">
              <div
                class="preview-box overflow-hidden max-w-full px-3.5 py-2 w-full flex items-center gap-2"
                :style="{ ...previewStyle(currentLiveStyle, true, 44), lineHeight: '1.15' }"
              >
                <PointSwatch
                  v-if="draft.hasPoint"
                  :fill="draft.pointColor || '#000000'"
                  :fill-opacity="draft.pointFillOpacity"
                  :stroke="draft.pointStrokeColor || '#000000'"
                  :stroke-width="Math.min(pointPreviewStrokeWidth, 2)"
                  :stroke-opacity="draft.pointStrokeOpacity"
                />
                <span class="truncate min-w-0 max-w-full">
                  {{ draft.name.trim() || "Exemple de texte" }}
                </span>
              </div>
            </div>
        </div>

        <!-- Typography: defines first-row height for the style list -->
        <div
          class="flex flex-col gap-3 min-w-0 order-2 md:order-none md:border-l md:border-gray-200 md:pl-6 md:row-start-1 md:col-start-2"
        >
          <div class="flex items-center justify-between gap-2 min-h-[2rem] shrink-0">
            <h4 class="section-title">
              {{ editingId ? "Modifier un style" : "Créer un style" }}
            </h4>
            <button
              v-if="editingId"
              type="button"
              class="icon-action-btn-sm text-gray-500 hover:text-gray-800"
              title="Réinitialiser les modifications"
              aria-label="Réinitialiser les modifications"
              data-testid="revert-style-btn"
              @click="revertStyle"
            >
              <ArrowPathIcon class="w-4 h-4" />
            </button>
          </div>

          <div class="flex flex-col gap-3 pr-1">
            <div class="flex flex-col gap-1">
              <label class="field-label" for="custom-style-name-input">
                Nom du style
              </label>
              <input
                id="custom-style-name-input"
                v-model="draft.name"
                class="input input-bordered w-full h-[46px] text-sm"
                required
                maxlength="50"
                data-testid="custom-style-name"
                placeholder="Ex: Titre Région, Fort..."
                @input="syncLiveDraft"
              />
            </div>

            <!-- Size & Color -->
            <div class="flex flex-col gap-1">
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full">
                <div
                  class="setting-card h-[50px]"
                  :class="{ 'border-error': isSizeOverMax }"
                >
                  <label class="setting-card-label" for="custom-style-size-input">
                    Taille (px)
                  </label>
                  <input
                    id="custom-style-size-input"
                    v-model.number="draft.sizePx"
                    class="setting-number-input"
                    type="number"
                    min="6"
                    max="96"
                    required
                    @input="syncLiveDraft"
                    @change="normalizeDraftSize"
                  />
                </div>

                <div class="setting-card h-[50px]">
                  <label class="setting-card-label" for="custom-style-color-input">
                    Couleur texte
                  </label>
                  <input
                    id="custom-style-color-input"
                    v-model="draft.color"
                    type="color"
                    class="setting-color-input"
                    @input="syncLiveDraft"
                  />
                </div>
              </div>

              <span
                v-if="isSizeOverMax"
                class="text-xs text-red-700 bg-white border border-red-500 rounded px-2 py-1 mt-1"
                data-testid="max-size-warning"
              >
                La taille maximale autorisée est de 96 px (la valeur sera plafonnée).
              </span>
            </div>

            <!-- Typography options -->
            <div class="editor-section-compact pt-2">
              <span class="field-label">Mise en forme</span>
              <div class="grid grid-cols-3 gap-2.5 w-full">
                <label class="setting-card h-[46px] cursor-pointer justify-start gap-2">
                  <input
                    v-model="draft.bold"
                    type="checkbox"
                    class="checkbox checkbox-xs checkbox-primary"
                    @change="syncLiveDraft"
                  />
                  <span class="setting-card-label">Gras</span>
                </label>

                <label class="setting-card h-[46px] cursor-pointer justify-start gap-2">
                  <input
                    v-model="draft.italic"
                    type="checkbox"
                    class="checkbox checkbox-xs checkbox-primary"
                    @change="syncLiveDraft"
                  />
                  <span class="setting-card-label">Italique</span>
                </label>

                <label class="setting-card h-[46px] cursor-pointer justify-start gap-2">
                  <input
                    v-model="draft.uppercase"
                    type="checkbox"
                    class="checkbox checkbox-xs checkbox-primary"
                    @change="syncLiveDraft"
                  />
                  <span class="setting-card-label">Majuscules</span>
                </label>
              </div>
            </div>
          </div>

        </div>

        <div
          class="flex flex-col gap-2.5 min-h-0 pt-3 border-t border-gray-200 order-4 md:order-none md:border-l md:border-gray-200 md:pl-6 md:row-start-2 md:col-start-2"
        >
          <div class="flex items-center justify-between gap-2 min-h-[1.75rem]">
            <span class="section-title">Réglages du point</span>
            <span class="field-hint">Symbole associé au texte</span>
          </div>

          <label
            class="setting-card cursor-pointer justify-between"
            data-testid="custom-style-has-point-toggle"
          >
            <div class="flex flex-col min-w-0">
              <span class="setting-card-label">Ajouter un point</span>
              <span class="field-hint">
                Affiche un marqueur ponctuel avec le libellé
              </span>
            </div>
            <input
              v-model="draft.hasPoint"
              type="checkbox"
              class="checkbox checkbox-sm checkbox-primary shrink-0"
              data-testid="custom-style-has-point-checkbox"
              @change="syncLiveDraft"
            />
          </label>

          <div
            v-if="draft.hasPoint"
            class="flex flex-col gap-2.5"
            data-testid="custom-style-point-settings"
          >
            <span class="field-label leading-5">Couleurs et aperçu</span>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full">
              <div class="setting-card h-[50px]">
                <label class="setting-card-label" for="custom-style-point-fill">
                  Fond
                </label>
                <input
                  id="custom-style-point-fill"
                  v-model="draft.pointColor"
                  type="color"
                  class="setting-color-input"
                  @input="syncLiveDraft"
                />
              </div>

              <div class="setting-card h-[50px] px-2.5 gap-1.5 min-w-0">
                <label
                  class="setting-card-label text-xs sm:text-sm font-medium truncate"
                  for="custom-style-point-fill-opacity"
                  title="Opacité du fond (0 à 1)"
                >
                  Opacité fond
                </label>
                <input
                  id="custom-style-point-fill-opacity"
                  v-model.number="draft.pointFillOpacity"
                  type="number"
                  step="0.1"
                  min="0"
                  max="1"
                  placeholder="0–1"
                  class="setting-number-input !w-12 text-xs sm:text-sm px-0.5 shrink-0"
                  @keydown="onOpacityKeydown"
                  @input="onOpacityInput('pointFillOpacity', $event)"
                  @change="syncLiveDraft"
                />
              </div>

              <div class="setting-card h-[50px]">
                <label class="setting-card-label" for="custom-style-point-stroke">
                  Contour
                </label>
                <input
                  id="custom-style-point-stroke"
                  v-model="draft.pointStrokeColor"
                  type="color"
                  class="setting-color-input"
                  @input="syncLiveDraft"
                />
              </div>

              <div class="setting-card h-[50px] px-2.5 gap-1.5 min-w-0">
                <label
                  class="setting-card-label text-xs sm:text-sm font-medium truncate"
                  for="custom-style-point-stroke-opacity"
                  title="Opacité du contour (0 à 1)"
                >
                  Opacité contour
                </label>
                <input
                  id="custom-style-point-stroke-opacity"
                  v-model.number="draft.pointStrokeOpacity"
                  type="number"
                  step="0.1"
                  min="0"
                  max="1"
                  placeholder="0–1"
                  class="setting-number-input !w-12 text-xs sm:text-sm px-0.5 shrink-0"
                  @keydown="onOpacityKeydown"
                  @input="onOpacityInput('pointStrokeOpacity', $event)"
                  @change="syncLiveDraft"
                />
              </div>

              <div
                class="setting-card h-[50px] px-2.5 gap-1.5 min-w-0"
                :class="{ 'border-error': isPointStrokeWidthOverMax }"
              >
                <label
                  class="setting-card-label text-xs sm:text-sm font-medium truncate"
                  for="custom-style-point-stroke-width"
                  title="Épaisseur du contour en pixels"
                >
                  Épaisseur contour
                </label>
                <input
                  id="custom-style-point-stroke-width"
                  v-model.number="draft.pointStrokeWidth"
                  type="number"
                  min="0"
                  :max="MAX_POINT_STROKE_WIDTH_PX"
                  class="setting-number-input !w-12 text-xs sm:text-sm px-0.5 shrink-0"
                  @input="onStrokeWidthInput"
                  @change="onStrokeWidthChange"
                />
              </div>

              <div class="setting-card h-[50px] flex items-center justify-between gap-2 px-3">
                <span class="setting-card-label">Aperçu</span>
                <div class="flex items-center justify-center shrink-0">
                  <svg width="32" height="32" viewBox="0 0 40 40" class="overflow-hidden">
                    <circle
                      cx="20"
                      cy="20"
                      r="12"
                      :fill="draft.pointColor || '#000000'"
                      :fill-opacity="draft.pointFillOpacity"
                      :stroke="draft.pointStrokeColor || '#000000'"
                      :stroke-width="pointPreviewStrokeWidth"
                      :stroke-opacity="draft.pointStrokeOpacity"
                    />
                  </svg>
                </div>
              </div>
            </div>

            <span
              v-if="isPointPreviewClamped"
              class="text-xs text-red-700 bg-white border border-red-500 rounded px-2 py-1"
              data-testid="custom-point-preview-limit-notice"
            >
              L'aperçu est plafonné pour tenir dans la fenêtre.
            </span>
            <span
              v-if="isPointStrokeWidthOverMax"
              class="text-xs text-red-700 bg-white border border-red-500 rounded px-2 py-1"
              data-testid="custom-point-stroke-width-max-warning"
            >
              L'épaisseur maximale autorisée est de {{ MAX_POINT_STROKE_WIDTH_PX }} px (la valeur sera plafonnée).
            </span>
          </div>
        </div>
      </form>

      <!-- Footer -->
      <div class="modal-action mt-0 pt-3 border-t border-base-200 flex items-center justify-end gap-2 shrink-0">
        <button
          type="button"
          class="modal-secondary-btn w-32"
          @click="dialogRef?.close()"
        >
          Annuler
        </button>
        <button
          type="button"
          class="btn btn-primary rounded-lg w-44"
          data-testid="save-custom-label-styles"
          @click="saveStyles"
        >
          <span class="text-white">Enregistrer</span>
        </button>
      </div>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button>Fermer</button>
    </form>
  </dialog>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type {
  CustomLabelStyle,
  NewCustomLabelStyle,
} from "../utils/labelPresentation";
import { getLabelStylePreviewCss } from "../utils/labelPresentation";
import PointSwatch from "./PointSwatch.vue";
import {
  MAX_POINT_STROKE_WIDTH_PX,
  MAX_PREVIEW_POINT_STROKE_WIDTH_PX,
  parseClampedOpacityFromInput,
  preventNumericShortcutKeys,
} from "../utils/featureTextEditing";
import {
  TrashIcon,
  ArrowPathIcon,
  PlusIcon,
  Bars3Icon,
} from "@heroicons/vue/24/outline";

const MAX_CUSTOM_LABEL_SIZE_PX = 96;
const MIN_CUSTOM_LABEL_SIZE_PX = 6;

type CustomLabelStyleExtended = CustomLabelStyle & {
  hasPoint?: boolean;
  pointColor?: string;
  pointStrokeColor?: string;
  pointFillOpacity?: number;
  pointStrokeOpacity?: number;
  pointStrokeWidth?: number;
};

const props = defineProps<{
  styles: CustomLabelStyle[];
}>();

const emit = defineEmits<{
  (event: "save", styles: CustomLabelStyle[]): void;
}>();

const dialogRef = ref<HTMLDialogElement | null>(null);
const draftStyles = ref<CustomLabelStyleExtended[]>([]);
const editingId = ref<string | null>(null);
const initialSnapshot = ref<CustomLabelStyleExtended | null>(null);
const draggedIndex = ref<number | null>(null);

function onDragStart(index: number, event: DragEvent) {
  draggedIndex.value = index;
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = "move";
  }
}

function onDragOver(index: number) {
  if (draggedIndex.value === null || draggedIndex.value === index) return;
  const item = draftStyles.value.splice(draggedIndex.value, 1)[0];
  draftStyles.value.splice(index, 0, item);
  draggedIndex.value = index;
}

function onDrop(_index: number) {
  draggedIndex.value = null;
}

const draft = ref({
  name: "",
  sizePx: 14,
  bold: false,
  italic: false,
  uppercase: false,
  color: "#000000",
  hasPoint: false,
  pointColor: "#000000",
  pointStrokeColor: "#000000",
  pointFillOpacity: 1,
  pointStrokeOpacity: 1,
  pointStrokeWidth: 1,
});

const isTextStyleActive = computed(() => true);

const isSizeOverMax = computed(() => {
  const num = Number(draft.value.sizePx);
  return Number.isFinite(num) && num > MAX_CUSTOM_LABEL_SIZE_PX;
});

function hasStylePoint(style: CustomLabelStyleExtended): boolean {
  return Boolean(style.hasPoint);
}

function clampSizePx(value: unknown): number {
  const num = Number(value);
  if (!Number.isFinite(num)) return 14;
  return Math.max(MIN_CUSTOM_LABEL_SIZE_PX, Math.min(MAX_CUSTOM_LABEL_SIZE_PX, num));
}

function normalizeDraftSize() {
  draft.value.sizePx = clampSizePx(draft.value.sizePx);
  syncLiveDraft();
}

function onOpacityKeydown(event: KeyboardEvent) {
  preventNumericShortcutKeys(event);
}

function onOpacityInput(field: "pointFillOpacity" | "pointStrokeOpacity", event: Event) {
  const input = event.target as HTMLInputElement;
  if (input.value === "" || input.value === null) {
    draft.value[field] = 0;
    syncLiveDraft();
    return;
  }
  const parsed = parseClampedOpacityFromInput(input.value);
  if (parsed === undefined) return;
  input.value = String(parsed);
  draft.value[field] = parsed;
  syncLiveDraft();
}

function clampOpacity(value: unknown, fallback: number): number {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  return Math.max(0, Math.min(1, num));
}

function clampStrokeWidth(value: unknown, fallback: number): number {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  return Math.max(0, Math.min(MAX_POINT_STROKE_WIDTH_PX, num));
}

const isPointPreviewClamped = computed(() => {
  if (!draft.value.hasPoint) return false;
  const raw = draft.value.pointStrokeWidth;
  return typeof raw === "number" && raw > MAX_PREVIEW_POINT_STROKE_WIDTH_PX;
});

const isPointStrokeWidthOverMax = computed(() => {
  if (!draft.value.hasPoint) return false;
  const raw = draft.value.pointStrokeWidth;
  return typeof raw === "number" && raw > MAX_POINT_STROKE_WIDTH_PX;
});

const pointPreviewStrokeWidth = computed(() => {
  const raw = clampStrokeWidth(draft.value.pointStrokeWidth, 1);
  return Math.min(raw, MAX_PREVIEW_POINT_STROKE_WIDTH_PX);
});

function onStrokeWidthInput(event: Event) {
  const input = event.target as HTMLInputElement;
  if (input.value === "" || input.value === null) {
    draft.value.pointStrokeWidth = 0;
    syncLiveDraft();
    return;
  }
  const val = parseInt(input.value, 10);
  if (isNaN(val)) return;
  draft.value.pointStrokeWidth = val < 0 ? 0 : val;
  syncLiveDraft();
}

function onStrokeWidthChange() {
  if (typeof draft.value.pointStrokeWidth === "number") {
    draft.value.pointStrokeWidth = Math.max(0, Math.min(MAX_POINT_STROKE_WIDTH_PX, draft.value.pointStrokeWidth));
    syncLiveDraft();
  }
}

const currentLiveStyle = computed<CustomLabelStyleExtended>(() => ({
  id: editingId.value ?? "preview",
  name: draft.value.name.trim() || "Style",
  sizePx: clampSizePx(draft.value.sizePx),
  fontStyle: draft.value.italic ? "italic" : "normal",
  fontWeight: draft.value.bold ? "bold" : "normal",
  bold: draft.value.bold,
  textTransform: draft.value.uppercase ? "uppercase" : "none",
  color: draft.value.color,
  priority: 30,
  minZoom: 1,
  hasPoint: draft.value.hasPoint,
  mapElementType: draft.value.hasPoint ? "point" : "label",
  pointColor: draft.value.pointColor || "#000000",
  pointStrokeColor: draft.value.pointStrokeColor || "#000000",
  pointFillOpacity: clampOpacity(draft.value.pointFillOpacity, 1),
  pointStrokeOpacity: clampOpacity(draft.value.pointStrokeOpacity, 1),
  pointStrokeWidth: clampStrokeWidth(draft.value.pointStrokeWidth, 1),
}));

function resetDraft() {
  editingId.value = null;
  initialSnapshot.value = null;
  draft.value = {
    name: "",
    sizePx: 14,
    bold: false,
    italic: false,
    uppercase: false,
    color: "#000000",
    hasPoint: false,
    pointColor: "#000000",
    pointStrokeColor: "#000000",
    pointFillOpacity: 1,
    pointStrokeOpacity: 1,
    pointStrokeWidth: 1,
  };
}

function open() {
  draftStyles.value = props.styles.map((style: CustomLabelStyle) => ({ ...style }));
  if (draftStyles.value.length > 0) {
    editStyle(draftStyles.value[0]);
  } else {
    resetDraft();
  }
  dialogRef.value?.showModal();
}

function editStyle(style: CustomLabelStyleExtended) {
  editingId.value = style.id;
  initialSnapshot.value = { ...style };
  const baseColor = style.color || "#000000";
  draft.value = {
    name: style.name,
    sizePx: style.sizePx,
    bold: Boolean(style.bold || style.fontWeight === "bold"),
    italic: style.fontStyle === "italic",
    uppercase: style.textTransform === "uppercase",
    color: baseColor,
    hasPoint: hasStylePoint(style),
    pointColor: style.pointColor || baseColor,
    pointStrokeColor: style.pointStrokeColor || "#000000",
    pointFillOpacity: clampOpacity(style.pointFillOpacity, 1),
    pointStrokeOpacity: clampOpacity(style.pointStrokeOpacity, 1),
    pointStrokeWidth: clampStrokeWidth(style.pointStrokeWidth, 1),
  };
}

function syncLiveDraft() {
  if (!editingId.value) {
    if (draft.value.name.trim()) {
      const newStyle: CustomLabelStyleExtended = {
        id: crypto.randomUUID(),
        ...toStyleDraft(draft.value.name.trim()),
      };
      draftStyles.value.push(newStyle);
      editStyle(newStyle);
    }
    return;
  }

  const index = draftStyles.value.findIndex(
    (item: CustomLabelStyleExtended) => item.id === editingId.value,
  );
  if (index >= 0) {
    draftStyles.value[index] = {
      ...draftStyles.value[index],
      ...toStyleDraft(draft.value.name.trim() || draftStyles.value[index].name),
    };
  }
}

function submitDraft() {
  syncLiveDraft();
}

function addNewStyle() {
  const newStyle: CustomLabelStyleExtended = {
    id: crypto.randomUUID(),
    name: `Style ${draftStyles.value.length + 1}`,
    sizePx: 14,
    fontStyle: "normal",
    fontWeight: "normal",
    bold: false,
    textTransform: "none",
    color: "#000000",
    priority: 30,
    minZoom: 1,
    hasPoint: false,
    pointColor: "#000000",
    pointStrokeColor: "#000000",
    pointFillOpacity: 1,
    pointStrokeOpacity: 1,
    pointStrokeWidth: 1,
  };
  draftStyles.value.push(newStyle);
  editStyle(newStyle);
}

function revertStyle() {
  if (!initialSnapshot.value || !editingId.value) {
    resetDraft();
    return;
  }
  const snap = initialSnapshot.value;
  const baseColor = snap.color || "#000000";
  draft.value = {
    name: snap.name,
    sizePx: snap.sizePx,
    bold: Boolean(snap.bold || snap.fontWeight === "bold"),
    italic: snap.fontStyle === "italic",
    uppercase: snap.textTransform === "uppercase",
    color: baseColor,
    hasPoint: hasStylePoint(snap),
    pointColor: snap.pointColor || baseColor,
    pointStrokeColor: snap.pointStrokeColor || "#000000",
    pointFillOpacity: clampOpacity(snap.pointFillOpacity, 1),
    pointStrokeOpacity: clampOpacity(snap.pointStrokeOpacity, 1),
    pointStrokeWidth: clampStrokeWidth(snap.pointStrokeWidth, 1),
  };
  const index = draftStyles.value.findIndex(
    (item: CustomLabelStyleExtended) => item.id === snap.id,
  );
  if (index >= 0) {
    draftStyles.value[index] = { ...snap };
  }
}

function removeStyle(id: string) {
  draftStyles.value = draftStyles.value.filter(
    (style: CustomLabelStyleExtended) => style.id !== id,
  );
  if (editingId.value === id) {
    if (draftStyles.value.length > 0) {
      editStyle(draftStyles.value[0]);
    } else {
      resetDraft();
    }
  }
}

function toStyleDraft(
  name = draft.value.name.trim(),
): NewCustomLabelStyle & Omit<CustomLabelStyleExtended, "id"> {
  return {
    name,
    sizePx: clampSizePx(draft.value.sizePx),
    fontStyle: draft.value.italic ? "italic" : "normal",
    fontWeight: draft.value.bold ? "bold" : "normal",
    bold: draft.value.bold,
    textTransform: draft.value.uppercase ? "uppercase" : "none",
    color: draft.value.color,
    priority: 30,
    minZoom: 1,
    hasPoint: draft.value.hasPoint,
    mapElementType: draft.value.hasPoint ? "point" : "label",
    pointColor: draft.value.pointColor || "#000000",
    pointStrokeColor: draft.value.pointStrokeColor || "#000000",
    pointFillOpacity: clampOpacity(draft.value.pointFillOpacity, 1),
    pointStrokeOpacity: clampOpacity(draft.value.pointStrokeOpacity, 1),
    pointStrokeWidth: clampStrokeWidth(draft.value.pointStrokeWidth, 1),
  };
}

function previewStyle(style: CustomLabelStyle, limitSize = false, maxPx = 16) {
  return getLabelStylePreviewCss(style, {
    limitSize,
    maxPx,
  });
}

function saveStyles() {
  emit(
    "save",
    draftStyles.value.map((style: CustomLabelStyleExtended) => ({ ...style })),
  );
  dialogRef.value?.close();
}

defineExpose({
  open,
  draftStyles,
  editingId,
  draft,
  addNewStyle,
  editStyle,
  revertStyle,
  removeStyle,
  syncLiveDraft,
});
</script>