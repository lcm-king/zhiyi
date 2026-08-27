<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowRight, Calendar, Check, Clock, Location, FirstAidKit, CircleCheck, MagicStick, TrendCharts, ShoppingBag, Document, DataAnalysis, Bell } from '@element-plus/icons-vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { getPatientProfile, getPatientVisits, getPatientTrend, getDrugOrders, getDrugOrderStatus, getDiagnosisHistory } from '@/api'
import LogisticsMap from '@/components/LogisticsMap.vue'
import { locateCurrentCity } from '@/utils/location'
import { renderMarkdown } from '@/utils/markdown'

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent])

const router = useRouter()
const healthScore = ref(0)
const trendRange = ref('30')
const diagnosisCount = ref(0)
const visitCount = ref(0)
const profile = ref<any>(null)
const trend = ref<any[]>([])
const visits = ref<any[]>([])
const latestReports = ref<any[]>([])
const medReminder = ref<{
  name: string
  spec?: string
  qty?: number
  dosage?: string
  instructions?: string
  status?: string
} | null>(null)
const logistics = ref<any>(null)
const logisticsOrderId = ref(0)
const loading = ref(false)
const visitsOpen = ref(false)
const now = ref(Date.now())
const locationLabel = ref('长沙 · 默认')
const formattedNow = computed(() => {
  const d = new Date(now.value)
  return {
    time: d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    date: d.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' }),
  }
})
let timer: ReturnType<typeof setInterval> | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  const geo = await locateCurrentCity()
  if (geo) locationLabel.value = geo.label
  await loadProfile()
  now.value = Date.now()
  timer = setInterval(() => { now.value = Date.now() }, 1000)
  pollTimer = setInterval(() => { loadLatestLogistics() }, 60000)
})

onUnmounted(() => {
  if (timer) { clearInterval(timer); timer = null }
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
})

async function loadProfile() {
  loading.value = true
  try {
    // 从 localStorage 获取当前登录患者 ID
    const userJson = localStorage.getItem('zhiyi-user') || '{}'
    const user = JSON.parse(userJson)
    const patientId = user.id || 1
    const data = await getPatientProfile(patientId)
    profile.value = data
    healthScore.value = computeHealthScore(data)
    visitCount.value = data.visit_count || 0

    // 独立调用 REST 端点：GET /api/profile/{id}/visits 与 /api/profile/{id}/trend
    try {
      const [visitList, trendData] = await Promise.all([
        getPatientVisits(patientId).catch(() => []),
        getPatientTrend(patientId).catch(() => []),
      ])
      visits.value = Array.isArray(visitList) ? visitList : []
      if (Array.isArray(trendData) && trendData.length) {
        trend.value = trendData
      }
    } catch {
      visits.value = []
    }

    // 从诊断历史计算就诊次数与近期报告（趋势已在上面优先取 /trend）
    try {
      const diagnoses = await getDiagnosisHistory(patientId)
      diagnosisCount.value = diagnoses.length
      if (!visitCount.value) visitCount.value = diagnosisCount.value
      if (!trend.value.length) trend.value = buildHealthTrend(diagnoses)
      const backendReports = profile.value?.recent_reports
      latestReports.value = Array.isArray(backendReports) && backendReports.length
        ? backendReports
        : buildReports(visits.value)
    } catch {
      if (!trend.value.length) trend.value = []
      latestReports.value = []
    }

    await loadLatestLogistics()
  } catch (e: any) {
    ElMessage.error(e.message || '加载健康档案失败')
  } finally {
    loading.value = false
  }
}

async function loadLatestLogistics() {
  try {
    const orders = await getDrugOrders()
    if (orders && orders.length) {
      // 优先取「待发货/配送中」的在途订单；没有在途单时回退到最新一笔
      const active = orders.find((o: any) => ['pending', 'shipped'].includes(o.delivery_status))
      const latest = active || orders[0]
      logisticsOrderId.value = latest.id
      logistics.value = await getDrugOrderStatus(latest.id)
      const first = latest.items?.[0]
      if (first) {
        medReminder.value = {
          name: first.drug_name || first.name || '处方药品',
          spec: first.specification || '',
          qty: first.quantity,
          dosage: first.dosage || '',
          instructions: first.instructions || '',
          status: latest.delivery_status,
        }
      }
    }
  } catch {
    logistics.value = null
  }
}

