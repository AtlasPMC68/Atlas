<template>
  <dialog ref="editFeatureDialogRef" class="modal" v-if="featureToEdit">
    <div
      class="modal-box w-11/12 flex flex-col gap-5 max-h-[90vh] overflow-y-auto"
      :class="editModalBoxClass"
    >
      <h3 class="text-lg font-bold truncate">
        Modification {{ editModalTypeLabel }}
        <span :class="isEditNameMissing ? 'text-error font-medium' : ''">
          {{ editModalNameText }}
        </span>
      </h3>

      <fieldset class="grid grid-cols-1 lg:grid-cols-2 gap-x-6 gap-y-5 items-start">
        <!-- Section 1 (Top Left): Informations générales -->
        <div class="flex flex-col gap-2 min-w-0 order-1 lg:col-start-1 lg:row-start-1">
          <div class="flex items-center justify-between min-h-[1.75rem]">
            <span class="section-title">
              Informations générales
            </span>
          </div>

          <div
            class="grid grid-cols-1 gap-3 items-start w-full"
            :class="isTextElement ? 'sm:grid-cols-2' : 'grid-cols-1'"
          >
            <div class="flex flex-col gap-1.5 min-w-0">
              <label class="field-label leading-5" for="edit-feature-name">
                Nom de l'élément
              </label>

              <template v-if="isTextElement">
                <textarea
                  id="edit-feature-name"
                  ref="labelTextareaRef"
                  v-model="editDraft.name"
                  rows="2"
                  class="textarea textarea-bordered w-full min-h-[60px] bg-base-100 text-sm leading-snug resize-y"
                  :class="isEditNameMissing ? 'border-error ring-1 ring-error' : 'border-gray-400'"
                  placeholder="Nom de l'élément"
                  required
                  @input="onNameInput"
                ></textarea>
                <span class="field-hint">
                  Vous pouvez le mettre sur plusieurs lignes en appuyant sur Entrée.
                </span>
              </template>

              <input
                v-else
                id="edit-feature-name"
                v-model="editDraft.name"
                type="text"
                class="input input-bordered w-full h-[50px] text-sm"
                :class="isEditNameMissing ? 'border-error ring-1 ring-error' : 'border-gray-400'"
                placeholder="Nom de l'élément"
                required
                @input="onNameInput"
              />
            </div>

            <div v-if="isTextElement" class="flex flex-col gap-1.5 min-w-0">
              <span class="field-label leading-5">
                Aperçu
              </span>
              <div class="preview-frame p-2 min-h-[60px] flex items-center">
                <div
                  class="preview-box px-3 py-1.5 min-h-[42px] w-full"
                  :style="editTextStyle"
                >
                  <svg
                    v-if="isEditingPoint"
                    width="14"
                    height="14"
                    viewBox="0 0 14 14"
                    class="shrink-0 overflow-hidden inline-block align-middle mr-1.5"
                  >
                    <circle
                      cx="7"
                      cy="7"
                      r="4.5"
                      :fill="pointPreviewFillColor"
                      :fill-opacity="pointPreviewFillOpacity"
                      :stroke="pointPreviewStrokeColor"
                      :stroke-width="Math.min(pointPreviewStrokeWidth, 2)"
                      :stroke-opacity="pointPreviewStrokeOpacity"
                    />
                  </svg>
                  <span class="whitespace-pre-line break-words">
                    {{ editDraft.labelText || editDraft.name || "Exemple de texte" }}
                  </span>
                </div>
              </div>
              <span
                v-if="isPreviewClamped"
                class="text-xs text-red-700 bg-white border border-red-500 rounded px-2 py-1"
                data-testid="preview-limit-notice"
              >
                L'aperçu est plafonné pour tenir dans la fenêtre.
              </span>
            </div>
          </div>
        </div>

        <!-- Section 2 (Top Right): Cartes associées -->
        <div
          v-if="props.mapPeriods && props.mapPeriods.length > 0"
          class="flex flex-col gap-2 min-w-0 order-3 lg:col-start-2 lg:row-start-1"
          :class="hasBottomRightSection ? '' : 'lg:row-span-2'"
          data-testid="map-assignment-section"
        >
          <div class="flex items-center justify-between gap-2 min-h-[1.75rem]">
            <label class="section-title">
              Cartes associées
            </label>
            <button
              type="button"
              class="btn btn-ghost btn-xs text-primary font-semibold hover:bg-primary/10 shrink-0"
              @click="toggleSelectAllMaps"
            >
              {{ areAllMapsSelected ? "Tout désélectionner" : "Tout sélectionner" }}
            </button>
          </div>

          <div class="flex flex-col gap-1.5 min-w-0">
            <span class="field-label leading-5">
              Sélection des cartes
            </span>
            <div
              class="flex flex-col gap-1 overflow-y-auto border border-gray-400 rounded-lg p-2 bg-base-100"
              :class="hasBottomRightSection ? 'max-h-36 sm:max-h-40' : 'max-h-72 sm:max-h-80'"
            >
              <label
                v-for="period in props.mapPeriods"
                :key="period.id"
                class="flex items-center gap-2 rounded px-1.5 py-0.5 cursor-pointer hover:bg-base-200/50"
              >
                <input
                  type="checkbox"
                  :value="period.id"
                  v-model="editDraft.selectedMapIds"
                  class="checkbox checkbox-xs checkbox-primary shrink-0"
                  :data-testid="`map-checkbox-${period.id}`"
                />
                <span class="text-sm truncate">{{ period.title }}</span>
              </label>
            </div>
            <div
              v-if="editDraft.selectedMapIds && editDraft.selectedMapIds.length > 1"
              class="alert alert-info py-1.5 px-2.5 text-xs rounded-lg flex items-center gap-2"
            >
              <InformationCircleIcon class="w-4 h-4 shrink-0 text-info" />
              <span>Cet élément est partagé sur {{ editDraft.selectedMapIds.length }} cartes. Toute modification sera synchronisée sur l'ensemble de ces cartes.</span>
            </div>
            <span class="field-hint">
              Si aucune carte n'est sélectionnée, l'élément reste dans « Éléments généraux ».
            </span>
          </div>
        </div>

        <!-- Section 3 (Bottom Left): Réglages du texte -->
        <div
          v-if="isTextElement"
          class="editor-section flex flex-col gap-3 pt-4 order-2 lg:col-start-1 lg:row-start-2"
        >
          <div class="flex items-center justify-between gap-2 min-h-[1.75rem]">
            <span class="section-title">
              Réglages du texte
            </span>
          </div>

          <div class="flex flex-col gap-1.5">
            <label class="field-label leading-5">Type de mot</label>
            <div class="flex flex-row items-center gap-2.5 w-full">
              <select
                v-model="editDraft.labelStyleSelection"
                data-testid="word-type-select"
                class="select select-bordered flex-1 min-w-0 h-[50px] text-sm"
                :style="selectedWordTypeSelectStyle"
                @change="onLabelStyleSelectionChange"
              >
                <option
                  v-for="style in availableCustomLabelStyles"
                  :key="style.id"
                  :value="`custom:${style.id}`"
                  :style="getCustomStyleObject(style)"
                  class="text-sm"
                >
                  {{ getCustomStyleOptionLabel(style) }}
                </option>
                <option
                  v-for="(_, typeKey) in WORD_TYPE_STYLES"
                  :key="typeKey"
                  :value="typeKey"
                  :style="getWordTypeOptionStyle(typeKey)"
                  class="text-sm"
                >
                  {{ getWordTypeOptionLabel(typeKey) }}
                </option>
              </select>
              <button
                type="button"
                class="modal-secondary-btn h-[50px]"
                data-testid="manage-custom-label-styles"
                @click="labelStyleManagerRef?.open()"
              >
                Personnaliser
              </button>
            </div>
            <p
              v-if="!editDraft.customLabelStyleId"
              class="alert alert-info py-1.5 px-2.5 text-xs rounded-lg flex items-start gap-2"
              data-testid="word-style-scope-notice"
            >
              <InformationCircleIcon class="w-4 h-4 shrink-0 text-info mt-0.5" />
              <span>
                La modification du type, des couleurs, de la taille et du point s'applique uniquement à ce mot.
                Elle ne change pas le style de tous les mots du même type.
                Pour un style réutilisable, créez un style personnalisé.
              </span>
            </p>
          </div>

          <div
            v-if="!editDraft.customLabelStyleId"
            class="flex flex-col gap-1.5 w-full"
          >
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full">
              <div class="setting-card h-[50px]">
                <label class="setting-card-label" for="edit-feature-text-color">
                  Couleur texte
                </label>
                <input
                  id="edit-feature-text-color"
                  v-model="editDraft.textColorHex"
                  data-testid="text-color-input"
                  type="color"
                  class="setting-color-input"
                />
              </div>

              <div
                class="setting-card h-[50px]"
                :class="{ 'border-error': isTextSizeOverMax }"
              >
                <label class="setting-card-label" for="edit-feature-text-size">
                  Taille (px)
                </label>
                <input
                  id="edit-feature-text-size"
                  v-model.number="editDraft.textSizePx"
                  data-testid="text-size-input"
                  type="number"
                  :min="MIN_TEXT_SIZE_PX"
                  :max="MAX_TEXT_SIZE_PX"
                  step="1"
                  class="setting-number-input"
                  @change="onTextSizeChange"
                />
              </div>
            </div>

            <span
              v-if="isTextSizeOverMax"
              class="text-xs text-red-700 bg-white border border-red-500 rounded px-2 py-1"
              data-testid="text-size-max-warning"
            >
              La taille maximale autorisée est de {{ MAX_TEXT_SIZE_PX }} px (la valeur a été plafonnée).
            </span>
          </div>
        </div>

        <!-- Section 4 (Bottom Right / Shape settings): Réglages géométriques unifiés -->
        <div
          v-if="hasGeometryControls"
          class="editor-section flex flex-col gap-3 pt-4"
          :class="isTextElement ? 'order-4 lg:col-start-2 lg:row-start-2' : 'order-2 lg:col-start-1 lg:row-start-2'"
        >
          <div class="flex items-center justify-between gap-2 min-h-[1.75rem]">
            <span class="section-title">
              {{ geometrySectionTitle }}
            </span>
            <span class="field-hint">
              {{ geometrySectionHint }}
            </span>
          </div>

          <div class="flex flex-col gap-1.5">
            <span class="field-label leading-5">Couleurs et aperçu</span>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full">
              <div class="setting-card h-[50px]">
                <label class="setting-card-label" for="edit-feature-fill-color">
                  Fond
                </label>
                <input
                  id="edit-feature-fill-color"
                  v-model="editDraft.colorHex"
                  data-testid="color-input"
                  type="color"
                  class="setting-color-input"
                />
              </div>

              <div class="setting-card h-[50px] px-2.5 gap-1.5 min-w-0">
                <label
                  class="setting-card-label text-xs sm:text-sm font-medium truncate"
                  for="edit-fill-opacity"
                  title="Opacité du fond (0 à 1)"
                >
                  Opacité fond
                </label>
                <input
                  id="edit-fill-opacity"
                  v-model.number="editDraft.fillOpacity"
                  data-testid="fill-opacity-input"
                  type="number"
                  step="0.1"
                  min="0"
                  max="1"
                  placeholder="0–1"
                  class="setting-number-input !w-12 text-xs sm:text-sm px-0.5 shrink-0"
                  @keydown="onOpacityKeydown"
                  @input="onOpacityInput('fillOpacity', $event)"
                  @change="onOpacityChange('fillOpacity', $event)"
                />
              </div>

              <div class="setting-card h-[50px]">
                <label class="setting-card-label" for="edit-feature-stroke-color">
                  Contour
                </label>
                <input
                  id="edit-feature-stroke-color"
                  v-model="editDraft.strokeColorHex"
                  data-testid="point-stroke-color-input"
                  type="color"
                  class="setting-color-input"
                />
              </div>

              <div class="setting-card h-[50px] px-2.5 gap-1.5 min-w-0">
                <label
                  class="setting-card-label text-xs sm:text-sm font-medium truncate"
                  for="edit-stroke-opacity"
                  title="Opacité du contour (0 à 1)"
                >
                  Opacité contour
                </label>
                <input
                  id="edit-stroke-opacity"
                  v-model.number="editDraft.strokeOpacity"
                  data-testid="stroke-opacity-input"
                  type="number"
                  step="0.1"
                  min="0"
                  max="1"
                  placeholder="0–1"
                  class="setting-number-input !w-12 text-xs sm:text-sm px-0.5 shrink-0"
                  @keydown="onOpacityKeydown"
                  @input="onOpacityInput('strokeOpacity', $event)"
                  @change="onOpacityChange('strokeOpacity', $event)"
                />
              </div>

              <div
                class="setting-card h-[50px] px-2.5 gap-1.5 min-w-0"
                :class="{ 'border-error': isPointStrokeWidthOverMax }"
              >
                <label
                  class="setting-card-label text-xs sm:text-sm font-medium truncate"
                  for="edit-stroke-width"
                  title="Épaisseur du contour en pixels"
                >
                  Épaisseur contour
                </label>
                <input
                  id="edit-stroke-width"
                  v-model.number="editDraft.strokeWidth"
                  data-testid="stroke-width-input"
                  type="number"
                  min="0"
                  :max="maxStrokeWidth"
                  class="setting-number-input !w-12 text-xs sm:text-sm px-0.5 shrink-0"
                  @input="onStrokeWidthInput"
                  @change="onStrokeWidthChange"
                />
              </div>

              <div
                class="setting-card h-[50px] flex items-center justify-between gap-2 px-3"
                data-testid="point-preview-container"
              >
                <span class="setting-card-label">
                  Aperçu
                </span>
                <div class="flex items-center justify-center shrink-0">
                  <svg width="32" height="32" viewBox="0 0 40 40" class="overflow-hidden">
                    <circle
                      v-if="isEditingPoint"
                      cx="20"
                      cy="20"
                      r="12"
                      :fill="pointPreviewFillColor"
                      :fill-opacity="pointPreviewFillOpacity"
                      :stroke="pointPreviewStrokeColor"
                      :stroke-width="pointPreviewStrokeWidth"
                      :stroke-opacity="pointPreviewStrokeOpacity"
                    />
                    <rect
                      v-else
                      x="3"
                      y="5"
                      width="34"
                      height="30"
                      rx="5"
                      :fill="pointPreviewFillColor"
                      :fill-opacity="pointPreviewFillOpacity"
                      :stroke="pointPreviewStrokeColor"
                      :stroke-width="pointPreviewStrokeWidth"
                      :stroke-opacity="pointPreviewStrokeOpacity"
                    />
                  </svg>
                </div>
              </div>
            </div>

            <span
              v-if="isPointPreviewClamped"
              class="text-xs text-red-700 bg-white border border-red-500 rounded px-2 py-1"
              data-testid="point-preview-limit-notice"
            >
              L'aperçu est plafonné pour tenir dans la fenêtre.
            </span>
            <span
              v-if="isPointStrokeWidthOverMax"
              class="text-xs text-red-700 bg-white border border-red-500 rounded px-2 py-1"
              data-testid="point-stroke-width-max-warning"
            >
              L'épaisseur maximale autorisée est de {{ maxStrokeWidth }} px (la valeur a été plafonnée).
            </span>
          </div>
        </div>
      </fieldset>

      <div class="modal-action mt-0 pt-3 border-t border-base-200 flex items-center justify-end gap-2">
        <button
          class="modal-secondary-btn w-32"
          :disabled="isEditing"
          @click="close"
        >
          Annuler
        </button>
        <button
          class="btn btn-primary rounded-lg w-32"
          :disabled="isEditing"
          @click="onEditFeature"
        >
          <span
            v-if="isEditing"
            class="loading loading-spinner loading-xs"
          ></span>
          <span v-else class="text-white">Modifier</span>
        </button>
      </div>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button :disabled="isEditing">close</button>
    </form>
  </dialog>

  <CustomLabelStyleManager
    ref="labelStyleManagerRef"
    :styles="availableCustomLabelStyles"
    @save="onSaveCustomLabelStyles"
  />
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from "vue";
import type { CSSProperties } from "vue";
import { InformationCircleIcon } from "@heroicons/vue/24/outline";
import type { Feature } from "../typescript/feature";
import type { MapPeriod } from "../typescript/map";
import type { CustomLabelStyle } from "../utils/labelPresentation";
import {
  MAX_TEXT_SIZE_PX,
  MIN_TEXT_SIZE_PX,
  normalizeTextSizePx,
  MAX_PREVIEW_FONT_SIZE_PX,
  getWordTypeOptionLabel,
  getWordTypeOptionStyle,
  getCustomStyleObject,
  getCustomStyleOptionLabel,
  hasCustomStylePoint,
  resolveLabelTypography,
} from "../utils/labelPresentation";
import CustomLabelStyleManager from "./CustomLabelStyleManager.vue";
import { getMapElementType } from "../utils/featureHelpers";
import {
  WORD_TYPE_STYLES,
  WORD_TYPE_TAXONOMY,
  isTextFeature,
  formatWordText,
} from "../utils/wordStyles";
import {
  prepareFeatureForEdit,
  coerceEditedFeature,
  createFeaturesForSelectedMaps,
  getDefaultTextSizePx,
  normalizeOpacity,
  normalizeStrokeWidth,
  DEFAULT_POINT_STROKE_OPACITY,
  MAX_STROKE_WIDTH_PX,
  MAX_POINT_STROKE_WIDTH_PX,
  MAX_PREVIEW_POINT_STROKE_WIDTH_PX,
  type FeatureEditSubmitPayload,
} from "../utils/featureTextEditing";
import { rgbToHex } from "../utils/utils";
import { createActionCallbacks } from "../utils/actionCallbacks";

