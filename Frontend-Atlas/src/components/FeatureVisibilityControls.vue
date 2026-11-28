<template>
  <div class="flex h-full min-h-0 flex-col overflow-auto" data-testid="feature-visibility-controls">
    <div
      v-if="collapsed"
      class="flex h-full w-full flex-col items-center gap-2 py-2 px-1 bg-white"
      data-testid="sidebar-collapsed-rail"
    >
      <button
        type="button"
        class="w-9 h-9 bg-primary-600 rounded-lg flex items-center justify-center shrink-0 hover:bg-primary-700 transition-colors"
        data-testid="toggle-sidebar-button"
        title="Afficher le panneau"
        aria-label="Afficher le panneau"
        @click="emit('toggle-collapsed')"
      >
        <MapIcon class="h-5 w-5 text-white" />
      </button>
      <div class="w-8 h-px bg-base-300 shrink-0" />
      <button
        v-for="group in featureGroups"
        :key="group.type"
        type="button"
        class="w-9 h-9 rounded-lg flex items-center justify-center hover:bg-base-200 transition-colors"
        :class="activeGroup?.type === group.type ? 'bg-primary/10 ring-1 ring-primary/40' : ''"
        :title="group.label"
        :data-testid="`feature-tab-${group.type}`"
        @click="onCollapsedGroupClick(group.type)"
      >
        <component
          :is="getGroupIcon(group.type)"
          class="h-5 w-5 text-primary-500"
        />
      </button>
    </div>

    <template v-else>
    <div class="flex items-center gap-1 shrink-0 bg-base-200 rounded-lg p-1.5">
      <div class="tabs tabs-boxed bg-transparent gap-2 p-0 overflow-x-auto flex-nowrap flex-1 min-w-0">
      <button
        v-for="group in featureGroups"
        :key="group.type"
        type="button"
        role="tab"
        :aria-selected="activeGroup?.type === group.type"
        :data-testid="`feature-tab-${group.type}`"
        class="tab flex-1 p-0 min-w-8"
        :title="`${group.label}`"
        @click="activeGroupType = group.type"
      >
        <component
          :is="getGroupIcon(group.type)"
          class="h-5 w-5 text-primary-500"
        />
      </button>
    </div>
      <button
        type="button"
        class="btn btn-ghost btn-sm btn-square shrink-0 bg-transparent hover:bg-base-300"
        data-testid="toggle-sidebar-button"
        title="Réduire le panneau"
        aria-label="Réduire le panneau"
        @click="emit('toggle-collapsed')"
      >
        <ChevronLeftIcon class="w-5 h-5" />
      </button>
    </div>

    <!-- Element list with visibility controls -->
    <div class="px-1 flex flex-1 flex-col min-h-0 min-w-0">
      <div
        class="card flex flex-1 flex-col gap-4 min-h-0 overflow-auto scroll-stable"
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
              {{ activeGroup?.label }}
            </span>
          </label>
        </div>
        <div class="divider m-0 h-0"></div>

        <!-- Validate extracted texts button -->
        <div
          v-if="activeGroup?.type === 'point' && validationFeaturesByMap.length > 0"
          class="flex flex-col gap-2 p-2 bg-primary-50 border border-primary-200 rounded-lg"
        >
          <span class="text-xs font-bold flex items-center gap-1.5">
            <DocumentCheckIcon class="w-4 h-4 text-primary-600" />
            Textes non reconnus
          </span>
          <button
            type="button"
            class="btn btn-primary btn-xs w-full"
            @click="openMapSelectionOrValidate"
          >
            Examiner les rejets
          </button>
        </div>

        <div class="flex flex-col gap-2">
          <template v-if="featuresByMap.length > 0">
            <div
              v-for="mapGroup in featuresByMap"
              :key="mapGroup.id ?? 'general'"
              class="flex flex-col gap-2"
            >
              <div
                class="flex items-center justify-between rounded-lg px-2 py-1 bg-gray-100 hover:bg-gray-200/80 border border-gray-300 group transition-colors cursor-pointer"
                :class="{ 'ring-2 ring-primary border-primary bg-primary/5': props.selectedMapId && String(mapGroup.id) === String(props.selectedMapId) }"
                @click="mapGroup.id !== null && emit('select-map', mapGroup.id)"
                @dblclick="mapGroup.id !== null && emit('edit-map', mapGroup.id)"
              >
                <div class="flex items-center gap-1.5 flex-1 min-w-0">
                  <button
                    type="button"
                    class="flex h-6 w-6 shrink-0 items-center justify-center rounded text-gray-500 hover:text-gray-800 hover:bg-gray-300/60 transition-colors focus:outline-none"
                    @click.stop="toggleMapCollapse(mapGroup.id)"
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
                    @click.stop
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
                      class="text-sm font-bold text-gray-900 truncate text-left hover:text-primary flex-1 min-w-0"
                      :title="`${mapGroup.title} (clic pour sélectionner, double-clic pour modifier)`"
                      :data-testid="`map-title-btn-${mapGroup.id}`"
                      @click.stop="emit('select-map', mapGroup.id)"
                      @dblclick.stop="emit('edit-map', mapGroup.id)"
                    >
                      {{ mapGroup.title }}
                    </button>
                    <span
                      v-else
                      class="text-sm font-bold text-gray-900 truncate flex-1 min-w-0"
                      title="Éléments qui appartiennent à toutes les cartes"
                    >
                      {{ mapGroup.title }}
                    </span>
                  </label>
                </div>
                <div class="flex items-center gap-0.5 shrink-0 ml-auto -mr-1.5" v-if="mapGroup.id !== null">
                  <button
                    type="button"
                    class="icon-action-btn-sm"
                    :aria-label="`Modifier le nom et la période de ${mapGroup.title}`"
                    title="Modifier le nom et la période"
                    @click.stop="emit('edit-map', mapGroup.id)"
                  >
                    <PencilSquareIcon class="w-3.5 h-3.5 text-gray-500 hover:text-primary" />
                  </button>
                  <button
                    type="button"
                    class="icon-action-btn-sm"
                    @click="showDeleteMapDialog(mapGroup.id, mapGroup.title)"
                    title="Supprimer la carte"
                    aria-label="Supprimer la carte"
                  >
                    <TrashIcon class="w-3.5 h-3.5 text-error hover:text-error/80" />
                  </button>
                </div>
              </div>
              <div v-if="!isMapCollapsed(mapGroup.id)" class="flex flex-col gap-1 pl-6">
                <div
                  v-for="feature in mapGroup.features"
                  :key="feature.id"
                  :data-feature-item-id="String(feature.id)"
                  class="flex w-full flex-row items-center justify-between gap-1 rounded-lg px-2 py-1 transition-all cursor-pointer select-none"
                  :class="[
                    isFeatureSelected(feature.id)
                      ? 'border-2 border-primary-700 ring-1 ring-primary-700/60 bg-primary-100/60 dark:bg-primary-950/40 font-semibold shadow-sm'
                      : 'border-2 border-transparent hover:bg-base-200/60'
                  ]"
                  @click="onFeatureItemClick(feature, $event)"
                  @dblclick.prevent.stop="onFeatureItemDblClick(feature, $event)"
                >
                  <div class="flex items-center gap-1.5 flex-1 min-w-0 py-0 pl-0">
                    <span
                      v-if="isFeatureNameMissing(feature)"
                      class="text-error font-extrabold text-sm leading-none shrink-0"
                      title="Nom manquant"
                    >
                      !
                    </span>
                    <input
                      type="checkbox"
                      :checked="featureVisibility.get(feature.id) !== false"
                      @click.stop
                      @change="onToggleFeatureCheckbox(feature.id, $event)"
                      class="checkbox checkbox-xs checkbox-primary shrink-0"
                    />
                    <span
                      class="label-text text-sm truncate flex-1 min-w-0 select-none"
                      :class="{ 'text-error font-medium': isFeatureNameMissing(feature) }"
                      :style="getFeatureNameStyle(feature)"
                      :title="getFeatureDisplayName(feature)"
                    >
                      {{ getFeatureDisplayName(feature) }}
                    </span>
                    <span
                      v-if="getFeatureMapIds(feature).length > 1"
                      class="badge badge-info badge-outline badge-xs font-semibold shrink-0 ml-auto"
                      :title="`Partagé sur ${getFeatureMapIds(feature).length} cartes`"
                    >
                      {{ getFeatureMapIds(feature).length }} cartes
                    </span>
                  </div>
                  <div class="flex items-center gap-0.5 shrink-0 ml-auto -mr-1">
                    <button
                      type="button"
                      class="icon-action-btn-sm"
                      @click.stop="showEditFeatureDialog(feature)"
                      title="Modifier l'élément"
                      aria-label="Modifier l'élément"
                    >
                      <PencilSquareIcon
                        class="w-3.5 h-3.5 text-gray-500 hover:text-gray-800"
                      />
                    </button>
                    <button
                      type="button"
                      class="icon-action-btn-sm"
                      @click.stop="showDeleteFeatureDialog(feature)"
                      title="Supprimer l'élément"
                      aria-label="Supprimer l'élément"
                    >
                      <TrashIcon
                        class="w-3.5 h-3.5 text-red-500 hover:text-red-800"
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
        <div class="flex flex-col gap-1.5">
          <button
            class="btn btn-primary btn-sm w-full font-bold"
            @click="emit('add-map')"
          >
            <PlusIcon class="w-5 h-5" />
            Ajouter une carte
          </button>
          <button
            class="btn btn-outline btn-primary btn-sm w-full font-bold"
            data-testid="sidebar-duplicate-map-button"
            title="Dupliquer entièrement une carte"
            @click="emit('duplicate-map')"
          >
            <DocumentDuplicateIcon class="w-4 h-4" />
            Dupliquer une carte
          </button>
        </div>

        <div class="flex gap-2 items-center">
          <button
            class="btn btn-outline btn-primary btn-sm flex-1 font-bold"
            @click="emit('open-add-image-feature-dialog')"
          >
            <PlusIcon class="w-5 h-5" />
            Image
          </button>
          <button
            class="btn btn-outline btn-primary btn-sm flex-1 font-bold"
            @click="emit('save-map')"
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
    </template>
  </div>

  <!-- Standardized element edit modal -->
  <EditFeatureDialog
    ref="editFeatureDialogRef"
    :map-periods="props.mapPeriods"
    :custom-label-styles="props.customLabelStyles"
    @update-feature="(payload, callbacks) => emit('update-feature', payload, callbacks)"
    @save-custom-label-styles="(styles) => emit('save-label-styles', styles)"
  />

  <!-- Delete map confirmation dialog -->
  <ConfirmDialog
    v-if="isDeleteMapModalOpen"
    title="Supprimer la carte"
    :message="`Êtes-vous sûr de vouloir supprimer la carte ${mapToDeleteTitle} ainsi que tous ses éléments ? Cette action est irréversible.`"
    confirm-label="Supprimer"
    cancel-label="Annuler"
    danger
    @confirm="onDeleteMap"
    @cancel="isDeleteMapModalOpen = false"
  />

  <!-- Delete feature confirmation dialog -->
  <DeleteFeatureDialog
    ref="deleteFeatureDialogRef"
    :features="props.features"
    :map-periods="props.mapPeriods"
    :active-map-id="props.activeMapId"
    :is-deleting="isDeletingFeature"
    @delete-features="onDeleteFeaturesConfirmed"
    @remove-from-maps="onRemoveFromMapsConfirmed"
  />

  <!-- Map selection dialog for text validation -->
  <dialog ref="selectMapValidationDialogRef" data-testid="select-map-validation-dialog" class="modal z-[2500]">
    <div class="modal-box w-11/12 max-w-lg md:max-w-xl relative">
      <button
        type="button"
        class="btn btn-sm btn-circle btn-ghost absolute right-4 top-4 z-10"
        @click="selectMapValidationDialogRef?.close()"
      >
        ✕
      </button>

      <h3 class="text-xl font-bold flex items-center gap-2 pr-10">
        <DocumentCheckIcon class="w-5 h-5 text-primary-600" />
        Choisir la carte
      </h3>
      <p class="text-sm text-base-content opacity-70 mt-1 mb-4">
        Sélectionnez la carte dont vous souhaitez examiner et valider les textes rejetés 
      </p>
      <div class="flex flex-col gap-2.5 max-h-80 overflow-y-auto pr-1">
        <button
          v-for="group in validationFeaturesByMap"
          :key="group.id ?? 'general'"
          type="button"
          class="btn btn-outline h-auto py-2.5 px-4 justify-between items-center text-left gap-3 w-full group hover:border-primary transition-colors"
          :title="group.title"
          @click="confirmMapValidation(group.id)"
        >
          <span class="font-medium truncate flex-1 min-w-0" :title="group.title">
            {{ group.title }}
          </span>
          <span class="text-xs font-semibold opacity-60 group-hover:opacity-100 group-hover:text-primary shrink-0 whitespace-nowrap flex items-center gap-1">
            Ouvrir →
          </span>
        </button>
      </div>
      <div class="modal-action mt-6 flex justify-end">
        <button
          type="button"
          class="modal-secondary-btn w-32"
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
import type { Component, CSSProperties } from "vue";
import {
  ChatBubbleLeftEllipsisIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
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
import { getLabelPresentation } from "../utils/labelPresentation";
import { isTextFeature } from "../utils/wordStyles";
import EditFeatureDialog from "./EditFeatureDialog.vue";
import ConfirmDialog from "./ConfirmDialog.vue";
import DeleteFeatureDialog from "./DeleteFeatureDialog.vue";
import { getFeatureMapId, getFeatureMapIds } from "../utils/featureHelpers";
import {
  groupFeaturesByType,
  groupFeaturesByMap,
  type MapGroupItem,
} from "../utils/featureGrouping";
import { isUnrecognizedTextFeature } from "../utils/textValidation";
import { FolderArrowDownIcon, PlusIcon, DocumentDuplicateIcon } from "@heroicons/vue/24/solid";
import { createFeatureDoubleClickHandler } from "../utils/featureInteraction";
import { applySelectionModifier } from "../utils/selectionUtils";
import { createActionCallbacks } from "../utils/actionCallbacks";

const props = defineProps<{
  collapsed?: boolean;
  features: Feature[];
  featureVisibility: Map<string, boolean>;
  mapPeriods?: MapPeriod[];
  isDevTestCreation?: boolean;
  selectedFeatureId?: string | null;
  multiSelectedFeatureIds?: string[];
  customLabelStyles?: CustomLabelStyle[];
  activeMapId?: string | null;
  selectedMapId?: string | null;
}>();

const emit = defineEmits([
  "toggle-collapsed",
  "toggle-feature",
  "open-add-image-feature-dialog",
  "save-map",
  "delete-feature",
  "delete-map",
  "add-map",
  "duplicate-map",
  "update-feature",
  "validate-texts",
  "select-feature",
  "select-features",
  "select-map",
  "edit-map",
  "save-label-styles",
]);

const editFeatureDialogRef = ref<InstanceType<typeof EditFeatureDialog> | null>(null);
const isDeleteMapModalOpen = ref(false);
const mapToDeleteId = ref<string | null>(null);
const mapToDeleteTitle = ref<string>("");
const isDeletingMap = ref(false);
const isDeletingFeature = ref(false);
const selectMapValidationDialogRef = ref<HTMLDialogElement | undefined>(undefined);
const activeGroupType = ref<FeatureVisibilityGroupType | undefined>(undefined);

function isFeatureNameMissing(feature: Feature): boolean {
  const name = (
    feature.properties?.name?.trim() ||
    feature.properties?.labelText?.trim() ||
    feature.name?.trim() ||
    ""
  ).toLowerCase();
  return !name || name === "nom manquant" || name === "! nom manquant";
}

function getFeatureDisplayName(feature: Feature): string {
  const name =
    feature.properties?.name?.trim() ||
    feature.properties?.labelText?.trim() ||
    feature.name?.trim();
  if (!name || isFeatureNameMissing(feature)) {
    return "Nom manquant";
  }
  return name;
}

function getFeatureNameStyle(feature: Feature): CSSProperties {
  if (!isTextFeature(feature) || isFeatureNameMissing(feature)) return {};
  const presentation = getLabelPresentation(feature);
  return {
    color: presentation.colorCss,
    fontStyle: presentation.fontStyle,
    fontWeight: presentation.fontWeight,
    textTransform: presentation.textTransform,
  };
}

function onToggleFeatureCheckbox(featureId: string, event: Event) {
  const target = event.target as HTMLInputElement | null;
  if (!target) return;
  emit("toggle-feature", featureId, target.checked);
}



watch(
  () => props.selectedFeatureId,
  async (newId: string | null | undefined) => {
    if (!newId) return;

    const feature = props.features.find(
      (item: Feature) => String(item.id) === newId,
    );
    if (!feature) return;

    const group = featureGroups.value.find((item: FeatureVisibilityGroup) =>
      item.features.some((groupFeature: Feature) => String(groupFeature.id) === newId),
    );
    if (!group) return;

    activeGroupType.value = group.type;
    await nextTick();

    const featMapId = getFeatureMapId(feature);
    const mapGroup = groupFeaturesByMap(group.features, props.mapPeriods).find(
      (item: MapGroupItem) => String(item.id ?? "") === String(featMapId ?? ""),
    );
    if (mapGroup) {
      collapsedMaps.value[`${group.type}_${mapGroup.id ?? "general"}`] = false;
    }

    await nextTick();
    requestAnimationFrame(() => {
      const el = Array.from(
        document.querySelectorAll<HTMLElement>("[data-feature-item-id]"),
      ).find((item: HTMLElement) => String(item.dataset.featureItemId) === String(newId));
      el?.scrollIntoView?.({ block: "center", behavior: "smooth" });
    });
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

function onCollapsedGroupClick(type: FeatureVisibilityGroupType) {
  activeGroupType.value = type;
  emit("toggle-collapsed");
}

function getGroupIcon(type: FeatureVisibilityGroupType): Component {
  return groupIcons[type];
}

function showEditFeatureDialog(feature: Feature) {
  editFeatureDialogRef.value?.open(feature);
}

const lastSelectedAnchorId = ref<string | null>(props.selectedFeatureId ?? null);

watch(
  () => props.selectedFeatureId,
  (newId: string | null | undefined) => {
    if (newId) lastSelectedAnchorId.value = String(newId);
  },
);

const visibleListFeatureIds = computed(() =>
  featuresByMap.value.flatMap((g: MapGroupItem) => g.features).map((f: Feature) => String(f.id)),
);

function isFeatureSelected(id: string | number | undefined): boolean {
  if (id == null) return false;
  const strId = String(id);
  if (props.selectedFeatureId && String(props.selectedFeatureId) === strId) return true;
  if (
    props.multiSelectedFeatureIds &&
    props.multiSelectedFeatureIds.some((i: string) => String(i) === strId)
  )
    return true;
  return false;
}

const { handleClick: onFeatureItemClick, handleDblClick: onFeatureItemDblClick } =
  createFeatureDoubleClickHandler<Feature>({
    onSelect: (feature: Feature, event?: unknown) => {
      if (feature.id == null) return;
      const featureId = String(feature.id);
      const mouseEv = event as MouseEvent | undefined;
      const isCtrl = Boolean(mouseEv?.ctrlKey || mouseEv?.metaKey);
      const isShift = Boolean(mouseEv?.shiftKey);

      if (isCtrl || isShift) {
        const result = applySelectionModifier(featureId, isCtrl, isShift, {
          selectedId: props.selectedFeatureId,
          multiSelectedIds: props.multiSelectedFeatureIds ?? [],
          lastAnchorId: lastSelectedAnchorId.value,
          orderedIds: visibleListFeatureIds.value,
        });
        lastSelectedAnchorId.value = result.newAnchorId;
        emit("select-feature", result.selectedId);
        emit("select-features", result.multiSelectedIds);
        return;
      }

      lastSelectedAnchorId.value = featureId;
      emit("select-features", []);
      emit("select-feature", featureId);
    },
    onEdit: (feature: Feature) => {
      if (feature.id != null) {
        lastSelectedAnchorId.value = String(feature.id);
        emit("select-feature", String(feature.id));
      }
      showEditFeatureDialog(feature);
    },
    getId: (feature: Feature) => feature.id,
  });

function toggleAll(visible: boolean) {
  props.features.forEach((feature: Feature) => {
    emit("toggle-feature", feature.id, visible);
  });
}

function showDeleteMapDialog(mapId: string, mapTitle: string) {
  mapToDeleteId.value = mapId;
  mapToDeleteTitle.value = mapTitle;
  isDeleteMapModalOpen.value = true;
}

async function onDeleteMap() {
  if (!mapToDeleteId.value) return;
  isDeletingMap.value = true;
  emit(
    "delete-map",
    mapToDeleteId.value,
    createActionCallbacks({
      successMessage: "Carte supprimée avec succès !",
      errorFallback: "Erreur lors de la suppression de la carte.",
      loadingRef: isDeletingMap,
      onSuccess: () => {
        isDeleteMapModalOpen.value = false;
      },
    }),
  );
}

const deleteFeatureDialogRef = ref<InstanceType<typeof DeleteFeatureDialog> | null>(null);

function showDeleteFeatureDialog(featureOrFeatures: Feature | Feature[]) {
  if (
    !Array.isArray(featureOrFeatures) &&
    props.multiSelectedFeatureIds &&
    props.multiSelectedFeatureIds.length > 1 &&
    props.multiSelectedFeatureIds.includes(String(featureOrFeatures.id))
  ) {
    const multiFeatures = props.features.filter((f: Feature) =>
      props.multiSelectedFeatureIds!.includes(String(f.id)),
    );
    deleteFeatureDialogRef.value?.open(multiFeatures.length > 0 ? multiFeatures : featureOrFeatures);
    return;
  }
  deleteFeatureDialogRef.value?.open(featureOrFeatures);
}

async function onDeleteFeaturesConfirmed(idsToDelete: string[]) {
  if (idsToDelete.length === 0) return;
  isDeletingFeature.value = true;
  emit(
    "delete-feature",
    idsToDelete.length === 1 ? idsToDelete[0] : idsToDelete,
    createActionCallbacks({
      successMessage: () =>
        idsToDelete.length > 1
          ? `${idsToDelete.length} éléments supprimés avec succès !`
          : "Élément supprimé avec succès !",
      errorFallback: "Erreur lors de la suppression de l'élément.",
      loadingRef: isDeletingFeature,
      dialogRef: deleteFeatureDialogRef,
    }),
  );
}

async function onRemoveFromMapsConfirmed(payload: { featureIds: string[]; mapIdsToRemove: string[] }) {
  const { featureIds, mapIdsToRemove } = payload;
  if (featureIds.length === 0 || mapIdsToRemove.length === 0) return;

  const removeSet = new Set(mapIdsToRemove.map(String));
  const feats = props.features.filter((f: Feature) => featureIds.includes(String(f.id)));
  if (feats.length === 0) return;

  isDeletingFeature.value = true;
  const updatedList: Feature[] = [];

  for (const feat of feats) {
    const existingIds = getFeatureMapIds(feat);
    const nextMapIds = existingIds.filter((id: string) => !removeSet.has(String(id)));
    const newMainMapId = nextMapIds.length > 0 ? nextMapIds[0] : null;

    const updated: Feature = {
      ...feat,
      mapId: newMainMapId,
      mapIds: nextMapIds,
      map_id: newMainMapId,
      properties: {
        ...feat.properties,
        mapId: newMainMapId,
        mapIds: nextMapIds,
        map_id: newMainMapId,
        mapTitle: newMainMapId === null ? null : (feat.properties?.mapTitle ?? null),
      },
    };
    updatedList.push(updated);
  }

  emit(
    "update-feature",
    (updatedList.length === 1 ? updatedList[0] : updatedList) as any,
    createActionCallbacks({
      successMessage: () =>
        updatedList.length > 1
          ? `${updatedList.length} éléments retirés avec succès !`
          : "Élément retiré de la carte avec succès !",
      errorFallback: "Erreur lors du retrait de l'élément.",
      loadingRef: isDeletingFeature,
      dialogRef: deleteFeatureDialogRef,
    }),
  );
}

defineExpose({
  showEditFeatureDialog,
  showDeleteFeatureDialog,
  isMapCollapsed,
  toggleMapCollapse,
});
</script>