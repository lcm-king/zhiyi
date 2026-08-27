<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps<{
  orderId: number
  startName?: string
  endName?: string
}>()

const mapContainer = ref<HTMLDivElement | null>(null)
const status = ref('初始化地图…')
const progress = ref(0)
const orderStatus = ref('')
const loaded = ref(false)
const currentTemp = ref<number | null>(null)
const coldChain = ref(false)
const tempAlert = ref(false)

let map: any = null
let ws: WebSocket | null = null
let positions: Array<{ lng: number; lat: number }> = []
let currentIndex = 0
let vehicleMarker: any = null
let routeLine: any = null
let startMarker: any = null
let endMarker: any = null
let hubMarker: any = null
let hubPosition: { lng: number; lat: number } | null = null
let routeLoaded = false

// ── 动态加载高德 JS API ─────────────────────────────────
let loadPromise: Promise<void> | null = null

function loadAMap(): Promise<void> {
  if (loadPromise) return loadPromise
  if ((window as any).AMap) {
    loadPromise = Promise.resolve()
    return loadPromise
  }
  loadPromise = new Promise((resolve, reject) => {
    const key = import.meta.env.VITE_AMAP_JS_API_KEY || ''
    if (!key) {
      status.value = '缺少高德 API Key'
      reject(new Error('missing amap key'))
      return
    }
    const cbName = '_amapCallback_' + Date.now()
    ;(window as any)[cbName] = () => {
      delete (window as any)[cbName]
      resolve()
    }
    const script = document.createElement('script')
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${key}&callback=${cbName}&plugin=AMap.MoveAnimation`
    script.onerror = () => { delete (window as any)[cbName]; reject(new Error('amap load failed')) }
    document.head.appendChild(script)
  })
  return loadPromise
}

// ── 初始化高德地图 ───────────────────────────────────────
async function initMap() {
  if (!mapContainer.value) return
  try {
    await loadAMap()
  } catch {
    status.value = '地图加载失败'
    return
  }

  const AMap = (window as any).AMap
  map = new AMap.Map(mapContainer.value, {
    zoom: 12,
    center: [121.38, 31.26],
    mapStyle: 'amap://styles/light',
    resizeEnable: true,
  })

  loaded.value = true
  status.value = '等待配送路线数据…'

  // 如果有已缓存的位置数据，立即绘制
  if (positions.length > 0) {
    drawRoute()
  }
}

// ── 绘制路线和标记 ───────────────────────────────────────
function drawRoute() {
  if (!map || positions.length === 0) return

  const AMap = (window as any).AMap

  // 清除旧标记
  if (startMarker) map.remove(startMarker)
  if (endMarker) map.remove(endMarker)
  if (hubMarker) map.remove(hubMarker)
  if (routeLine) map.remove(routeLine)

  const path = positions.map((p: any) => [p.lng, p.lat])

  // 起点（绿色药房）
  startMarker = new AMap.Marker({
    position: path[0],
    icon: new AMap.Icon({
      size: new AMap.Size(28, 34),
      imageSize: new AMap.Size(28, 34),
      image: createMarkerIcon('#16A34A', '🏪'),
    }),
    offset: new AMap.Pixel(-14, -34),
  })
  startMarker.setLabel({
    content: '药房',
    direction: 'top',
    offset: new AMap.Pixel(0, -12),
    style: {
      fontSize: '11px',
      color: '#16A34A',
      backgroundColor: 'transparent',
      border: 'none',
    },
  })
  map.add(startMarker)

  // 终点（红色收货地址）
  endMarker = new AMap.Marker({
    position: path[path.length - 1],
    icon: new AMap.Icon({
      size: new AMap.Size(28, 34),
      imageSize: new AMap.Size(28, 34),
      image: createMarkerIcon('#DC2626', '📍'),
    }),
    offset: new AMap.Pixel(-14, -34),
  })
  endMarker.setLabel({
    content: '收货',
    direction: 'top',
    offset: new AMap.Pixel(0, -12),
    style: {
      fontSize: '11px',
      color: '#DC2626',
      backgroundColor: 'transparent',
      border: 'none',
    },
  })
  map.add(endMarker)

  // 中转站（琥珀色）
  if (hubPosition) {
    hubMarker = new AMap.Marker({
      position: [hubPosition.lng, hubPosition.lat],
      icon: new AMap.Icon({
        size: new AMap.Size(26, 32),
        imageSize: new AMap.Size(26, 32),
        image: createMarkerIcon('#F59E0B', '中'),
      }),
      offset: new AMap.Pixel(-13, -32),
    })
    hubMarker.setLabel({
      content: '中转站',
      direction: 'top',
      offset: new AMap.Pixel(0, -10),
      style: {
        fontSize: '11px',
        color: '#B45309',
        backgroundColor: 'transparent',
        border: 'none',
      },
    })
    map.add(hubMarker)
  }

  // 已行驶路线
  if (currentIndex > 0) {
    const traveled = path.slice(0, currentIndex + 1)
    routeLine = new AMap.Polyline({
      path: traveled,
      strokeColor: '#3B82F6',
      strokeWeight: 4,
      strokeOpacity: 0.8,
      lineJoin: 'round',
    })
    map.add(routeLine)
  }

  // 全路线（虚线背景）
  const fullLine = new AMap.Polyline({
    path,
    strokeColor: '#CBD5E1',
    strokeWeight: 3,
    strokeOpacity: 0.5,
    strokeStyle: 'dashed',
    lineJoin: 'round',
  })
  map.add(fullLine)

  // 调整视野包含所有点
  map.setFitView(null, false, [60, 60, 60, 60])

  // 移动车辆到当前位置
  moveVehicle()
}

function moveVehicle() {
  if (!map || positions.length === 0) return
  if (currentIndex >= positions.length) return
  if (currentIndex < 0) currentIndex = 0

  const AMap = (window as any).AMap
  const pos = positions[currentIndex]

  if (vehicleMarker) {
    map.remove(vehicleMarker)
  }

  vehicleMarker = new AMap.Marker({
    position: [pos.lng, pos.lat],
    icon: new AMap.Icon({
      size: new AMap.Size(32, 32),
      imageSize: new AMap.Size(32, 32),
      image: createVehicleIcon('#3B82F6'),
    }),
    offset: new AMap.Pixel(-16, -16),
    zIndex: 999,
  })

  // 脉冲波纹效果（用 Circle）
  const pulseCircle = new AMap.Circle({
    center: [pos.lng, pos.lat],
    radius: 300,
    strokeColor: 'rgba(59,130,246,0.3)',
    strokeWeight: 2,
    fillColor: 'rgba(59,130,246,0.08)',
    strokeOpacity: 0.6,
  })
  map.add(pulseCircle)

  vehicleMarker._pulseCircle = pulseCircle
  map.add(vehicleMarker)

  progress.value = ((currentIndex / (positions.length - 1)) * 100)
}

function createMarkerIcon(color: string, emoji: string): string {
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='28' height='34' viewBox='0 0 28 34'>
    <circle cx='14' cy='12' r='12' fill='${color}' opacity='0.15'/>
    <circle cx='14' cy='12' r='9' fill='${color}'/>
    <text x='14' y='16' text-anchor='middle' font-size='11'>${emoji}</text>
    <path d='M14 24 L4 34 L24 34 Z' fill='${color}'/>
  </svg>`
  return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg)
}

function createVehicleIcon(color: string): string {
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='32' height='32' viewBox='0 0 32 32'>
    <circle cx='16' cy='16' r='15' fill='white' stroke='${color}' stroke-width='3'/>
    <circle cx='16' cy='16' r='10' fill='${color}'/>
    <text x='16' y='20' text-anchor='middle' font-size='14' fill='white'>🚚</text>
  </svg>`
  return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg)
}

// ── WebSocket ────────────────────────────────────────────
function connectWS() {
  if (!props.orderId) return
  try {
    const token = localStorage.getItem('zhiyi-token') || ''
    const apiBase = import.meta.env.VITE_API_BASE_URL || '/api'
    let wsHost: string
    if (apiBase.startsWith('http')) {
      wsHost = apiBase.replace(/^http/, 'ws').replace(/\/api$/, '')
    } else {
      const loc = window.location
      wsHost = `ws://${loc.host}`
    }
    const wsUrl = `${wsHost}/api/logistics/ws/${props.orderId}?token=${encodeURIComponent(token)}`
    ws = new WebSocket(wsUrl)

    ws.onopen = () => { if (loaded.value) status.value = '已连接，等待位置数据' }

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        // 冷链温度：任意消息携带 temperature/cold_chain 都更新
        if (typeof msg.temperature === 'number') {
          currentTemp.value = msg.temperature
          tempAlert.value = !!msg.temperature_alert
        }
        if (typeof msg.cold_chain === 'boolean') coldChain.value = msg.cold_chain
        if (msg.type === 'route_overview') {
          status.value = '配送路线已加载'
          // 全量路线一次到位：起点=药房，终点=收货地址，货车只沿这条线移动
          if (Array.isArray(msg.route) && msg.route.length >= 2) {
            positions = msg.route.map((p: any) => ({ lng: p.lng, lat: p.lat }))
            currentIndex = 0
            routeLoaded = true
          }
          if (msg.hub && typeof msg.hub.lng === 'number' && typeof msg.hub.lat === 'number') {
            hubPosition = { lng: msg.hub.lng, lat: msg.hub.lat }
          } else {
            hubPosition = null
          }
          if (loaded.value && positions.length > 0) drawRoute()
        } else if (msg.type === 'cached_position' || msg.type === 'position_update') {
          if (msg.position) {
            const idx = msg.index !== undefined ? msg.index - 1 : -1
            if (routeLoaded && idx >= 0 && idx < positions.length) {
              // 全量路线已加载：按后端索引推进，绝不重复追加导致超界
              currentIndex = idx
            } else {
              positions.push(msg.position)
              currentIndex = positions.length - 1
            }
            progress.value = msg.progress ?? ((currentIndex / Math.max(1, positions.length - 1)) * 100)
            status.value = msg.status || '配送中'
            orderStatus.value = msg.status || ''
            if (loaded.value) {
              if (positions.length <= 2) drawRoute()
              else moveVehicle()
            }
          }
        } else if (msg.type === 'delivery_complete') {
          if (msg.position) {
            if (!routeLoaded) positions.push(msg.position)
            currentIndex = positions.length - 1
          }
          progress.value = 100
          status.value = msg.status || '已送达'
          orderStatus.value = 'delivered'
          // 货车精确停在收货地址（路线最后一点），不再前进
          if (loaded.value && positions.length > 0) {
            drawRoute()
            moveVehicle()
          }
        } else if (msg.type === 'waiting') {
          status.value = msg.message || '等待发货'
        }
      } catch { /* ignore */ }
    }

    ws.onerror = () => { status.value = '连接失败' }
    ws.onclose = () => { if (ws) status.value += '（已断开）' }
  } catch {
    status.value = 'WebSocket 不可用'
  }
}

