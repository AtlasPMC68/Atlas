<template>
  <section
    class="bg-white rounded-[13px] overflow-hidden shadow-[0_1px_4px_rgba(0,0,0,0.07)]"
    :class="{ 'opacity-50': locked }"
  >
    <header class="px-4 py-3 border-b border-gray-100 flex items-center gap-2">
      <span class="w-[7px] h-[7px] rounded-full shrink-0" :class="DOT[tone]" />
      <h3 class="text-[11px] font-bold text-gray-700 tracking-wider uppercase">
        {{ title }}
      </h3>
      <span
        v-if="badge"
        class="ml-auto text-[10px] font-semibold px-2 py-0.5 rounded"
        :class="BADGE[tone]"
      >
        {{ badge }}
      </span>
      <span
        v-else-if="lockedHint"
        class="ml-auto flex items-center gap-1 text-[10px] text-gray-400 font-medium"
      >
        <LockClosedIcon class="w-3.5 h-3.5" />
        {{ lockedHint }}
      </span>
    </header>
    <slot />
  </section>
</template>

<script setup lang="ts">
import { LockClosedIcon } from "@heroicons/vue/24/outline";

export type GroupTone = "pending" | "progress" | "done" | "locked";

withDefaults(
  defineProps<{
    title: string;
    tone: GroupTone;
    badge?: string;
    locked?: boolean;
    lockedHint?: string;
  }>(),
  { badge: "", locked: false, lockedHint: "" },
);

const DOT: Record<GroupTone, string> = {
  pending: "bg-amber-500",
  progress: "bg-blue-500",
  done: "bg-green-600",
  locked: "bg-gray-300",
};

const BADGE: Record<GroupTone, string> = {
  pending: "text-amber-700 bg-amber-100",
  progress: "text-blue-700 bg-blue-100",
  done: "text-green-700 bg-green-100",
  locked: "text-gray-500 bg-gray-100",
};
</script>
