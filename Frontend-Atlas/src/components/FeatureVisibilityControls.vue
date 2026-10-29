<template>
  <div class="flex h-full min-h-0 flex-col">
    <div class="tabs tabs-boxed bg-base-200 gap-2 p-1.5">
      <button
        v-for="group in featureGroups"
        :key="group.type"
        type="button"
        role="tab"
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
          v-if="activeGroup?.type === 'point' && featuresByMap.length > 0"
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
                    <span class="text-sm font-semibold text-gray-700 truncate" :title="mapGroup.title">
                      {{ mapGroup.title }}
                    </span>
                  </label>
                </div>
                <div class="flex items-center gap-1 shrink-0" v-if="mapGroup.id !== null">
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
                  class="flex w-full flex-row items-center justify-between gap-2"
                >
                  <label
                    class="label cursor-pointer justify-start gap-2 flex-1 min-w-0 py-0 pl-6"
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
                      {{ feature.properties?.name || "Élément sans nom" }}
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
            v-model="featureToEditName"
            type="text"
            class="input"
            placeholder="Nom de l'élément"
            required
          />
        </div>
        <div
          class="flex flex-col gap-2"
          v-if="featureToEdit.properties.labelText !== undefined || isTextElement"
        >
          <label class="label">Texte</label>
          <input v-model="featureToEditLabelText" type="text" class="input" />
        </div>
        <div
          class="flex flex-col gap-2"
          v-if="isTextElement"
        >
          <label class="label">Type de mot</label>
          <select
            v-model="featureToEditWordType"
            data-testid="word-type-select"
            class="select select-bordered w-full"
            @change="onWordTypeChange"
          >
            <option
              v-for="(style, typeKey) in WORD_TYPE_STYLES"
              :key="typeKey"
              :value="typeKey"
            >
              {{ style.label }}
            </option>
          </select>
        </div>
        <div
          class="flex gap-2"
          v-if="
            !isEditingLabel &&
            (featureToEdit.properties.fillOpacity !== undefined ||
              featureToEdit.properties.strokeOpacity !== undefined)
          "
        >
          <div
            class="flex flex-col gap-2 w-full"
            v-if="featureToEdit.properties.fillOpacity !== undefined"
          >
            <label class="label">Opacité</label>
            <input v-model="featureToEditOpacity" type="number" class="input" />
          </div>
          <div
            class="flex flex-col gap-2 w-full"
            v-if="featureToEdit.properties.strokeOpacity !== undefined"
          >
            <label class="label">Opacité du contour</label>
            <input
              v-model="featureToEditStrokeOpacity"
              type="number"
              class="input"
            />
          </div>
        </div>
        <div
          class="flex flex-col gap-2 w-full"
          v-if="!isEditingLabel && featureToEdit.properties.strokeWidth !== undefined"
        >
          <label class="label">Épaisseur du contour</label>
          <input
            v-model="featureToEditStrokeWidth"
            type="number"
            class="input"
          />
        </div>
        <div
          class="flex flex-col gap-2"
          v-if="featureToEditColor || featureToEditStrokeColor"
        >
          <div
            class="flex items-center gap-2"
            v-if="featureToEdit.properties.colorRgb !== undefined || isEditingLabel || getMapElementType(featureToEdit) === 'point'"
          >
            <label class="label">Couleur :</label>
            <input
              v-model="featureToEditColor"
              type="color"
              class="h-9 w-8 cursor-pointer bg-base-100"
            />
          </div>
          <div
            class="flex items-center gap-2"
            v-if="featureToEdit.properties.strokeColor !== undefined && !isEditingLabel"
          >
            <label class="label">Couleur du contour :</label>
            <input
              v-model="featureToEditStrokeColor"
              type="color"
              class="h-9 w-8 cursor-pointer bg-base-100"
            />
          </div>
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
          v-for="group in featuresByMap"
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
import type {
  Feature,
  FeatureVisibilityGroup,
  FeatureVisibilityGroupType,
} from "../typescript/feature";
import type { MapPeriod } from "../typescript/map";
import { getMapElementType } from "../utils/featureHelpers";
import { WORD_TYPE_STYLES } from "../utils/mapLabelUtils";
import { FolderArrowDownIcon, PlusIcon } from "@heroicons/vue/24/solid";
import { showAlert } from "../composables/useAlert";
import { hexToRgb, rgbToHex } from "../utils/utils";

const props = defineProps<{
  features: Feature[];
  featureVisibility: Map<string, boolean>;
  mapPeriods?: MapPeriod[];
  isDevTestCreation?: boolean;
}>();
const editFeatureDialogRef = ref<HTMLDialogElement | undefined>(undefined);
const featureToEdit = ref<Feature | undefined>(undefined);
const featureToEditName = ref<string>("");
const featureToEditLabelText = ref<string | undefined>(undefined);
const featureToEditWordType = ref<string>("city");
const featureToEditColor = ref<string | undefined>(undefined);
const featureToEditStrokeColor = ref<string | undefined>(undefined);
const featureToEditOpacity = ref<number | undefined>(undefined);
const featureToEditStrokeOpacity = ref<number | undefined>(undefined);
const featureToEditStrokeWidth = ref<number | undefined>(undefined);