onMounted(async () => {
  await initMap()
  connectWS()
})

onUnmounted(() => {
  if (ws) { ws.close(); ws = null }
  if (vehicleMarker && vehicleMarker._pulseCircle && map) {
    map.remove(vehicleMarker._pulseCircle)
  }
  if (hubMarker && map) { map.remove(hubMarker); hubMarker = null }
  if (map) { map.destroy(); map = null }
})

watch(() => props.orderId, (val) => {
  if (val) {
    positions = []; currentIndex = 0; progress.value = 0; routeLoaded = false
    if (vehicleMarker && map) { map.remove(vehicleMarker); vehicleMarker = null }
    if (startMarker && map) { map.remove(startMarker); startMarker = null }
    if (endMarker && map) { map.remove(endMarker); endMarker = null }
    if (hubMarker && map) { map.remove(hubMarker); hubMarker = null }
    hubPosition = null
    if (routeLine && map) { map.remove(routeLine); routeLine = null }
    if (ws) { ws.close(); ws = null }
    connectWS()
  }
})
</script>

<template>
  <div class="logistics-wrap">
    <div ref="mapContainer" class="amap-container" />
    <div class="logistics-meta">
      <span class="status-dot" :class="{
        active: currentIndex > 0 && orderStatus !== 'delivered',
        done: orderStatus === 'delivered',
      }" />
      <span>{{ status }}</span>
      <span v-if="coldChain" class="temp-chip" :class="{ alert: tempAlert }">
        {{ tempAlert ? '⚠ 超温' : '❄ 冷链' }}{{ currentTemp !== null ? ' ' + currentTemp.toFixed(1) + '℃' : '' }}
      </span>
      <span v-if="progress > 0 && orderStatus !== 'delivered'" class="progress-text">{{ progress.toFixed(0) }}%</span>
      <span v-if="orderStatus === 'delivered'" class="done-badge">已送达</span>
    </div>
  </div>
</template>

<style scoped>
.logistics-wrap {
  position: relative;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--border-light);
  background: #fff;
  margin-top: 12px;
}
.amap-container {
  width: 100%;
  height: 300px;
}
.temp-chip {
  font-size: 11px;
  font-weight: 700;
  padding: 1px 8px;
  border-radius: 10px;
  background: #E0F2FE;
  color: #0369A1;
}
.temp-chip.alert {
  background: #FEE2E2;
  color: #DC2626;
  animation: temp-blink 1s ease-in-out infinite;
}
@keyframes temp-blink { 50% { opacity: .55; } }
.logistics-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  font-size: 12px;
  color: var(--text-secondary);
  border-top: 1px solid var(--border-light);
}
.status-dot {
  width: 8px; height: 8px; border-radius: 50%; background: #ccc;
}
.status-dot.active { background: #3B82F6; animation: pulse 1.5s infinite; }
.status-dot.done { background: #16A34A; }
.progress-text {
  font-weight: 700; color: #3B82F6;
}
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.done-badge {
  margin-left: auto; font-size: 11px; padding: 2px 8px; border-radius: 4px;
  background: #DCFCE7; color: #16A34A; font-weight: 600;
}
</style>