const props = defineProps<{
  mapPeriods?: MapPeriod[];
  customLabelStyles?: CustomLabelStyle[];
}>();

const emit = defineEmits<{
  (e: "update-feature", payload: any, callbacks?: any): void;
  (e: "save-custom-label-styles", styles: CustomLabelStyle[]): void;
}>();

const editFeatureDialogRef = ref<HTMLDialogElement | undefined>(undefined);
const labelTextareaRef = ref<HTMLTextAreaElement | null>(null);
const labelStyleManagerRef = ref<InstanceType<typeof CustomLabelStyleManager> | null>(null);
const featureToEdit = ref<Feature | undefined>(undefined);
const editDraft = ref<FeatureEditSubmitPayload>({
  name: "",
  wordType: "city",
});
const isEditing = ref(false);

const isTextElement = computed(() => isTextFeature(featureToEdit.value));

const availableCustomLabelStyles = computed<CustomLabelStyle[]>(() => {
  return props.customLabelStyles ?? [];
});

const activeCustomLabelStyle = computed<CustomLabelStyle | undefined>(() => {
  const selection = editDraft.value.labelStyleSelection ?? "";
  if (selection.startsWith("custom:")) {
    const customId = selection.replace("custom:", "");
    return (
      availableCustomLabelStyles.value.find(
        (item: CustomLabelStyle) => item.id === customId,
      ) ?? editDraft.value.customLabelStyle ?? undefined
    );
  }
  if (!selection && editDraft.value.customLabelStyleId) {
    return (
      availableCustomLabelStyles.value.find(
        (item: CustomLabelStyle) => item.id === editDraft.value.customLabelStyleId,
      ) ?? editDraft.value.customLabelStyle ?? undefined
    );
  }
  return undefined;
});

