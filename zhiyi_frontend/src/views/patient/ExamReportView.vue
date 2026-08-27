<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Document, Refresh, DataLine } from '@element-plus/icons-vue'
import { renderMarkdown } from '@/utils/markdown'

interface Report {
  appointment_id: number; exam_name: string; status: string
  report_url?: string; report_data?: any; has_report: boolean; ai_interpretation?: string
}
interface Order { order_id: number; order_no: string; items: any[]; status?: string; created_at?: string }

const orders = ref<Order[]>([])
const loading = ref(true)
const selectedOrder = ref<Order | null>(null)
const reports = ref<Report[]>([])
const reportLoading = ref(false)
let pollTimer: ReturnType<typeof setInterval> | null = null

const STATUS_MAP: Record<string, { text: string; cls: string }> = {
  pending: { text: '待支付', cls: 'st-pending' },
  paid: { text: '报告生成中', cls: 'st-paid' },
  confirmed: { text: '已确认', cls: 'st-confirmed' },
  completed: { text: '报告已出', cls: 'st-completed' },
  cancelled: { text: '已取消', cls: 'st-cancelled' },
}
function statusInfo(status?: string) {
  return STATUS_MAP[status || ''] || { text: status || '未知', cls: 'st-default' }
}

async function loadOrders(silent = false) {
  if (!silent) loading.value = true
  try {
    const token = localStorage.getItem('zhiyi-token') || ''
    const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'
    const resp = await fetch(`${apiBase}/exams/orders`, { headers: { Authorization: `Bearer ${token}` } })
    orders.value = resp.ok ? (await resp.json()) : []
    if (!selectedOrder.value && orders.value.length) {
      viewReport(orders.value[0])
    } else if (selectedOrder.value) {
      const fresh = orders.value.find(o => o.order_id === selectedOrder.value?.order_id)
      if (fresh) viewReport(fresh, true)
    }
  } catch { if (!silent) ElMessage.error('加载订单失败') }
  finally { loading.value = false }
}

async function viewReport(order: Order, silent = false) {
  selectedOrder.value = order
  if (!silent) reportLoading.value = true
  try {
    const token = localStorage.getItem('zhiyi-token') || ''
    const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'
    const resp = await fetch(`${apiBase}/exams/orders/${order.order_id}/report`, { headers: { Authorization: `Bearer ${token}` } })
    const data = await resp.json()
    reports.value = data.reports || []
  } catch { reports.value = [] }
  finally { reportLoading.value = false }
}

function fmtDate(d?: string) { return d ? d.slice(0, 10) : '' }
function itemNames(order: Order) {
  return (order.items || []).map((i: any) => i.name || i.exam_name || '').filter(Boolean).slice(0, 2).join('、')
}
const reportCount = computed(() => reports.value.filter(r => r.has_report).length)

onMounted(() => {
  loadOrders()
  pollTimer = setInterval(() => loadOrders(true), 30000)
})

