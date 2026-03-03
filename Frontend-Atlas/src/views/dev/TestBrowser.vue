<script setup lang="ts">
import { useRouter } from "vue-router";

const router = useRouter();

const createNewTest = () => {
  router.push({ path: "/demo/upload-test" });
};
</script>

<template>
  <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
    <button class="btn btn-primary" @click="createNewTest">
      Create new test
    </button>
  </div>
</template>
