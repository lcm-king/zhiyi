<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import ParticleField from '@/components/ParticleField.vue'

const auth = useAuthStore()
const cleanups: Array<() => void> = []

onMounted(() => {
  auth.restore()

  const syncSpotlight = (event: PointerEvent) => {
    const root = document.documentElement
    root.style.setProperty('--spot-x', `${event.clientX}px`)
    root.style.setProperty('--spot-y', `${event.clientY}px`)
  }
  const syncTopbar = () => {
    const scrolled = window.scrollY > 8
    document.querySelectorAll('.topbar').forEach((el) => el.classList.toggle('is-scrolled', scrolled))
  }

  window.addEventListener('pointermove', syncSpotlight, { passive: true })
  window.addEventListener('scroll', syncTopbar, { passive: true })
  cleanups.push(() => window.removeEventListener('pointermove', syncSpotlight))
  cleanups.push(() => window.removeEventListener('scroll', syncTopbar))
})

onBeforeUnmount(() => {
  cleanups.forEach((cleanup) => cleanup())
})
</script>

<template>
  <div class="app-root">
    <ParticleField />
    <router-view />
  </div>
</template>
