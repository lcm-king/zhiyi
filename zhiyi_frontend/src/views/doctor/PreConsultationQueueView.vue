<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowRight, ChatDotRound, Check, Clock, DocumentChecked, FirstAidKit, Refresh } from '@element-plus/icons-vue'
import { confirmPreConsultation, getPreConsultationDetail, getPreConsultations } from '@/api'
import type { PreConsultationItem, PreConsultationResult, PreConsultPrescriptionItem } from '@/types'

interface RxDraft {
  drug_id: number
  drug_name: string
  checked: boolean
  quantity: number
  dosage: string
}

const list = ref<PreConsultationItem[]>([])
const loading = ref(false)
const filter = ref<'all' | 'pending' | 'confirmed'>('all')
const dialogOpen = ref(false)
const saving = ref(false)
const detail = ref<PreConsultationResult | null>(null)
const router = useRouter()
const form = reactive({
  final_diagnosis: '',
  treatment_plan: '',
  rxItems: [] as RxDraft[],
})

const urgencyLabel: Record<string, string> = { low: '低', medium: '中', high: '高' }
const statusLabel: Record<string, string> = { pending: '待确认', confirmed: '已确认', dismissed: '已忽略' }

const filtered = computed(() => {
  if (filter.value === 'all') return list.value
  return list.value.filter((i) => i.status === filter.value)
})

const pendingCount = computed(() => list.value.filter((i) => i.status === 'pending').length)
const confirmedCount = computed(() => list.value.filter((i) => i.status === 'confirmed').length)

async function load() {
  loading.value = true
  try {
    list.value = await getPreConsultations()
  } catch (e: any) {
    ElMessage.error(e.message || '加载失败，请确认后端服务已启动')
  } finally {
    loading.value = false
  }
}

function openConfirm(item: PreConsultationItem) {
  detail.value = null
  form.final_diagnosis = item.primary_diagnosis || ''
  form.treatment_plan = ''
  form.rxItems = []
  dialogOpen.value = true
  void loadDetail(item.id)
}

async function loadDetail(id: number) {
  try {
    const data = await getPreConsultationDetail(id)
    detail.value = data
    form.final_diagnosis = data.primary_diagnosis || data.medical_record?.preliminary_diagnosis || ''
    form.treatment_plan = (data.medical_record?.treatment_plan || []).join('；')

    const seen = new Set<string | number>()
    const drafts: RxDraft[] = []
    for (const s of data.suggestions || []) {
      for (const d of s.recommended_drugs || []) {
        const key = d.drug_id || d.drug_name
        if (key == null || seen.has(key)) continue
        seen.add(key)
        drafts.push({
          drug_id: d.drug_id || 0,
          drug_name: d.drug_name,
          checked: true,
          quantity: 1,
          dosage: '',
        })
      }
    }
    form.rxItems = drafts
  } catch (e: any) {
    ElMessage.error(e.message || '加载预问诊详情失败')
  }
}

async function submitConfirm() {
  if (!detail.value) return
  if (!form.final_diagnosis.trim()) {
    ElMessage.warning('请填写最终确诊')
    return
  }
  const prescription_items: PreConsultPrescriptionItem[] = form.rxItems
    .filter((i) => i.checked && i.drug_id)
    .map((i) => ({
      drug_id: i.drug_id,
      dosage: i.dosage.trim() || '按医嘱',
      quantity: Math.max(1, i.quantity),
    }))

  saving.value = true
  try {
    await confirmPreConsultation(detail.value.id, {
      final_diagnosis: form.final_diagnosis.trim(),
      treatment_plan: form.treatment_plan.trim() || undefined,
      prescription_items,
    })
    ElMessage.success('已确认并生成正式就诊记录')
    dialogOpen.value = false
    await load()
  } catch (e: any) {
    let msg = e?.message || '确认失败'
    try {
      const parsed = JSON.parse(msg)
      msg = parsed.detail || msg
    } catch { /* 非 JSON 错误直接展示 */ }
    ElMessage.error(`确认失败：${msg}`)
  } finally {
    saving.value = false
  }
}

