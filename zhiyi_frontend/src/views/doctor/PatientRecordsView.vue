<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, User, Calendar, ArrowRight, ArrowLeft } from '@element-plus/icons-vue'
import { getPatients, getPatientProfile, getDiagnosisHistory, deleteDiagnosis } from '@/api'

interface PatientListItem {
  id: number
  name: string
  age?: number
  gender?: string
  phone?: string
  last_visit?: string
  chief_complaint?: string
}
interface DiagnosisRecord {
  id: number; created_at: string; symptoms: string
  generated_at?: string
  suggestions?: Array<{ name: string }>; final_diagnosis?: string
  extracted_symptoms?: string[]
}

const router = useRouter()
const route = useRoute()
const patients = ref<PatientListItem[]>([])
const loading = ref(true)
const query = ref(typeof route.query.q === 'string' ? route.query.q : '')
const selectedPatient = ref<PatientListItem | null>(null)
const profile = ref<any>(null)
const history = ref<DiagnosisRecord[]>([])
const historyLoading = ref(false)
const deletingId = ref<number | null>(null)
const profileLoading = ref(false)

async function loadPatients() {
  loading.value = true
  try {
    patients.value = await getPatients()
  } catch {
    ElMessage.error('加载患者列表失败')
  } finally { loading.value = false }
}

const filtered = computed(() =>
  query.value
    ? patients.value.filter(p => p.name.includes(query.value) || (p.phone || '').includes(query.value))
    : patients.value
)

async function selectPatient(p: PatientListItem) {
  selectedPatient.value = p
  profileLoading.value = true
  historyLoading.value = true
  try {
    const [prof, diags] = await Promise.all([
      getPatientProfile(p.id).catch(() => null),
      getDiagnosisHistory(p.id).catch(() => []),
    ])
    profile.value = prof
    history.value = Array.isArray(diags) ? diags : []
  } catch {
    profile.value = null
    history.value = []
  } finally {
    profileLoading.value = false
    historyLoading.value = false
  }
}

function goDiagnosis(p: PatientListItem) {
  router.push({ path: '/doctor/diagnosis', query: { patient_id: p.id, patient_name: p.name } })
}

const diagnosisName = (d: any) =>
  d.final_diagnosis || d.suggestions?.[0]?.name || 'AI 辅助诊断'
