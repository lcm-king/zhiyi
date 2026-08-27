<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Clock, CircleCheck, CircleClose, ArrowRight, Warning } from '@element-plus/icons-vue'
import { getAdminOrders } from '@/api'
import { renderMarkdown } from '@/utils/markdown'

interface ReviewItem {
  id: number; order_no: string; patient_name: string; patient_id: number
  pay_status: string; delivery_status: string
  items: Array<{ drug_name: string; quantity: number }>
  total_price: number; created_at: string
  review_status: string; risk: string
  ai_review: { passed: boolean; warnings: string[]; suggestion: string }
}

const router = useRouter()
const list = ref<ReviewItem[]>([])
const loading = ref(true)
const filter = ref<'all' | 'pending' | 'reviewed' | 'warning'>('all')

async function load() {
  loading.value = true
  try {
    list.value = await getAdminOrders()
  } catch (e: any) {
    ElMessage.error(e.message || '加载失败，请确认后端服务已启动')
  } finally {
    loading.value = false
  }
}

const filtered = computed(() => {
  if (filter.value === 'pending') return list.value.filter(p => p.review_status === 'pending')
  if (filter.value === 'reviewed') return list.value.filter(p => p.review_status === 'reviewed')
  if (filter.value === 'warning') return list.value.filter(p => p.review_status === 'warning')
  return list.value
})

const riskLabel: Record<string, string> = { high: '高风险', medium: '中风险', low: '低风险' }
const reviewLabel: Record<string, string> = { pending: '待审核', reviewed: '通过', warning: '风险提示' }

function openPatient(pid: number) {
  router.push(`/doctor/records/${pid}`)
}

onMounted(load)
</script>
<template>
  <div class="pr-page">
    <div class="pr-head">
      <div>
        <h1>处方审核</h1>
        <p>AI 辅助审核处方合理性 · 共 {{ list.length }} 张处方</p>
      </div>
      <button class="refresh-btn" :disabled="loading" @click="load">{{ loading ? '…' : '刷新' }}</button>
    </div>

    <div class="pr-filters">
      <button :class="{ active: filter === 'all' }" @click="filter = 'all'">全部 {{ list.length }}</button>
      <button :class="{ active: filter === 'pending' }" @click="filter = 'pending'">待审核</button>
      <button :class="{ active: filter === 'reviewed' }" @click="filter = 'reviewed'">已通过</button>
      <button :class="{ active: filter === 'warning' }" @click="filter = 'warning'">风险提示</button>
    </div>

    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="!filtered.length" class="empty">
      <p>暂无处方数据</p>
      <small>诊断完成后开具的药品将出现在此处供审核</small>
    </div>
    <div v-else class="pr-list">
      <div v-for="p in filtered" :key="p.id" class="pr-card">
        <div class="pr-top">
          <div class="pr-meta">
            <strong>{{ p.order_no }}</strong>
            <small>{{ p.patient_name || '患者 #' + p.patient_id }} · {{ (p.created_at || '').slice(0, 10) }}</small>
          </div>
          <div class="pr-badges">
            <span class="risk-badge" :class="p.risk">{{ riskLabel[p.risk] }}</span>
            <span class="review-badge" :class="p.review_status">{{ reviewLabel[p.review_status] }}</span>
          </div>
        </div>

        <div class="pr-items">
          <span v-for="it in (p.items || []).slice(0, 6)" :key="it.drug_name" class="drug-tag">{{ it.drug_name }} ×{{ it.quantity }}</span>
        </div>

        <div v-if="p.ai_review?.warnings?.length" class="pr-warnings">
          <div v-for="(w, i) in p.ai_review.warnings" :key="i" class="warn-item">
            <Warning /> <span v-html="renderMarkdown(w)"></span>
          </div>
        </div>
        <div v-else class="pr-warnings">
          <div class="warn-item ok"><CircleCheck /> <span v-html="renderMarkdown(p.ai_review?.suggestion || '处方合理，未发现风险')"></span></div>
        </div>

        <div class="pr-bottom">
          <strong>¥{{ p.total_price?.toFixed(2) }}</strong>
          <span v-if="p.pay_status === 'pending'" class="status pending"><Clock /> 待支付</span>
          <span v-else-if="p.delivery_status === 'shipped'" class="status shipped">配送中</span>
          <span v-else class="status done"><CircleCheck /> 已支付</span>
          <button class="btn-view" @click="openPatient(p.patient_id)">查看患者 <ArrowRight /></button>
        </div>
      </div>
    </div>
  </div>