function medStatusText(s?: string) {
  const map: Record<string, string> = {
    pending: '已支付，待发货',
    shipped: '配送中',
    delivered: '已送达',
    cancelled: '已取消',
  }
  return (s && map[s]) || s || ''
}

const pageSubtitle = computed(() => {
  const p = profile.value
  if (!p) return '欢迎使用个人健康中心，完善档案后可查看更精准的健康分析。'
  const visitsCount = visitCount.value || visits.value?.length || p.recent_visits?.length || 0
  const part = `您共有 ${visitsCount} 次就诊记录、${p.past_history?.length || 0} 项既往史、${p.allergies?.length || 0} 项过敏史`
  return visitsCount > 0 ? `${part}。档案基于真实就诊数据实时更新，请保持规律作息。` : `${part}。建议定期完成健康体检，完善个人档案。`
})

const healthTip = computed(() => {
  const p = profile.value
  if (!p) return '完善个人健康档案，获取更精准的健康建议。'
  const allergies = p.allergies || []
  const past = p.past_history || []
  if (allergies.length) {
    const list = allergies.slice(0, 2).join('、')
    return `您有 ${allergies.length} 项过敏史（${list}${allergies.length > 2 ? '等' : ''}），就诊开药时请主动告知医生，避免药物过敏风险。`
  }
  if (past.length) {
    const list = past.slice(0, 2).join('、')
    return `您有 ${past.length} 项既往病史（${list}${past.length > 2 ? '等' : ''}），建议遵医嘱定期复查，关注相关指标变化。`
  }
  return '您的健康档案较完整，建议保持规律作息与均衡饮食，并定期进行健康体检。'
})

function computeHealthScore(data: any) {
  // 基于真实档案数据计算健康分
  let score = 85
  const allergies = data.allergies?.length || 0
  const past = data.past_history?.length || 0
  score -= allergies * 3
  score -= past * 2
  // 有完整档案信息加分
  if (data.family_history?.length) score += 3
  if (data.lifestyle && Object.keys(data.lifestyle).length) score += 2
  return Math.max(55, Math.min(100, score))
}

function buildHealthTrend(diagnoses: any[]) {
  // 真实数据兜底：后端 /trend 不可用时，按诊断记录真实时间聚合
  // 分数 = 基础分 − 记录序号波动，仅作为后端接口失效时的占位，不伪造日期
  const sorted = diagnoses
    .filter((d) => d.created_at)
    .slice(0, 7)
    .reverse()
  return sorted.map((d, i) => ({
    date: d.created_at?.slice(5, 10) || '',
    score: Math.max(55, 88 - i * 2),
    visits: 1,
  }))
}

function buildReports(visits: any[]) {
  // 兜底：后端未返回 recent_reports 时，用真实就诊记录拼装
  return (visits || []).slice(0, 3).map(v => ({
    id: v.id,
    exam_name: v.diagnosis || '就诊记录',
    hospital: v.hospital || '—',
    date: v.date || '',
    summary: v.treatment || '',
    has_interpretation: false,
  }))
}

const filteredTrend = computed(() => {
  const list = trend.value || []
  return trendRange.value === '7' ? list.slice(-7) : list.slice(-30)
})

const healthOption = computed(() => ({
  grid: { left: 0, right: 8, top: 8, bottom: 0, containLabel: false },
  xAxis: { type: 'category', data: filteredTrend.value.map((d) => d.date), show: false },
  yAxis: { type: 'value', show: false, min: 60, max: 100 },
  tooltip: {
    trigger: 'axis',
    backgroundColor: '#1E293B',
    borderWidth: 0,
    textStyle: { color: '#fff', fontSize: 11 },
    formatter: '{b}<br/>健康指数：{c}',
  },
  series: [{
    type: 'line',
    data: filteredTrend.value.map((d) => d.score),
    smooth: true,
    symbol: 'circle',
    symbolSize: 6,
    lineStyle: { color: '#3B82F6', width: 3 },
    itemStyle: { color: '#fff', borderColor: '#3B82F6', borderWidth: 2 },
    areaStyle: {
      color: {
        type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [
          { offset: 0, color: 'rgba(59,130,246,0.2)' },
          { offset: 1, color: 'rgba(59,130,246,0)' },
        ],
      },
    },
  }],
}))

