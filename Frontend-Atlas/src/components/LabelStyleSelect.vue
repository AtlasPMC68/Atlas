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
      <PointSwatch v-if="selectedHasPoint" :fill="selectedPointColor" />
      <span
        v-else
        class="shrink-0"
        :style="{ width: `${STYLE_POINT_SWATCH_PX}px` }"
      />
      <span class="truncate text-sm" :style="selectedTextStyle">{{ selectedLabel }}</span>
    </button>
    <ul
      v-if="open"
      class="absolute z-50 max-h-60 w-full overflow-auto rounded-lg border border-base-300 bg-base-100 py-1 shadow-lg"
      :class="dropUp ? 'bottom-full mb-1' : 'top-full mt-1'"
      role="listbox"
    >
      <li
        v-for="option in options"
        :key="option.value"
        role="option"
        class="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm hover:bg-base-200"
        :aria-selected="modelValue === option.value"
        :data-value="option.value"
        @click="choose(option.value)"
      >
        <PointSwatch v-if="option.hasPoint" :fill="option.fill" />
        <span
          v-else
          class="shrink-0"
          :style="{ width: `${STYLE_POINT_SWATCH_PX}px` }"
        />
        <span class="truncate" :style="option.textStyle">{{ option.label }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import type { CSSProperties } from "vue";
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
import PointSwatch from "./PointSwatch.vue";

type StyleOption = {
  value: string;
  label: string;
  textStyle: CSSProperties;
  hasPoint: boolean;
  fill: string;
};

const props = withDefaults(
  defineProps<{
    modelValue?: string;
    customStyles: CustomLabelStyle[];
    compact?: boolean;
    dropUp?: boolean;
    testId?: string;
  }>(),
  {
    compact: false,
    dropUp: false,
    testId: "word-type-select",
    modelValue: "",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
  change: [];
}>();

const open = ref(false);

function taxonomyHasPoint(typeKey: string): boolean {
  return WORD_TYPE_TAXONOMY[typeKey as WordType]?.mapElementType === "point";
}

const options = computed<StyleOption[]>(() => {
  const custom = props.customStyles.map((style) => ({
    value: `custom:${style.id}`,
    label: getCustomStyleOptionLabel(style),
    textStyle: getCustomStyleObject(style),
    hasPoint: hasCustomStylePoint(style),
    fill: style.pointColor || "#000000",
  }));
  const taxonomy = Object.keys(WORD_TYPE_STYLES).map((typeKey) => ({
    value: typeKey,
    label: getWordTypeOptionLabel(typeKey),
    textStyle: getWordTypeOptionStyle(typeKey),
    hasPoint: taxonomyHasPoint(typeKey),
    fill: "#000000",
  }));
  return [...custom, ...taxonomy];
});

const selected = computed(
  () => options.value.find((option) => option.value === props.modelValue),
);
const selectedHasPoint = computed(() => selected.value?.hasPoint ?? false);
const selectedPointColor = computed(() => selected.value?.fill ?? "#000000");
const selectedTextStyle = computed(() => selected.value?.textStyle ?? {});
const selectedLabel = computed(() => selected.value?.label ?? "");

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
