<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { CreditCard, CircleCheck, Clock, Refresh } from '@element-plus/icons-vue'
import LogisticsMap from '@/components/LogisticsMap.vue'
import { getExamOrders, getDrugOrders } from '@/api'

const orders = ref<any[]>([])
const loading = ref(true)
const debugInfo = ref('')
const filter = ref<'all' | 'pending' | 'paid'>('all')
const keyword = ref('')
const logOpen = ref<Set<string>>(new Set())
let payWindow: Window | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8002/api'
const route = useRoute()
keyword.value = typeof route.query.q === 'string' ? route.query.q : ''

async function loadOrders(silent = false) {
  if (!silent) loading.value = true
  try {
    const token = localStorage.getItem('zhiyi-token') || ''
    if (!token) { ElMessage.error('请先登录'); return }

    const [exams, drugs] = await Promise.all([
      getExamOrders().catch((e: any) => { console.warn('检查订单获取失败:', e); return [] }),
      getDrugOrders().catch((e: any) => { console.warn('药品订单获取失败:', e); return [] }),
    ])

    const examArr = Array.isArray(exams) ? exams : []
    const drugArr = Array.isArray(drugs) ? drugs : []

    const all = [
      ...examArr.map((o: any) => ({
        id: o.order_id, orderNo: o.order_no, type: 'exam',
        payStatus: o.status, deliveryStatus: '',
        items: (o.items || []).map((i: any) => ({ name: i.name || '', qty: 1 })),
        total: o.total_price || 0, created: o.created_at || o.appointment_time || '',
      })),
      ...drugArr.map((o: any) => {
        const items = (o.items || []).map((i: any) => ({
          name: i.drug_name || '', qty: i.quantity || 1,
          need_cold_chain: !!i.need_cold_chain,
        }))
        return {
          id: o.id, orderNo: o.order_no, type: 'drug',
          payStatus: o.pay_status || 'pending', deliveryStatus: o.delivery_status || '',
          address: o.address || '',
          items,
          coldChain: items.some((it: any) => it.need_cold_chain),
          total: o.total_price || 0, created: o.created_at || '',
        }
      }),
    ].sort((a, b) => new Date(b.created || '').getTime() - new Date(a.created || '').getTime())

    debugInfo.value = `已加载: 检查 ${examArr.length} 条 + 药品 ${drugArr.length} 条，共 ${all.length} 条`
    orders.value = all
  } catch (e: any) {
    debugInfo.value = '加载失败: ' + (e.message || String(e))
    if (!silent) ElMessage.error('加载订单失败: ' + (e.message || '网络异常'))
  } finally {
    loading.value = false
  }
}

const filtered = computed(() => {
  let list = orders.value
  if (filter.value === 'pending') list = list.filter(o => o.payStatus === 'pending')
  if (filter.value === 'paid') list = list.filter(o => o.payStatus !== 'pending')
  const k = keyword.value.trim().toLowerCase()
  if (k) {
    list = list.filter((o: any) =>
      String(o.orderNo || '').toLowerCase().includes(k)
      || String(o.address || '').toLowerCase().includes(k)
      || (o.items || []).some((i: any) => String(i.name || '').toLowerCase().includes(k))
    )
  }
  return list
})
const pendingCount = computed(() => orders.value.filter(o => o.payStatus === 'pending').length)
const paidCount = computed(() => orders.value.filter(o => o.payStatus !== 'pending').length)

function openPayWindow(order: any) {
  const token = localStorage.getItem('zhiyi-token') || ''
  const items = (order.items || []).map((i: any) => i.name).join('、')
  const url = `/pay.html?order_id=${order.id}&type=${order.type}&order_no=${encodeURIComponent(order.orderNo)}&amount=${order.total || 0}&items=${encodeURIComponent(items)}&token=${encodeURIComponent(token)}&api=${encodeURIComponent(API_BASE)}`
  payWindow = window.open(url, 'zhiyi-pay', 'width=460,height=580,left=' + ((screen.width - 460) / 2) + ',top=' + ((screen.height - 580) / 3))
}

// 监听支付完成消息
window.addEventListener('message', (e) => {
  if (e.data?.type === 'payment-done') {
    ElMessage.success('支付成功！订单已更新')
    loadOrders()
  }
})