function openPatient(pid: number) {
  router.push(`/doctor/records/${pid}`)
}

onMounted(load)
</script>

<template>
  <div class="pcq-page">
    <div class="pcq-head">
      <div>
        <div class="eyebrow">患者 AI 预问诊 / 医生确认</div>
        <h1>待确认问诊</h1>
        <p>患者提交的 AI 预问诊仅为健康参考，确认后才生成正式就诊记录与处方</p>
      </div>
      <button class="refresh-btn" :disabled="loading" @click="load">
        <Refresh /> {{ loading ? '加载中…' : '刷新' }}
      </button>
    </div>

    <div class="pcq-stats">
      <div class="stat-card">
        <strong>{{ list.length }}</strong>
        <span>全部预问诊</span>
      </div>
      <div class="stat-card pending">
        <strong>{{ pendingCount }}</strong>
        <span>待确认</span>
      </div>
      <div class="stat-card done">
        <strong>{{ confirmedCount }}</strong>
        <span>已确认</span>
      </div>
    </div>

    <div class="pcq-filters">
      <button :class="{ active: filter === 'all' }" @click="filter = 'all'">全部 {{ list.length }}</button>
      <button :class="{ active: filter === 'pending' }" @click="filter = 'pending'">待确认 {{ pendingCount }}</button>
      <button :class="{ active: filter === 'confirmed' }" @click="filter = 'confirmed'">已确认 {{ confirmedCount }}</button>
    </div>

    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="!filtered.length" class="empty">
      <ChatDotRound style="width: 44px; opacity: .3; margin-bottom: 8px" />
      <p>暂无预问诊记录</p>
      <small>患者完成 AI 预问诊后会出现在这里，供医生确认</small>
    </div>
    <div v-else class="pcq-list">
      <div v-for="item in filtered" :key="item.id" class="pcq-card">
        <div class="pcq-top">
          <div class="pcq-meta">
            <strong>{{ item.patient_name || '患者 #' + item.patient_id }}</strong>
            <small>{{ item.created_at }} · {{ item.suggestions_count }} 条评估建议</small>
          </div>
          <div class="pcq-badges">
            <span class="urgency-badge" :class="item.urgency">紧急 {{ urgencyLabel[item.urgency] || item.urgency }}</span>
            <span class="status-badge" :class="item.status">{{ statusLabel[item.status] || item.status }}</span>
          </div>
        </div>

        <p class="pcq-symptoms">{{ item.symptoms }}</p>

        <div class="pcq-lines">
          <span class="line-item"><FirstAidKit /> AI 首选：{{ item.primary_diagnosis || '待评估' }}</span>
          <span v-if="item.suggested_department" class="line-item"><DocumentChecked /> 建议科室：{{ item.suggested_department }}</span>
        </div>

        <div class="pcq-bottom">
          <button v-if="item.status === 'pending'" class="primary-button" @click="openConfirm(item)">
            确认就诊 <ArrowRight />
          </button>
          <button v-else class="ghost-button" @click="openPatient(item.patient_id)">
            查看患者档案 <ArrowRight />
          </button>
        </div>
      </div>
    </div>

    <el-dialog v-model="dialogOpen" title="确认 AI 预问诊" width="680px" destroy-on-close>
      <div v-if="detail" class="confirm-body">
        <div class="confirm-patient">
          <div class="patient-avatar">{{ detail.patient_id }}</div>
          <div>
            <strong>患者 #{{ detail.patient_id }}</strong>
            <span>{{ detail.symptoms }}</span>
          </div>
        </div>

        <div class="ai-suggestions">
          <div class="block-title">AI 评估建议（仅供参考）</div>
          <div v-for="s in detail.suggestions" :key="s.id" class="suggestion-row">
            <span class="suggestion-name">{{ s.name }}</span>
            <span class="suggestion-confidence">{{ s.confidence }}%</span>
          </div>
        </div>

        <div class="form-grid">
          <label>
            <span>最终确诊</span>
            <input v-model="form.final_diagnosis" placeholder="请填写医生确认后的诊断" />
          </label>
          <label>
            <span>治疗方案</span>
            <textarea v-model="form.treatment_plan" rows="2" placeholder="治疗方案或用药建议" />
          </label>
        </div>

        <div v-if="form.rxItems.length" class="rx-block">
          <div class="block-title">开具处方药</div>
          <div v-for="rx in form.rxItems" :key="rx.drug_id" class="rx-row">
            <label class="rx-check">
              <input v-model="rx.checked" type="checkbox" />
              <span>{{ rx.drug_name }}</span>
            </label>
            <input v-model="rx.dosage" class="rx-dosage" placeholder="用法用量" />
            <div class="rx-qty">
              <button @click="rx.quantity = Math.max(1, rx.quantity - 1)">−</button>
              <span>{{ rx.quantity }}</span>
              <button @click="rx.quantity += 1">+</button>
            </div>
          </div>
          <p class="rx-note">处方药必须经医生确认后患者方可购买</p>
        </div>
      </div>
      <template #footer>
        <button class="ghost-button" @click="dialogOpen = false">取消</button>
        <button class="primary-button" :disabled="saving || !detail" @click="submitConfirm">
          <Check v-if="!saving" /> {{ saving ? '确认中…' : '确认并生成正式就诊' }}
        </button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.pcq-page { max-width: 900px; margin: 0 auto; padding: 24px; }