const isEditingPoint = computed(() => {
  if (!featureToEdit.value) return false;
  if (isTextElement.value) {
    if (activeCustomLabelStyle.value) {
      return hasCustomStylePoint(activeCustomLabelStyle.value);
    }
    const entry = WORD_TYPE_TAXONOMY[editDraft.value.wordType as keyof typeof WORD_TYPE_TAXONOMY];
    return (entry?.mapElementType ?? getMapElementType(featureToEdit.value)) === "point";
  }
  return getMapElementType(featureToEdit.value) === "point";
});

const isEditNameMissing = computed(() => !editDraft.value.name?.trim());
const editModalNameText = computed(() => editDraft.value.name?.trim() || "Élément sans nom");

const editModalTypeLabel = computed(() => {
  if (isTextElement.value) return "du texte";
  if (isEditingPoint.value) return "du point";
  const elementType = featureToEdit.value
    ? getMapElementType(featureToEdit.value)
    : undefined;
  if (elementType === "image") return "de l'image";
  return "de la forme";
});

const isPreviewClamped = computed(() => {
  const rawSize =
    activeCustomLabelStyle.value?.sizePx ??
    editDraft.value.textSizePx ??
    defaultTextSizePx.value;
  return isTextElement.value && rawSize > MAX_PREVIEW_FONT_SIZE_PX;
});

