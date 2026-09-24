<template>
  <div class="space-y-2">
    <h2 class="text-sm font-semibold mb-1">Créer une nouvelle zone</h2>

    <div v-if="!isCreateMode" class="space-y-2 text-xs text-base-content/70">
      <p>
        Active le mode création, puis dessine un ou plusieurs traits à la
        souris. Quand le contour revient près de son point de départ, tu
        pourras enregistrer la zone.
      </p>
      <button
        class="btn btn-xs btn-primary w-full"
        type="button"
        @click="$emit('start-create')"
      >
        Activer le mode création
      </button>
    </div>

    <div v-else class="space-y-2 text-xs text-base-content/70">
      <p>
        Dessine un ou plusieurs traits sur la carte. Les extrémités des
        traits se collent automatiquement si elles sont proches.
      </p>

      <label class="flex flex-col gap-1 text-xs" :for="zoneNameInputId">
        <span>Nom de la zone</span>
        <input
          :id="zoneNameInputId"
          :value="zoneName"
          type="text"
          class="input input-xs input-bordered w-full"
          placeholder="Nom de la nouvelle zone"
          @input="onNameInput"
        />
      </label>

      <div class="space-y-2">
        <button
          class="btn btn-xs btn-outline w-full"
          type="button"
          @click="$emit('undo-last-stroke')"
        >
          Annuler le dernier trait
        </button>

        <div class="form-control">
          <label class="label cursor-pointer justify-between gap-2">
            <span class="label-text text-xs">Mode frontière (côtes)</span>
            <input
              type="checkbox"
              class="toggle toggle-xs toggle-accent"
              :checked="isFrontierMode"
              @change="$emit('toggle-frontier')"
            />
          </label>
        </div>

        <div class="form-control">
          <div class="flex items-center gap-2">
            <span class="label-text min-w-0 flex-1 text-xs">Frontières géopolitiques</span>
            <input
              type="checkbox"
              class="toggle toggle-xs toggle-secondary"
              :checked="isGeoBorderMode"
              @change="$emit('toggle-geo-border')"
            />
              <details ref="geoBorderDropdown" class="dropdown dropdown-end w-40">
              <summary
                class="btn btn-xs btn-outline w-full justify-between"
                :class="{ 'btn-disabled': !isGeoBorderMode }"
                :aria-disabled="!isGeoBorderMode"
              >
                <span class="truncate">{{ selectedBorderSummary }}</span>
                <span aria-hidden="true">⌄</span>
              </summary>
              <div class="dropdown-content z-[2] mt-1 max-h-64 w-56 overflow-y-auto rounded-box bg-base-100 p-2 shadow-lg">
                <label class="flex w-full cursor-pointer items-center gap-2 border-b border-base-300 py-1">
                  <input
                    type="checkbox"
                    class="checkbox checkbox-xs checkbox-secondary"
                    :checked="allGeoBordersSelected"
                    :indeterminate="someGeoBordersSelected && !allGeoBordersSelected"
                    :disabled="!isGeoBorderMode || geoBorderOptions.length === 0"
                    @change="toggleAllGeoBorders"
                  />
                  <span class="label-text text-xs font-semibold">Tout sélectionner</span>
                </label>

                <details
                  v-for="group in geoBorderGroups"
                  :key="group.id"
                  class="w-full border-b border-base-200 last:border-b-0"
                >
                  <summary class="group flex w-full cursor-pointer list-none items-center gap-2 py-1 font-semibold text-xs">
                    <input
                      type="checkbox"
                      class="checkbox checkbox-xs checkbox-secondary"
                      :checked="isGroupFullySelected(group)"
                      :indeterminate="isGroupPartiallySelected(group)"
                      :disabled="!isGeoBorderMode"
                      @click.stop
                      @change="toggleGeoBorderGroup(group)"
                    />
                    <ChevronRightIcon
                      class="h-4 w-4 shrink-0 transition-transform group-open:rotate-90"
                      aria-hidden="true"
                    />
                    <span>{{ group.label }}</span>
                  </summary>
                  <div class="flex w-full flex-col pl-5">
                    <label
                      v-for="border in group.borders"
                      :key="border.id"
                      class="flex w-full cursor-pointer items-center gap-2 py-1"
                    >
                      <input
                        type="checkbox"
                        class="checkbox checkbox-xs checkbox-secondary"
                        :value="border.id"
                        :checked="selectedGeoBorders.includes(border.id)"
                        :disabled="!isGeoBorderMode"
                        @change="toggleGeoBorderSelection(border.id)"
                      />
                      <span class="label-text text-xs whitespace-nowrap">{{ border.label }}</span>
                    </label>
                  </div>
                </details>
              </div>
            </details>
          </div>
        </div>

        <p v-if="subzoneCount > 0" class="text-[11px] text-info">
          Sous-zones ajoutées : {{ subzoneCount }}
        </p>

        <button
          class="btn btn-xs btn-outline w-full"
          type="button"
          :disabled="!canAddSubzone"
          :aria-disabled="!canAddSubzone"
          :title="addSubzoneTitle"
          @click="$emit('add-subzone')"
        >
          Ajouter une sous-zone
        </button>
      </div>

      <div class="flex gap-2 pt-2">
        <button
          class="btn btn-xs btn-success flex-1"
          type="button"
          :disabled="!canSaveZone"
          :aria-disabled="!canSaveZone"
          :title="saveZoneTitle"
          @click="$emit('save-zone')"
        >
          Enregistrer la zone
        </button>
        <button
          class="btn btn-xs btn-error flex-1"
          type="button"
          @click="$emit('cancel-create')"
        >
          Annuler
        </button>
      </div>

      <p v-if="pendingCreateGeometry" class="text-[11px] text-success">
        Contour fermé — prêt à enregistrer.
      </p>
      <p v-else class="text-[11px] text-warning">
        Le contour doit revenir près de son point de départ pour pouvoir
        être enregistré.
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ChevronRightIcon } from "@heroicons/vue/24/outline";

