<template>
  <div class="card overflow-hidden group">
    <!-- Thumbnail -->
    <div class="aspect-video bg-gray-100 overflow-hidden">
      <img
        :src="project.thumbnail"
        :alt="project.title"
        class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
      >
    </div>
    
    <!-- Content -->
    <div class="p-6">
      <div class="flex items-start justify-between mb-3">
        <h3 class="text-lg font-semibold text-gray-900 line-clamp-1">
          {{ project.title }}
        </h3>
        <div class="flex items-center space-x-1 ml-2">
          <button
            @click="$emit('edit', project.id)"
            class="p-1 text-gray-400 hover:text-primary-600 rounded transition-colors"
          >
            <PencilIcon class="h-4 w-4" />
          </button>
          <button
            @click="$emit('delete', project.id)"
            class="p-1 text-gray-400 hover:text-red-600 rounded transition-colors"
          >
            <TrashIcon class="h-4 w-4" />
          </button>
        </div>
      </div>
      
      <p class="text-gray-600 text-sm mb-4 line-clamp-2">
        {{ project.description }}
      </p>
      
      <!-- Stats -->
      <div class="flex items-center justify-between text-sm text-gray-500 mb-4">
        <div class="flex items-center space-x-4">
          <span class="flex items-center">
            <EyeIcon class="h-4 w-4 mr-1" />
            {{ project.views }}
          </span>
          <span class="flex items-center">
            <CalendarIcon class="h-4 w-4 mr-1" />
            {{ formatDate(project.lastModified) }}
          </span>
        </div>
        <div class="flex items-center">
          <span
            v-if="project.isPublic"
            class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800"
          >
            <GlobeAltIcon class="h-3 w-3 mr-1" />
            Public
          </span>
          <span
            v-else
            class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-800"
          >
            <LockClosedIcon class="h-3 w-3 mr-1" />
            Privé
          </span>
        </div>
      </div>
      
      <!-- Actions -->
      <div class="flex space-x-2">
        <button
          @click="$emit('edit', project.id)"
          class="flex-1 btn-primary text-sm py-2"
        >
          Modifier
        </button>
        <button class="btn-secondary text-sm py-2 px-4">
          <ShareIcon class="h-4 w-4" />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  PencilIcon,
  TrashIcon,
  EyeIcon,
  CalendarIcon,
  ShareIcon,
  GlobeAltIcon,
  LockClosedIcon
} from '@heroicons/vue/24/outline'

interface Project {
  id: number
  title: string
  description: string
  thumbnail: string
  lastModified: string
  views: number
  isPublic: boolean
}

defineProps<{
  project: Project
}>()

defineEmits<{
  edit: [id: number]
  delete: [id: number]
}>()

function formatDate(dateString: string) {
  const date = new Date(dateString)
  return date.toLocaleDateString('fr-FR', {
    day: 'numeric',
    month: 'short'
  })
}
</script>

<style scoped>
.line-clamp-1 {
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>