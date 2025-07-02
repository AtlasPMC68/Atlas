<template>
  <aside class="w-80 bg-white border-l border-gray-200 overflow-y-auto">
    <div class="p-6">
      <h3 class="text-lg font-semibold text-gray-900 mb-6">Propriétés</h3>
      
      <!-- No Selection State -->
      <div v-if="!selectedElement" class="text-center py-12">
        <Square3Stack3DIcon class="h-12 w-12 text-gray-400 mx-auto mb-4" />
        <p class="text-gray-600">Sélectionnez un élément pour modifier ses propriétés</p>
      </div>

      <!-- Element Properties -->
      <div v-else class="space-y-6">
        <!-- Element Type -->
        <div class="flex items-center space-x-2 pb-4 border-b border-gray-200">
          <DocumentTextIcon v-if="selectedElement.type === 'text'" class="h-5 w-5 text-primary-600" />
          <Square3Stack3DIcon v-else class="h-5 w-5 text-primary-600" />
          <span class="font-medium text-gray-900 capitalize">{{ selectedElement.type }}</span>
        </div>

        <!-- Position & Size -->
        <div>
          <h4 class="font-medium text-gray-900 mb-3">Position et taille</h4>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-medium text-gray-700 mb-1">X</label>
              <input
                type="number"
                :value="selectedElement.x"
                @input="updateProperty('x', parseInt(($event.target as HTMLInputElement).value))"
                class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
              >
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-700 mb-1">Y</label>
              <input
                type="number"
                :value="selectedElement.y"
                @input="updateProperty('y', parseInt(($event.target as HTMLInputElement).value))"
                class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
              >
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-700 mb-1">Largeur</label>
              <input
                type="number"
                :value="selectedElement.width"
                @input="updateProperty('width', parseInt(($event.target as HTMLInputElement).value))"
                class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
              >
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-700 mb-1">Hauteur</label>
              <input
                type="number"
                :value="selectedElement.height"
                @input="updateProperty('height', parseInt(($event.target as HTMLInputElement).value))"
                class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
              >
            </div>
          </div>
        </div>

        <!-- Text Properties -->
        <div v-if="selectedElement.type === 'text'">
          <h4 class="font-medium text-gray-900 mb-3">Texte</h4>
          <div class="space-y-3">
            <div>
              <label class="block text-xs font-medium text-gray-700 mb-1">Contenu</label>
              <textarea
                :value="selectedElement.content"
                @input="updateProperty('content', ($event.target as HTMLTextAreaElement).value)"
                class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
                rows="3"
              ></textarea>
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-700 mb-1">Taille de police</label>
              <input
                type="number"
                :value="selectedElement.fontSize"
                @input="updateProperty('fontSize', parseInt(($event.target as HTMLInputElement).value))"
                class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
                min="8"
                max="72"
              >
            </div>
          </div>
        </div>

        <!-- Shape Properties -->
        <div v-if="selectedElement.type === 'shape'">
          <h4 class="font-medium text-gray-900 mb-3">Forme</h4>
          <div class="space-y-3">
            <div>
              <label class="block text-xs font-medium text-gray-700 mb-1">Type</label>
              <select
                :value="selectedElement.shape"
                @change="updateProperty('shape', ($event.target as HTMLSelectElement).value)"
                class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
              >
                <option value="rectangle">Rectangle</option>
                <option value="circle">Cercle</option>
              </select>
            </div>
          </div>
        </div>

        <!-- Color -->
        <div>
          <h4 class="font-medium text-gray-900 mb-3">Couleur</h4>
          <div class="flex items-center space-x-3">
            <input
              type="color"
              :value="selectedElement.color"
              @input="updateProperty('color', ($event.target as HTMLInputElement).value)"
              class="w-12 h-10 border border-gray-300 rounded-md cursor-pointer"
            >
            <input
              type="text"
              :value="selectedElement.color"
              @input="updateProperty('color', ($event.target as HTMLInputElement).value)"
              class="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-md focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
              placeholder="#000000"
            >
          </div>
        </div>

        <!-- Actions -->
        <div class="pt-4 border-t border-gray-200">
          <div class="flex space-x-2">
            <button class="flex-1 btn-secondary text-sm py-2">
              <DocumentDuplicateIcon class="h-4 w-4 mr-2" />
              Dupliquer
            </button>
            <button class="btn-secondary text-sm py-2 px-3">
              <TrashIcon class="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import {
  Square3Stack3DIcon,
  DocumentTextIcon,
  DocumentDuplicateIcon,
  TrashIcon
} from '@heroicons/vue/24/outline'

interface CanvasElement {
  id: string
  type: 'text' | 'shape'
  x: number
  y: number
  width: number
  height: number
  content?: string
  fontSize?: number
  color: string
  shape?: 'rectangle' | 'circle'
}

defineProps<{
  selectedElement: CanvasElement | null
}>()

const emit = defineEmits<{
  'update-element': [updates: Partial<CanvasElement>]
}>()

function updateProperty(property: string, value: any) {
  emit('update-element', { [property]: value })
}
</script>