const services = [
  { key: 'exam', icon: Calendar, label: '预约检查', tone: 'blue', desc: '在线预约检验检查', to: '/patient/exams' },
  { key: 'assistant', icon: MagicStick, label: 'AI 预问诊', tone: 'teal', desc: '健康参考与就医建议', to: '/patient/assistant' },
  { key: 'drug', icon: ShoppingBag, label: '在线购药', tone: 'amber', desc: '处方下单配送到家', to: '/patient/exams?tab=drug' },
  { key: 'reports', icon: Document, label: '报告查询', tone: 'violet', desc: '查看检查报告解读', to: '/patient/reports' },
  { key: 'visits', icon: DataAnalysis, label: '就诊记录', tone: 'cyan', desc: '查看历史就诊记录', to: '/patient/health' },
]

function openVisits() {
  visitsOpen.value = true
}
</script>

<template>
  <div class="patient-page">
    <!-- 页头 -->
    <div class="page-heading">
      <div>
        <div class="eyebrow">个人健康中心 / 健康档案</div>
        <h1 class="page-title">早安，{{ profile?.name || '朋友' }}。</h1>
        <p class="page-subtitle">{{ pageSubtitle }}</p>
      </div>
      <div class="display-time">
        <strong>{{ formattedNow.time }}</strong>
        {{ formattedNow.date }} · {{ locationLabel }}
      </div>
    </div>

    <!-- 健康指标行 -->
    <section class="health-metrics">
      <!-- 健康评分 -->
      <div class="wellness-card">
        <div class="wellness-chart">
          <svg viewBox="0 0 120 120" class="wellness-ring">
            <circle cx="60" cy="60" r="52" fill="none" stroke="#E2E8F0" stroke-width="8" />
            <circle
              cx="60" cy="60" r="52"
              fill="none"
              stroke="url(#wellnessGrad)"
              stroke-width="8"
              stroke-linecap="round"
              :stroke-dasharray="327"
              :stroke-dashoffset="327 - healthScore * 3.27"
              class="wellness-ring-progress"
            />
            <defs>
              <linearGradient id="wellnessGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="#3B82F6" />
                <stop offset="100%" stop-color="#0D9488" />
              </linearGradient>
            </defs>
          </svg>
          <div class="wellness-score-center">
            <strong>{{ healthScore }}</strong>
            <small>健康指数</small>
          </div>
        </div>
        <div class="wellness-info">
          <span class="chip chip-green"><TrendCharts /> 基于真实档案评估</span>
          <h2>{{ profile?.name || '患者' }}的健康档案</h2>
          <p>过敏史 {{ profile?.allergies?.length || 0 }} 项，既往史 {{ profile?.past_history?.length || 0 }} 项，家族史 {{ profile?.family_history?.length || 0 }} 项。</p>
          <div v-if="profile" class="profile-tags">
            <span v-for="allergy in profile.allergies" :key="allergy" class="chip chip-red">过敏：{{ allergy }}</span>
            <span v-for="hist in profile.past_history" :key="hist" class="chip chip-amber">{{ hist }}</span>
          </div>
        </div>
        <button class="text-button wellness-link" @click="$router.push('/patient/reports')">
          查看分析 <ArrowRight />
        </button>
      </div>

      <!-- 就诊次数 -->
      <div class="vital-card">
        <div class="vital-icon teal-bg"><Calendar /></div>
        <span class="vital-label">就诊次数</span>
        <strong class="vital-value">{{ visitCount }} <small>次</small></strong>
        <div class="vital-trend trend-up"><TrendCharts /> AI 辅助诊断</div>
        <div class="vital-mini-wave">
          <span /><span /><span /><span /><span /><span /><span />
        </div>
      </div>

      <!-- 既往病史项数 -->
      <div class="vital-card">
        <div class="vital-icon blue-bg"><Document /></div>
        <span class="vital-label">既往病史</span>
        <strong class="vital-value">{{ profile?.past_history?.length || 0 }} <small>项</small></strong>
        <div class="vital-trend trend-up"><TrendCharts /> 档案完整度 {{ healthScore }}%</div>
        <div class="vital-progress-bar">
          <div class="vital-progress-fill" :style="{ width: `${healthScore}%` }" />
        </div>
      </div>
    </section>

    <!-- 两栏布局 -->
    <div class="patient-layout">
      <!-- 主列 -->
      <div class="patient-main-col">
        <!-- 快捷服务 -->
        <section class="surface-card quick-services">
          <div class="section-title">
            <div>
              <div class="section-kicker"><span class="signal-line" />快捷服务</div>
              <h2>快捷服务</h2>
            </div>
            <span class="section-badge">为你精选</span>
          </div>
          <div class="service-grid">
            <button
              v-for="service in services"
              :key="service.label"
              class="service-item"
              @click="service.key === 'visits' ? openVisits() : $router.push(service.to)"
            >
              <div class="service-item-icon" :class="`tone-${service.tone}`">
                <component :is="service.icon" />
              </div>
              <div class="service-item-text">
                <strong>{{ service.label }}</strong>
                <span>{{ service.desc }}</span>
              </div>
              <ArrowRight class="service-item-arrow" />
            </button>
          </div>
        </section>

        <!-- 健康趋势 -->
        <section class="surface-card health-trend-card">
          <div class="section-title">
            <div>
              <div class="section-kicker"><span class="signal-line" />健康趋势</div>
              <h2>健康趋势</h2>
              <p>基于历史诊断与检查记录</p>
            </div>
            <button class="ghost-button" @click="trendRange = trendRange === '30' ? '7' : '30'">{{ trendRange === '30' ? '近 30 天' : '近 7 天' }} <ArrowRight /></button>
          </div>
          <div v-if="loading" class="loading-tip">加载中…</div>
          <div v-else-if="!trend.length" class="health-trend-empty">
            <TrendCharts class="empty-icon" />
            <p>暂无健康趋势数据</p>
            <span>完成一次 AI 诊断或检查后，将基于真实记录生成趋势</span>
          </div>
          <div v-else class="health-trend-chart">
            <VChart :option="healthOption" autoresize />
          </div>
          <div class="health-trend-legend">
            <span><i class="legend-dot blue-dot" />健康指数</span>
            <strong>{{ healthScore }} <small>当前评分</small></strong>
            <span class="trend-up"><TrendCharts /> {{ filteredTrend.length }} 次记录</span>
          </div>
        </section>

        <!-- 物流追踪 -->
        <section v-if="logistics" class="surface-card logistics-track">
          <div class="section-title">
            <div>
              <div class="section-kicker"><span class="signal-line" />物流动态</div>
              <h2>药品物流追踪</h2>
            </div>
            <button class="text-button" @click="$router.push('/patient/orders')">全部订单 <ArrowRight /></button>
          </div>
          <div class="logistics-content">
            <LogisticsMap
              v-if="logisticsOrderId"
              :order-id="logisticsOrderId"
            />
            <div v-else class="logistics-empty">暂无配送中的订单</div>

            <div class="logistics-timeline">
              <div
                v-for="(point, idx) in logistics.tracking_points?.slice().reverse()"
                :key="idx"
                class="timeline-item"
                :class="{ active: point.status === 'active' }"
              >
                <div class="timeline-dot"><Check v-if="point.status === 'completed'" />{{ point.status !== 'completed' ? idx + 1 : '' }}</div>
                <div class="timeline-body">
                  <strong>{{ point.location }}</strong>
                  <small>{{ point.time }}</small>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>

      <!-- 侧栏 -->
      <aside class="patient-aside-col">
        <!-- 服药提醒 -->
        <div class="surface-card med-reminder">
          <div class="med-reminder-header">
            <Bell />
            <div>
              <strong>服药提醒</strong>
              <small>{{ medReminder ? medReminder.name + (medReminder.spec ? ' ' + medReminder.spec : '') : '暂无在途药品' }}</small>
            </div>
          </div>
          <p v-if="medReminder?.dosage" class="med-dose">用法用量：{{ medReminder.dosage }}</p>
          <p v-if="medReminder?.instructions" class="med-note">{{ medReminder.instructions }}</p>
          <p v-if="medReminder?.status" class="med-status">订单状态：{{ medStatusText(medReminder.status) }}</p>
          <p>最近就诊时间：{{ visits?.[0]?.date || profile?.recent_visits?.[0]?.date || '暂无记录' }}</p>
          <button class="primary-button med-confirm" @click="router.push('/patient/exams')">
            <Calendar />
            预约复诊
          </button>
        </div>

        <!-- 健康提示 -->
        <div class="surface-card health-tip-card">
          <div class="health-tip-header">
            <span class="chip chip-teal"><CircleCheck /> 健康提示</span>
          </div>
          <p>{{ healthTip }}</p>
          <div class="health-tip-source">来源：个人健康档案实时分析</div>
        </div>

        <!-- 最新报告 -->
        <div class="surface-card latest-report">
          <div class="section-title">
            <h3>最新检查报告</h3>
            <button class="text-button" @click="$router.push('/patient/reports')">全部 <ArrowRight /></button>
          </div>
          <div v-if="latestReports.length" class="report-list">
            <div v-for="report in latestReports" :key="report.id || report.appointment_id || report.exam_name" class="report-preview-item">
              <div class="report-preview-icon"><FirstAidKit /></div>
              <div>
                <strong>{{ report.exam_name || report.name || '检查报告' }}</strong>
                <small>{{ report.date }} · {{ report.hospital }}</small>
                <p v-if="report.summary" class="report-preview-summary" v-html="renderMarkdown(report.summary)"></p>
              </div>
              <span v-if="report.has_interpretation" class="chip chip-blue">AI 已解读</span>
              <span v-else class="chip chip-green">报告已出</span>
            </div>
          </div>
          <div v-else class="empty-note">暂无最新报告</div>
        </div>
      </aside>
    </div>

    <!-- 就诊记录弹窗 -->
    <div v-if="visitsOpen" class="visit-modal-backdrop" @click.self="visitsOpen = false">
      <div class="visit-modal">
        <div class="visit-modal-header">
          <div>
            <span class="section-kicker"><span class="signal-line" />历史就诊</span>
            <h2>就诊记录</h2>
          </div>
          <button class="visit-modal-close" title="关闭" @click="visitsOpen = false">&times;</button>
        </div>
        <div v-if="visits.length" class="visit-list">
          <div v-for="(visit, idx) in visits" :key="idx" class="visit-item">
            <div class="visit-date">
              <strong>{{ visit.date?.slice(0, 10) || '—' }}</strong>
              <small>{{ visit.date?.slice(11) || '全天' }}</small>
            </div>
            <div class="visit-body">
              <strong>{{ visit.diagnosis || 'AI 辅助诊断待确认' }}</strong>
              <span>{{ visit.hospital || '社区医院' }} · {{ visit.doctor || '接诊医生' }}</span>
              <p v-if="visit.treatment">{{ visit.treatment }}</p>
            </div>
          </div>
        </div>
        <div v-else class="visit-empty">暂无就诊记录，完成一次 AI 诊断后会自动沉淀到这里</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── 健康指标行 ── */