</template>
<style scoped>
.pr-page { max-width: 860px; margin: 0 auto; padding: 24px; }

.pr-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 14px; }
.pr-head h1 { font-size: 22px; font-weight: 700; margin-bottom: 2px; }
.pr-head p { margin: 0; color: var(--text-secondary); font-size: 13px; }
.refresh-btn { padding: 6px 14px; border-radius: 7px; border: 1px solid var(--border-light); background: #fff; cursor: pointer; font-size: 12px; }
.refresh-btn:disabled { opacity: .5; }

.pr-filters { display: flex; gap: 6px; margin-bottom: 16px; }
.pr-filters button { padding: 5px 14px; border-radius: 7px; border: 1px solid var(--border-light); background: #fff; font-size: 12px; cursor: pointer; transition: all .15s; }
.pr-filters button.active { background: var(--primary); color: #fff; border-color: var(--primary); }

.pr-list { display: flex; flex-direction: column; gap: 10px; }
.pr-card { background: #fff; border-radius: 14px; padding: 16px 18px; border: 1px solid var(--border-light); }

.pr-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.pr-meta strong { display: block; font-size: 14px; }
.pr-meta small { font-size: 11px; color: var(--text-tertiary); }
.pr-badges { display: flex; gap: 6px; align-items: center; }

.risk-badge, .review-badge { font-size: 10px; padding: 2px 8px; border-radius: 4px; font-weight: 700; }
.risk-badge.high { background: #FEE2E2; color: #DC2626; }
.risk-badge.medium { background: #FEF3C7; color: #D97706; }
.risk-badge.low { background: #DCFCE7; color: #16A34A; }
.review-badge.pending { background: #F1F5F9; color: #64748B; }
.review-badge.reviewed { background: #DCFCE7; color: #16A34A; }
.review-badge.warning { background: #FEF3C7; color: #D97706; }

.pr-items { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 10px; }
.drug-tag { font-size: 11px; padding: 2px 7px; border-radius: 4px; background: var(--gray-100); color: var(--text-secondary); }

.pr-warnings { margin-bottom: 10px; }
.warn-item { display: flex; align-items: flex-start; gap: 6px; font-size: 12px; padding: 4px 0; color: #D97706; }
.warn-item svg { width: 14px; flex-shrink: 0; margin-top: 1px; }
.warn-item.ok { color: #16A34A; }

.pr-bottom { display: flex; align-items: center; gap: 12px; padding-top: 8px; border-top: 1px solid var(--border-light); }
.pr-bottom strong { font-size: 15px; }
.status { display: flex; align-items: center; gap: 4px; font-size: 12px; }
.status.pending { color: #D97706; }
.status.shipped { color: #2563EB; }
.status.done { color: #16A34A; }
.btn-view { margin-left: auto; padding: 6px 14px; border-radius: 8px; border: 1px solid var(--border-light); background: #fff; font-size: 12px; cursor: pointer; display: flex; align-items: center; gap: 4px; }
.btn-view:hover { border-color: var(--primary); color: var(--primary); }

.empty { text-align: center; padding: 60px; color: var(--text-tertiary); font-size: 14px; }
.empty p { margin: 0 0 4px; }
.empty small { font-size: 12px; }
</style>
