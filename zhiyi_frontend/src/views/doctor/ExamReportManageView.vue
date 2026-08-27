<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { CircleCheck, Clock, Document, Edit, Plus, Refresh } from '@element-plus/icons-vue'
import { renderMarkdown } from '@/utils/markdown'

interface Metric {
  name: string
  value: string
  unit: string
  reference_range: string
  status: 'normal' | 'high' | 'low' | 'abnormal'
}

interface Appointment {
  appointment_id: number
  order_id: number | null
  patient_id: number
  patient_name: string
  exam_name: string
  category: string
  status: string
  appointment_time: string | null
  has_report: boolean
  report_data: { summary?: string; metrics?: Metric[] } | null
  ai_interpretation: string | null
}

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'
const token = () => localStorage.getItem('zhiyi-token') || ''

const list = ref<Appointment[]>([])
const loading = ref(true)
const filter = ref<'all' | 'todo' | 'completed'>('all')

const statusLabel: Record<string, string> = {
  pending: '待支付',
  paid: '已支付',
  confirmed: '已确认',
  completed: '已完成',
  cancelled: '已取消',
}

const statusClass: Record<string, string> = {
  pending: 'st-pending',
  paid: 'st-paid',
  confirmed: 'st-confirmed',
  completed: 'st-completed',
  cancelled: 'st-cancelled',
}