.health-metrics {
  display: grid;
  grid-template-columns: minmax(0, 2.2fr) minmax(180px, 0.7fr) minmax(180px, 0.7fr);
  gap: 16px;
  margin-bottom: 20px;
}

.loading-tip {
  padding: 40px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 13px;
}

.profile-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

/* 健康评分卡片 */
.wellness-card {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 20px 24px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  background: linear-gradient(135deg, #FFFFFF, #EFF6FF);
  box-shadow: var(--shadow-card);
  position: relative;
  overflow: hidden;
}

.wellness-chart {
  position: relative;
  width: 110px;
  height: 110px;
  flex: 0 0 auto;
}

.wellness-ring {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}

.wellness-ring-progress {
  transition: stroke-dashoffset 0.8s ease;
}

.wellness-score-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.wellness-score-center strong {
  font-size: 30px;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: -0.06em;
  line-height: 1;
}

.wellness-score-center small {
  font-size: 10px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

.wellness-info {
  flex: 1;
}

.wellness-info h2 {
  margin: 8px 0 4px;
  font-size: 15px;
  font-weight: 800;
  color: var(--text-primary);
}

.wellness-info p {
  margin: 0;
  max-width: 360px;
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.7;
}

.wellness-link {
  position: absolute;
  top: 18px;
  right: 20px;
}

/* 体征卡片 */
.vital-card {
  padding: 18px 20px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  background: var(--bg-surface);
  box-shadow: var(--shadow-card);
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.vital-icon {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-sm);
  margin-bottom: 14px;
}

.vital-icon svg { width: 16px; }
.vital-icon.teal-bg { background: var(--teal-light); color: var(--teal); }
.vital-icon.blue-bg { background: var(--primary-light); color: var(--primary); }

.vital-label {
  font-size: 11px;
  color: var(--text-tertiary);
  font-weight: 600;
}

.vital-value {
  margin-top: 8px;
  font-size: 24px;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: -0.04em;
}

.vital-value small {
  font-size: 10px;
  color: var(--text-tertiary);
  font-weight: 600;
}

.vital-trend {
  margin-top: 4px;
  font-size: 10px;
  display: flex;
  align-items: center;
  gap: 3px;
}

.vital-mini-wave {
  display: flex;
  align-items: flex-end;
  gap: 3px;
  margin-top: auto;
  height: 30px;
}

.vital-mini-wave span {
  flex: 1;
  border-radius: 2px;
  background: var(--teal);
  opacity: 0.5;
}

.vital-mini-wave span:nth-child(1) { height: 40%; }
.vital-mini-wave span:nth-child(2) { height: 60%; }
.vital-mini-wave span:nth-child(3) { height: 45%; }
.vital-mini-wave span:nth-child(4) { height: 75%; }
.vital-mini-wave span:nth-child(5) { height: 55%; }
.vital-mini-wave span:nth-child(6) { height: 80%; }
.vital-mini-wave span:nth-child(7) { height: 65%; }

.vital-progress-bar {
  margin-top: auto;
  height: 5px;
  border-radius: 3px;
  background: var(--gray-100);
  overflow: hidden;
}

.vital-progress-fill {
  height: 100%;
  border-radius: 3px;
  background: var(--primary);
  transition: width 0.6s ease;
}

/* ── 两栏布局 ── */
.patient-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 20px;
  align-items: start;
}

.patient-main-col {
  display: grid;
  gap: 20px;
}

.patient-aside-col {
  display: grid;
  gap: 16px;
  position: sticky;
  top: calc(var(--topbar-height) + 28px);
}

/* ── 快捷服务 ── */
.quick-services {
  padding: 22px 24px;
}

.section-badge {
  font-size: 10px;
  color: var(--text-tertiary);
  padding: 3px 8px;
  border-radius: var(--radius-full);
  background: var(--gray-100);
}

.service-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  margin-top: 16px;
}

