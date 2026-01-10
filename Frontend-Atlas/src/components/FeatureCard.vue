<script setup lang="ts">
import { FunctionalComponent } from "vue";

interface Props {
  title: string;
  description: string;
  icon: FunctionalComponent; // Accepts a Vue component (Heroicon)
  color?: "primary" | "secondary" | "accent";
}

withDefaults(defineProps<Props>(), {
  color: "primary",
});

const colorClasses = {
  primary: {
    bg: "bg-primary-100",
    text: "text-primary-600",
    border: "border-primary-200",
  },
  secondary: {
    bg: "bg-secondary-100",
    text: "text-secondary-600",
    border: "border-secondary-200",
  },
  accent: {
    bg: "bg-accent-100",
    text: "text-accent-600",
    border: "border-accent-200",
  },
};
</script>

<template>
  <div class="card group hover:scale-105 transform transition-all duration-300">
    <!-- Icon -->
    <div
      class="flex items-center justify-center w-12 h-12 rounded-lg mb-4 transition-colors"
      :class="[colorClasses[color].bg, colorClasses[color].border, 'border']"
    >
      <component :is="icon" class="w-8 h-8" :class="colorClasses[color].text" />
    </div>

    <!-- Content -->
    <h3
      class="text-xl font-semibold text-gray-900 mb-3 group-hover:text-primary-600 transition-colors"
    >
      {{ title }}
    </h3>
    <p class="text-gray-600 leading-relaxed">
      {{ description }}
    </p>
  </div>
</template>
