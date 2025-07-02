<template>
  <div class="min-h-screen bg-gray-50">
    <!-- Navigation -->
    <NavBar />

    <!-- Main Content -->
    <main class="max-w-7xl mx-auto px-6 py-8">
      <!-- Header -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-8">
        <div>
          <h1 class="text-3xl font-bold text-gray-900 mb-2">Mes projets</h1>
          <p class="text-gray-600">Gérez et créez vos cartes interactives</p>
        </div>
        <router-link to="/editor" class="btn-primary mt-4 sm:mt-0">
          <PlusIcon class="h-5 w-5 mr-2" />
          Nouveau projet
        </router-link>
      </div>

      <!-- Stats Cards -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div class="card p-6">
          <div class="flex items-center">
            <div class="bg-primary-100 p-3 rounded-lg">
              <MapIcon class="h-6 w-6 text-primary-600" />
            </div>
            <div class="ml-4">
              <p class="text-sm font-medium text-gray-600">Total des projets</p>
              <p class="text-2xl font-bold text-gray-900">{{ projects.length }}</p>
            </div>
          </div>
        </div>
        
        <div class="card p-6">
          <div class="flex items-center">
            <div class="bg-secondary-100 p-3 rounded-lg">
              <EyeIcon class="h-6 w-6 text-secondary-600" />
            </div>
            <div class="ml-4">
              <p class="text-sm font-medium text-gray-600">Vues totales</p>
              <p class="text-2xl font-bold text-gray-900">1,247</p>
            </div>
          </div>
        </div>
        
        <div class="card p-6">
          <div class="flex items-center">
            <div class="bg-accent-100 p-3 rounded-lg">
              <ShareIcon class="h-6 w-6 text-accent-600" />
            </div>
            <div class="ml-4">
              <p class="text-sm font-medium text-gray-600">Partages</p>
              <p class="text-2xl font-bold text-gray-900">89</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Projects Grid -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <ProjectCard
          v-for="project in projects"
          :key="project.id"
          :project="project"
          @edit="editProject"
          @delete="deleteProject"
        />
      </div>

      <!-- Empty State -->
      <div v-if="projects.length === 0" class="text-center py-12">
        <MapIcon class="h-12 w-12 text-gray-400 mx-auto mb-4" />
        <h3 class="text-lg font-medium text-gray-900 mb-2">Aucun projet pour le moment</h3>
        <p class="text-gray-600 mb-6">Créez votre première carte interactive pour commencer.</p>
        <router-link to="/editor" class="btn-primary">
          <PlusIcon class="h-5 w-5 mr-2" />
          Créer mon premier projet
        </router-link>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { PlusIcon, MapIcon, EyeIcon, ShareIcon } from '@heroicons/vue/24/outline'
import NavBar from '../components/NavBar.vue'
import ProjectCard from '../components/ProjectCard.vue'

const router = useRouter()

const projects = ref([
  {
    id: 1,
    title: 'Carte Marketing Q1',
    description: 'Présentation des résultats du premier trimestre avec données interactives.',
    thumbnail: 'https://images.pexels.com/photos/590022/pexels-photo-590022.jpeg?auto=compress&cs=tinysrgb&w=400',
    lastModified: '2025-01-02',
    views: 245,
    isPublic: true
  },
  {
    id: 2,
    title: 'Dashboard Ventes',
    description: 'Tableau de bord interactif pour suivre les performances commerciales.',
    thumbnail: 'https://images.pexels.com/photos/669615/pexels-photo-669615.jpeg?auto=compress&cs=tinysrgb&w=400',
    lastModified: '2024-12-28',
    views: 189,
    isPublic: false
  },
  {
    id: 3,
    title: 'Carte Géographique',
    description: 'Visualisation des données de vente par région avec heatmap.',
    thumbnail: 'https://images.pexels.com/photos/346796/pexels-photo-346796.jpeg?auto=compress&cs=tinysrgb&w=400',
    lastModified: '2024-12-25',
    views: 312,
    isPublic: true
  }
])

function editProject(id: number) {
  router.push(`/editor/${id}`)
}

function deleteProject(id: number) {
  if (confirm('Êtes-vous sûr de vouloir supprimer ce projet ?')) {
    projects.value = projects.value.filter(p => p.id !== id)
  }
}
</script>