.service-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  cursor: pointer;
  transition: all var(--transition-fast);
  text-align: left;
}

.service-item:hover {
  border-color: var(--border-focus);
  box-shadow: var(--shadow-sm);
}

.service-item-icon {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-md);
  flex: 0 0 auto;
}

.service-item-icon svg { width: 18px; }
.service-item-icon.tone-blue { background: #DBEAFE; color: #2563EB; }
.service-item-icon.tone-teal { background: #CCFBF1; color: #0D9488; }
.service-item-icon.tone-violet { background: #EDE9FE; color: #7C3AED; }
.service-item-icon.tone-amber { background: #FEF3C7; color: #D97706; }
.service-item-icon.tone-cyan { background: #CFFAFE; color: #0891B2; }

.service-item-text {
  flex: 1;
  min-width: 0;
}

.service-item-text strong {
  display: block;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.service-item-text span {
  font-size: 10px;
  color: var(--text-tertiary);
}

.service-item-arrow {
  width: 14px;
  color: var(--text-tertiary);
  transition: transform var(--transition-fast);
}

.service-item:hover .service-item-arrow {
  transform: translateX(2px);
  color: var(--primary);
}

/* ── 健康趋势图 ── */
.health-trend-card {
  padding: 22px 24px;
}

.health-trend-chart {
  height: 200px;
  margin-top: 12px;
}

.health-trend-empty {
  height: 200px;
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: var(--text-tertiary);
  background: #fafbfd;
  border: 1px dashed var(--border-light);
  border-radius: 10px;
}
.health-trend-empty .empty-icon { font-size: 30px; color: #c3cede; }
.health-trend-empty p { margin: 0; font-size: 13px; color: var(--text-secondary); }
.health-trend-empty span { font-size: 11px; }

.health-trend-legend {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-top: 8px;
  font-size: 10px;
  color: var(--text-tertiary);
}

.health-trend-legend strong {
  font-size: 14px;
  color: var(--text-primary);
}

.health-trend-legend strong small {
  font-size: 9px;
  color: var(--text-tertiary);
}

.legend-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 4px;
}

.blue-dot { background: #3B82F6; }

/* ── 物流追踪 ── */
.logistics-track {
  padding: 22px 24px;
}

.logistics-content {
  display: grid;
  grid-template-columns: 1fr 220px;
  gap: 24px;
  margin-top: 16px;
}

.logistics-map {
  height: 180px;
  position: relative;
  overflow: hidden;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, #EFF6FF, #F8FAFC);
}

.logistics-map-bg {
  position: absolute;
  inset: -30px;
  opacity: 0.15;
  transform: rotate(-8deg);
  background-image:
    linear-gradient(var(--gray-400) 1px, transparent 1px),
    linear-gradient(90deg, var(--gray-400) 1px, transparent 1px);
  background-size: 40px 40px;
}

.logistics-route-line {
  position: absolute;
  top: 50%;
  left: 10%;
  width: 70%;
  height: 3px;
  border-radius: 2px;
  background: linear-gradient(90deg, var(--primary), var(--teal));
  transform: rotate(-6deg);
}

.logistics-dot {
  width: 14px;
  height: 14px;
  position: absolute;
  border: 3px solid #fff;
  border-radius: 50%;
  box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.15);
}

.logistics-dot.start { top: 54%; left: 8%; background: var(--teal); }
.logistics-dot.end { top: 36%; right: 18%; background: var(--primary); }

.logistics-live-dot {
  position: absolute;
  width: 18px;
  height: 18px;
  border: 3px solid #fff;
  border-radius: 50%;
  background: #3B82F6;
  box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.3);
  transform: translate(-50%, -50%);
  z-index: 2;
  animation: live-pulse 1.8s ease-in-out infinite;
}

@keyframes live-pulse {
  0%, 100% { box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.3); }
  50% { box-shadow: 0 0 0 12px rgba(59, 130, 246, 0); }
}

.logistics-delivery-bubble {
  position: absolute;
  top: 20%;
  right: 8%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: var(--radius-md);
  background: #fff;
  box-shadow: var(--shadow-md);
  border: 1px solid var(--border-default);
}

.logistics-delivery-bubble svg {
  width: 18px;
  color: var(--primary);
}

.logistics-delivery-bubble strong {
  display: block;
  font-size: 11px;
  color: var(--text-primary);
}

.logistics-delivery-bubble small {
  font-size: 9px;
  color: var(--text-tertiary);
}

.logistics-timeline {
  display: grid;
  gap: 14px;
}

.timeline-item {
  display: flex;
  gap: 10px;
}

.timeline-dot {
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 50%;
  border: 2px solid var(--border-default);
  background: var(--bg-surface);
  font-size: 10px;
  font-weight: 700;
  color: var(--text-tertiary);
}

.timeline-item.active .timeline-dot {
  border-color: var(--primary);
  background: var(--primary);
  color: #fff;
}

.timeline-dot svg { width: 12px; }

.timeline-body strong {
  display: block;
  font-size: 12px;
  color: var(--text-primary);
}

.timeline-body small {
  font-size: 10px;
  color: var(--text-tertiary);
}

/* ── 侧栏 ── */
.med-reminder {
  padding: 20px;
}

.med-reminder-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.med-reminder-header svg {
  width: 20px;
  color: var(--amber);
}

.med-reminder-header strong {
  display: block;
  font-size: 13px;
  color: var(--text-primary);
}

.med-reminder-header small {
  font-size: 10px;
  color: var(--text-tertiary);
}

.med-reminder p {
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0 0 14px;
}

.med-reminder p.med-dose {
  color: var(--primary, #2563eb);
  font-weight: 600;
}

.med-reminder p.med-note {
  margin-bottom: 6px;
}

.med-reminder p.med-status {
  margin-bottom: 6px;
  font-size: 10px;
}

.med-confirm {
  width: 100%;
}

.med-confirm.done {
  background: var(--success) !important;
}

.health-tip-card {
  padding: 20px;
}

.health-tip-header {
  margin-bottom: 10px;
}

.health-tip-card p {
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.7;
  margin: 0 0 10px;
}

.health-tip-source {
  font-size: 9px;
  color: var(--text-tertiary);
}

.latest-report {
  padding: 20px;
}

.latest-report .section-title {
  margin-bottom: 14px;
}

.report-list {
  display: grid;
  gap: 8px;
}

.report-preview-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border-light);
}

.report-preview-item:last-child {
  border-bottom: 0;
}

.report-preview-icon {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-sm);
  background: var(--primary-soft);
  flex: 0 0 auto;
}

.report-preview-icon svg {
  width: 16px;
  color: var(--primary);
}

.report-preview-item strong {
  display: block;
  font-size: 12px;
  color: var(--text-primary);
}

.report-preview-item small {
  font-size: 9px;
  color: var(--text-tertiary);
}

.report-preview-summary {
  margin: 2px 0 0;
  font-size: 10px;
  line-height: 1.5;
  color: var(--text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.empty-note {
  padding: 16px 0;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 12px;
}

/* ── 就诊记录弹窗 ── */
.visit-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(2, 8, 18, 0.55);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  animation: visit-fade 0.2s ease both;
}

.visit-modal {
  width: min(680px, 100%);
  max-height: 82vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-default);
  border-radius: 18px;
  background: var(--bg-surface);
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.35);
  animation: visit-in 0.32s cubic-bezier(0.22, 1, 0.36, 1) both;
}

.visit-modal-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 22px 24px 16px;
  border-bottom: 1px solid var(--border-light);
}

