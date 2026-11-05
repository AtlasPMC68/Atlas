<template>
  <div class="flex h-full min-h-0 flex-col">
    <div class="tabs tabs-boxed bg-base-200 gap-2 p-1.5">
      <button
        v-for="group in featureGroups"
        :key="group.type"
        type="button"
        role="tab"
        :aria-selected="activeGroup?.type === group.type"
        :data-testid="`feature-tab-${group.type}`"
        class="tab flex-1 p-0"
        :title="`${group.label}`"
        @click="activeGroupType = group.type"
      >
        <component
          :is="getGroupIcon(group.type)"
          class="h-5 w-5 text-primary-500"
        />
      </button>
    </div>

    <!-- Liste des éléments avec contrôle de visibilité -->

    <div class="px-3 flex flex-1 flex-col min-h-0">
      <div
        class="card flex flex-1 flex-col gap-4 min-h-0 overflow-y-auto scroll-stable"
      >
        <div class="flex items-center justify-between">
          <label
            class="label cursor-pointer justify-start gap-2 flex-1 min-w-0"
          >
            <input
              type="checkbox"
              :checked="isAnyVisible"
              @change="toggleActiveGroup(!isAnyVisible)"
              class="checkbox checkbox-sm checkbox-primary"
            />
            <span class="text-sm font-bold text-gray-900 truncate">
              {{ activeGroup.label }}
            </span>
          </label>
        </div>
        <div class="divider m-0 h-0"></div>

        <!-- Validate extracted texts button -->
        <div
          v-if="activeGroup?.type === 'point' && validationFeaturesByMap.length > 0"
          class="flex flex-col gap-2 p-2 bg-indigo-50/70 border border-indigo-200/80 rounded-xl"
        >
          <div class="flex items-center justify-between">
            <span class="text-xs font-bold text-indigo-950 flex items-center gap-1.5">
              <DocumentCheckIcon class="w-4 h-4 text-indigo-600" />
              Textes non reconnus
            </span>
          </div>

          <div class="flex items-center gap-1.5">
            <button
              type="button"
              class="btn btn-primary btn-xs flex-1 bg-blue-600 hover:bg-blue-700 border-none text-white font-semibold flex items-center justify-center gap-1 py-1 h-auto"
              @click="openMapSelectionOrValidate"
            >
              <span>Examiner les rejets</span>
            </button>
          </div>
        </div>

        <div class="flex flex-col gap-2">
          <template v-if="featuresByMap.length > 0">
            <div
              v-for="mapGroup in featuresByMap"
              :key="mapGroup.id || 'general'"
              class="flex flex-col gap-2"
            >
              <div class="flex items-center justify-between rounded group">
                <div class="flex items-center gap-1.5 flex-1 min-w-0">
                  <button
                    type="button"
                    class="flex h-6 w-6 shrink-0 items-center justify-center rounded text-gray-400 hover:text-gray-700 hover:bg-base-200 transition-colors focus:outline-none"
                    @click="toggleMapCollapse(mapGroup.id)"
                    :title="isMapCollapsed(mapGroup.id) ? `Développer ${mapGroup.title}` : `Réduire ${mapGroup.title}`"
                    :aria-label="isMapCollapsed(mapGroup.id) ? `Développer ${mapGroup.title}` : `Réduire ${mapGroup.title}`"
                  >
                    <ChevronDownIcon
                      class="w-4 h-4 transition-transform duration-200"
                      :class="{ '-rotate-90': isMapCollapsed(mapGroup.id) }"
                    />
                  </button>
                  <label
                    class="label cursor-pointer justify-start gap-2 flex-1 min-w-0 p-0"
                  >
                    <input
                      type="checkbox"
                      :checked="isMapGroupAnyVisible(mapGroup.id)"
                      @change="
                        toggleMapGroup(
                          mapGroup.id,
                          !isMapGroupAnyVisible(mapGroup.id),
                        )
                      "
                      class="checkbox checkbox-sm checkbox-primary shrink-0"
                    />
                    <button
                      v-if="mapGroup.id !== null"
                      type="button"
                      class="text-sm font-semibold text-gray-700 truncate text-left hover:text-primary flex-1 min-w-0"
                      :title="`Modifier ${mapGroup.title}`"
                      @click.stop="emit('edit-map', mapGroup.id)"
                    >
                      {{ mapGroup.title }}
                    </button>
                    <span
                      v-else
                      class="text-sm font-semibold text-gray-700 truncate flex-1 min-w-0"
                      :title="mapGroup.title"
                    >
                      {{ mapGroup.title }}
                    </span>
                  </label>
                </div>
                <div class="flex items-center gap-1 shrink-0" v-if="mapGroup.id !== null">
                  <button
                    type="button"
                    class="flex h-8 w-8 items-center justify-center rounded hover:bg-base-200"
                    :aria-label="`Modifier le nom et la période de ${mapGroup.title}`"
                    title="Modifier le nom et la période"
                    @click.stop="emit('edit-map', mapGroup.id)"
                  >
                    <PencilSquareIcon class="w-4 h-4 text-gray-500 hover:text-primary" />
                  </button>
                  <button
                    class="flex h-8 w-8 items-center justify-center"
                    @click="showDeleteMapDialog(mapGroup.id, mapGroup.title)"
                    title="Supprimer la carte"
                  >
                    <TrashIcon class="w-5 h-5 text-red-500 hover:text-red-800" />
                  </button>
                </div>
              </div>
              <div v-if="!isMapCollapsed(mapGroup.id)" class="flex flex-col gap-2">
                <div
                  v-for="feature in mapGroup.features"
                  :key="feature.id"
                  :data-feature-item-id="String(feature.id)"
                  class="flex w-full flex-row items-center justify-between gap-2 rounded px-1.5 py-1 transition-all cursor-pointer"
                  :class="[
                    selectedFeatureId === String(feature.id)
                      ? 'ring-2 ring-primary bg-primary/10 border border-primary font-semibold'
                      : 'hover:bg-base-200/60'
                  ]"
                  @click="emit('select-feature', String(feature.id))"
                >
                  <label
                    class="label cursor-pointer justify-start gap-1 flex-1 min-w-0 py-0 pl-2"
                  >
                    <input
                      type="checkbox"
                      :checked="featureVisibility.get(feature.id) !== false"
                      @change="
                        $emit(
                          'toggle-feature',
                          feature.id,
                          ($event.target as HTMLInputElement).checked,
                        )
                      "
                      class="checkbox checkbox-xs checkbox-primary"
                    />
                    <span class="label-text text-sm truncate">
                      {{ feature.properties?.name || "! Nom manquant" }}
                    </span>
                  </label>
                  <div class="flex items-center gap-1">
                    <button
                      class="flex h-8 w-8 items-center justify-center"
                      @click="showEditFeatureDialog(feature)"
                      title="Modifier l'élément"
                    >
                      <PencilSquareIcon
                        class="w-5 h-5 text-gray-500 hover:text-gray-800"
                      />
                    </button>
                    <button
                      class="flex h-8 w-8 items-center justify-center"
                      @click="showDeleteFeatureDialog(feature)"
                      title="Supprimer l'élément"
                    >
                      <TrashIcon
                        class="w-5 h-5 text-red-500 hover:text-red-800"
                      />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </template>
          <div v-else class="flex text-sm opacity-60">
            Aucun élément à afficher
          </div>
        </div>
      </div>
    </div>

    <div class="px-3 py-1.5 flex flex-col gap-1.5">
      <div class="divider m-0"></div>
      <template v-if="!props.isDevTestCreation">
        <div class="flex gap-2 items-center">
          <button
            class="btn btn-primary btn-sm flex-1 font-bold"
            @click="$emit('add-map')"
          >
            <PlusIcon class="w-5 h-5" />
            Ajouter une carte
          </button>
        </div>

        <div class="flex gap-2 items-center">
          <button
            class="btn btn-outline btn-primary btn-sm flex-1 font-bold"
            @click="$emit('open-add-image-feature-dialog')"
          >
            <PlusIcon class="w-5 h-5" />
            Image
          </button>
          <button
            class="btn btn-outline btn-primary btn-sm flex-1 font-bold"
            @click="$emit('save-map')"
          >
            <FolderArrowDownIcon class="w-5 h-5" />
            Enregistrer
          </button>
        </div>
      </template>
      <div class="flex gap-2 items-center">
        <button
          @click="toggleAll(true)"
          class="btn btn-outline btn-primary btn-sm flex-1 w-full font-bold"
        >
          Tout afficher
        </button>
        <button
          @click="toggleAll(false)"
          class="btn btn-outline btn-primary btn-sm flex-1 w-full font-bold"
        >
          Tout masquer
        </button>
      </div>
    </div>
  </div>

  <dialog ref="editFeatureDialogRef" class="modal" v-if="featureToEdit">
    <div class="modal-box flex flex-col gap-4">
      <h3 class="text-lg font-bold truncate">
        Modification de {{ featureToEdit.properties.name }}
      </h3>
      <fieldset class="flex flex-col gap-2">
        <div class="flex flex-col gap-2">
          <label class="label">Nom de l'élément</label>
          <input
            v-model="editDraft.name"
            type="text"
            class="input"
            placeholder="Nom de l'élément"
            required
            @input="onNameInput"
          />
        </div>
        <div
          class="flex flex-col gap-2"
          v-if="featureToEdit.properties.labelText !== undefined || isTextElement"
        >
          <label class="label">Texte (Aperçu)</label>
          <input
            v-model="editDraft.labelText"
            type="text"
            class="input"
            :style="editTextStyle"
          />
        </div>
        <div
          class="flex flex-col gap-2"
          v-if="isTextElement"
        >
          <!-- Le label reste au-dessus -->
          
          <label class="label">Type de mot</label>
          <!-- Conteneur flex horizontal obligatoire ici -->
          <div class="flex flex-row items-center gap-2 w-full">
            <select
              v-model="editDraft.labelStyleSelection"
              data-testid="word-type-select"
              class="select select-bordered flex-1 min-w-0"
              @change="onLabelStyleSelectionChange"
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
              class="btn btn-outline border-base-300 rounded-lg shrink-0 hover:bg-base-200 hover:border-base-content/40 hover:text-base-content"
              data-testid="manage-custom-label-styles"
              @click="labelStyleManagerRef?.open()"
            >
              Personnaliser
            </button>
          </div>
        </div>

        <div
          class="flex items-center gap-2"
          v-if="!editDraft.customLabelStyleId"
        >
          <label class="label">Couleur:</label>
          <input
            v-model="editDraft.colorHex"
            type="color"
            class="h-9 w-8 cursor-pointer bg-base-100"
          />
        </div>

        <!-- Controls for shapes / zones / polygons / lines / legend (non-text elements) -->
        <div
          v-if="!isTextElement"
          class="flex flex-col gap-2"
        >
        <p
          class="text-xs text-base-content/60 italic"
        >
          Ces réglages suivants s'appliquent au formes (zones, polygones, lignes, légendes) qui représentent la ville sur la carte.
        </p>
          <div class="flex gap-2">
            <div class="flex flex-col gap-1 w-full">
              <label class="label py-0 text-sm">Opacité du fond</label>
              <input
                v-model="editDraft.fillOpacity"
                type="number"
                step="0.1"
                min="0"
                max="1"
                class="input"
              />
            </div>
            <div class="flex flex-col gap-1 w-full">
              <label class="label py-0 text-sm">Opacité du contour</label>
              <input
                v-model="editDraft.strokeOpacity"
                type="number"
                step="0.1"
                min="0"
                max="1"
                class="input"
              />
            </div>
          </div>
          <div class="flex flex-col gap-1 w-full">
            <label class="label py-0 text-sm">Épaisseur du contour</label>
            <input
              v-model="editDraft.strokeWidth"
              type="number"
              min="0"
              class="input"
            />
          </div>
          <div class="flex items-center gap-2 pt-1">
            <label class="label py-0 text-sm">Couleur du contour :</label>
            <input
              v-model="editDraft.strokeColorHex"
              type="color"
              class="h-9 w-8 cursor-pointer bg-base-100"
            />
          </div>
        </div>

          <p
            v-if="isEditingPoint"
            class="text-xs text-base-content/60 italic"
          >
            Ces réglages suivants s'appliquent au symbole du point qui représente la ville
            sur la carte.
          </p>
        <div
          v-if="isEditingPoint"
          class="grid grid-cols-2 gap-4 items-center"
        >
          <!-- Contrôles du point (alignés à gauche) -->
          <div class="flex flex-col gap-2">
            <div class="flex flex-col gap-1">
              <label class="label py-0 text-sm">Opacité du fond</label>
              <input
                v-model="editDraft.fillOpacity"
                type="number"
                class="input"
              />
            </div>
            <div class="flex flex-col gap-1">
              <label class="label py-0 text-sm">Opacité du contour du point</label>
              <input
                v-model="editDraft.strokeOpacity"
                type="number"
                class="input"
              />
            </div>
            <div class="flex flex-col gap-1">
              <label class="label py-0 text-sm">Épaisseur du contour du point</label>
              <input
                v-model="editDraft.strokeWidth"
                type="number"
                class="input"
              />
            </div>
            <div class="flex items-center gap-2 pt-1">
              <label class="label py-0 text-sm">Couleur du contour :</label>
              <input
                v-model="editDraft.strokeColorHex"
                type="color"
                class="h-9 w-8 cursor-pointer bg-base-100"
              />
            </div>
          </div>

          <!-- Aperçu du point (en bas à droite) -->
          <div
            class="flex flex-col items-center justify-center rounded-lg border border-base-300 bg-base-200/40 p-3 self-stretch"
            data-testid="point-preview-container"
          >
            <span class="text-xs text-base-content/60 font-medium mb-2">Aperçu du point</span>
            <div class="flex items-center justify-center flex-1 w-full min-h-[90px]">
              <svg width="70" height="70" viewBox="0 0 70 70" class="overflow-visible">
                <circle
                  cx="35"
                  cy="35"
                  r="16"
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

        <!-- Map assignment: choose which map(s) the element belongs to -->
        <div
          v-if="props.mapPeriods && props.mapPeriods.length > 0"
          class="flex flex-col gap-2 pt-2 border-t border-base-200"
          data-testid="map-assignment-section"
        >
          <label class="label py-0 font-medium text-sm">
            Cartes associées :
          </label>
          <div class="flex flex-col gap-1.5 max-h-40 overflow-y-auto border border-base-300 rounded-lg p-2 bg-base-100">
            <label
              v-for="period in props.mapPeriods"
              :key="period.id"
              class="flex items-center gap-2 cursor-pointer hover:bg-base-200/50 rounded px-1.5 py-1"
            >
              <input
                type="checkbox"
                :value="period.id"
                v-model="editDraft.selectedMapIds"
                class="checkbox checkbox-xs checkbox-primary"
                :data-testid="`map-checkbox-${period.id}`"
              />
              <span class="text-sm truncate">{{ period.title }}</span>
            </label>
          </div>
          <span class="text-xs text-base-content/60 italic">
            Si aucune carte n'est sélectionnée, l'élément reste dans « Éléments généraux ».
          </span>
        </div>
      </fieldset>
      <div class="modal-action">
        <button
          class="btn"
          :disabled="isEditing"
          @click="editFeatureDialogRef?.close()"
        >
          Annuler
        </button>
        <button
          class="btn btn-primary"
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

  <!-- Delete map confirmation dialog -->
  <dialog ref="deleteMapDialogRef" class="modal">
    <div class="modal-box">
      <h3 class="text-lg font-bold">Supprimer la carte</h3>
      <p class="py-4">
        Êtes-vous sûr de vouloir supprimer la carte
        <span class="font-semibold">{{ mapToDeleteTitle }}</span> ainsi que tous ses éléments ?
        Cette action est irréversible.
      </p>
      <div class="modal-action">
        <button
          class="btn"
          :disabled="isDeletingMap"
          @click="deleteMapDialogRef?.close()"
        >
          Annuler
        </button>
        <button
          class="btn btn-error"
          :disabled="isDeletingMap"
          @click="onDeleteMap"
        >
          <span
            v-if="isDeletingMap"
            class="loading loading-spinner loading-xs"
          ></span>
          <span v-else class="text-white">Supprimer</span>
        </button>
      </div>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button :disabled="isDeletingMap">close</button>
    </form>
  </dialog>

  <!-- Delete feature confirmation dialog -->
  <dialog ref="deleteFeatureDialogRef" class="modal">
    <div class="modal-box">
      <h3 class="text-lg font-bold">Supprimer l'élément</h3>
      <p class="py-4">
        Êtes-vous sûr de vouloir supprimer
        <span class="font-semibold">{{ featureToDeleteName }}</span> ?
        Cette action est irréversible.
      </p>
      <div class="modal-action">
        <button
          class="btn"
          :disabled="isDeletingFeature"
          @click="deleteFeatureDialogRef?.close()"
        >
          Annuler
        </button>
        <button
          class="btn btn-error"
          :disabled="isDeletingFeature"
          @click="onDeleteFeature"
        >
          <span
            v-if="isDeletingFeature"
            class="loading loading-spinner loading-xs"
          ></span>
          <span v-else class="text-white">Supprimer</span>
        </button>
      </div>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button :disabled="isDeletingFeature">close</button>
    </form>
  </dialog>

  <!-- Map selection dialog for text validation -->
  <dialog ref="selectMapValidationDialogRef" data-testid="select-map-validation-dialog" class="modal z-[2500]">
    <div class="modal-box max-w-sm">
      <h3 class="text-base font-bold text-gray-900 flex items-center gap-2">
        <DocumentCheckIcon class="w-5 h-5 text-indigo-600" />
        Choisir la carte à examiner
      </h3>
      <p class="text-xs text-gray-500 mt-1 mb-4">
        Sélectionnez la carte dont vous souhaitez examiner et valider les textes rejetés :
      </p>
      <div class="flex flex-col gap-2">
        <button
          v-for="group in validationFeaturesByMap"
          :key="group.id || 'general'"
          type="button"
          class="btn btn-outline btn-sm justify-between text-left normal-case border-gray-300 hover:border-indigo-500 hover:bg-indigo-50 hover:text-indigo-900"
          @click="confirmMapValidation(group.id)"
        >
          <span class="font-medium truncate">{{ group.title }}</span>
          <span class="text-xs text-gray-400 font-normal">Ouvrir →</span>
        </button>
      </div>
      <div class="modal-action mt-4">
        <button
          type="button"
          class="btn btn-sm btn-ghost"
          @click="selectMapValidationDialogRef?.close()"
        >
          Annuler
        </button>
      </div>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button>close</button>
    </form>
  </dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import type { Component } from "vue";