function toggleLog(orderNo: string) {
  const s = new Set(logOpen.value); s.has(orderNo) ? s.delete(orderNo) : s.add(orderNo); logOpen.value = s
}
function fmtDate(d: string) { return d ? d.slice(0, 16).replace('T', ' ') : '' }
function logisticsTimeline(status: string) {
  const stages = [
    { key: 'pending', desc: '已支付，待发货' },
    { key: 'shipped', desc: '已出库，运输中' },
    { key: 'delivered', desc: '已送达' },
  ]
  const idx = stages.findIndex(s => s.key === (status || 'pending'))
  return stages.map((s, i) => ({ ...s, active: i <= idx }))
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
  <div class="orders-page">
    <div class="page-heading">
      <div>
        <div class="eyebrow">订单中心</div>
        <h1>订单与物流</h1>
        <p>检查预约、药品订单、支付与物流追踪一站式管理。</p>
      </div>
      <button class="refresh-btn" :disabled="loading" @click="() => loadOrders()"><Refresh /> {{ loading ? '刷新中…' : '刷新' }}</button>
    </div>

    <div class="stats-row">
      <div class="stat-card"><strong>{{ orders.length }}</strong><span>全部订单</span></div>
      <div class="stat-card warn"><strong>{{ pendingCount }}</strong><span>待支付</span></div>
      <div class="stat-card ok"><strong>{{ paidCount }}</strong><span>已完成</span></div>
    </div>

    <div class="order-filters">
      <button :class="{ active: filter === 'all' }" @click="filter = 'all'">全部 {{ orders.length }}</button>
      <button :class="{ active: filter === 'pending' }" @click="filter = 'pending'">待支付 {{ pendingCount }}</button>
      <button :class="{ active: filter === 'paid' }" @click="filter = 'paid'">已完成 {{ paidCount }}</button>
    </div>

    <div v-if="debugInfo" class="debug-bar">{{ debugInfo }}</div>

    <div v-if="loading" class="empty-state"><span class="spinner" /> 加载中…</div>
    <div v-else-if="!filtered.length" class="empty-state">
      <p v-if="keyword.trim()">未找到与「{{ keyword.trim() }}」相关的订单</p>
      <p v-else-if="filter !== 'all'">暂无此类订单</p>
      <p v-else>暂无订单，前往「检查与购药」页面下单后请点击右上角刷新按钮查看最新订单</p>
    </div>

    <div v-else class="order-cards">
      <article v-for="o in filtered" :key="o.orderNo + o.type" class="order-card">
        <div class="oc-top">
          <div class="oc-top-left">
            <span class="oc-type" :class="o.type">{{ o.type === 'exam' ? '检查' : '药品' }}</span>
            <span v-if="o.coldChain" class="oc-type cold">❄ 冷链</span>
            <strong>{{ o.orderNo }}</strong>
          </div>
          <span class="oc-date">{{ fmtDate(o.created) }}</span>
        </div>
        <div class="oc-body">
          <div class="oc-item-list">
            <span v-for="(it,i) in (o.items||[]).slice(0,4)" :key="i" class="oc-item-tag">{{ it.name }}<template v-if="it.qty>1"> ×{{ it.qty }}</template></span>
          </div>
          <div class="oc-total"><small>合计</small><strong>&yen;{{ (o.total||0).toFixed(2) }}</strong></div>
        </div>

        <div v-if="o.type==='drug' && o.payStatus!=='pending'" class="oc-logistics">
          <div class="log-header" @click="toggleLog(o.orderNo)">
            <span>物流追踪</span><span class="log-toggle">{{ logOpen.has(o.orderNo) ? '收起 ▲' : '展开 ▼' }}</span>
          </div>
          <div v-if="logOpen.has(o.orderNo)" class="log-timeline">
            <div v-for="s in logisticsTimeline(o.deliveryStatus)" :key="s.key" class="log-node" :class="{ done: s.active }">
              <div class="log-dot"><CircleCheck v-if="s.active" /><Clock v-else /></div>
              <div class="log-info"><strong>{{ s.desc }}</strong></div>
            </div>
            <div class="log-addr" v-if="o.address">配送至：{{ o.address }}</div>
            <LogisticsMap
              v-if="o.type === 'drug' && o.deliveryStatus === 'shipped'"
              :order-id="o.id"
            />
          </div>
        </div>

        <div class="oc-footer">
          <span class="oc-pay-status" :class="o.payStatus==='pending'?'badge-pending':'badge-done'">{{ o.payStatus==='pending'?'待支付':'已支付' }}</span>
          <button v-if="o.payStatus==='pending'" class="btn-pay" @click="openPayWindow(o)"><CreditCard /> 去支付</button>
          <span v-else class="done-mark"><CircleCheck /> 已完成</span>
        </div>
      </article>
    </div>
  </div>
</template>

<style scoped>
.orders-page { max-width: 900px; margin: 0 auto; padding: 24px; }
.page-heading { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.eyebrow { font-size: 12px; color: var(--primary); letter-spacing: .06em; text-transform: uppercase; }
.page-heading h1 { margin: 4px 0 6px; font-size: 22px; font-weight: 700; }
.page-heading p { margin: 0; color: var(--text-secondary); font-size: 14px; }
.refresh-btn { display: flex; align-items: center; gap: 4px; padding: 8px 18px; border-radius: 8px; border: 1px solid var(--border-light); background: #fff; cursor: pointer; font-size: 13px; font-weight: 600; color: var(--primary); }
.refresh-btn:hover { background: var(--primary-soft); }
.refresh-btn:disabled { opacity: .5; cursor: not-allowed; }

.stats-row { display: grid; grid-template-columns: repeat(3,1fr); gap: 12px; margin-bottom: 20px; }
.stat-card { background: #fff; border-radius: 12px; padding: 14px 18px; border: 1px solid var(--border-light); }
.stat-card strong { display: block; font-size: 24px; font-weight: 800; }
.stat-card span { font-size: 12px; color: var(--text-tertiary); }
.stat-card.warn strong { color: #D97706; }
.stat-card.ok strong { color: #16A34A; }

.order-filters { display: flex; gap: 6px; margin-bottom: 16px; }
.order-filters button { padding: 6px 14px; border-radius: 7px; border: 1px solid var(--border-light); background: #fff; font-size: 13px; cursor: pointer; }
.order-filters button.active { background: var(--primary); color: #fff; border-color: var(--primary); }

.empty-state { text-align: center; padding: 60px 20px; color: var(--text-tertiary); font-size: 14px; }
.spinner { display: inline-block; width: 18px; height: 18px; border: 2px solid #e2e8f0; border-top-color: var(--primary); border-radius: 50%; animation: spin .6s linear infinite; vertical-align: middle; margin-right: 8px; }
@keyframes spin { to { transform: rotate(360deg); } }

.order-cards { display: flex; flex-direction: column; gap: 10px; }
.order-card { background: #fff; border-radius: 14px; border: 1px solid var(--border-light); padding: 16px 20px; }

.oc-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.oc-top-left { display: flex; align-items: center; gap: 10px; }
.oc-type { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 5px; }
.oc-type.exam { background: #DBEAFE; color: #2563EB; }
.oc-type.drug { background: #DCFCE7; color: #16A34A; }
.oc-type.cold { background: #E0F2FE; color: #0369A1; }
.oc-top-left strong { font-size: 14px; }
.oc-date { font-size: 12px; color: var(--text-tertiary); }

.oc-body { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.oc-item-list { display: flex; flex-wrap: wrap; gap: 4px; }
.oc-item-tag { font-size: 12px; padding: 2px 8px; border-radius: 4px; background: var(--gray-100); color: var(--text-secondary); }
.oc-total { text-align: right; white-space: nowrap; }
.oc-total small { display: block; font-size: 10px; color: var(--text-tertiary); }
.oc-total strong { font-size: 17px; font-weight: 800; }

.oc-logistics { margin: 8px 0; border-top: 1px dashed var(--border-light); padding-top: 8px; }
.log-header { display: flex; justify-content: space-between; font-size: 12px; color: var(--primary); cursor: pointer; padding: 4px 0; }
.log-toggle { font-size: 11px; color: var(--text-tertiary); }
.log-timeline { margin-top: 8px; padding-left: 4px; }
.log-node { display: flex; gap: 10px; padding: 4px 0; font-size: 12px; color: var(--text-tertiary); }
.log-node.done { color: var(--text-primary); }
.log-dot { flex-shrink: 0; width: 18px; text-align: center; }
.log-node.done .log-dot { color: #16A34A; }
.log-info strong { display: block; font-size: 13px; }
.log-addr { margin-top: 6px; font-size: 11px; color: var(--text-tertiary); display: flex; align-items: center; gap: 4px; }

.oc-footer { display: flex; justify-content: space-between; align-items: center; padding-top: 10px; border-top: 1px solid var(--border-light); }
.oc-pay-status { font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 6px; }
.badge-pending { background: #FEF3C7; color: #D97706; }
.badge-done { background: #DCFCE7; color: #16A34A; }
.btn-pay { display: flex; align-items: center; gap: 5px; padding: 7px 20px; border: none; border-radius: 8px; background: var(--primary); color: #fff; font-size: 13px; font-weight: 600; cursor: pointer; }
.btn-pay:hover { background: var(--primary-hover); }
.done-mark { font-size: 13px; color: #16A34A; font-weight: 600; display: flex; align-items: center; gap: 4px; }

.debug-bar {
  padding: 8px 14px;
  margin-bottom: 12px;
  background: #FEF3C7;
  border: 1px solid #FCD34D;
  border-radius: 8px;
  font-size: 12px;
  color: #92400E;
  font-family: monospace;
}
</style>
