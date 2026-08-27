<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

const canvasRef = ref<HTMLCanvasElement | null>(null)

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  radius: number
  alpha: number
  pulse: number
  pulseSpeed: number
}

let ctx: CanvasRenderingContext2D | null = null
let animationId = 0
let width = 0
let height = 0
let dpr = 1
let particles: Particle[] = []
let reducedMotion = false
const pointer = { x: -9999, y: -9999 }

function palette(): string[] {
  const styles = getComputedStyle(document.documentElement)
  return ['--particle-a', '--particle-b', '--particle-c'].map((name) => {
    const value = styles.getPropertyValue(name).trim()
    if (value) return value
    return 'rgba(96, 165, 250, 0.35)'
  })
}

function seed() {
  const colors = palette()
  const target = Math.min(90, Math.max(32, Math.floor((width * height) / 22000)))
  particles = Array.from({ length: target }, () => ({
    x: Math.random() * width,
    y: Math.random() * height,
    vx: (Math.random() - 0.5) * 0.35,
    vy: -0.08 - Math.random() * 0.22,
    radius: 0.8 + Math.random() * 1.9,
    alpha: 0.18 + Math.random() * 0.4,
    pulse: Math.random() * Math.PI * 2,
    pulseSpeed: 0.005 + Math.random() * 0.012,
  }))
}

function resize() {
  const canvas = canvasRef.value
  if (!canvas) return
  dpr = Math.min(window.devicePixelRatio || 1, 2)
  width = window.innerWidth
  height = window.innerHeight
  canvas.width = Math.floor(width * dpr)
  canvas.height = Math.floor(height * dpr)
  canvas.style.width = `${width}px`
  canvas.style.height = `${height}px`
  ctx = canvas.getContext('2d')
  ctx?.setTransform(dpr, 0, 0, dpr, 0, 0)
  seed()
}

function drawFrame() {
  if (!ctx) return
  const colors = palette()
  ctx.clearRect(0, 0, width, height)

  for (const p of particles) {
    p.x += p.vx
    p.y += p.vy
    p.pulse += p.pulseSpeed
    if (p.x < -24) p.x = width + 24
    if (p.x > width + 24) p.x = -24
    if (p.y < -24) p.y = height + 24
    if (p.y > height + 24) p.y = -24

    const dx = p.x - pointer.x
    const dy = p.y - pointer.y
    const dist2 = dx * dx + dy * dy
    if (dist2 < 14400) {
      const dist = Math.sqrt(dist2) || 1
      const force = ((120 - dist) / 120) * 0.16
      p.x += (dx / dist) * force
      p.y += (dy / dist) * force
    }
  }

  for (let i = 0; i < particles.length; i++) {
    const a = particles[i]
    for (let j = i + 1; j < particles.length; j++) {
      const b = particles[j]
      const dist = Math.hypot(a.x - b.x, a.y - b.y)
      if (dist < 120) {
        const alpha = (1 - dist / 120) * 0.12
        ctx.strokeStyle = `rgba(96, 165, 250, ${alpha.toFixed(3)})`
        ctx.lineWidth = 1
        ctx.beginPath()
        ctx.moveTo(a.x, a.y)
        ctx.lineTo(b.x, b.y)
        ctx.stroke()
      }
    }
  }

  if (pointer.x > -1000) {
    const glow = ctx.createRadialGradient(pointer.x, pointer.y, 0, pointer.x, pointer.y, 160)
    glow.addColorStop(0, 'rgba(59, 130, 246, 0.07)')
    glow.addColorStop(1, 'rgba(59, 130, 246, 0)')
    ctx.fillStyle = glow
    ctx.fillRect(pointer.x - 160, pointer.y - 160, 320, 320)
  }

  particles.forEach((p, index) => {
    const alpha = p.alpha * (0.75 + 0.25 * Math.sin(p.pulse))
    ctx!.globalAlpha = Math.max(0.06, alpha)
    ctx!.fillStyle = colors[index % colors.length]
    ctx!.beginPath()
    ctx!.arc(p.x, p.y, p.radius, 0, Math.PI * 2)
    ctx!.fill()
  })
  ctx.globalAlpha = 1

  animationId = requestAnimationFrame(drawFrame)
}

function stop() {
  cancelAnimationFrame(animationId)
}

function start() {
  stop()
  if (reducedMotion) {
    drawFrame()
    cancelAnimationFrame(animationId)
    return
  }
  animationId = requestAnimationFrame(drawFrame)
}

function onVisibility() {
  if (document.hidden) stop()
  else start()
}

function onPointerMove(event: PointerEvent) {
  pointer.x = event.clientX
  pointer.y = event.clientY
}

onMounted(() => {
  const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  reducedMotion = motionQuery.matches
  resize()
  start()
  window.addEventListener('resize', resize)
  window.addEventListener('pointermove', onPointerMove, { passive: true })
  document.addEventListener('visibilitychange', onVisibility)
})

onBeforeUnmount(() => {
  stop()
  window.removeEventListener('resize', resize)
  window.removeEventListener('pointermove', onPointerMove)
  document.removeEventListener('visibilitychange', onVisibility)
})
</script>

<template>
  <canvas ref="canvasRef" class="particle-field" aria-hidden="true" />
</template>
