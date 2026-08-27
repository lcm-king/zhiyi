<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import type { Component } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowDown, ArrowRight, Download, Refresh, TrendCharts, FirstAidKit, MagicStick, ShoppingBag, Bell, User } from '@element-plus/icons-vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TitleComponent, TooltipComponent } from 'echarts/components'
import { getDashboard, getAlerts, resolveAlert, exportReport } from '@/api'

use([CanvasRenderer, BarChart, LineChart, PieChart, GridComponent, LegendComponent, TitleComponent, TooltipComponent])

const refreshedAt = ref('刚刚')
const loading = ref(false)
const dashboard = ref<any>(null)
const alerts = ref<any[]>([])
const router = useRouter()
let pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  await refresh()
  pollTimer = setInterval(() => refresh(true), 30000)
})

onUnmounted(() => {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
})

async function refresh(silent = false) {
  loading.value = true
  try {
    const [dash, alertList] = await Promise.all([getDashboard(), getAlerts()])
    dashboard.value = dash
    alerts.value = Array.isArray(alertList) ? alertList : []
    refreshedAt.value = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    if (!silent) ElMessage.success('数据已刷新')
  } catch (e: any) {
    if (!silent) ElMessage.error(e.message || '刷新数据失败')
  } finally {
    loading.value = false
  }
}

async function handleAlert(alert: any) {
  try {
    await resolveAlert(alert.id)
    alerts.value = alerts.value.filter(a => a.id !== alert.id)
    ElMessage.success('告警已处理')
  } catch (e: any) {
    ElMessage.error(e.message || '处理失败')
  }
}