import type { CSSProperties } from "vue";
import {
  ChatBubbleLeftEllipsisIcon,
  ChevronDownIcon,
  DocumentCheckIcon,
  MapIcon,
  PencilSquareIcon,
  PhotoIcon,
  Square2StackIcon,
  TrashIcon,
} from "@heroicons/vue/24/outline";
import {
  type Feature,
  type FeatureVisibilityGroup,
  type FeatureVisibilityGroupType,
} from "../typescript/feature";
import type { MapPeriod } from "../typescript/map";
import type { CustomLabelStyle } from "../utils/labelPresentation";
import {
  getCustomStyleObject,
  getLabelStylePreviewCss,
  getWordTypeOptionLabel,
  getWordTypeOptionStyle,
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
  getWordTypePreviewStyle,
  type FeatureEditSubmitPayload,
} from "../utils/featureTextEditing";
import { rgbToHex } from "../utils/utils";
import {
  groupFeaturesByType,
  groupFeaturesByMap,
  type MapGroupItem,
} from "../utils/featureGrouping";
import { isUnrecognizedTextFeature } from "../utils/textValidation";
import { FolderArrowDownIcon, PlusIcon } from "@heroicons/vue/24/solid";
import { showAlert } from "../composables/useAlert";

const props = defineProps<{
  features: Feature[];
  featureVisibility: Map<string, boolean>;
  mapPeriods?: MapPeriod[];
  isDevTestCreation?: boolean;
  selectedFeatureId?: string | null;
  customLabelStyles?: CustomLabelStyle[];
}>();
const editFeatureDialogRef = ref<HTMLDialogElement | undefined>(undefined);
const featureToEdit = ref<Feature | undefined>(undefined);
const editDraft = ref<FeatureEditSubmitPayload>({
  name: "",
  wordType: "city",
});