onUnmounted(() => {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
})
</script>
<template>
  <div class="reports-page">
    <div class="rp-head">
      <div>
        <h1>检查报告</h1>
        <p>查看历史检查报告与 AI 解读</p>
      </div>
      <button class="refresh-btn" @click="() => loadOrders()"><Refresh /> 刷新</button>
    </div>

    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="!orders.length" class="empty">
      <Document style="width:44px;height:44px;opacity:.3;margin-bottom:10px" />
      <p>暂无检查报告，请先预约检查</p>
    </div>
    <div v-else class="rp-layout">
      <aside class="order-list">
        <div class="order-list-head">
          <span>检查单</span>
          <span class="order-count">{{ orders.length }}</span>
        </div>
        <div class="order-scroll">
          <div
            v-for="o in orders"
            :key="o.order_id"
            class="order-row"
            :class="{ active: selectedOrder?.order_id === o.order_id }"
            @click="viewReport(o)"
          >
            <div class="or-top">
              <strong>{{ o.order_no }}</strong>
              <span class="badge" :class="statusInfo(o.status).cls">{{ statusInfo(o.status).text }}</span>
            </div>
            <div class="or-mid">
              <span>{{ fmtDate(o.created_at) }}</span>
              <span v-if="itemNames(o)" class="or-items">{{ itemNames(o) }}</span>
            </div>
          </div>
        </div>
      </aside>

      <main class="report-detail">
        <div v-if="selectedOrder" class="detail-toolbar">
          <span class="dt-order">{{ selectedOrder.order_no }}</span>
          <span class="dt-stats">{{ reports.length }} 项检查 · {{ reportCount }} 项报告已出</span>
        </div>

        <div v-if="!selectedOrder" class="empty">选择左侧检查单查看报告</div>
        <div v-else-if="reportLoading" class="empty">加载报告中…</div>
        <div v-else-if="!reports.length" class="empty">该订单暂无报告</div>
        <div v-else class="report-stack">
          <div v-for="r in reports" :key="r.appointment_id" class="report-card">
            <div class="report-card-head">
              <div class="rc-title">
                <span class="rc-dot" :class="r.has_report ? 'ok' : 'waiting'" />
                <strong>{{ r.exam_name }}</strong>
              </div>
              <span class="badge" :class="statusInfo(r.status).cls">{{ statusInfo(r.status).text }}</span>
            </div>

            <div v-if="!r.has_report" class="report-waiting">
              <span class="pulse-dot" />
              <div>
                <strong>报告生成中</strong>
                <small>支付完成后报告通常会在几分钟内生成，页面每 30 秒自动刷新</small>
              </div>
            </div>

            <template v-else>
              <div v-if="r.ai_interpretation" class="report-interpret">
                <div class="interpret-label"><DataLine /> AI 解读</div>
                <p v-html="renderMarkdown(r.ai_interpretation)"></p>
              </div>
              <div v-if="r.report_data?.metrics?.length" class="report-metrics">
                <div class="metric-header"><span>检查项目</span><span>结果</span><span>参考范围</span></div>
                <div v-for="m in r.report_data.metrics" :key="m.name" class="metric-row">
                  <span class="metric-name">{{ m.name }}</span>
                  <span class="metric-value" :class="{ abnormal: m.status !== 'normal' }">{{ m.value }} {{ m.unit || '' }}</span>
                  <span class="metric-ref">{{ m.reference_range || '—' }}</span>
                </div>
              </div>
              <div v-if="r.report_data?.summary" class="report-summary" v-html="renderMarkdown(r.report_data.summary)"></div>
            </template>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>
