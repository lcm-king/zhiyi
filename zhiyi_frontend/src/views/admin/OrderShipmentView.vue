<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, CircleCheck, Clock, Van } from '@element-plus/icons-vue'
import { shipAdminOrder } from '@/api'

interface AdminOrder { id: number; order_no: string; patient_name?: string; status?: string; pay_status: string; delivery_status: string; total_price: number; address: string; items: Array<{ drug_name: string; quantity: number }>; created_at: string }

const orders = ref<AdminOrder[]>([])
const loading = ref(true)
const activeFilter = ref<'pending' | 'tobe' | 'shipped' | 'delivered' | 'all'>('pending')
const keyword = ref('')
const shippingId = ref<number | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null

const route = useRoute()
keyword.value = typeof route.query.q === 'string' ? route.query.q : ''

async function loadOrders(silent = false) {
  if (!silent) loading.value = true
  try {
    const token = localStorage.getItem('zhiyi-token') || ''
    const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'
    const resp = await fetch(`${apiBase}/admin/orders`, { headers: { Authorization: `Bearer ${token}` } })
    orders.value = resp.ok ? await resp.json() : []
  } catch { if (!silent) ElMessage.error('加载失败') }
  finally { loading.value = false }
}

const filtered = computed(() => {
  let list = orders.value
  if (activeFilter.value === 'pending') list = list.filter(o => o.pay_status === 'pending')
  if (activeFilter.value === 'tobe') list = list.filter(o => o.pay_status === 'paid' && o.delivery_status === 'pending')
  if (activeFilter.value === 'shipped') list = list.filter(o => o.delivery_status === 'shipped')
  if (activeFilter.value === 'delivered') list = list.filter(o => o.delivery_status === 'delivered')
  const k = keyword.value.trim().toLowerCase()
  if (k) {
    list = list.filter(o =>
      String(o.order_no || '').toLowerCase().includes(k)
      || String(o.patient_name || '').toLowerCase().includes(k)
      || String(o.address || '').toLowerCase().includes(k)
    )
  }
  return list
})

const pendingCount = computed(() => orders.value.filter(o => o.pay_status === 'pending').length)
const toBeShippedCount = computed(() => orders.value.filter(o => o.pay_status === 'paid' && o.delivery_status === 'pending').length)
const shippedCount = computed(() => orders.value.filter(o => o.delivery_status === 'shipped').length)
const deliveredCount = computed(() => orders.value.filter(o => o.delivery_status === 'delivered').length)