async function load() {
  loading.value = true
  try {
    const query = filter.value === 'completed' ? '?status=completed' : filter.value === 'todo' ? '?status=paid' : ''
    const resp = await fetch(`${apiBase}/exams/appointments${query}`, {
      headers: { Authorization: `Bearer ${token()}` },
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    list.value = await resp.json()
  } catch (e: any) {
    ElMessage.error(e.message || '加载失败，请确认后端服务已启动')
  } finally {
    loading.value = false
  }
}

const todoCount = computed(() => list.value.filter(a => !['completed', 'cancelled'].includes(a.status)).length)
const doneCount = computed(() => list.value.filter(a => a.status === 'completed').length)

// ── 录入报告 ─────────────────────────────
const dialogOpen = ref(false)
const saving = ref(false)
const current = ref<Appointment | null>(null)
const form = reactive({
  summary: '',
  report_url: '',
  metrics: [] as Metric[],
})

function addMetric() {
  form.metrics.push({ name: '', value: '', unit: '', reference_range: '', status: 'normal' })
}

function removeMetric(i: number) {
  form.metrics.splice(i, 1)
}

function openInput(a: Appointment) {
  current.value = a
  form.summary = a.report_data?.summary || ''
  form.report_url = ''
  form.metrics = (a.report_data?.metrics || []).map(m => ({
    name: m.name || '',
    value: m.value || '',
    unit: m.unit || '',
    reference_range: m.reference_range || '',
    status: m.status || 'normal',
  }))
  if (!form.metrics.length) addMetric()
  dialogOpen.value = true
}

async function saveReport() {
  if (!current.value) return
  const metrics = form.metrics.filter(m => m.name.trim())
  if (!metrics.length && !form.summary.trim()) {
    ElMessage.warning('请至少填写报告摘要或一项指标')
    return
  }
  saving.value = true
  try {
    const resp = await fetch(`${apiBase}/exams/appointments/${current.value.appointment_id}/report`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token()}` },
      body: JSON.stringify({
        report_data: { summary: form.summary.trim(), metrics },
        report_url: form.report_url.trim() || undefined,
        status: 'completed',
      }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => null)
      throw new Error(err?.detail || `HTTP ${resp.status}`)
    }
    const data = await resp.json()
    ElMessage.success(data.message || '检查报告已更新并生成 AI 解读')
    dialogOpen.value = false
    await load()
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

// ── 查看报告 ─────────────────────────────
const viewOpen = ref(false)
const viewItem = ref<Appointment | null>(null)

function openView(a: Appointment) {
  viewItem.value = a
  viewOpen.value = true
}

onMounted(load)
</script>

<template>
  <div class="erm-page">
    <div class="erm-head">
      <div>
        <h1>检查报告</h1>
        <p>检查预约管理 · 录入结构化报告，自动生成 AI 解读</p>
      </div>
      <button class="refresh-btn" :disabled="loading" @click="load">
        <Refresh /> {{ loading ? '加载中…' : '刷新' }}
      </button>
    </div>

    <div class="erm-stats">
      <div class="stat-card">
        <strong>{{ list.length }}</strong>
        <span>当前列表</span>
      </div>
      <div class="stat-card">
        <strong>{{ todoCount }}</strong>
        <span>待出报告</span>
      </div>
      <div class="stat-card done">
        <strong>{{ doneCount }}</strong>
        <span>已完成</span>
      </div>
    </div>

    <div class="erm-filters">
      <button :class="{ active: filter === 'all' }" @click="filter = 'all'; load()">全部</button>
      <button :class="{ active: filter === 'todo' }" @click="filter = 'todo'; load()">待出报告</button>
      <button :class="{ active: filter === 'completed' }" @click="filter = 'completed'; load()">已完成</button>
    </div>

    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="!list.length" class="empty">
      <Document style="width:44px;opacity:.3;margin-bottom:8px" />
      <p>暂无检查预约</p>
    </div>
    <div v-else class="erm-list">
      <div v-for="a in list" :key="a.appointment_id" class="erm-card">
        <div class="erm-top">
          <div class="erm-meta">
            <strong>{{ a.exam_name }}</strong>
            <small>{{ a.patient_name || '患者 #' + a.patient_id }} · {{ a.category || '常规检查' }}</small>
          </div>
          <span class="status-badge" :class="statusClass[a.status] || 'st-pending'">{{ statusLabel[a.status] || a.status }}</span>
        </div>

        <div class="erm-info">
          <span class="info-item"><Clock /> 预约 {{ (a.appointment_time || '').replace('T', ' ').slice(0, 16) || '—' }}</span>
          <span class="info-item"><CircleCheck v-if="a.has_report" style="color:#16A34A" /> {{ a.has_report ? '已有报告' : '未出报告' }}</span>
          <span class="info-item" v-if="a.order_id">单号 EX{{ a.order_id }}</span>
        </div>

        <div v-if="a.ai_interpretation" class="erm-interpret">
          <div class="interpret-label">AI 解读</div>
          <p v-html="renderMarkdown(a.ai_interpretation)"></p>
        </div>

        <div class="erm-bottom">
          <button class="btn-input" @click="openInput(a)"><Edit /> {{ a.has_report ? '更新报告' : '录入报告' }}</button>
          <button class="btn-view" :disabled="!a.has_report" @click="openView(a)">查看详情</button>
        </div>
      </div>
    </div>

    <!-- 录入/编辑报告 -->
    <el-dialog v-model="dialogOpen" :title="`${current?.has_report ? '更新' : '录入'}检查报告 · ${current?.exam_name || ''}`" width="640px" destroy-on-close>
      <div class="report-form">
        <label class="form-label">报告摘要</label>
        <textarea v-model="form.summary" rows="2" placeholder="例如：胸部正位片未见明显异常，心影大小形态正常。" />

        <div class="metric-head">
          <label class="form-label">检查指标</label>
          <button class="add-metric" @click="addMetric"><Plus /> 添加指标</button>
        </div>

        <div v-for="(m, i) in form.metrics" :key="i" class="metric-row">
          <input v-model="m.name" placeholder="指标名" class="m-name" />
          <input v-model="m.value" placeholder="数值" class="m-value" />
          <input v-model="m.unit" placeholder="单位" class="m-unit" />
          <input v-model="m.reference_range" placeholder="参考范围" class="m-ref" />
          <select v-model="m.status" class="m-status">
            <option value="normal">正常</option>
            <option value="high">偏高</option>
            <option value="low">偏低</option>
            <option value="abnormal">异常</option>
          </select>
          <button class="m-del" @click="removeMetric(i)">×</button>
        </div>

        <label class="form-label">报告链接（可选）</label>
        <input v-model="form.report_url" placeholder="https://…（PDF 或影像链接）" class="url-input" />
      </div>
      <template #footer>
        <button class="ghost-button" @click="dialogOpen = false">取消</button>
        <button class="primary-button" :disabled="saving" @click="saveReport">{{ saving ? '保存中…' : '保存并生成 AI 解读' }}</button>
      </template>
    </el-dialog>

    <!-- 查看报告 -->
    <el-dialog v-model="viewOpen" :title="`检查报告 · ${viewItem?.exam_name || ''}`" width="640px">
      <div v-if="viewItem" class="view-body">
        <p class="view-summary">{{ viewItem.report_data?.summary || '（无摘要）' }}</p>
        <div v-if="viewItem.report_data?.metrics?.length" class="metric-table">
          <div class="metric-table-head">
            <span>指标</span><span>结果</span><span>参考范围</span><span>状态</span>
          </div>
          <div v-for="m in viewItem.report_data.metrics" :key="m.name" class="metric-table-row">
            <span>{{ m.name }}</span>
            <span>{{ m.value }}{{ m.unit }}</span>
            <span>{{ m.reference_range || '—' }}</span>
            <span :class="{ abnormal: m.status !== 'normal' }">
              {{ { normal: '正常', high: '偏高', low: '偏低', abnormal: '异常' }[m.status] || m.status }}
            </span>
          </div>
        </div>
        <div v-if="viewItem.ai_interpretation" class="view-interpret">
          <div class="interpret-label">AI 解读</div>
          <p v-html="renderMarkdown(viewItem.ai_interpretation)"></p>
        </div>
      </div>
      <template #footer>
        <button class="ghost-button" @click="viewOpen = false">关闭</button>
        <button class="primary-button" @click="viewOpen = false; openInput(viewItem!)">编辑报告</button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.erm-page { max-width: 900px; margin: 0 auto; padding: 24px; }
.erm-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 14px; }
.erm-head h1 { font-size: 22px; font-weight: 700; margin-bottom: 2px; }
.erm-head p { margin: 0; color: var(--text-secondary); font-size: 13px; }
.refresh-btn { display: flex; align-items: center; gap: 5px; padding: 6px 14px; border-radius: 7px; border: 1px solid var(--border-light); background: #fff; cursor: pointer; font-size: 12px; }
.refresh-btn:disabled { opacity: .5; }

.erm-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; }
.stat-card { background: #fff; border: 1px solid var(--border-light); border-radius: 12px; padding: 14px 16px; }
.stat-card strong { display: block; font-size: 26px; font-weight: 800; color: var(--primary); }
.stat-card.done strong { color: #16A34A; }
.stat-card span { font-size: 12px; color: var(--text-tertiary); }

.erm-filters { display: flex; gap: 6px; margin-bottom: 16px; }
.erm-filters button { padding: 5px 14px; border-radius: 7px; border: 1px solid var(--border-light); background: #fff; font-size: 12px; cursor: pointer; transition: all .15s; }
.erm-filters button.active { background: var(--primary); color: #fff; border-color: var(--primary); }

.empty { text-align: center; padding: 60px 20px; color: var(--text-tertiary); font-size: 14px; }

.erm-list { display: flex; flex-direction: column; gap: 12px; }
.erm-card { background: #fff; border: 1px solid var(--border-light); border-radius: 14px; padding: 16px 18px; }
.erm-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }
.erm-meta strong { font-size: 15px; display: block; }
.erm-meta small { font-size: 12px; color: var(--text-tertiary); }
.status-badge { font-size: 11px; padding: 3px 9px; border-radius: 6px; font-weight: 600; }
.st-pending { background: #FEF3C7; color: #D97706; }
.st-paid { background: #DCFCE7; color: #16A34A; }
.st-confirmed { background: #DBEAFE; color: #2563EB; }
.st-completed { background: #E0E7FF; color: #4F46E5; }
.st-cancelled { background: #F3F4F6; color: #9CA3AF; }

.erm-info { display: flex; flex-wrap: wrap; gap: 14px; font-size: 12px; color: var(--text-secondary); margin-bottom: 10px; }
.info-item { display: flex; align-items: center; gap: 4px; }

.erm-interpret { background: #F0F9FF; border-radius: 8px; padding: 10px 12px; margin-bottom: 12px; }
.interpret-label { font-size: 11px; color: var(--primary); font-weight: 600; margin-bottom: 3px; }
.erm-interpret p { font-size: 13px; line-height: 1.6; margin: 0; }

.erm-bottom { display: flex; gap: 8px; }
.btn-input, .btn-view { display: flex; align-items: center; gap: 4px; padding: 6px 13px; border-radius: 7px; font-size: 12px; cursor: pointer; }
.btn-input { background: var(--primary); color: #fff; border: none; }
.btn-view { background: #fff; border: 1px solid var(--border-light); }
.btn-view:disabled { opacity: .45; cursor: not-allowed; }

.report-form .form-label { display: block; font-size: 12px; color: var(--text-secondary); margin: 12px 0 6px; font-weight: 600; }
.report-form textarea, .report-form input, .metric-row select { width: 100%; box-sizing: border-box; padding: 8px 10px; border: 1px solid var(--border-light); border-radius: 8px; font-size: 13px; outline: none; }
.report-form textarea:focus, .report-form input:focus, .metric-row select:focus { border-color: var(--primary); }
.report-form textarea { resize: vertical; font-family: inherit; }
.metric-head { display: flex; justify-content: space-between; align-items: center; }
.add-metric { display: flex; align-items: center; gap: 3px; padding: 4px 10px; border: 1px dashed var(--primary); color: var(--primary); background: #fff; border-radius: 7px; font-size: 12px; cursor: pointer; }
.metric-row { display: grid; grid-template-columns: 1.3fr .8fr .6fr 1fr .7fr 26px; gap: 6px; margin-bottom: 8px; align-items: center; }
.metric-row .m-del { border: none; background: #FEF2F2; color: #DC2626; border-radius: 6px; height: 30px; cursor: pointer; font-size: 15px; }
.url-input { margin-bottom: 4px; }
.ghost-button { padding: 8px 16px; border-radius: 8px; border: 1px solid var(--border-light); background: #fff; font-size: 13px; cursor: pointer; }
.primary-button { padding: 8px 16px; border-radius: 8px; border: none; background: var(--primary); color: #fff; font-size: 13px; cursor: pointer; }
.primary-button:disabled { opacity: .5; }

.view-body .view-summary { font-size: 14px; line-height: 1.7; color: var(--text-primary); background: var(--gray-50); padding: 12px; border-radius: 8px; }
.metric-table { border: 1px solid var(--border-light); border-radius: 8px; overflow: hidden; margin-top: 12px; }
.metric-table-head, .metric-table-row { display: grid; grid-template-columns: 1.2fr 1fr 1fr .8fr; gap: 8px; padding: 8px 12px; font-size: 13px; }
.metric-table-head { background: var(--gray-50); color: var(--text-tertiary); font-size: 12px; font-weight: 600; }
.metric-table-row { border-top: 1px solid var(--border-light); }
.metric-table-row .abnormal { color: #DC2626; font-weight: 700; }
.view-interpret { background: #F0F9FF; border-radius: 8px; padding: 12px; margin-top: 12px; }
.view-interpret p { font-size: 13px; line-height: 1.6; margin: 0; }
</style>
