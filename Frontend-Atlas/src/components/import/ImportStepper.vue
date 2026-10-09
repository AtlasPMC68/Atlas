<template>
  <nav class="bg-white border-b border-gray-200 px-8 py-4" aria-label="Étapes de l'import">
    <ol class="flex items-center max-w-xl mx-auto">
      <template v-for="(step, index) in STEPS" :key="step.phase">
        <li class="flex flex-col items-center gap-1.5">
          <div
            class="w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold"
            :class="circleClass(index)"
            :aria-current="index === currentIndex ? 'step' : undefined"
          >
            <CheckIcon v-if="index < currentIndex" class="w-4 h-4 text-white" />
            <span v-else>{{ index + 1 }}</span>
          </div>
          <span
            class="text-xs whitespace-nowrap"
            :class="
              index <= currentIndex
                ? 'text-indigo-600 ' + (index === currentIndex ? 'font-bold' : 'font-semibold')
                : 'text-gray-400 font-medium'
            "
          >
            {{ step.label }}
          </span>
        </li>
        <li
          v-if="index < STEPS.length - 1"
          aria-hidden="true"
          class="flex-1 h-0.5 mx-2.5 mb-5"
          :class="index < currentIndex ? 'bg-indigo-600' : 'bg-gray-200'"
        />
      </template>
    </ol>
  </nav>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { CheckIcon } from "@heroicons/vue/24/solid";
import type { ImportPhase } from "../../typescript/importSession";

const props = defineProps<{ phase: ImportPhase }>();

const STEPS: { phase: ImportPhase; label: string }[] = [
  { phase: "import", label: "Import" },
  { phase: "saisie", label: "Saisie utilisateur" },
  { phase: "extraction", label: "Extraction" },
];

const currentIndex = computed(() => STEPS.findIndex((s) => s.phase === props.phase));

function circleClass(index: number): string {
  if (index < currentIndex.value) return "bg-indigo-600";
  if (index === currentIndex.value) return "bg-indigo-600 text-white ring-4 ring-indigo-50";
  return "bg-gray-200 text-gray-400";
}
</script>