const isTextElement = computed(() => isTextFeature(featureToEdit.value));

const editTextStyle = computed<CSSProperties>(() => {
  if (!isTextElement.value) return {};
  const selection = editDraft.value.labelStyleSelection ?? "";
  const style = selection.startsWith("custom:")
    ? availableCustomLabelStyles.value.find(
        (item: CustomLabelStyle) => item.id === selection.slice("custom:".length),
      ) ?? editDraft.value.customLabelStyle
    : editDraft.value.customLabelStyle;

  if (style) {
    return getLabelStylePreviewCss(style, { limitSize: true, maxPx: 18 });
  }
  const preview = getWordTypePreviewStyle(
    editDraft.value.wordType,
    editDraft.value.colorHex,
  );
  return {
    ...preview,
    fontSize: preview.fontSize
      ? `${Math.min(parseInt(String(preview.fontSize), 10) || 14, 18)}px`
      : undefined,
  };
});

const isEditingPoint = computed(() => {
  if (!featureToEdit.value) return false;
  if (isTextElement.value) {
    if (editDraft.value.customLabelStyle) return false;
    const entry = WORD_TYPE_TAXONOMY[editDraft.value.wordType as keyof typeof WORD_TYPE_TAXONOMY];
    return (entry?.mapElementType ?? getMapElementType(featureToEdit.value)) === "point";
  }
  return getMapElementType(featureToEdit.value) === "point";
});

