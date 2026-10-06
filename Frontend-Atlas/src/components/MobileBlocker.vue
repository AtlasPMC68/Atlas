<template>
  <div class="fixed inset-0 z-[10000] bg-gray-900/95 backdrop-blur-md flex flex-col items-center justify-center p-6 text-center md:hidden">
    <div class="bg-white rounded-2xl shadow-2xl p-8 max-w-sm w-full border border-gray-100 animate-slide-up">
      <div class="w-20 h-20 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-6">
        <svg class="w-10 h-10 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
        </svg>
      </div>
      <h2 class="text-2xl font-bold text-gray-800 mb-3">Écran trop petit</h2>
      <p class="text-gray-600 mb-6 leading-relaxed">
        Atlas est une plateforme conçue pour les ordinateurs. L'écran de votre appareil est trop petit pour afficher les cartes et les données correctement.
      </p>
      <div class="bg-blue-50 text-blue-800 p-4 rounded-xl text-sm font-medium">
        Veuillez vous connecter depuis un ordinateur pour une expérience optimale.
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// Ce composant s'affiche uniquement sur les écrans de téléphone
</script>
