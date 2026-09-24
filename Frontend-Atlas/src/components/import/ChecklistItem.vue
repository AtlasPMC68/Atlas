<template>
  <div
    class="px-4 py-3 flex items-center gap-3 border-b border-gray-50 last:border-b-0"
    :class="{
      'bg-indigo-50/40': status === 'available' && highlight,
      'opacity-50': status === 'locked',
    }"
  >
    <!-- State indicator -->
    <span
      class="w-[22px] h-[22px] rounded-full shrink-0 flex items-center justify-center border-2"
      :class="indicatorClass"
      aria-hidden="true"
    >
      <CheckIcon v-if="status === 'done'" class="w-3 h-3 text-green-600" />
      <LockClosedIcon v-else-if="status === 'locked'" class="w-3 h-3 text-gray-400" />
      <span
        v-else-if="highlight"
        class="w-2 h-2 rounded-full bg-indigo-600"
      />
    </span>

    <div class="flex-1 min-w-0">
      <div class="text-sm font-semibold text-gray-900 flex items-center gap-1.5">
        {{ title }}
        <span
          v-if="!required"
          class="text-[10px] font-medium bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded"
        >
          Optionnel
        </span>
      </div>
      <slot name="detail">
        <div
          class="text-[11px] mt-0.5"
          :class="status === 'done' ? 'text-green-600' : 'text-gray-400'"
        >
          {{ status === "locked" ? lockedDescription || description : description }}
        </div>
      </slot>
    </div>

    <!-- Action -->
    <button
      v-if="status === 'done'"
      type="button"
      class="h-7 px-2.5 rounded-[7px] border border-green-200 bg-green-50 text-green-600 text-[11px] font-semibold flex items-center gap-1 hover:bg-green-100 disabled:opacity-50"
      :disabled="disabled"
      @click="emit('open')"
    >
      <PencilSquareIcon class="w-3 h-3" />
      Modifier
    </button>
    <button
      v-else
      type="button"
      class="h-8 px-3 rounded-lg text-xs font-semibold flex items-center gap-1 whitespace-nowrap"
      :class="
        status === 'locked'
          ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
          : highlight
            ? 'bg-indigo-600 text-white hover:bg-indigo-700'
            : 'bg-gray-50 border border-gray-200 text-gray-700 hover:bg-gray-100'
      "
      :disabled="status === 'locked' || disabled"
      @click="emit('open')"
    >
      Ouvrir
      <ChevronRightIcon class="w-3 h-3" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { CheckIcon } from "@heroicons/vue/24/solid";
import {
  ChevronRightIcon,
  LockClosedIcon,
  PencilSquareIcon,
} from "@heroicons/vue/24/outline";
import type { StepStatus } from "../../typescript/importSession";

const props = withDefaults(
  defineProps<{
    title: string;
    description: string;
    status: StepStatus;
    required?: boolean;
    // The next thing to do: drawn in the primary colour.
    highlight?: boolean;
    lockedDescription?: string;
    disabled?: boolean;
  }>(),
  { required: true, highlight: false, lockedDescription: "", disabled: false },
);

const emit = defineEmits<{ (e: "open"): void }>();

const indicatorClass = computed(() => {
  if (props.status === "done") return "bg-green-100 border-green-600";
  if (props.status === "locked") return "bg-gray-50 border-gray-300";
  return props.highlight ? "bg-white border-indigo-600" : "bg-white border-gray-300";
});
</script>