const pointPreviewFillColor = computed(() => {
  return editDraft.value.colorHex || "#000000";
});

const pointPreviewFillOpacity = computed(() => {
  const val = editDraft.value.fillOpacity;
  if (val === undefined || val === null || (val as unknown) === "") return 0.5;
  const num = Number(val);
  if (Number.isNaN(num)) return 0.5;
  const normalized = num > 1 ? (num <= 10 ? num / 10 : num / 100) : num;
  return Math.max(0, Math.min(1, normalized));
});

const pointPreviewStrokeColor = computed(() => {
  return editDraft.value.strokeColorHex || editDraft.value.colorHex || "#000000";
});

const pointPreviewStrokeOpacity = computed(() => {
  const val = editDraft.value.strokeOpacity;
  if (val === undefined || val === null || (val as unknown) === "") return 1;
  const num = Number(val);
  if (Number.isNaN(num)) return 1;
  const normalized = num > 1 ? (num <= 10 ? num / 10 : num / 100) : num;
  return Math.max(0, Math.min(1, normalized));
});

const pointPreviewStrokeWidth = computed(() => {
  const val = editDraft.value.strokeWidth;
  if (val === undefined || val === null || (val as unknown) === "") return 1;
  const num = Number(val);
  return Number.isNaN(num) ? 1 : Math.max(0, num);
});