.pcq-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 14px; }
.pcq-head h1 { font-size: 22px; font-weight: 700; margin: 2px 0; }
.pcq-head p { margin: 0; color: var(--text-secondary); font-size: 13px; }
.eyebrow { font-size: 11px; color: var(--text-tertiary); font-weight: 600; }
.refresh-btn { display: flex; align-items: center; gap: 5px; padding: 6px 14px; border-radius: 7px; border: 1px solid var(--border-light); background: #fff; cursor: pointer; font-size: 12px; }
.refresh-btn:disabled { opacity: .5; }
.refresh-btn svg { width: 14px; }

.pcq-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; }
.stat-card { background: #fff; border: 1px solid var(--border-light); border-radius: 12px; padding: 14px 16px; }
.stat-card strong { display: block; font-size: 26px; font-weight: 800; color: var(--primary); }
.stat-card.pending strong { color: #D97706; }
.stat-card.done strong { color: #16A34A; }
.stat-card span { font-size: 12px; color: var(--text-tertiary); }

.pcq-filters { display: flex; gap: 6px; margin-bottom: 16px; }
.pcq-filters button { padding: 5px 14px; border-radius: 7px; border: 1px solid var(--border-light); background: #fff; font-size: 12px; cursor: pointer; transition: all .15s; }
.pcq-filters button.active { background: var(--primary); color: #fff; border-color: var(--primary); }

.empty { text-align: center; padding: 60px 20px; color: var(--text-tertiary); font-size: 14px; }
.empty p { margin: 0 0 4px; }
.empty small { font-size: 12px; }

.pcq-list { display: flex; flex-direction: column; gap: 12px; }
.pcq-card { background: #fff; border: 1px solid var(--border-light); border-radius: 14px; padding: 16px 18px; }
.pcq-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.pcq-meta strong { display: block; font-size: 14px; }
.pcq-meta small { font-size: 11px; color: var(--text-tertiary); }
.pcq-badges { display: flex; gap: 6px; align-items: center; }

.urgency-badge, .status-badge { font-size: 10px; padding: 2px 8px; border-radius: 4px; font-weight: 700; }
.urgency-badge.low { background: #DCFCE7; color: #16A34A; }
.urgency-badge.medium { background: #FEF3C7; color: #D97706; }
.urgency-badge.high { background: #FEE2E2; color: #DC2626; }
.status-badge.pending { background: #F1F5F9; color: #64748B; }
.status-badge.confirmed { background: #DCFCE7; color: #16A34A; }
.status-badge.dismissed { background: #F3F4F6; color: #9CA3AF; }

.pcq-symptoms { margin: 0 0 10px; font-size: 12.5px; color: var(--text-secondary); line-height: 1.6; }
.pcq-lines { display: flex; flex-wrap: wrap; gap: 8px 16px; margin-bottom: 12px; font-size: 12px; color: var(--text-secondary); }
.line-item { display: inline-flex; align-items: center; gap: 4px; }
.line-item svg { width: 13px; color: var(--primary); }

.pcq-bottom { display: flex; justify-content: flex-end; padding-top: 8px; border-top: 1px solid var(--border-light); }
.pcq-bottom .primary-button, .pcq-bottom .ghost-button { display: inline-flex; align-items: center; gap: 4px; }

.confirm-body { display: flex; flex-direction: column; gap: 14px; }
.confirm-patient { display: flex; align-items: center; gap: 10px; padding: 12px; background: var(--gray-50); border-radius: 8px; }
.patient-avatar { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 8px; background: var(--primary); color: #fff; font-weight: 800; flex: 0 0 auto; }
.confirm-patient strong { display: block; font-size: 13px; }
.confirm-patient span { font-size: 12px; color: var(--text-secondary); line-height: 1.5; }

.block-title { font-size: 12px; font-weight: 700; color: var(--text-secondary); margin-bottom: 8px; }
.ai-suggestions { border: 1px solid var(--border-light); border-radius: 8px; padding: 10px 12px; }
.suggestion-row { display: flex; justify-content: space-between; gap: 10px; padding: 4px 0; font-size: 12.5px; }
.suggestion-confidence { color: var(--primary); font-weight: 700; }

.form-grid { display: grid; gap: 10px; }
.form-grid label { display: grid; gap: 5px; }
.form-grid label span { font-size: 12px; font-weight: 600; color: var(--text-secondary); }
.form-grid input, .form-grid textarea { width: 100%; box-sizing: border-box; padding: 8px 10px; border: 1px solid var(--border-light); border-radius: 8px; font-size: 13px; outline: none; font-family: inherit; }
.form-grid input:focus, .form-grid textarea:focus { border-color: var(--primary); }
.form-grid textarea { resize: vertical; }

.rx-block { border: 1px solid var(--border-light); border-radius: 8px; padding: 10px 12px; }
.rx-row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(140px, .9fr) 92px; gap: 8px; align-items: center; padding: 6px 0; border-top: 1px dashed var(--border-light); }
.rx-row:first-of-type { border-top: 0; }
.rx-check { display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer; }
.rx-dosage { padding: 5px 8px; border: 1px solid var(--border-light); border-radius: 6px; font-size: 12px; outline: none; }
.rx-qty { display: flex; align-items: center; gap: 4px; justify-content: flex-end; }
.rx-qty button { width: 24px; height: 24px; border: 1px solid var(--border-light); border-radius: 5px; background: #fff; cursor: pointer; }
.rx-note { margin: 8px 0 0; font-size: 11px; color: var(--text-tertiary); }

.primary-button, .ghost-button { display: inline-flex; align-items: center; gap: 5px; padding: 8px 16px; border-radius: 8px; font-size: 13px; cursor: pointer; }
.primary-button { background: var(--primary); border: none; color: #fff; }
.primary-button:disabled { opacity: .5; cursor: not-allowed; }
.ghost-button { background: #fff; border: 1px solid var(--border-light); color: var(--text-secondary); }
.primary-button svg, .ghost-button svg { width: 14px; }

@media (max-width: 600px) {
  .pcq-stats { grid-template-columns: 1fr; }
  .rx-row { grid-template-columns: 1fr; }
}
</style>