const isTextSizeOverMax = computed(() => {
  const rawSize = editDraft.value.textSizePx;
  return typeof rawSize === "number" && rawSize > MAX_TEXT_SIZE_PX;
});

const maxStrokeWidth = computed(() => {
  return isEditingPoint.value ? MAX_POINT_STROKE_WIDTH_PX : MAX_STROKE_WIDTH_PX;
});

const isPointPreviewClamped = computed(() => {
  if (!isEditingPoint.value) return false;
  const raw = editDraft.value.strokeWidth;
  return typeof raw === "number" && raw > MAX_PREVIEW_POINT_STROKE_WIDTH_PX;
});

const isPointStrokeWidthOverMax = computed(() => {
  if (!isEditingPoint.value) return false;
  const raw = editDraft.value.strokeWidth;
  return typeof raw === "number" && raw > MAX_POINT_STROKE_WIDTH_PX;
});

const defaultTextSizePx = computed(() => {
  return getDefaultTextSizePx(
    editDraft.value.wordType,
  );
});

const hasGeometryControls = computed(() => {
  if (!featureToEdit.value) return false;
  if (activeCustomLabelStyle.value || editDraft.value.customLabelStyleId) return false;
  return isEditingPoint.value || !isTextElement.value;
});

const hasBottomRightSection = computed(
  () => hasGeometryControls.value && isTextElement.value,
);