const isTextElement = computed(() => {
  if (!featureToEdit.value) return false;
  const type = getMapElementType(featureToEdit.value);
  return (
    type === "label" ||
    type === "point" ||
    featureToEdit.value.properties.labelText !== undefined ||
    featureToEdit.value.properties.rawType !== undefined
  );
});

const isEditingLabel = computed(() => {
  if (!featureToEdit.value) return false;
  if (isTextElement.value) {
    const style = WORD_TYPE_STYLES[featureToEditWordType.value];
    return (style?.mapElementType ?? getMapElementType(featureToEdit.value)) === "label";
  }
  return getMapElementType(featureToEdit.value) === "label";
});

function onWordTypeChange() {
  const style = WORD_TYPE_STYLES[featureToEditWordType.value];
  if (!style) return;

  if (featureToEditLabelText.value !== undefined) {
    featureToEditLabelText.value = style.transform(featureToEditLabelText.value);
  }
  if (featureToEditName.value) {
    featureToEditName.value = style.transform(featureToEditName.value);
  }
}

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
]);

function openMapSelectionOrValidate() {
  if (featuresByMap.value.length > 1) {
    selectMapValidationDialogRef.value?.showModal?.();
  } else {
    emit("validate-texts", featuresByMap.value[0]?.id ?? null);
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

const featureGroups = computed(() => {
  const groups: FeatureVisibilityGroup[] = [
    { type: "point", label: "Texte", features: [] as Feature[] },
    { type: "zone", label: "Zone(s)", features: [] as Feature[] },
    { type: "shape", label: "Forme(s)", features: [] as Feature[] },
    { type: "image", label: "Image(s)", features: [] as Feature[] },
    { type: "drawing", label: "Dessins", features: [] as Feature[] },
  ];

  props.features.forEach((feature: Feature) => {
    // Unrecognized OCR texts must not be listed on the page
    if (
      feature.properties?.isOcrText &&
      (feature.properties?.recognized === false ||
        (!feature.properties?.recognized && feature.properties?.show === false))
    ) {
      return;
    }

    const featureType = getMapElementType(feature);
    if (!featureType) return;

    const targetGroup = groups.find((currentGroup) => {
      if (featureType === "label" || featureType === "point") {
        return currentGroup.type === "point";
      }
      if (featureType === "polyline" || featureType === "arrow") {
        return currentGroup.type === "drawing";
      }
      return currentGroup.type === featureType;
    }) ?? groups.find((currentGroup) => currentGroup.type === "drawing");

    if (targetGroup) targetGroup.features.push(feature);
  });

  return groups;
});

const activeGroup = computed(() => {
  if (!activeGroupType.value) return featureGroups.value[0] ?? undefined;

  return (
    featureGroups.value.find((group) => group.type === activeGroupType.value) ??
    featureGroups.value[0] ??
    undefined
  );
});

const isAnyVisible = computed(() => {
  if (!activeGroup.value || activeGroup.value.features.length === 0)
    return false;
  return activeGroup.value.features.some(
    (feature) => props.featureVisibility.get(feature.id) !== false,
  );
});

const featuresByMap = computed(() => {
  if (!activeGroup.value) return [];

  const mapGroups = new Map<
    string | null,
    { id: string | null; title: string; startDate?: string | null; features: Feature[] }
  >();

  activeGroup.value.features.forEach((feature) => {
    const mapId = feature.mapId || null;
    if (!mapGroups.has(mapId)) {
      let title = "Éléments généraux";
      let startDate: string | null = null;
      if (mapId && props.mapPeriods) {
        const period = props.mapPeriods.find((p) => p.id === mapId);
        if (period) {
          title = period.title;
          startDate = period.startDate;
        }
      }
      mapGroups.set(mapId, { id: mapId, title, startDate, features: [] });
    }
    mapGroups.get(mapId)!.features.push(feature);
  });

  return Array.from(mapGroups.values())
    .map((group) => {
      group.features.sort((a, b) => {
        const nameA = a.properties?.name || "Élément sans nom";
        const nameB = b.properties?.name || "Élément sans nom";
        return nameA.localeCompare(nameB);
      });
      return group;
    })
    .sort((a, b) => {
      if (a.id === null) return -1;
      if (b.id === null) return 1;

      if (a.startDate && b.startDate) {
        if (a.startDate < b.startDate) return -1;
        if (a.startDate > b.startDate) return 1;
      } else if (a.startDate) {
        return -1;
      } else if (b.startDate) {
        return 1;
      }

      return a.title.localeCompare(b.title);
    });
});

function toggleMapGroup(mapId: string | null, visible: boolean) {
  const mapGroup = featuresByMap.value.find((g) => g.id === mapId);
  if (mapGroup) {
    mapGroup.features.forEach((feature) => {
      emit("toggle-feature", feature.id, visible);
    });
  }
}

function isMapGroupAnyVisible(mapId: string | null) {
  const mapGroup = featuresByMap.value.find((g) => g.id === mapId);
  if (!mapGroup || mapGroup.features.length === 0) return false;
  return mapGroup.features.some(
    (feature) => props.featureVisibility.get(feature.id) !== false,
  );
}

function toggleActiveGroup(visible: boolean) {
  if (!activeGroup.value) return;
  activeGroup.value.features.forEach((feature) => {
    emit("toggle-feature", feature.id, visible);
  });
}

watch(
  featureGroups,
  (groups) => {
    if (groups.length === 0) {
      activeGroupType.value = undefined;
      return;
    }

    const hasActiveGroup = groups.some(
      (group) => group.type === activeGroupType.value,
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
  featureToEdit.value = feature;
  featureToEditName.value = feature.properties.name;
  const elemType = getMapElementType(feature);
  const isText =
    elemType === "label" ||
    elemType === "point" ||
    feature.properties.labelText !== undefined ||
    feature.properties.rawType !== undefined;

  const rawType = (
    feature.properties.rawType ||
    feature.properties.type ||
    ""
  ).toLowerCase();

  if (rawType && WORD_TYPE_STYLES[rawType]) {
    featureToEditWordType.value = rawType;
  } else if (elemType === "label") {
    featureToEditWordType.value = "province";
  } else {
    featureToEditWordType.value = "city";
  }

  featureToEditLabelText.value =
    feature.properties.labelText ?? (isText ? feature.properties.name : undefined);

  featureToEditColor.value =
    rgbToHex(feature.properties.colorRgb) ??
    (elemType === "label" || elemType === "point" ? "#000000" : undefined);
  featureToEditStrokeColor.value = rgbToHex(feature.properties.strokeColor);
  featureToEditOpacity.value = feature.properties.fillOpacity;
  featureToEditStrokeOpacity.value = feature.properties.strokeOpacity;
  featureToEditStrokeWidth.value = feature.properties.strokeWidth;

  await nextTick();
  editFeatureDialogRef.value?.showModal();
}

async function onEditFeature() {
  if (!featureToEdit.value) return;
  isEditing.value = true;
  const isText = isTextElement.value;
  const wordStyle = isText ? WORD_TYPE_STYLES[featureToEditWordType.value] : null;

  const currentMapElementType = getMapElementType(featureToEdit.value);
  const newMapElementType = wordStyle ? wordStyle.mapElementType : currentMapElementType;
  const newSizePx = wordStyle ? wordStyle.sizePx : featureToEdit.value.properties.sizePx;
  const newFontStyle = wordStyle ? wordStyle.fontStyle : featureToEdit.value.properties.fontStyle;

  const isLabel = newMapElementType === "label";

  const finalName = wordStyle ? wordStyle.transform(featureToEditName.value) : featureToEditName.value;
  const rawLabelText = featureToEditLabelText.value ?? (isText ? featureToEditName.value : undefined);
  const finalLabelText = wordStyle && rawLabelText ? wordStyle.transform(rawLabelText) : rawLabelText;

  const updatedFeature: Feature = {
    ...featureToEdit.value,
    name: finalName,
    properties: {
      ...featureToEdit.value.properties,
      name: finalName,
      labelText: finalLabelText,
      rawType: wordStyle ? featureToEditWordType.value : featureToEdit.value.properties.rawType,
      type: wordStyle ? featureToEditWordType.value : featureToEdit.value.properties.type,
      mapElementType: newMapElementType ?? featureToEdit.value.properties.mapElementType,
      sizePx: newSizePx,
      fontStyle: newFontStyle,
      colorRgb: hexToRgb(featureToEditColor.value),
      strokeColor: isLabel ? undefined : hexToRgb(featureToEditStrokeColor.value),
      fillOpacity: isLabel ? undefined : featureToEditOpacity.value,
      strokeOpacity: isLabel ? undefined : featureToEditStrokeOpacity.value,
      strokeWidth: isLabel ? undefined : featureToEditStrokeWidth.value,
    },
  };

  featureToEdit.value = updatedFeature;

  emit("update-feature", updatedFeature, {
    onSuccess: () => {
      showAlert("success", "Élément mis à jour !");
    },
    onError: (message: string) => {
      showAlert("error", message);
    },
  });

  isEditing.value = false;
  editFeatureDialogRef.value?.close();
}

function toggleAll(visible: boolean) {
  props.features.forEach((feature) => {
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
  isMapCollapsed,
  toggleMapCollapse,
});
</script>