const props = defineProps<{
  isCreateMode: boolean;
  zoneName: string;
  pendingCreateGeometry: any | null;
  isFrontierMode: boolean;
  isGeoBorderMode: boolean;
  geoBorderGroups: Array<{
    id: string;
    label: string;
    borders: Array<{ id: string; label: string }>;
  }>;
  geoBorderOptions: Array<{ id: string; label: string }>;
  selectedGeoBorders: string[];
  subzoneCount: number;
}>();

const emit = defineEmits<{
  (e: "update:zoneName", value: string): void;
  (e: "start-create"): void;
  (e: "cancel-create"): void;
  (e: "undo-last-stroke"): void;
  (e: "toggle-frontier"): void;
  (e: "toggle-geo-border"): void;
  (e: "toggle-geo-border-selection", value: string): void;
  (e: "toggle-all-geo-borders"): void;
  (e: "toggle-geo-border-group", value: string[]): void;
  (e: "save-zone"): void;
  (e: "add-subzone"): void;
}>();

const geoBorderDropdown = ref<HTMLDetailsElement | null>(null);

watch(
  () => props.isGeoBorderMode,
  (isEnabled) => {
    if (!isEnabled && geoBorderDropdown.value) {
      geoBorderDropdown.value.open = false;
    }
  },
);

function onNameInput(event: Event) {
  const target = event.target as HTMLInputElement | null;
  emit("update:zoneName", (target?.value ?? "").trim());
}

const zoneNameInputId = "create-zone-name";
const trimmedZoneName = computed(() => (props.zoneName ?? "").trim());
const isZoneNameValid = computed(() => trimmedZoneName.value.length > 0);

const canAddSubzone = computed(() => Boolean(props.pendingCreateGeometry));
const canSaveZone = computed(
  () =>
    isZoneNameValid.value &&
    (Boolean(props.pendingCreateGeometry) || props.subzoneCount > 0),
);

const allGeoBordersSelected = computed(
  () =>
    props.geoBorderOptions.length > 0 &&
    props.selectedGeoBorders.length === props.geoBorderOptions.length,
);
const someGeoBordersSelected = computed(
  () => props.selectedGeoBorders.length > 0,
);

const selectedBorderSummary = computed(() => {
  if (!props.isGeoBorderMode) return "Sélectionner les frontières";
  if (props.selectedGeoBorders.length === 0) return "Aucune frontière";
  if (props.selectedGeoBorders.length === props.geoBorderOptions.length) {
    return "Toutes les frontières";
  }
  return `${props.selectedGeoBorders.length} frontière(s) sélectionnée(s)`;
});

function toggleGeoBorderSelection(borderId: string) {
  emit("toggle-geo-border-selection", borderId);
}

function toggleAllGeoBorders() {
  emit("toggle-all-geo-borders");
}

function isGroupFullySelected(group: (typeof props.geoBorderGroups)[number]) {
  return (
    group.borders.length > 0 &&
    group.borders.every((border) => props.selectedGeoBorders.includes(border.id))
  );
}

function isGroupPartiallySelected(group: (typeof props.geoBorderGroups)[number]) {
  const selectedCount = group.borders.filter((border) =>
    props.selectedGeoBorders.includes(border.id),
  ).length;
  return selectedCount > 0 && selectedCount < group.borders.length;
}

function toggleGeoBorderGroup(group: (typeof props.geoBorderGroups)[number]) {
  emit("toggle-geo-border-group", group.borders.map((border) => border.id));
}

const addSubzoneTitle = computed(() => {
  if (canAddSubzone.value) return "";
  return "Dessine un contour fermé pour pouvoir ajouter une sous-zone";
});

const saveZoneTitle = computed(() => {
  if (canSaveZone.value) return "";
  if (!isZoneNameValid.value) return "Donne un nom à la zone";
  return "Dessine un contour fermé ou ajoute une sous-zone";
});
</script>
