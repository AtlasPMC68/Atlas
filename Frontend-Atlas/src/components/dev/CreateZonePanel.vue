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

      <label class="flex flex-col gap-1 text-xs">
        <span>Nom de la zone</span>
        <input
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
          <label class="label cursor-pointer justify-between gap-2">
            <span class="label-text text-xs">Frontières géopolitiques</span>
            <input
              type="checkbox"
              class="toggle toggle-xs toggle-secondary"
              :checked="isGeoBorderMode"
              @change="$emit('toggle-geo-border')"
            />
          </label>
        </div>

        <p v-if="subzoneCount > 0" class="text-[11px] text-info">
          Sous-zones ajoutées : {{ subzoneCount }}
        </p>

        <button
          class="btn btn-xs btn-outline w-full"
          type="button"
          :disabled="!pendingCreateGeometry"
          @click="$emit('add-subzone')"
        >
          Ajouter une sous-zone
        </button>
      </div>

      <div class="flex gap-2 pt-2">
        <button
          class="btn btn-xs btn-success flex-1"
          type="button"
          :disabled="!pendingCreateGeometry && subzoneCount === 0"
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

      <p v-if="!pendingCreateGeometry" class="text-[11px] text-warning">
        Le contour doit revenir près de son point de départ pour pouvoir
        être enregistré.
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{
  isCreateMode: boolean;
  zoneName: string;
  pendingCreateGeometry: any | null;
  isFrontierMode: boolean;
  isGeoBorderMode: boolean;
  subzoneCount: number;
}>();

const emit = defineEmits<{
  (e: "update:zoneName", value: string): void;
  (e: "start-create"): void;
  (e: "cancel-create"): void;
  (e: "undo-last-stroke"): void;
  (e: "toggle-frontier"): void;
  (e: "toggle-geo-border"): void;
  (e: "save-zone"): void;
  (e: "add-subzone"): void;
}>();

function onNameInput(event: Event) {
  const target = event.target as HTMLInputElement | null;
  emit("update:zoneName", target?.value ?? "");
}
</script>