const editModalBoxClass = computed(() => {
  if (!featureToEdit.value) return "max-w-4xl";
  const elementType = getMapElementType(featureToEdit.value);
  if (elementType === "image") return "max-w-2xl";
  return "max-w-7xl w-[96vw]";
});

const geometrySectionTitle = computed(() => {
  return isEditingPoint.value ? "Réglages du point" : "Réglages de la forme";
});

const geometrySectionHint = computed(() => {
  if (isEditingPoint.value && isTextElement.value) {
    return "Symbole associé au texte";
  }
  return isEditingPoint.value
    ? "Symbole sur la carte"
    : "Zone, polygone ou ligne";
});

const editTextStyle = computed<CSSProperties>(() => {
  if (!isTextElement.value) return {};
  const typo = resolveLabelTypography({
    wordType: editDraft.value.wordType,
    customLabelStyle: activeCustomLabelStyle.value ?? editDraft.value.customLabelStyle ?? null,
    color: editDraft.value.textColorHex ?? editDraft.value.colorHex,
    sizePx: normalizeTextSizePx(editDraft.value.textSizePx),
  });
  return {
    fontStyle: typo.fontStyle,
    fontWeight: typo.fontWeight,
    textTransform: typo.textTransform,
    color: typo.color,
    fontSize: `${Math.min(typo.sizePx, MAX_PREVIEW_FONT_SIZE_PX)}px`,
  };
});