<style scoped>
.reports-page { max-width: 1040px; margin: 0 auto; padding: 24px; }
.rp-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.rp-head h1 { font-size: 22px; font-weight: 700; margin-bottom: 4px; }
.rp-head p { margin: 0; color: var(--text-secondary); font-size: 14px; }
.refresh-btn { display: flex; align-items: center; gap: 4px; padding: 7px 14px; border-radius: 8px; border: 1px solid var(--border-light); background: #fff; cursor: pointer; font-size: 12px; }
.refresh-btn:hover { background: var(--primary-soft); }

.rp-layout { display: grid; grid-template-columns: 280px 1fr; gap: 20px; align-items: start; }

/* 左侧检查单列表 */
.order-list { background: #fff; border-radius: 14px; border: 1px solid var(--border-light); overflow: hidden; display: flex; flex-direction: column; max-height: 70vh; }
.order-list-head { display: flex; justify-content: space-between; align-items: center; padding: 14px 16px; border-bottom: 1px solid var(--border-light); font-size: 13px; font-weight: 700; color: var(--text-secondary); }
.order-count { font-size: 11px; background: var(--gray-100); color: var(--text-tertiary); padding: 1px 8px; border-radius: 10px; }
.order-scroll { overflow-y: auto; }
.order-row { padding: 12px 16px; border-bottom: 1px solid var(--border-light); cursor: pointer; border-left: 3px solid transparent; transition: background .15s; }
.order-row:hover { background: var(--gray-50); }
.order-row.active { background: var(--primary-soft); border-left-color: var(--primary); }
.or-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.or-top strong { font-size: 13px; color: var(--text-primary); }
.or-mid { display: flex; align-items: center; gap: 8px; margin-top: 5px; font-size: 11px; color: var(--text-tertiary); }
.or-items { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 150px; }

/* 状态徽章 */
.badge { font-size: 10px; padding: 2px 8px; border-radius: 5px; font-weight: 600; white-space: nowrap; }
.st-pending { background: #FEF3C7; color: #D97706; }
.st-paid { background: #DBEAFE; color: #2563EB; }
.st-confirmed { background: #CCFBF1; color: #0D9488; }
.st-completed { background: #DCFCE7; color: #16A34A; }
.st-cancelled { background: #F1F5F9; color: #94A3B8; }
.st-default { background: var(--gray-100); color: var(--text-secondary); }

/* 右侧报告区 */
.report-detail { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.detail-toolbar { display: flex; justify-content: space-between; align-items: center; padding: 0 2px; }
.dt-order { font-size: 13px; font-weight: 700; color: var(--text-primary); }
.dt-stats { font-size: 11px; color: var(--text-tertiary); }
.report-stack { display: flex; flex-direction: column; gap: 14px; }
.report-card { background: #fff; border-radius: 14px; border: 1px solid var(--border-light); padding: 18px 20px; box-shadow: 0 1px 2px rgba(15,23,42,.04); }
.report-card-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 14px; }
.rc-title { display: flex; align-items: center; gap: 8px; min-width: 0; }
.rc-title strong { font-size: 15px; color: var(--text-primary); }
.rc-dot { width: 8px; height: 8px; border-radius: 50%; flex: 0 0 auto; }
.rc-dot.ok { background: #16A34A; box-shadow: 0 0 0 3px rgba(22,163,74,.15); }
.rc-dot.waiting { background: #F59E0B; box-shadow: 0 0 0 3px rgba(245,158,11,.18); animation: dot-pulse 1.6s ease-in-out infinite; }
@keyframes dot-pulse { 0%,100% { opacity: 1; } 50% { opacity: .4; } }

/* 报告生成中 */
.report-waiting { display: flex; align-items: center; gap: 12px; padding: 20px; border-radius: 10px; background: #FFFBEB; border: 1px dashed #FCD34D; }
.pulse-dot { width: 14px; height: 14px; border-radius: 50%; background: #F59E0B; position: relative; flex: 0 0 auto; }
.pulse-dot::after { content: ''; position: absolute; inset: -5px; border-radius: 50%; border: 2px solid #F59E0B; opacity: .5; animation: pulse-ring 1.6s ease-out infinite; }
@keyframes pulse-ring { 0% { transform: scale(.6); opacity: .6; } 100% { transform: scale(1.4); opacity: 0; } }
.report-waiting strong { display: block; font-size: 13px; color: #92400E; }
.report-waiting small { display: block; margin-top: 3px; font-size: 11px; color: #B45309; }

/* AI 解读 */
.report-interpret { background: linear-gradient(135deg, #F0F9FF, #EFF6FF); border: 1px solid #BAE6FD; border-radius: 10px; padding: 14px 16px; margin-bottom: 12px; }
.interpret-label { display: flex; align-items: center; gap: 5px; font-size: 11px; color: #0369A1; font-weight: 700; margin-bottom: 6px; }
.interpret-label svg { width: 13px; height: 13px; }
.report-interpret p { font-size: 13px; line-height: 1.7; margin: 0; color: #334155; }

/* 指标表 */
.report-metrics { border: 1px solid var(--border-light); border-radius: 10px; overflow: hidden; }
.metric-header, .metric-row { display: grid; grid-template-columns: 1fr 130px 150px; gap: 8px; padding: 9px 14px; font-size: 12px; }
.metric-header { background: var(--gray-50); color: var(--text-tertiary); font-size: 11px; font-weight: 600; }
.metric-row { border-top: 1px solid var(--border-light); }
.metric-row:nth-child(2) { border-top: 0; }
.metric-name { color: var(--text-secondary); }
.metric-value { font-weight: 700; color: var(--text-primary); }
.metric-value.abnormal { color: #DC2626; }
.metric-ref { font-size: 11px; color: var(--text-tertiary); }

/* 报告小结 */
.report-summary { margin-top: 12px; padding: 12px 14px; background: #F8FAFC; border-radius: 8px; font-size: 12px; line-height: 1.7; color: var(--text-secondary); }

.empty { text-align: center; padding: 60px 20px; color: var(--text-tertiary); font-size: 14px; }
@media (max-width: 820px) {
  .rp-layout { grid-template-columns: 1fr; }
  .order-list { max-height: 280px; }
  .metric-header, .metric-row { grid-template-columns: 1fr 90px 110px; }
}
</style>