async function shipOrder(o: AdminOrder) {
  try {
    await ElMessageBox.confirm(`确认对订单 ${o.order_no} 发货？`, '发货确认', {
      confirmButtonText: '确认发货',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  shippingId.value = o.id
  try {
    await shipAdminOrder(o.id)
    ElMessage.success('发货成功，配送路径已生成')
    await loadOrders()
  } catch (e: any) {
    ElMessage.error(e.message || '发货失败')
  } finally {
    shippingId.value = null
  }
}

onMounted(() => {
  loadOrders()
  pollTimer = setInterval(() => loadOrders(true), 30000)
})

watch(
  () => route.query.q,
  (v) => { if (typeof v === 'string') keyword.value = v },
)

onUnmounted(() => {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
})
</script>
<template>
  <div class="ship-page">
    <div class="ship-head">
      <div>
        <h1>订单发货</h1>
        <p>管理已支付订单的发货与配送状态，实时追踪物流</p>
      </div>
      <button class="refresh-btn" @click="() => loadOrders()"><Refresh /> 刷新</button>
    </div>

    <div class="stats-row">
      <div class="stat-card warn"><strong>{{ pendingCount }}</strong><span>待支付</span></div>
      <div class="stat-card ship"><strong>{{ toBeShippedCount }}</strong><span>待发货</span></div>
      <div class="stat-card"><strong>{{ shippedCount }}</strong><span>配送中</span></div>
      <div class="stat-card ok"><strong>{{ deliveredCount }}</strong><span>已送达</span></div>
    </div>

    <div class="filters">
      <button :class="{ active: activeFilter === 'all' }" @click="activeFilter = 'all'">全部 {{ orders.length }}</button>
      <button :class="{ active: activeFilter === 'pending' }" @click="activeFilter = 'pending'">待支付 {{ pendingCount }}</button>
      <button :class="{ active: activeFilter === 'tobe' }" @click="activeFilter = 'tobe'">待发货 {{ toBeShippedCount }}</button>
      <button :class="{ active: activeFilter === 'shipped' }" @click="activeFilter = 'shipped'">配送中 {{ shippedCount }}</button>
      <button :class="{ active: activeFilter === 'delivered' }" @click="activeFilter = 'delivered'">已送达 {{ deliveredCount }}</button>
    </div>

    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="!filtered.length" class="empty">暂无此类订单</div>
    <div v-else class="order-list">
      <div v-for="o in filtered" :key="o.id" class="order-row">
        <div class="order-top">
          <strong>{{ o.order_no }}</strong>
          <span class="tag" :class="{ pending: o.pay_status === 'pending', tobe: o.pay_status === 'paid' && o.delivery_status === 'pending', shipped: o.delivery_status === 'shipped', delivered: o.delivery_status === 'delivered' }">
            {{ o.delivery_status === 'delivered' ? '已送达' : o.delivery_status === 'shipped' ? '配送中' : o.pay_status === 'paid' ? '待发货' : '待支付' }}
          </span>
          <span class="price">¥{{ o.total_price?.toFixed(2) }}</span>
        </div>
        <div class="order-items">
          <span v-for="it in (o.items || []).slice(0, 4)" :key="it.drug_name" class="item-tag">{{ it.drug_name }} ×{{ it.quantity }}</span>
        </div>
        <div class="order-bottom">
          <small class="addr">{{ o.address || '—' }}</small>
          <div class="bottom-right">
            <span v-if="o.delivery_status === 'delivered'" class="done"><CircleCheck /> 已送达</span>
            <span v-else-if="o.delivery_status === 'shipped'" class="shipping"><Clock /> 配送中</span>
            <span v-else-if="o.pay_status === 'paid'" class="tobe"><Van /> 待发货</span>
            <span v-else class="wait">等待支付</span>
            <button
              v-if="o.pay_status === 'paid' && o.delivery_status === 'pending'"
              class="ship-btn"
              :disabled="shippingId === o.id"
              @click="shipOrder(o)"
            >
              <Van /> {{ shippingId === o.id ? '发货中…' : '确认发货' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
<style scoped>
.ship-page { max-width: 800px; margin: 0 auto; padding: 24px; }
.ship-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.ship-head h1 { font-size: 22px; font-weight: 700; margin-bottom: 4px; }
.ship-head p { margin: 0; color: var(--text-secondary); font-size: 14px; }
.refresh-btn { display: flex; align-items: center; gap: 4px; padding: 7px 14px; border-radius: 8px; border: 1px solid var(--border-light); background: #fff; cursor: pointer; font-size: 12px; }

.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
.stat-card { background: #fff; border-radius: 12px; padding: 14px 18px; border: 1px solid var(--border-light); }
.stat-card strong { display: block; font-size: 24px; font-weight: 800; }
.stat-card span { font-size: 12px; color: var(--text-tertiary); }
.stat-card.warn strong { color: #D97706; }
.stat-card.ship strong { color: #2563EB; }
.stat-card.ok strong { color: #16A34A; }

.filters { display: flex; gap: 6px; margin-bottom: 16px; }
.filters button { padding: 6px 14px; border-radius: 7px; border: 1px solid var(--border-light); background: #fff; font-size: 13px; cursor: pointer; }
.filters button.active { background: var(--primary); color: #fff; border-color: var(--primary); }
.order-list { display: flex; flex-direction: column; gap: 10px; }
.order-row { background: #fff; border-radius: 14px; padding: 16px 18px; border: 1px solid var(--border-light); }
.order-top { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.order-top strong { font-size: 14px; }
.tag { font-size: 10px; padding: 2px 8px; border-radius: 4px; }
.tag.pending { background: #FEF3C7; color: #D97706; }
.tag.tobe { background: #DBEAFE; color: #2563EB; }
.tag.shipped { background: #DBEAFE; color: #2563EB; }
.tag.delivered { background: #DCFCE7; color: #16A34A; }
.price { margin-left: auto; font-weight: 800; font-size: 16px; }
.order-items { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
.item-tag { font-size: 11px; padding: 2px 7px; border-radius: 4px; background: var(--gray-100); color: var(--text-secondary); }
.order-bottom { display: flex; align-items: center; justify-content: space-between; }
.addr { display: flex; align-items: center; gap: 4px; font-size: 11px; color: var(--text-tertiary); }
.bottom-right { display: flex; align-items: center; gap: 10px; }
.done { font-size: 13px; color: #16A34A; font-weight: 600; display: flex; align-items: center; gap: 4px; }
.shipping { font-size: 13px; color: #2563EB; font-weight: 600; display: flex; align-items: center; gap: 4px; }
.tobe { font-size: 13px; color: #2563EB; font-weight: 600; display: flex; align-items: center; gap: 4px; }
.wait { font-size: 12px; color: var(--text-tertiary); }
.ship-btn { display: inline-flex; align-items: center; gap: 4px; padding: 6px 14px; border-radius: 7px; border: none; background: var(--primary, #2563EB); color: #fff; font-size: 12px; font-weight: 600; cursor: pointer; }
.ship-btn svg { width: 13px; }
.ship-btn:disabled { opacity: .55; cursor: not-allowed; }
.empty { text-align: center; padding: 60px; color: var(--text-tertiary); font-size: 14px; }
</style>