const deleteMapDialogRef = ref<HTMLDialogElement | undefined>(undefined);
const mapToDeleteId = ref<string | null>(null);
const mapToDeleteTitle = ref<string>("");
const isDeletingMap = ref(false);

const deleteFeatureDialogRef = ref<HTMLDialogElement | undefined>(undefined);
const featureToDeleteId = ref<string | null>(null);
const featureToDeleteName = ref<string>("");
const isDeletingFeature = ref(false);

const selectMapValidationDialogRef = ref<HTMLDialogElement | undefined>(undefined);

const activeGroupType = ref<FeatureVisibilityGroupType | undefined>(undefined);

const isEditing = ref(false);

const emit = defineEmits([
  "toggle-feature",
  "open-add-image-feature-dialog",
  "save-map",
  "delete-feature",
  "delete-map",
  "add-map",
  "update-feature",
  "validate-texts",
  "select-feature",
  "edit-map",
  "save-label-styles",
]);

const labelStyleManagerRef = ref<InstanceType<typeof CustomLabelStyleManager> | null>(null);

const localCustomStyles = ref<CustomLabelStyle[]>([]);

watch(
  () => props.customLabelStyles,
  (styles: CustomLabelStyle[] | undefined) => {
    if (styles) {
      localCustomStyles.value = [...styles];
    }
  },
  { immediate: true },
);