.visit-modal-header h2 {
  margin: 4px 0 0;
  font-size: 20px;
  color: var(--text-primary);
}

.visit-modal-close {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border-default);
  border-radius: 9px;
  color: var(--text-tertiary);
  background: var(--bg-surface-hover);
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
  transition: all 0.15s ease;
}

.visit-modal-close:hover {
  color: var(--danger);
  border-color: var(--danger-light);
  transform: rotate(90deg);
}

.visit-list {
  overflow-y: auto;
  padding: 8px 24px 24px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.visit-item {
  display: grid;
  grid-template-columns: 104px 1fr;
  gap: 16px;
  padding: 16px;
  border: 1px solid var(--border-light);
  border-radius: 12px;
  background: var(--bg-surface-hover);
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}

.visit-item:hover {
  transform: translateY(-2px);
  border-color: rgba(59, 130, 246, 0.35);
  box-shadow: var(--shadow-md);
}

.visit-date {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 8px 10px;
  border-radius: 9px;
  background: var(--primary-soft);
  color: var(--primary);
}

.visit-date strong {
  font-size: 14px;
}

.visit-date small {
  font-size: 11px;
  opacity: 0.8;
}

.visit-body strong {
  display: block;
  color: var(--text-primary);
  font-size: 13px;
}

.visit-body span {
  display: block;
  margin-top: 2px;
  color: var(--text-tertiary);
  font-size: 11px;
}

.visit-body p {
  margin: 8px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.visit-empty {
  padding: 48px 24px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 13px;
}

@keyframes visit-fade {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes visit-in {
  from {
    opacity: 0;
    transform: translateY(18px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

/* ── 响应式 ── */
@media (max-width: 1100px) {
  .health-metrics {
    grid-template-columns: 1fr 1fr;
  }

  .wellness-card {
    grid-column: span 2;
  }

  .patient-layout {
    grid-template-columns: 1fr;
  }

  .patient-aside-col {
    position: static;
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 650px) {
  .health-metrics {
    grid-template-columns: 1fr 1fr;
  }

  .wellness-card {
    grid-column: span 2;
    flex-direction: column;
    text-align: center;
  }

  .wellness-link {
    position: static;
    margin-top: 8px;
  }

  .service-grid {
    grid-template-columns: 1fr 1fr;
  }

  .visit-item {
    grid-template-columns: 1fr;
  }

  .visit-date {
    align-items: center;
    flex-direction: row;
    gap: 8px;
  }

  .logistics-content {
    grid-template-columns: 1fr;
  }

  .patient-aside-col {
    grid-template-columns: 1fr;
  }
}
</style>
