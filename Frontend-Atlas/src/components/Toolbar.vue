<template>
  <aside class="w-16 bg-white border-r border-gray-200">
    <div class="p-2 space-y-1">
      <!-- Select Tool -->
      <button
        @click="$emit('tool-change', 'select')"
        :class="[
          'w-12 h-12 flex items-center justify-center rounded-lg transition-colors',
          activeTool === 'select' 
            ? 'bg-primary-100 text-primary-600' 
            : 'text-gray-600 hover:bg-gray-100'
        ]"
        title="Sélectionner"
      >
        <CursorArrowRaysIcon class="h-6 w-6" />
      </button>

      <!-- Text Tool -->
      <button
        @click="$emit('tool-change', 'text')"
        :class="[
          'w-12 h-12 flex items-center justify-center rounded-lg transition-colors',
          activeTool === 'text' 
            ? 'bg-primary-100 text-primary-600' 
            : 'text-gray-600 hover:bg-gray-100'
        ]"
        title="Texte"
      >
        <DocumentTextIcon class="h-6 w-6" />
      </button>

      <!-- Shape Tool -->
      <button
        @click="$emit('tool-change', 'shape')"
        :class="[
          'w-12 h-12 flex items-center justify-center rounded-lg transition-colors',
          activeTool === 'shape' 
            ? 'bg-primary-100 text-primary-600' 
            : 'text-gray-600 hover:bg-gray-100'
        ]"
        title="Formes"
      >
        <Square3Stack3DIcon class="h-6 w-6" />
      </button>

      <!-- Line Tool -->
      <button
        @click="$emit('tool-change', 'line')"
        :class="[
          'w-12 h-12 flex items-center justify-center rounded-lg transition-colors',
          activeTool === 'line' 
            ? 'bg-primary-100 text-primary-600' 
            : 'text-gray-600 hover:bg-gray-100'
        ]"
        title="Ligne"
      >
        <div class="w-6 h-6 flex items-center justify-center">
          <div class="w-5 h-0.5 bg-current transform rotate-45"></div>
        </div>
      </button>

      <!-- Image Tool -->
      <button
        @click="$emit('tool-change', 'image')"
        :class="[
          'w-12 h-12 flex items-center justify-center rounded-lg transition-colors',
          activeTool === 'image' 
            ? 'bg-primary-100 text-primary-600' 
            : 'text-gray-600 hover:bg-gray-100'
        ]"
        title="Image"
      >
        <PhotoIcon class="h-6 w-6" />
      </button>

      <hr class="my-3 border-gray-200">

      <!-- Hand Tool -->
      <button
        @click="$emit('tool-change', 'hand')"
        :class="[
          'w-12 h-12 flex items-center justify-center rounded-lg transition-colors',
          activeTool === 'hand' 
            ? 'bg-primary-100 text-primary-600' 
            : 'text-gray-600 hover:bg-gray-100'
        ]"
        title="Main"
      >
        <HandRaisedIcon class="h-6 w-6" />
      </button>

      <!-- Zoom Tool -->
      <button
        @click="$emit('tool-change', 'zoom')"
        :class="[
          'w-12 h-12 flex items-center justify-center rounded-lg transition-colors',
          activeTool === 'zoom' 
            ? 'bg-primary-100 text-primary-600' 
            : 'text-gray-600 hover:bg-gray-100'
        ]"
        title="Zoom"
      >
        <MagnifyingGlassIcon class="h-6 w-6" />
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import {
  CursorArrowRaysIcon,
  DocumentTextIcon,
  Square3Stack3DIcon,
  PhotoIcon,
  HandRaisedIcon,
  MagnifyingGlassIcon
} from '@heroicons/vue/24/outline'

defineProps<{
  activeTool: string
}>()

defineEmits<{
  'tool-change': [tool: string]
  'add-element': [type: string]
}>()
</script>