const availableCustomLabelStyles = computed(() => {
  return localCustomStyles.value.length > 0
    ? localCustomStyles.value
    : props.customLabelStyles ?? [];
});

function onSaveCustomLabelStyles(styles: CustomLabelStyle[]) {
  localCustomStyles.value = [...styles];
  if (editDraft.value.customLabelStyleId) {
    const updated = styles.find((s) => s.id === editDraft.value.customLabelStyleId);
    if (updated) {
      editDraft.value.customLabelStyle = updated;
      editDraft.value.colorHex = updated.color;
      if (updated.textTransform === "uppercase" && editDraft.value.labelText) {
        editDraft.value.labelText = editDraft.value.labelText.toUpperCase();
      }
    }
  }
  emit("save-label-styles", styles);
}

function onNameInput() {
  if (!isTextElement.value) return;
  const baseText = editDraft.value.name || "";
  if (editDraft.value.customLabelStyle) {
    editDraft.value.labelText =
      editDraft.value.customLabelStyle.textTransform === "uppercase"
        ? baseText.toUpperCase()
        : baseText;
  } else {
    editDraft.value.labelText = formatWordText(baseText, editDraft.value.wordType);
  }
}

function onLabelStyleSelectionChange() {
  const selection = editDraft.value.labelStyleSelection ?? "";
  if (selection.startsWith("custom:")) {
    const style = availableCustomLabelStyles.value.find(
      (item: CustomLabelStyle) => item.id === selection.slice("custom:".length),
    );
    if (!style) return;
    editDraft.value.customLabelStyleId = style.id;
    editDraft.value.customLabelStyle = style;
    editDraft.value.colorHex = style.color;
    const baseText = editDraft.value.labelText || editDraft.value.name || "";
    editDraft.value.labelText =
      style.textTransform === "uppercase" ? baseText.toUpperCase() : baseText;
    return;
  }
  editDraft.value.customLabelStyleId = undefined;
  editDraft.value.customLabelStyle = undefined;
  const wordType = selection;
  if (Object.prototype.hasOwnProperty.call(WORD_TYPE_TAXONOMY, wordType)) {
    editDraft.value.wordType = wordType as keyof typeof WORD_TYPE_TAXONOMY;
  }
  // Réinitialiser la couleur vers celle d'origine de l'élément (ou noir par défaut pour les labels)
  const originalColorHex = featureToEdit.value
    ? rgbToHex(featureToEdit.value.properties.colorRgb)
    : undefined;
  editDraft.value.colorHex = originalColorHex ?? "#000000";

  const baseText = editDraft.value.labelText || editDraft.value.name || "";
  editDraft.value.labelText = formatWordText(baseText, editDraft.value.wordType);
}