const pointPreviewFillColor = computed(() => {
  if (activeCustomLabelStyle.value) {
    return (
      activeCustomLabelStyle.value.pointColor ||
      activeCustomLabelStyle.value.color ||
      editDraft.value.colorHex ||
      "#000000"
    );
  }
  return editDraft.value.colorHex || "#000000";
});

const pointPreviewStrokeColor = computed(() => {
  if (activeCustomLabelStyle.value) {
    return (
      activeCustomLabelStyle.value.pointStrokeColor ||
      "#000000"
    );
  }
  if (isEditingPoint.value) {
    return editDraft.value.strokeColorHex || "#000000";
  }
  return editDraft.value.strokeColorHex || editDraft.value.colorHex || "#000000";
});

const pointPreviewFillOpacity = computed(() => {
  if (activeCustomLabelStyle.value) {
    return activeCustomLabelStyle.value.pointFillOpacity ?? 1;
  }
  return normalizeOpacity(editDraft.value.fillOpacity) ?? 1;
});

const pointPreviewStrokeOpacity = computed(() => {
  if (activeCustomLabelStyle.value) {
    return activeCustomLabelStyle.value.pointStrokeOpacity ?? 1;
  }
  return normalizeOpacity(editDraft.value.strokeOpacity) ?? 1;
});

const pointPreviewStrokeWidth = computed(() => {
  if (activeCustomLabelStyle.value) {
    const raw = activeCustomLabelStyle.value.pointStrokeWidth ?? 1;
    return Math.min(raw, MAX_PREVIEW_POINT_STROKE_WIDTH_PX);
  }
  const raw = normalizeStrokeWidth(editDraft.value.strokeWidth) ?? 1;
  if (isEditingPoint.value) {
    return Math.min(raw, MAX_PREVIEW_POINT_STROKE_WIDTH_PX);
  }
  return raw;
});

