<script setup lang="ts">
import {
  ClockIcon,
  LightBulbIcon,
  MapIcon,
  UserCircleIcon,
} from "@heroicons/vue/24/outline";
</script>

<template>
  <div class="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
    <div class="text-center mb-12">
      <h1 class="text-4xl font-semibold tracking-tight text-gray-900">
        À propos d'Atlas
      </h1>

      <p class="mt-4 max-w-2xl mx-auto text-lg text-gray-500 leading-relaxed">
        Une plateforme collaborative pour créer, organiser et partager du
        matériel cartographique adapté à l'enseignement de
        l'histoire-géographie.
      </p>
    </div>

    <section
      class="bg-white border border-gray-200 rounded-xl shadow-sm p-6 sm:p-8 mb-6"
    >
      <div class="flex items-center gap-3 mb-4">
        <div
          class="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center text-blue-600"
        >
          <MapIcon class="h-5 w-5" />
        </div>

        <h2 class="text-2xl font-semibold text-gray-900">Le problème</h2>
      </div>

      <p class="text-gray-600 leading-relaxed">
        Les enseignants d'histoire-géographie ont souvent de la difficulté à
        trouver des cartes adaptées à leurs cours. Les cartes disponibles sont
        parfois trop chargées ou utilisent des représentations visuelles
        différentes, ce qui peut nuire à la clarté et à la compréhension des
        élèves.
      </p>
    </section>

    <section
      class="bg-white border border-gray-200 rounded-xl shadow-sm p-6 sm:p-8 mb-6"
    >
      <div class="flex items-center gap-3 mb-4">
        <div
          class="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center text-blue-600"
        >
          <LightBulbIcon class="h-5 w-5" />
        </div>

        <h2 class="text-2xl font-semibold text-gray-900">Notre solution</h2>
      </div>

      <p class="text-gray-600 leading-relaxed">
        Atlas permet d'importer des cartes géographiques, d'en extraire le
        contenu et de le repositionner sur un référentiel uniforme. Les
        différents territoires peuvent ainsi être représentés de manière
        cohérente au sein d'une même interface.
      </p>
    </section>

    <section
      class="bg-white border border-gray-200 rounded-xl shadow-sm p-6 sm:p-8 mb-6"
    >
      <div class="flex items-center gap-3 mb-4">
        <div
          class="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center text-blue-600"
        >
          <ClockIcon class="h-5 w-5" />
        </div>

        <h2 class="text-2xl font-semibold text-gray-900">
          Une histoire interactive
        </h2>
      </div>

      <p class="text-gray-600 leading-relaxed">
        Grâce à une ligne du temps interactive, Atlas permet de suivre
        l'évolution des territoires à travers différentes périodes historiques.
        Les changements territoriaux peuvent ainsi être visualisés de façon
        fluide et cohérente, sans avoir à jongler entre plusieurs sources.
      </p>
    </section>

    <section
      class="bg-white border border-gray-200 rounded-xl shadow-sm p-6 sm:p-8"
    >
      <div class="flex items-center gap-3 mb-4">
        <div
          class="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center text-blue-600"
        >
          <UserCircleIcon class="h-5 w-5" />
        </div>

        <h2 class="text-2xl font-semibold text-gray-900">
          Un projet collaboratif
        </h2>
      </div>

      <p class="text-gray-600 leading-relaxed">
        Atlas est un projet open source qui vise à remplacer les échanges
        informels de matériel didactique par une bibliothèque collaborative
        structurée. Les enseignants peuvent ainsi personnaliser et partager
        gratuitement du matériel de qualité adapté à leurs besoins pédagogiques.
      </p>
    </section>

    <div class="mt-10 text-center">
      <p class="text-sm font-medium text-blue-600">Atlas</p>

      <p class="mt-2 text-gray-500">
        Simplifier la création et le partage de cartes historiques.
      </p>
    </div>
  </div>
</template>