watch(
  () => props.selectedFeatureId,
  async (newId: string | null | undefined) => {
    if (!newId) return;

    const feature = props.features.find(
      (item: any) => String(item.id) === newId,
    );
    if (!feature) return;

    const group = featureGroups.value.find((item: FeatureVisibilityGroup) =>
      item.features.some((groupFeature: Feature) => String(groupFeature.id) === newId),
    );
    if (!group) return;

    activeGroupType.value = group.type;
    await nextTick();

    const mapGroup = groupFeaturesByMap(group.features, props.mapPeriods).find(
      (item: MapGroupItem) => String(item.id ?? "") === String(feature.mapId ?? ""),
    );
    if (mapGroup) {
      collapsedMaps.value[`${group.type}_${mapGroup.id ?? "general"}`] = false;
    }

    await nextTick();
    const el = Array.from(
      document.querySelectorAll<HTMLElement>("[data-feature-item-id]"),
    ).find((item) => item.dataset.featureItemId === newId);
    el?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  },
);

function openMapSelectionOrValidate() {
  if (validationFeaturesByMap.value.length > 1) {
    selectMapValidationDialogRef.value?.showModal?.();
  } else {
    emit("validate-texts", validationFeaturesByMap.value[0]?.id ?? null);
  }
}

function confirmMapValidation(mapId: string | null) {
  selectMapValidationDialogRef.value?.close?.();
  emit("validate-texts", mapId);
}

const collapsedMaps = ref<Record<string, boolean>>({});

function getMapCollapseKey(mapId: string | null): string {
  return `${activeGroup.value?.type || "default"}_${mapId ?? "general"}`;
}

function isMapCollapsed(mapId: string | null): boolean {
  return !!collapsedMaps.value[getMapCollapseKey(mapId)];
}

function toggleMapCollapse(mapId: string | null) {
  const key = getMapCollapseKey(mapId);
  collapsedMaps.value[key] = !collapsedMaps.value[key];
}

const groupIcons: Record<FeatureVisibilityGroupType, Component> = {
  point: ChatBubbleLeftEllipsisIcon,
  zone: MapIcon,
  shape: Square2StackIcon,
  drawing: PencilSquareIcon,
  image: PhotoIcon,
};

const featureGroups = computed(() => groupFeaturesByType(props.features));

const activeGroup = computed(() => {
  if (!activeGroupType.value) return featureGroups.value[0] ?? undefined;

  return (
    featureGroups.value.find((group: FeatureVisibilityGroup) => group.type === activeGroupType.value) ??
    featureGroups.value[0] ??
    undefined
  );
});

const isAnyVisible = computed(() => {
  if (!activeGroup.value || activeGroup.value.features.length === 0)
    return false;
  return activeGroup.value.features.some(
    (feature: Feature) => props.featureVisibility.get(feature.id) !== false,
  );
});

const featuresByMap = computed((): MapGroupItem[] => {
  if (!activeGroup.value) return [];
  return groupFeaturesByMap(activeGroup.value.features, props.mapPeriods);
});

