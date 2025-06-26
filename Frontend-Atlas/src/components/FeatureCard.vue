<script setup lang="ts">
interface Props {
  title: string
  description: string
  icon: string
  color?: 'primary' | 'secondary' | 'accent'
}

withDefaults(defineProps<Props>(), {
  color: 'primary'
})

const colorClasses = {
  primary: {
    bg: 'bg-primary-100',
    text: 'text-primary-600',
    border: 'border-primary-200'
  },
  secondary: {
    bg: 'bg-secondary-100',
    text: 'text-secondary-600',
    border: 'border-secondary-200'
  },
  accent: {
    bg: 'bg-accent-100',
    text: 'text-accent-600',
    border: 'border-accent-200'
  }
}
</script>

<template>
  <div class="card group hover:scale-105 transform transition-all duration-300">
    <!-- Icon -->
    <div class="flex items-center justify-center w-12 h-12 rounded-lg mb-4 transition-colors"
         :class="[colorClasses[color].bg, colorClasses[color].border, 'border']">
      <span class="text-2xl">{{ icon }}</span>
    </div>
    
    <!-- Content -->
    <h3 class="text-xl font-semibold text-gray-900 mb-3 group-hover:text-primary-600 transition-colors">
      {{ title }}
    </h3>
    <p class="text-gray-600 leading-relaxed">
      {{ description }}
    </p>
    
    <!-- Learn more link -->
    <div class="mt-4 pt-4 border-t border-gray-100">
      <a href="#" 
         class="inline-flex items-center text-sm font-medium transition-colors"
         :class="colorClasses[color].text">
        En savoir plus
        <svg class="ml-1 w-4 h-4 group-hover:translate-x-1 transition-transform" 
             fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path>
        </svg>
      </a>
    </div>
  </div>
</template>