async function exportData() {
  try {
    const blob = await exportReport()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `智医运营报表_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('报表已导出')
  } catch (e: any) {
    ElMessage.error(e.message || '导出失败')
  }
}

const metricIcons: Record<string, Component> = {
  medical_services: FirstAidKit,
  auto_awesome: MagicStick,
  medication: ShoppingBag,
  notifications_active: Bell,
}

const metrics = computed(() => [
  { label: '今日接诊总量', value: String(dashboard.value?.today_consultations || 0), icon: 'medical_services', tone: 'blue' },
  { label: '人工智能辅助率', value: `${dashboard.value?.ai_usage_rate || 0}%`, icon: 'auto_awesome', tone: 'violet' },
  { label: '今日药品订单量', value: String(dashboard.value?.drug_order_count || 0), icon: 'medication', tone: 'green' },
  { label: '待处理告警', value: String(dashboard.value?.pending_alerts || 0), icon: 'notifications_active', tone: 'amber' },
])

const accessItems = [
  { icon: User, label: '医生管理', tone: 'blue', to: '/admin/doctors' },
  { icon: ShoppingBag, label: '药品与检查', tone: 'amber', to: '/admin/catalog' },
  { icon: FirstAidKit, label: '订单发货', tone: 'teal', to: '/admin/orders' },
  { icon: TrendCharts, label: '运营看板', tone: 'violet', to: '/admin/overview' },
]

const trendOption = computed(() => ({
  grid: { left: 0, right: 12, top: 16, bottom: 20, containLabel: true },
  tooltip: {
    trigger: 'axis',
    backgroundColor: '#1E293B',
    borderWidth: 0,
    textStyle: { color: '#fff', fontSize: 10 },
  },
  xAxis: {
    type: 'category',
    data: dashboard.value?.trend_labels || [],
    axisLine: { lineStyle: { color: '#E2E8F0' } },
    axisLabel: { color: '#94A3B8', fontSize: 9 },
  },
  yAxis: {
    type: 'value',
    splitLine: { lineStyle: { color: '#F1F5F9' } },
    axisLabel: { color: '#94A3B8', fontSize: 9 },
  },
  series: [
    {
      name: '总申请量',
      type: 'bar',
      barWidth: 16,
      data: dashboard.value?.trend_data || [],
      itemStyle: { color: '#3B82F6', borderRadius: [4, 4, 0, 0] },
    },
  ],
}))

const pieOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: {
    bottom: 0,
    itemWidth: 8,
    itemHeight: 8,
    textStyle: { color: '#94A3B8', fontSize: 9 },
  },
  series: [{
    type: 'pie',
    radius: ['52%', '74%'],
    center: ['50%', '43%'],
    label: { show: false },
    data: dashboard.value?.service_distribution || [],
  }],
}))

const alertCount = computed(() => alerts.value.length)
</script>

<template>
  <div class="admin-page">
    <!-- 页头 -->
    <div class="page-heading">
      <div>
        <div class="eyebrow">智医运营中心 / 管理总览</div>
        <h1 class="page-title">运营大盘</h1>
        <p class="page-subtitle">全域医疗服务实时概览，今天也在为每一个基层患者保持连接。</p>
      </div>
      <div class="admin-actions">
        <span class="admin-update-time">数据更新于 {{ refreshedAt }}</span>
        <button class="ghost-button" :disabled="loading" @click="() => refresh()">
          <Refresh /> {{ loading ? '刷新中…' : '刷新数据' }}
        </button>
        <button class="primary-button" @click="exportData">
          <Download /> 导出报表
        </button>
      </div>
    </div>

    <!-- 指标卡片 -->
    <div class="metric-grid">
      <div
        v-for="item in metrics"
        :key="item.label"
        class="metric-card"
        :style="{
          '--tone': `var(--${item.tone})`,
          '--tone-bg': `var(--${item.tone}-light, var(--primary-soft))`,
        }"
      >
        <div class="metric-top">
          <span>{{ item.label }}</span>
          <component :is="metricIcons[item.icon as keyof typeof metricIcons]" class="metric-icon" />
        </div>
        <div class="metric-value">{{ item.value }}</div>
        <div class="metric-foot">
          <span>实时数据库统计</span>
        </div>
      </div>
    </div>

    <!-- 管理员网格 -->
    <div class="admin-grid">
      <!-- 转诊趋势 -->
      <section class="surface-card admin-chart-card">
        <div class="section-title">
          <div>
            <div class="section-kicker"><span class="signal-line" />平台服务趋势</div>
            <h2>服务量趋势</h2>
            <p>过去 7 天 · 全平台聚合数据</p>
          </div>
          <div class="chart-legend-inline">
            <span><i class="legend-line blue-line" /> 诊断服务量</span>
          </div>
        </div>
        <VChart class="admin-chart-canvas" :option="trendOption" autoresize />
      </section>

      <!-- 服务类型分布 -->
      <section class="surface-card admin-pie-card">
        <div class="section-title">
          <div>
            <div class="section-kicker"><span class="signal-line" />服务类型</div>
            <h2>服务类型分布</h2>
          </div>
        </div>
        <VChart class="admin-pie-canvas" :option="pieOption" autoresize />
        <div class="admin-pie-total">
          <strong>{{ (dashboard?.monthly_services || 0).toLocaleString() }}</strong>
          <span>本月服务总量</span>
        </div>
      </section>

      <!-- 告警中心 -->
      <section class="surface-card admin-alert-card">
        <div class="section-title">
          <div>
            <div class="section-kicker"><span class="signal-line" />实时监控</div>
            <h2>
              告警中心
              <span class="alert-count-badge" v-if="alertCount">{{ alertCount }}</span>
            </h2>
          </div>
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th>告警内容</th>
              <th>级别</th>
              <th>时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="alert in alerts" :key="alert.id">
              <td><strong>{{ alert.content }}</strong></td>
              <td><span class="chip" :class="alert.level === 'high' ? 'chip-red' : alert.level === 'medium' ? 'chip-amber' : 'chip-blue'">{{ alert.level === 'high' ? '高' : alert.level === 'medium' ? '中' : '低' }}</span></td>
              <td>{{ alert.time }}</td>
              <td><button class="text-button" @click="handleAlert(alert)">{{ alert.action }}</button></td>
            </tr>
            <tr v-if="alerts.length === 0">
              <td colspan="4" style="text-align: center; color: var(--text-tertiary); padding: 24px;">暂无告警，系统运行正常</td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- 快捷入口 -->
      <section class="surface-card admin-access-card">
        <div class="section-title">
          <div>
            <div class="section-kicker"><span class="signal-line" />管理工具</div>
            <h2>快捷入口</h2>
          </div>
        </div>
        <div class="access-grid">
          <button
            v-for="item in accessItems"
            :key="item.label"
            class="access-item"
            :class="`tone-${item.tone}`"
            @click="router.push(item.to)"
          >
            <div class="access-icon">
              <component :is="item.icon" />
            </div>
            <span>{{ item.label }}</span>
            <ArrowRight />
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.admin-page { position: relative; }

/* ── 操作按钮 ── */
.admin-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.admin-update-time {
  color: var(--text-tertiary);
  font-size: 10px;
  font-family: var(--font-mono);
}

/* ── 指标网格 ── */
.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.metric-card {
  min-height: 130px;
  position: relative;
  overflow: hidden;
  padding: 20px 24px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  background: var(--bg-surface);
  box-shadow: var(--shadow-card);
  transition: all var(--transition-base);
}

.metric-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}

.metric-card::after {
  width: 52px;
  height: 52px;
  position: absolute;
  right: -24px;
  bottom: -30px;
  content: '';
  border-radius: 50%;
  background: var(--tone-bg);
  opacity: 0.35;
  transition: transform var(--transition-base);
}

.metric-card:hover::after {
  transform: scale(1.1);
}

/* 复用全局 metric 样式 */

/* ── 管理网格 ── */
.admin-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(280px, 0.65fr);
  gap: 20px;
  margin-top: 20px;
}

.admin-chart-card,
.admin-pie-card,
.admin-alert-card,
.admin-access-card {
  padding: 22px 24px;
}

.admin-chart-card {
  min-height: 340px;
}

.admin-chart-canvas {
  height: 240px;
  margin-top: 4px;
}

.chart-legend-inline {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: 10px;
  color: var(--text-tertiary);
}

.legend-line {
  display: inline-block;
  width: 16px;
  height: 2px;
  margin-right: 4px;
  border-radius: 1px;
}

.blue-line { background: #3B82F6; }
.teal-line { background: #0D9488; }

/* 饼图 */
.admin-pie-card {
  min-height: 340px;
  position: relative;
}

.admin-pie-canvas {
  height: 220px;
}

.admin-pie-total {
  position: absolute;
  left: 50%;
  top: 142px;
  transform: translateX(-50%);
  text-align: center;
  pointer-events: none;
}

.admin-pie-total strong {
  display: block;
  font-size: 22px;
  font-weight: 800;
  color: var(--text-primary);
}

.admin-pie-total span {
  font-size: 9px;
  color: var(--text-tertiary);
}

/* 告警中心 */
.admin-alert-card {
  min-height: 300px;
}

.alert-count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 5px;
  border-radius: var(--radius-full);
  background: var(--danger-light);
  color: var(--danger);
  font-size: 10px;
  font-weight: 800;
  margin-left: 8px;
}

.admin-alert-card .data-table {
  margin-top: 18px;
}

.data-table td:first-child strong {
  font-size: 11px;
  color: var(--text-primary);
}

.data-table td {
  vertical-align: middle;
}

.data-table td:nth-child(3) {
  font-size: 10px;
}

/* 快捷入口 */
.admin-access-card {
  min-height: 300px;
}

.access-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-top: 18px;
}

.access-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 16px 12px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  cursor: pointer;
  transition: all var(--transition-fast);
  text-align: center;
}

.access-item:hover {
  border-color: var(--border-focus);
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}

.access-icon {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-md);
}

.access-icon svg { width: 16px; }

.access-item.tone-blue .access-icon { background: #DBEAFE; color: #2563EB; }
.access-item.tone-teal .access-icon { background: #CCFBF1; color: #0D9488; }
.access-item.tone-amber .access-icon { background: #FEF3C7; color: #D97706; }
.access-item.tone-violet .access-icon { background: #EDE9FE; color: #7C3AED; }

.access-item span {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.access-item svg:last-child {
  width: 13px;
  color: var(--text-tertiary);
}

/* ── 响应式 ── */
@media (max-width: 900px) {
  .admin-grid {
    grid-template-columns: 1fr;
  }

  .admin-pie-card {
    min-height: 280px;
  }
}

@media (max-width: 650px) {
  .admin-actions > .admin-update-time { display: none; }
  .admin-actions > .ghost-button { display: none; }

  .admin-grid {
    gap: 14px;
  }

  .data-table {
    min-width: 560px;
  }

  .admin-alert-card {
    overflow-x: auto;
  }

  .admin-chart-card {
    padding: 16px;
  }

  .chart-legend-inline span { display: none; }
}
</style>
