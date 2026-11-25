<template>
  <div
    class="relative min-w-0 flex-1"
    :data-testid="testId"
    :data-selected-value="modelValue"
  >
    <button
      type="button"
      class="select select-bordered w-full min-w-0 text-left flex items-center gap-2 pr-8"
      :class="compact ? 'select-sm h-8 min-h-8' : 'h-[50px] min-h-[50px]'"
      :aria-expanded="open"
      aria-haspopup="listbox"
      @click="open = !open"
    >
      <svg
        v-if="selectedHasPoint"
        :width="STYLE_POINT_SWATCH_PX"
        :height="STYLE_POINT_SWATCH_PX"
        :viewBox="`0 0 ${STYLE_POINT_SWATCH_PX} ${STYLE_POINT_SWATCH_PX}`"
        class="shrink-0 overflow-hidden"
      >
        <circle
          :cx="STYLE_POINT_SWATCH_PX / 2"
          :cy="STYLE_POINT_SWATCH_PX / 2"
          :r="STYLE_POINT_SWATCH_PX / 2 - 2"
          :fill="selectedPointColor"
        />
      </svg>
      <span class="truncate text-sm" :style="selectedTextStyle">{{ selectedLabel }}</span>
    </button>
    <ul
      v-if="open"
      class="absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-lg border border-base-300 bg-base-100 py-1 shadow-lg"
      role="listbox"
    >
      <li
        v-for="style in customStyles"
        :key="style.id"
        role="option"
        class="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm hover:bg-base-200"
        :aria-selected="modelValue === `custom:${style.id}`"
        :data-value="`custom:${style.id}`"
        @click="choose(`custom:${style.id}`)"
      >
        <svg
          v-if="hasCustomStylePoint(style)"
          :width="STYLE_POINT_SWATCH_PX"
          :height="STYLE_POINT_SWATCH_PX"
          :viewBox="`0 0 ${STYLE_POINT_SWATCH_PX} ${STYLE_POINT_SWATCH_PX}`"
          class="shrink-0 overflow-hidden"
        >
          <circle
            :cx="STYLE_POINT_SWATCH_PX / 2"
            :cy="STYLE_POINT_SWATCH_PX / 2"
            :r="STYLE_POINT_SWATCH_PX / 2 - 2"
            :fill="style.pointColor || '#000000'"
          />
        </svg>
        <span
          v-else
          class="shrink-0"
          :style="{ width: `${STYLE_POINT_SWATCH_PX}px` }"
        />
        <span class="truncate" :style="getCustomStyleObject(style)">{{
          optionLabel(style)
        }}</span>
      </li>
      <li
        v-for="(_, typeKey) in WORD_TYPE_STYLES"
        :key="String(typeKey)"
        role="option"
        class="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm hover:bg-base-200"
        :aria-selected="modelValue === typeKey"
        :data-value="String(typeKey)"
        @click="choose(String(typeKey))"
      >
        <svg
          v-if="taxonomyHasPoint(String(typeKey))"
          :width="STYLE_POINT_SWATCH_PX"
          :height="STYLE_POINT_SWATCH_PX"
          :viewBox="`0 0 ${STYLE_POINT_SWATCH_PX} ${STYLE_POINT_SWATCH_PX}`"
          class="shrink-0 overflow-hidden"
        >
          <circle
            :cx="STYLE_POINT_SWATCH_PX / 2"
            :cy="STYLE_POINT_SWATCH_PX / 2"
            :r="STYLE_POINT_SWATCH_PX / 2 - 2"
            fill="#000000"
          />
        </svg>
        <span
          v-else
          class="shrink-0"
          :style="{ width: `${STYLE_POINT_SWATCH_PX}px` }"
        />
        <span class="truncate" :style="getWordTypeOptionStyle(String(typeKey))">{{
          taxonomyLabel(String(typeKey))
        }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import {
  STYLE_POINT_SWATCH_PX,
  getCustomStyleObject,
  getCustomStyleOptionLabel,
  getWordTypeOptionLabel,
  getWordTypeOptionStyle,
  hasCustomStylePoint,
  type CustomLabelStyle,
} from "../utils/labelPresentation";
import { WORD_TYPE_STYLES, WORD_TYPE_TAXONOMY, type WordType } from "../utils/wordStyles";

const props = withDefaults(
  defineProps<{
    modelValue?: string;
    customStyles: CustomLabelStyle[];
    compact?: boolean;
    testId?: string;
  }>(),
  {
    compact: false,
    testId: "word-type-select",
    modelValue: "",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
  change: [];
}>();

const open = ref(false);

function optionLabel(style: CustomLabelStyle): string {
  return getCustomStyleOptionLabel(style).replace(/^•\s*/, "");
}

function taxonomyLabel(typeKey: string): string {
  return getWordTypeOptionLabel(typeKey).replace(/^•\s*/, "");
}

function taxonomyHasPoint(typeKey: string): boolean {
  return WORD_TYPE_TAXONOMY[typeKey as WordType]?.mapElementType === "point";
}

const selectedCustom = computed(() => {
  if (!props.modelValue?.startsWith("custom:")) return undefined;
  const id = props.modelValue.slice("custom:".length);
  return props.customStyles.find((style) => style.id === id);
});

const selectedHasPoint = computed(() => {
  if (selectedCustom.value) return hasCustomStylePoint(selectedCustom.value);
  return WORD_TYPE_TAXONOMY[props.modelValue as WordType]?.mapElementType === "point";
});

const selectedPointColor = computed(() => {
  if (selectedCustom.value) {
    return selectedCustom.value.pointColor || "#000000";
  }
  return "#000000";
});

const selectedTextStyle = computed(() => {
  if (selectedCustom.value) return getCustomStyleObject(selectedCustom.value);
  return getWordTypeOptionStyle(props.modelValue || "");
});

const selectedLabel = computed(() => {
  if (selectedCustom.value) return optionLabel(selectedCustom.value);
  return taxonomyLabel(props.modelValue || "");
});

function choose(value: string) {
  open.value = false;
  emit("update:modelValue", value);
  void nextTick(() => emit("change"));
}

function onWindowPointerDown(event: PointerEvent) {
  const root = (event.target as HTMLElement | null)?.closest?.(
    `[data-testid="${props.testId}"]`,
  );
  if (!root) open.value = false;
}

onMounted(() => {
  window.addEventListener("pointerdown", onWindowPointerDown, true);
});
onBeforeUnmount(() => {
  window.removeEventListener("pointerdown", onWindowPointerDown, true);
});
</script>
