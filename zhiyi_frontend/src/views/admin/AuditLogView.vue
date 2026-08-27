<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Document, Clock } from '@element-plus/icons-vue'
import { getAuditLogs } from '@/api'
import type { AuditLogItem } from '@/types'

const list = ref<AuditLogItem[]>([])
const loading = ref(false)
const filter = ref<'all' | 'login' | 'business' | 'admin'>('all')

const actionLabel: Record<string, string> = {
  user_register: '注册',
  user_login: '登录',
  demo_login: '演示登录',
  sms_login: '短信登录',
  pre_consult: 'AI 预问诊',
  diagnosis_create: '生成诊断',
  diagnosis_confirm: '确认诊断',
  drug_order_create: '药品下单',
  order_ship: '订单发货',
  doctor_create: '新增医生',
  doctor_toggle: '启停医生',
  doctor_delete: '删除医生',
  drug_create: '新增药品',
  drug_update: '更新药品',
  drug_delete: '下架药品',
  exam_item_create: '新增检查',
  exam_item_update: '更新检查',
  exam_item_delete: '下架检查',
  alert_resolve: '处理告警',
}

const filtered = computed(() => {
  if (filter.value === 'all') return list.value
  if (filter.value === 'login') {
    return list.value.filter((i) => ['user_register', 'user_login', 'demo_login', 'sms_login'].includes(i.action))
  }
  if (filter.value === 'admin') {
    return list.value.filter((i) => i.action.startsWith('doctor_') || i.action.startsWith('drug_') || i.action.startsWith('exam_item_') || i.action === 'order_ship' || i.action === 'alert_resolve')
  }
  return list.value.filter((i) => ['pre_consult', 'diagnosis_create', 'diagnosis_confirm', 'drug_order_create'].includes(i.action))
})

async function load() {
  loading.value = true
  try {
    list.value = await getAuditLogs()
  } catch (e: any) {
    ElMessage.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function actionText(action: string): string {
  return actionLabel[action] || action
}

function detailText(item: AuditLogItem): string {
  if (!item.detail) return '—'
  try {
    return JSON.stringify(item.detail)
  } catch {
    return String(item.detail)
  }
}

onMounted(load)
</script>

<template>
  <div class="audit-page">
    <div class="audit-head">
      <div>
        <h1>操作日志</h1>
        <p>关键操作留痕，支持按类型追溯（医疗合规）</p>
      </div>
      <button class="refresh-btn" :disabled="loading" @click="load">
        <Refresh /> {{ loading ? '加载中…' : '刷新' }}
      </button>
    </div>

    <div class="filters">
      <button :class="{ active: filter === 'all' }" @click="filter = 'all'">全部 {{ list.length }}</button>
      <button :class="{ active: filter === 'login' }" @click="filter = 'login'">登录认证</button>
      <button :class="{ active: filter === 'business' }" @click="filter = 'business'">诊疗业务</button>
      <button :class="{ active: filter === 'admin' }" @click="filter = 'admin'">后台管理</button>
    </div>

    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="!filtered.length" class="empty">暂无日志记录</div>
    <div v-else class="table-wrap">
      <table class="audit-table">
        <thead>
          <tr>
            <th>时间</th>
            <th>操作人</th>
            <th>动作</th>
            <th>对象</th>
            <th>详情</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in filtered" :key="item.id">
            <td><span class="time-cell"><Clock /> {{ item.created_at }}</span></td>
            <td>{{ item.username || ('#' + (item.user_id ?? '匿名')) }}</td>
            <td><span class="action-tag">{{ actionText(item.action) }}</span></td>
            <td>
              <span v-if="item.resource">{{ item.resource }}<template v-if="item.resource_id"> #{{ item.resource_id }}</template></span>
              <span v-else>—</span>
            </td>
            <td class="detail-cell">{{ detailText(item) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.audit-page { max-width: 980px; margin: 0 auto; padding: 24px; }
.audit-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.audit-head h1 { font-size: 22px; font-weight: 700; margin-bottom: 4px; }
.audit-head p { margin: 0; color: var(--text-secondary); font-size: 13px; }
.refresh-btn { display: flex; align-items: center; gap: 5px; padding: 7px 14px; border-radius: 8px; border: 1px solid var(--border-light); background: #fff; cursor: pointer; font-size: 12px; }
.refresh-btn svg { width: 14px; }

.filters { display: flex; gap: 6px; margin-bottom: 16px; }
.filters button { padding: 6px 14px; border-radius: 7px; border: 1px solid var(--border-light); background: #fff; font-size: 13px; cursor: pointer; }
.filters button.active { background: var(--primary); color: #fff; border-color: var(--primary); }

.empty { text-align: center; padding: 60px; color: var(--text-tertiary); font-size: 14px; }
.table-wrap { background: #fff; border: 1px solid var(--border-light); border-radius: 12px; overflow-x: auto; }
.audit-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.audit-table th, .audit-table td { text-align: left; padding: 11px 14px; border-bottom: 1px solid var(--border-light); vertical-align: top; }
.audit-table th { background: var(--gray-50); color: var(--text-tertiary); font-size: 11px; font-weight: 700; white-space: nowrap; }
.audit-table tr:last-child td { border-bottom: 0; }
.time-cell { display: inline-flex; align-items: center; gap: 4px; color: var(--text-secondary); white-space: nowrap; }
.time-cell svg { width: 12px; }
.action-tag { display: inline-block; padding: 2px 8px; border-radius: 5px; background: #EFF6FF; color: #2563EB; font-size: 11px; font-weight: 600; }
.detail-cell { color: var(--text-tertiary); max-width: 360px; word-break: break-all; }
</style>