const selectedWordTypeSelectStyle = computed<CSSProperties>(() => {
  if (activeCustomLabelStyle.value) {
    return getCustomStyleObject(activeCustomLabelStyle.value);
  }
  return getWordTypeOptionStyle(editDraft.value.wordType || "");
});

const areAllMapsSelected = computed(() => {
  if (!props.mapPeriods || props.mapPeriods.length === 0) return false;
  const selected = editDraft.value.selectedMapIds ?? [];
  return props.mapPeriods.every((p: MapPeriod) => selected.includes(p.id));
});

function toggleSelectAllMaps() {
  if (!props.mapPeriods) return;
  if (areAllMapsSelected.value) {
    editDraft.value.selectedMapIds = [];
  } else {
    editDraft.value.selectedMapIds = props.mapPeriods.map((p: MapPeriod) => p.id);
  }
}

function resizeLabelTextarea() {
  const el = labelTextareaRef.value;
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${el.scrollHeight}px`;
}

function onNameInput() {
  if (!isTextElement.value) return;
  editDraft.value.labelText = editDraft.value.name;
  nextTick(() => resizeLabelTextarea());
}

function onTextSizeChange() {
  if (typeof editDraft.value.textSizePx === "number") {
    editDraft.value.textSizePx = normalizeTextSizePx(editDraft.value.textSizePx);
  }
}

function onOpacityKeydown(event: KeyboardEvent) {
  if (event.key === "-" || event.key === "+" || event.key === "e" || event.key === "E") {
    event.preventDefault();
  }
}

function onOpacityInput(field: "fillOpacity" | "strokeOpacity", event: Event) {
  const input = event.target as HTMLInputElement;
  const raw = input.value;
  if (raw === "" || raw === null) {
    editDraft.value[field] = undefined;
    return;
  }
  const clean = raw.replace(",", ".");
  let num = parseFloat(clean);
  if (isNaN(num)) return;
  if (num > 1) {
    num = 1;
    input.value = "1";
  } else if (num < 0) {
    num = 0;
    input.value = "0";
  }
  editDraft.value[field] = num;
}

function onOpacityChange(field: "fillOpacity" | "strokeOpacity", event: Event) {
  const input = event.target as HTMLInputElement;
  const val = normalizeOpacity(editDraft.value[field]);
  editDraft.value[field] = val;
  if (val !== undefined) {
    input.value = String(val);
  }
}

function onStrokeWidthInput(event: Event) {
  const input = event.target as HTMLInputElement;
  if (input.value === "" || input.value === null) {
    editDraft.value.strokeWidth = undefined;
    return;
  }
  const val = parseInt(input.value, 10);
  if (isNaN(val)) return;
  if (val < 0) {
    input.value = "0";
    editDraft.value.strokeWidth = 0;
  } else {
    editDraft.value.strokeWidth = val;
  }
}

function onStrokeWidthChange() {
  if (typeof editDraft.value.strokeWidth === "number") {
    const max = maxStrokeWidth.value;
    editDraft.value.strokeWidth = Math.max(0, Math.min(max, editDraft.value.strokeWidth));
  }
}

function onLabelStyleSelectionChange() {
  const selection = editDraft.value.labelStyleSelection ?? "";
  if (selection.startsWith("custom:")) {
    const customId = selection.slice("custom:".length);
    const style = availableCustomLabelStyles.value.find(
      (item: CustomLabelStyle) => item.id === customId,
    ) ?? editDraft.value.customLabelStyle ?? featureToEdit.value?.properties?.customLabelStyle;
    editDraft.value.customLabelStyleId = customId;
    if (!style) return;
    editDraft.value.customLabelStyle = style;
    editDraft.value.colorHex = style.pointColor || style.color || "#000000";
    editDraft.value.textColorHex = style.color || "#000000";
    const baseText = editDraft.value.labelText || editDraft.value.name || "";
    editDraft.value.labelText =
      style.textTransform === "uppercase" ? baseText.toUpperCase() : baseText;
    return;
  }

  const hadCustomStyle = Boolean(
    editDraft.value.customLabelStyleId ||
    editDraft.value.customLabelStyle ||
    featureToEdit.value?.properties?.customLabelStyleId,
  );
  editDraft.value.customLabelStyleId = undefined;
  editDraft.value.customLabelStyle = undefined;
  const wordType = selection;
  if (Object.prototype.hasOwnProperty.call(WORD_TYPE_TAXONOMY, wordType)) {
    editDraft.value.wordType = wordType as keyof typeof WORD_TYPE_TAXONOMY;
  }

  if (hadCustomStyle) {
    editDraft.value.colorHex = "#000000";
    editDraft.value.textColorHex = "#000000";
  } else {
    const originalColorHex = featureToEdit.value
      ? rgbToHex(featureToEdit.value.properties.colorRgb)
      : undefined;
    const originalTextColorHex = featureToEdit.value
      ? rgbToHex(featureToEdit.value.properties.textColorRgb)
      : undefined;
    editDraft.value.colorHex = editDraft.value.colorHex || originalColorHex || "#000000";
    editDraft.value.textColorHex =
      editDraft.value.textColorHex ||
      originalTextColorHex ||
      (featureToEdit.value && getMapElementType(featureToEdit.value) === "label"
        ? editDraft.value.colorHex
        : "#000000");
  }

  editDraft.value.textSizePx = defaultTextSizePx.value;
  const entry = WORD_TYPE_TAXONOMY[editDraft.value.wordType];
  if (entry?.mapElementType === "point") {
    editDraft.value.fillOpacity =
      normalizeOpacity(editDraft.value.fillOpacity) ?? 1;
    editDraft.value.strokeOpacity =
      normalizeOpacity(editDraft.value.strokeOpacity) ?? DEFAULT_POINT_STROKE_OPACITY;
    editDraft.value.strokeWidth =
      normalizeStrokeWidth(editDraft.value.strokeWidth) ?? 1;
    editDraft.value.strokeColorHex = editDraft.value.strokeColorHex || "#000000";
    editDraft.value.colorHex = editDraft.value.colorHex || "#000000";
  }
  const baseText = editDraft.value.labelText || editDraft.value.name || "";
  editDraft.value.labelText = formatWordText(baseText, editDraft.value.wordType);
}

function open(feature: Feature) {
  const state = prepareFeatureForEdit(feature);
  featureToEdit.value = state.feature;
  editDraft.value = state.draft;
  if (editDraft.value.customLabelStyleId) {
    const matched = availableCustomLabelStyles.value.find(
      (s: CustomLabelStyle) => s.id === editDraft.value.customLabelStyleId,
    );
    if (matched) {
      editDraft.value.customLabelStyle = matched;
      editDraft.value.colorHex = matched.pointColor || matched.color || editDraft.value.colorHex || "#000000";
      editDraft.value.textColorHex = matched.color || editDraft.value.textColorHex || "#000000";
    }
  }

  nextTick(() => {
    editFeatureDialogRef.value?.showModal();
    if (isTextElement.value) {
      resizeLabelTextarea();
    }
  });
}

function close() {
  editFeatureDialogRef.value?.close();
}

function onSaveCustomLabelStyles(styles: CustomLabelStyle[]) {
  emit("save-custom-label-styles", styles);
  if (editDraft.value.customLabelStyleId) {
    const updated = styles.find((s) => s.id === editDraft.value.customLabelStyleId);
    if (updated) {
      editDraft.value.customLabelStyle = updated;
    }
  }
}

async function onEditFeature() {
  if (!featureToEdit.value) return;

  isEditing.value = true;

  const isLabel = !isEditingPoint.value && isTextElement.value;
  if (!isEditingPoint.value && (isLabel || !hasGeometryControls.value) && editDraft.value.textColorHex) {
    editDraft.value.colorHex = editDraft.value.textColorHex;
  }

  const currentCustomStyle = activeCustomLabelStyle.value ?? editDraft.value.customLabelStyle;
  const updatedFeature = coerceEditedFeature(featureToEdit.value, {
    ...editDraft.value,
    customLabelStyle: currentCustomStyle,
  });

  const allUpdated = createFeaturesForSelectedMaps(
    updatedFeature,
    editDraft.value.selectedMapIds,
  );

  featureToEdit.value = updatedFeature;

  emit(
    "update-feature",
    (allUpdated.length === 1 ? allUpdated[0] : allUpdated) as any,
    createActionCallbacks({
      successMessage: "Élément mis à jour !",
      errorFallback: "Erreur lors de la mise à jour de l'élément.",
      loadingRef: isEditing,
      dialogRef: editFeatureDialogRef,
    }),
  );
}

defineExpose({
  open,
  close,
});
</script>
