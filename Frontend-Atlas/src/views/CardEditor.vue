<template>
  <div class="h-screen bg-gray-50 flex flex-col">
    <!-- Header -->
    <header class="bg-white border-b border-gray-200 px-6 py-4">
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-4">
          <router-link to="/dashboard" class="text-gray-600 hover:text-gray-900">
            <ArrowLeftIcon class="h-6 w-6" />
          </router-link>
          <div>
            <h1 class="text-xl font-semibold text-gray-900">{{ projectTitle }}</h1>
            <p class="text-sm text-gray-600">Dernière modification: {{ lastSaved }}</p>
          </div>
        </div>
        
        <div class="flex items-center space-x-3">
          <button class="btn-secondary">
            <EyeIcon class="h-5 w-5 mr-2" />
            Aperçu
          </button>
          <button class="btn-primary">
            <ShareIcon class="h-5 w-5 mr-2" />
            Publier
          </button>
        </div>
      </div>
    </header>

    <div class="flex-1 flex">
      <!-- Toolbar -->
      <Toolbar 
        :active-tool="activeTool" 
        @tool-change="setActiveTool"
        @add-element="addElement"
      />

      <!-- Canvas Area -->
      <main class="flex-1 bg-gray-100 relative overflow-hidden">
        <div class="absolute inset-4 bg-white rounded-lg shadow-sm border border-gray-200">
          <!-- Canvas -->
          <div 
            ref="canvas"
            class="w-full h-full relative overflow-hidden cursor-crosshair"
            @click="handleCanvasClick"
            @mousemove="handleMouseMove"
          >
            <!-- Grid Background -->
            <div class="absolute inset-0 opacity-5" style="background-image: url('data:image/svg+xml,<svg xmlns=\'http://www.w3.org/2000/svg\' width=\'20\' height=\'20\' viewBox=\'0 0 20 20\'><rect width=\'20\' height=\'20\' fill=\'none\' stroke=\'%23000\' stroke-width=\'0.5\'/></svg>')"></div>
            
            <!-- Canvas Elements -->
            <div
              v-for="element in canvasElements"
              :key="element.id"
              :class="[
                'absolute cursor-pointer',
                { 'ring-2 ring-primary-500': selectedElement?.id === element.id }
              ]"
              :style="{
                left: element.x + 'px',
                top: element.y + 'px',
                width: element.width + 'px',
                height: element.height + 'px'
              }"
              @click.stop="selectElement(element)"
            >
              <!-- Text Element -->
              <div
                v-if="element.type === 'text'"
                class="w-full h-full flex items-center justify-center border-2 border-dashed border-gray-300 bg-white"
                :style="{ fontSize: element.fontSize + 'px', color: element.color }"
              >
                {{ element.content }}
              </div>
              
              <!-- Shape Element -->
              <div
                v-else-if="element.type === 'shape'"
                class="w-full h-full border-2 border-dashed border-gray-300"
                :style="{ backgroundColor: element.color, borderRadius: element.shape === 'circle' ? '50%' : '4px' }"
              ></div>
            </div>
          </div>
        </div>
      </main>

      <!-- Properties Sidebar -->
      <Sidebar 
        :selected-element="selectedElement"
        @update-element="updateElement"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeftIcon, EyeIcon, ShareIcon } from '@heroicons/vue/24/outline'
import Toolbar from '../components/Toolbar.vue'
import Sidebar from '../components/Sidebar.vue'

const route = useRoute()
const projectId = route.params.id as string
const projectTitle = ref('Nouveau projet')
const lastSaved = ref('Il y a quelques secondes')
const activeTool = ref('select')
const selectedElement = ref<any>(null)
const canvas = ref<HTMLElement>()

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

const canvasElements = ref<CanvasElement[]>([
  {
    id: '1',
    type: 'text',
    x: 100,
    y: 100,
    width: 200,
    height: 50,
    content: 'Titre principal',
    fontSize: 24,
    color: '#1f2937'
  },
  {
    id: '2',
    type: 'shape',
    x: 100,
    y: 200,
    width: 150,
    height: 100,
    color: '#3b82f6',
    shape: 'rectangle'
  }
])

function setActiveTool(tool: string) {
  activeTool.value = tool
  selectedElement.value = null
}

function addElement(type: string) {
  const newElement: CanvasElement = {
    id: Date.now().toString(),
    type: type as 'text' | 'shape',
    x: 200,
    y: 200,
    width: type === 'text' ? 200 : 100,
    height: type === 'text' ? 50 : 100,
    color: type === 'text' ? '#1f2937' : '#3b82f6'
  }
  
  if (type === 'text') {
    newElement.content = 'Nouveau texte'
    newElement.fontSize = 16
  } else {
    newElement.shape = 'rectangle'
  }
  
  canvasElements.value.push(newElement)
  selectedElement.value = newElement
}

function handleCanvasClick(event: MouseEvent) {
  if (activeTool.value === 'text') {
    const rect = canvas.value!.getBoundingClientRect()
    addElementAt('text', event.clientX - rect.left, event.clientY - rect.top)
  } else if (activeTool.value === 'shape') {
    const rect = canvas.value!.getBoundingClientRect()
    addElementAt('shape', event.clientX - rect.left, event.clientY - rect.top)
  }
}

function addElementAt(type: string, x: number, y: number) {
  const newElement: CanvasElement = {
    id: Date.now().toString(),
    type: type as 'text' | 'shape',
    x,
    y,
    width: type === 'text' ? 200 : 100,
    height: type === 'text' ? 50 : 100,
    color: type === 'text' ? '#1f2937' : '#3b82f6'
  }
  
  if (type === 'text') {
    newElement.content = 'Nouveau texte'
    newElement.fontSize = 16
  } else {
    newElement.shape = 'rectangle'
  }
  
  canvasElements.value.push(newElement)
  selectedElement.value = newElement
}

function selectElement(element: CanvasElement) {
  selectedElement.value = element
  activeTool.value = 'select'
}

function updateElement(updates: Partial<CanvasElement>) {
  if (selectedElement.value) {
    Object.assign(selectedElement.value, updates)
    // Update in array
    const index = canvasElements.value.findIndex(el => el.id === selectedElement.value.id)
    if (index !== -1) {
      canvasElements.value[index] = { ...selectedElement.value }
    }
  }
}

function handleMouseMove(event: MouseEvent) {
  // Handle element dragging if needed
}

onMounted(() => {
  if (projectId && projectId !== 'new') {
    // Load existing project
    projectTitle.value = `Projet ${projectId}`
  }
})
</script>