const validationFeaturesByMap = computed(() =>
  groupFeaturesByMap(
    props.features.filter((feature: Feature) => isUnrecognizedTextFeature(feature)),
    props.mapPeriods,
  ),
);

function toggleMapGroup(mapId: string | null, visible: boolean) {
  const mapGroup = featuresByMap.value.find((g: MapGroupItem) => g.id === mapId);
  if (mapGroup) {
    mapGroup.features.forEach((feature: Feature) => {
      emit("toggle-feature", feature.id, visible);
    });
  }
}

function isMapGroupAnyVisible(mapId: string | null) {
  const mapGroup = featuresByMap.value.find((g: MapGroupItem) => g.id === mapId);
  if (!mapGroup || mapGroup.features.length === 0) return false;
  return mapGroup.features.some(
    (feature: Feature) => props.featureVisibility.get(feature.id) !== false,
  );
}

function toggleActiveGroup(visible: boolean) {
  if (!activeGroup.value) return;
  activeGroup.value.features.forEach((feature: Feature) => {
    emit("toggle-feature", feature.id, visible);
  });
}

watch(
  featureGroups,
  (groups: FeatureVisibilityGroup[]) => {
    if (groups.length === 0) {
      activeGroupType.value = undefined;
      return;
    }

    const hasActiveGroup = groups.some(
      (group: FeatureVisibilityGroup) => group.type === activeGroupType.value,
    );

    if (!hasActiveGroup) {
      activeGroupType.value = groups[0].type;
    }
  },
  { immediate: true },
);

function getGroupIcon(type: FeatureVisibilityGroupType): Component {
  return groupIcons[type];
}

async function showEditFeatureDialog(feature: Feature) {
  const state = prepareFeatureForEdit(feature);
  featureToEdit.value = state.feature;
  editDraft.value = state.draft;

  await nextTick();
  editFeatureDialogRef.value?.showModal();
}

async function onEditFeature() {
  if (!featureToEdit.value) return;
  isEditing.value = true;

  const updatedFeature = coerceEditedFeature(featureToEdit.value, {
    ...editDraft.value,
  });

  const allUpdated = createFeaturesForSelectedMaps(
    updatedFeature,
    editDraft.value.selectedMapIds,
  );

  featureToEdit.value = updatedFeature;

  emit(
    "update-feature",
    (allUpdated.length === 1 ? allUpdated[0] : allUpdated) as any,
    {
      onSuccess: () => {
        showAlert("success", "Élément mis à jour !");
      },
      onError: (message: string) => {
        showAlert("error", message);
      },
    },
  );

  isEditing.value = false;
  editFeatureDialogRef.value?.close();
}

function toggleAll(visible: boolean) {
  props.features.forEach((feature: Feature) => {
    emit("toggle-feature", feature.id, visible);
  });
}

function showDeleteMapDialog(mapId: string, mapTitle: string) {
  mapToDeleteId.value = mapId;
  mapToDeleteTitle.value = mapTitle;
  deleteMapDialogRef.value?.showModal();
}

async function onDeleteMap() {
  if (!mapToDeleteId.value) return;
  isDeletingMap.value = true;
  emit("delete-map", mapToDeleteId.value, {
    onSuccess: () => {
      showAlert("success", "Carte supprimée avec succès !");
      isDeletingMap.value = false;
      deleteMapDialogRef.value?.close();
    },
    onError: (message: string) => {
      showAlert("error", message || "Erreur lors de la suppression de la carte.");
      isDeletingMap.value = false;
    },
  });
}

function showDeleteFeatureDialog(feature: Feature) {
  featureToDeleteId.value = feature.id as string;
  featureToDeleteName.value = feature.properties?.name || "Élément sans nom";
  deleteFeatureDialogRef.value?.showModal();
}

async function onDeleteFeature() {
  if (!featureToDeleteId.value) return;
  isDeletingFeature.value = true;
  emit("delete-feature", featureToDeleteId.value, {
    onSuccess: () => {
      showAlert("success", "Élément supprimé avec succès !");
      isDeletingFeature.value = false;
      deleteFeatureDialogRef.value?.close();
    },
    onError: (message: string) => {
      showAlert("error", message || "Erreur lors de la suppression de l'élément.");
      isDeletingFeature.value = false;
    },
  });
}

defineExpose({
  showEditFeatureDialog,
  showDeleteFeatureDialog,
  isMapCollapsed,
  toggleMapCollapse,
});
</script>
