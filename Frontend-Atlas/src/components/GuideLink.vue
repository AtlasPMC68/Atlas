<script setup lang="ts">
import { computed } from "vue";
import { InformationCircleIcon } from "@heroicons/vue/24/outline";
import { GUIDES, guideUrl, type GuideId } from "../utils/guides";

const props = withDefaults(
  defineProps<{
    guide: GuideId;
    page?: number;
    tooltipPosition?: "top" | "bottom" | "left" | "right";
  }>(),
  { page: undefined, tooltipPosition: "bottom" },
);

const href = computed(() => guideUrl(props.guide, props.page));
const label = computed(() => `Ouvrir le guide « ${GUIDES[props.guide].title} »`);
</script>

<template>
  <span class="tooltip inline-flex align-middle" :class="`tooltip-${tooltipPosition}`" :data-tip="label">
    <a
      :href="href"
      target="_blank"
      rel="noopener"
      class="inline-flex items-center justify-center rounded-full text-gray-400 hover:text-primary-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-500 transition-colors"
      :aria-label="label"
      data-testid="guide-link"
    >
      <InformationCircleIcon class="h-5 w-5" />
    </a>
  </span>
</template>