async function removeDiagnosis(record: DiagnosisRecord) {
  if (deletingId.value) return
  try {
    await ElMessageBox.confirm('确定删除这条诊断记录吗？删除后不可恢复。', '删除诊断记录', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  deletingId.value = record.id
  try {
    await deleteDiagnosis(record.id)
    history.value = history.value.filter(d => d.id !== record.id)
    ElMessage.success('诊断记录已删除')
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败，请稍后重试')
  } finally {
    deletingId.value = null
  }
}

watch(
  () => route.query.q,
  (v) => { if (typeof v === 'string') query.value = v },
)

onMounted(loadPatients)
</script>
<template>
  <div class="records-page">
    <div class="page-head">
      <h1>患者档案</h1>
      <el-input v-model="query" placeholder="搜索患者姓名或手机号" prefix-icon="Search" clearable style="width:260px" />
    </div>
    <div class="records-layout">
      <!-- 左侧：患者列表 -->
      <aside class="patient-list">
        <div v-if="loading" class="empty">加载中…</div>
        <div v-else-if="!filtered.length" class="empty">暂无患者数据</div>
        <div v-for="p in filtered" :key="p.id" class="patient-row" :class="{ active: selectedPatient?.id === p.id }" @click="selectPatient(p)">
          <div class="avatar">{{ p.name?.charAt(0) || '?' }}</div>
          <div class="info">
            <strong>{{ p.name }}</strong>
            <small>{{ p.gender || '—' }} · {{ p.age || '—' }}岁 · {{ p.phone || '—' }}</small>
          </div>
          <span class="last-visit">{{ p.last_visit || '—' }}</span>
        </div>
      </aside>

      <!-- 右侧：详情面板 -->
      <main class="detail-panel">
        <div v-if="!selectedPatient" class="empty">请选择患者查看详情</div>

        <template v-else-if="profileLoading || historyLoading">
          <div class="empty">加载档案中…</div>
        </template>

        <template v-else>
          <!-- 患者横幅 -->
          <div class="pdp-hero">
            <div class="pdp-hero-bg" />
            <div class="pdp-hero-inner">
              <div class="pdp-avatar-wrap">
                <div class="pdp-avatar">{{ selectedPatient.name?.charAt(0) || '患' }}</div>
                <div class="pdp-avatar-ring" />
              </div>
              <div class="pdp-hero-text">
                <h1>{{ selectedPatient.name }}</h1>
                <div class="pdp-hero-chips">
                  <span class="pdp-chip">{{ selectedPatient.gender === 'M' ? '男' : '女' }} · {{ profile?.age || '—' }}岁</span>
                  <span class="pdp-chip blue">{{ selectedPatient.phone }}</span>
                  <span class="pdp-chip green">既往就诊 {{ history.length }} 次</span>
                </div>
              </div>
              <button class="btn-primary" @click="goDiagnosis(selectedPatient)">开始诊疗 <ArrowRight /></button>
            </div>
          </div>

          <!-- 健康档案卡片 -->
          <div class="pdp-grid">
            <div class="pdp-card allergy">
              <div class="pdp-card-icon allergy-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
              </div>
              <h3>过敏史</h3>
              <div class="pdp-tags" v-if="profile?.allergies?.length">
                <span v-for="a in profile.allergies" :key="a" class="pdp-tag danger">{{ a }}</span>
              </div>
              <p v-else class="pdp-none">无已知过敏史</p>
            </div>

            <div class="pdp-card history">
              <div class="pdp-card-icon history-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
              </div>
              <h3>既往病史</h3>
              <div class="pdp-tags" v-if="profile?.past_history?.length">
                <span v-for="h in profile.past_history" :key="h" class="pdp-tag warn">{{ h }}</span>
              </div>
              <p v-else class="pdp-none">无记录</p>
            </div>

            <div class="pdp-card family">
              <div class="pdp-card-icon family-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
              </div>
              <h3>家族病史</h3>
              <div class="pdp-tags" v-if="profile?.family_history?.length">
                <span v-for="f in profile.family_history" :key="f" class="pdp-tag purple">{{ f }}</span>
              </div>
              <p v-else class="pdp-none">无记录</p>
            </div>

            <div class="pdp-card lifestyle" v-if="profile?.lifestyle && Object.keys(profile.lifestyle).length">
              <div class="pdp-card-icon lifestyle-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
              </div>
              <h3>生活方式</h3>
              <div class="pdp-lifestyle-grid">
                <div v-for="(v, k) in profile.lifestyle" :key="k" class="pdp-life-item">
                  <span class="pdp-life-key">{{ k }}</span>
                  <span class="pdp-life-val">{{ v }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 诊断历史时间线 -->
          <div class="pdp-timeline">
            <div class="pdp-timeline-head">
              <h2>诊断历史</h2>
              <span class="pdp-count">{{ history.length }} 条记录</span>
            </div>
            <div v-if="!history.length" class="pdp-none" style="padding:32px 0">暂无诊断记录</div>
            <div v-for="(d, i) in history" :key="d.id" class="tl-item" :style="{ animationDelay: `${i * 0.06}s` }">
              <div class="tl-dot-wrap">
                <div class="tl-dot" />
                <div class="tl-line" />
              </div>
              <div class="tl-card">
                <div class="tl-card-top">
                  <strong>{{ diagnosisName(d) }}</strong>
                  <span class="tl-date">{{ (d.created_at || d.generated_at || '').slice(0, 16) }}</span>
                  <button class="tl-delete" :disabled="deletingId === d.id" @click="removeDiagnosis(d)">{{ deletingId === d.id ? '删除中…' : '删除' }}</button>
                </div>
                <p class="tl-symptoms" v-if="d.symptoms">主诉：{{ d.symptoms }}</p>
                <div class="tl-extract" v-if="d.extracted_symptoms?.length">
                  <span v-for="s in (Array.isArray(d.extracted_symptoms) ? d.extracted_symptoms.slice(0, 6) : [])" :key="s" class="pdp-tag sm blue">{{ s }}</span>
                </div>
              </div>
            </div>
          </div>
        </template>
      </main>
    </div>
  </div>
</template>
<style scoped>
.records-page { max-width: 1200px; margin: 0 auto; padding: 24px; }
.page-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-head h1 { font-size: 22px; font-weight: 700; }
.records-layout { display: grid; grid-template-columns: 320px 1fr; gap: 20px; min-height: 70vh; }

/* patient list */
.patient-list { background: #fff; border-radius: 14px; border: 1px solid var(--border-light); overflow-y: auto; max-height: calc(100vh - 140px); }
.patient-row { display: flex; align-items: center; gap: 12px; padding: 14px 16px; cursor: pointer; border-bottom: 1px solid var(--border-light); transition: background .15s; }
.patient-row:hover { background: var(--gray-50); }
.patient-row.active { background: var(--primary-soft); }
.avatar { width: 40px; height: 40px; border-radius: 50%; background: var(--primary); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: 700; flex-shrink: 0; }
.info { flex: 1; }
.info strong { display: block; font-size: 14px; }
.info small { font-size: 12px; color: var(--text-tertiary); }
.last-visit { font-size: 11px; color: var(--text-tertiary); white-space: nowrap; }

/* detail panel */
.detail-panel { background: #fff; border-radius: 14px; border: 1px solid var(--border-light); padding: 20px 24px; min-height: 60vh; }

/* hero banner */
.pdp-hero { position: relative; border-radius: 14px; overflow: hidden; margin-bottom: 20px; background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 50%, #7c3aed 100%); }
.pdp-hero-bg { position: absolute; inset: 0; opacity: .12; background: radial-gradient(circle at 20% 50%, #fff 0%, transparent 60%), radial-gradient(circle at 80% 30%, #60a5fa 0%, transparent 50%); }
.pdp-hero-inner { position: relative; z-index: 1; display: flex; align-items: center; gap: 16px; padding: 24px 28px; flex-wrap: wrap; }
.pdp-avatar-wrap { position: relative; flex-shrink: 0; }
.pdp-avatar { width: 56px; height: 56px; border-radius: 50%; background: rgba(255,255,255,.18); display: flex; align-items: center; justify-content: center; font-size: 24px; font-weight: 700; color: #fff; }
.pdp-avatar-ring { position: absolute; inset: -4px; border-radius: 50%; border: 2px solid rgba(255,255,255,.25); animation: ring-pulse 2.5s ease-in-out infinite; }
@keyframes ring-pulse { 0%,100%{border-color:rgba(255,255,255,.2);transform:scale(1)} 50%{border-color:rgba(255,255,255,.45);transform:scale(1.06)} }
.pdp-hero-text h1 { margin: 0 0 4px; font-size: 22px; color: #fff; font-weight: 700; }
.pdp-hero-chips { display: flex; gap: 8px; flex-wrap: wrap; }
.pdp-chip { display: inline-block; padding: 3px 12px; border-radius: 20px; font-size: 12px; font-weight: 500; backdrop-filter: blur(8px); background: rgba(255,255,255,.18); color: #e0f2fe; }
.pdp-chip.blue { background: rgba(255,255,255,.12); color: #cbd5e1; }
.pdp-chip.green { background: rgba(52,211,153,.15); color: #a7f3d0; }
.btn-primary { margin-left: auto; display: inline-flex; align-items: center; gap: 6px; padding: 10px 22px; border: none; border-radius: 10px; background: rgba(255,255,255,.18); color: #fff; font-size: 14px; font-weight: 600; cursor: pointer; transition: all .25s; }
.btn-primary:hover { background: rgba(255,255,255,.28); transform: translateY(-1px); }

/* health cards */
.pdp-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 20px; }
.pdp-card { position: relative; border-radius: 12px; padding: 18px 18px 14px; background: #fff; border: 1px solid var(--border-light); overflow: hidden; }
.pdp-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; }
.pdp-card.allergy::before { background: linear-gradient(90deg,#ef4444,#f97316); }
.pdp-card.history::before { background: linear-gradient(90deg,#f59e0b,#eab308); }
.pdp-card.family::before { background: linear-gradient(90deg,#8b5cf6,#a855f7); }
.pdp-card.lifestyle::before { background: linear-gradient(90deg,#10b981,#34d399); }
.pdp-card-icon { width: 34px; height: 34px; border-radius: 8px; display: flex; align-items: center; justify-content: center; margin-bottom: 10px; }
.pdp-card-icon svg { width: 18px; height: 18px; }
.allergy-icon { background: #fef2f2; color: #ef4444; }
.history-icon { background: #fffbeb; color: #f59e0b; }
.family-icon { background: #f5f3ff; color: #8b5cf6; }
.lifestyle-icon { background: #ecfdf5; color: #10b981; }
.pdp-card h3 { margin: 0 0 10px; font-size: 13px; font-weight: 600; }
.pdp-tags { display: flex; flex-wrap: wrap; gap: 5px; }
.pdp-tag { display: inline-block; padding: 3px 10px; border-radius: 5px; font-size: 11px; font-weight: 500; }
.pdp-tag.danger { background: #fef2f2; color: #dc2626; }
.pdp-tag.warn { background: #fffbeb; color: #d97706; }
.pdp-tag.purple { background: #f5f3ff; color: #7c3aed; }
.pdp-tag.blue { background: #eff6ff; color: #2563eb; }
.pdp-tag.sm { padding: 2px 7px; font-size: 10px; }
.pdp-none { color: var(--text-tertiary); font-size: 12px; margin: 0; }
.pdp-lifestyle-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.pdp-life-item { display: flex; flex-direction: column; gap: 1px; }
.pdp-life-key { font-size: 10px; color: var(--text-tertiary); text-transform: uppercase; }
.pdp-life-val { font-size: 13px; color: var(--text-primary); font-weight: 500; }

/* timeline */
.pdp-timeline { border-radius: 12px; background: #fff; border: 1px solid var(--border-light); padding: 20px 24px; }
.pdp-timeline-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 18px; }
.pdp-timeline-head h2 { margin: 0; font-size: 16px; font-weight: 700; }
.pdp-count { font-size: 12px; color: var(--text-tertiary); }
.tl-item { display: flex; gap: 14px; animation: tl-in .4s ease-out both; }
@keyframes tl-in { from{opacity:0;transform:translateX(-6px)} to{opacity:1;transform:translateX(0)} }
.tl-dot-wrap { display: flex; flex-direction: column; align-items: center; flex-shrink: 0; width: 18px; }
.tl-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--primary); box-shadow: 0 0 0 3px rgba(37,99,235,.12); margin-top: 5px; }
.tl-line { width: 2px; flex: 1; min-height: 14px; background: linear-gradient(180deg,var(--primary),#e0e7ff); }
.tl-item:last-child .tl-line { background: transparent; }
.tl-card { flex: 1; background: #f8fafc; border-radius: 8px; padding: 12px 14px; margin-bottom: 12px; border: 1px solid #eef2f6; }
.tl-card-top { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px; flex-wrap: wrap; gap: 4px; }
.tl-card-top strong { font-size: 13px; }
.tl-date { font-size: 10px; color: var(--text-tertiary); }
.tl-delete {
  margin-left: 8px;
  padding: 4px 10px;
  border: 1px solid var(--danger-light);
  border-radius: 6px;
  color: var(--danger);
  background: var(--bg-surface);
  font-size: 11px;
  cursor: pointer;
  transition: all .15s;
}
.tl-delete:hover:not(:disabled) { background: var(--danger-light); }
.tl-delete:disabled { opacity: .5; cursor: not-allowed; }
html.dark .tl-delete { background: var(--bg-surface); border-color: rgba(248,113,113,.45); }
.tl-symptoms { margin: 0 0 6px; font-size: 12px; color: var(--text-secondary); line-height: 1.5; }
.tl-extract { display: flex; flex-wrap: wrap; gap: 4px; }

.empty { text-align: center; padding: 60px 20px; color: var(--text-tertiary); font-size: 14px; }

@media (max-width: 900px) {
  .records-layout { grid-template-columns: 1fr; }
  .patient-list { max-height: 300px; }
  .pdp-grid { grid-template-columns: 1fr; }
  .pdp-hero-inner { flex-direction: column; align-items: flex-start; }
  .btn-primary { margin-left: 0; }
}
</style>
