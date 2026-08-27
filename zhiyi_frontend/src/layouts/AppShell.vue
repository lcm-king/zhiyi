<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Bell, CaretBottom, ChatDotRound, Menu, Moon, Search, Setting, Sunny, SwitchButton, MagicStick, FirstAidKit, User, DataAnalysis, ShoppingBag, Document, Collection, Van } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { roleHome } from '@/router'
import { getAlerts, getDrugOrders, getPatients } from '@/api'
import type { NavItem, UserRole } from '@/types'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const mobileOpen = ref(false)
const searchTerm = ref('')
const noticeOpen = ref(false)
const settingsOpen = ref(false)
const saving = ref(false)
const settingsForm = ref({ name: '', phone: '', password: '', department: '', specialty: '' })
const theme = ref<'light' | 'dark'>(localStorage.getItem('zhiyi-theme') === 'dark' ? 'dark' : 'light')

function applyTheme() {
  document.documentElement.classList.toggle('dark', theme.value === 'dark')
  localStorage.setItem('zhiyi-theme', theme.value)
}

function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  applyTheme()
}

function openSettings() {
  const u = auth.user || ({} as any)
  settingsForm.value = {
    name: u.name || '',
    phone: u.phone || '',
    password: '',
    department: u.department || '',
    specialty: u.specialty || '',
  }
  settingsOpen.value = true
}

async function saveProfile() {
  const phone = settingsForm.value.phone?.trim() || ''
  const password = settingsForm.value.password || ''
  if (phone && !/^1[3-9]\d{9}$/.test(phone)) {
    ElMessage.warning('请输入正确的 11 位手机号')
    return
  }
  if (password && password.length < 6) {
    ElMessage.warning('新密码至少需要 6 位')
    return
  }
  saving.value = true
  try {
    const token = localStorage.getItem('zhiyi-token') || ''
    const resp = await fetch(
      `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'}/auth/profile`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(Object.fromEntries(
          Object.entries(settingsForm.value).filter(([, v]) => v)
        )),
      }
    )
    if (!resp.ok) {
      let detail: any = null
      try { detail = (await resp.json())?.detail } catch { /* 空响应体 */ }
      let msg = ''
      if (Array.isArray(detail)) msg = detail.map((d: any) => d.msg).filter(Boolean).join('；')
      else if (typeof detail === 'string' && detail) msg = detail
      else msg = resp.status >= 500 ? '服务器暂时不可用，请稍后重试' : `保存失败（HTTP ${resp.status}）`
      throw new Error(msg)
    }
    const data = await resp.json()
    // 更新本地 store
    auth.$patch({ user: { ...auth.user, name: data.name, phone: data.phone, department: data.department, specialty: data.specialty } as any })
    ElMessage.success('个人设置已保存')
    settingsOpen.value = false
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

function saveAndClose() { settingsOpen.value = false }

const roleLabel: Record<UserRole, string> = { doctor: '医生工作台', patient: '患者服务中心', admin: '管理后台' }
const navByRole: Record<UserRole, NavItem[]> = {
  doctor: [
    { label: '智能诊疗', icon: FirstAidKit, to: '/doctor/diagnosis' },
    { label: '待确认问诊', icon: ChatDotRound, to: '/doctor/pre-consults' },
    { label: '患者档案', icon: User, to: '/doctor/records' },
    { label: '处方审核', icon: Document, to: '/doctor/prescriptions' },
    { label: '检查报告', icon: DataAnalysis, to: '/doctor/reports' },
    { label: '医学知识库', icon: Collection, to: '/doctor/knowledge' },
  ],
  patient: [
    { label: '健康档案', icon: User, to: '/patient/health' },
    { label: '检查与购药', icon: ShoppingBag, to: '/patient/exams' },
    { label: '订单与物流', icon: Van, to: '/patient/orders' },
    { label: '检查报告', icon: Document, to: '/patient/reports' },
    { label: '智能助手', icon: MagicStick, to: '/patient/assistant' },
  ],
  admin: [
    { label: '运营总览', icon: DataAnalysis, to: '/admin/overview' },
    { label: '医生管理', icon: User, to: '/admin/doctors' },
    { label: '药品与检查', icon: ShoppingBag, to: '/admin/catalog' },
    { label: '订单发货', icon: Van, to: '/admin/orders' },
    { label: '操作日志', icon: Document, to: '/admin/audit-logs' },
  ],
}
const navItems = computed(() => navByRole[auth.role])
const currentTitle = computed(() => (route.meta.title as string) || '工作台')
const notices = ref<string[]>([])

// 通知已读状态：存 localStorage，刷新后不重复提醒
const NOTICE_READ_KEY = 'zhiyi-notice-read'
const readNotices = ref<Set<string>>(new Set(loadReadNotices()))

function loadReadNotices(): string[] {
  try {
    return JSON.parse(localStorage.getItem(NOTICE_READ_KEY) || '[]')
  } catch {
    return []
  }
}

function persistReadNotices() {
  localStorage.setItem(NOTICE_READ_KEY, JSON.stringify([...readNotices.value]))
}

const unreadCount = computed(() => notices.value.filter((n) => !readNotices.value.has(n)).length)

function markNoticeRead(notice: string) {
  readNotices.value.add(notice)
  persistReadNotices()
}

function markAllNoticesRead() {
  notices.value.forEach((n) => readNotices.value.add(n))
  persistReadNotices()
}

onMounted(async () => {
  applyTheme()
  await loadNotices()
})

async function loadNotices() {
  try {
    if (auth.role === 'admin') {
      const alertList = await getAlerts()
      notices.value = alertList.slice(0, 3).map((a: any) => a.content)
      if (notices.value.length === 0) notices.value = ['当前无告警，系统运行正常']
    } else if (auth.role === 'patient') {
      const orders = await getDrugOrders()
      const active = orders.filter((o: any) => o.delivery_status === 'pending' || o.delivery_status === 'shipped')
      notices.value = active.length > 0
        ? active.slice(0, 3).map((o: any) => `订单 ${o.order_no} ${o.delivery_status === 'shipped' ? '配送中' : '待发货'}`)
        : ['暂无进行中的订单']
    } else {
      const patients = await getPatients()
      notices.value = [`当前管理 ${patients.length} 位患者`]
    }
  } catch {
    notices.value = ['通知加载失败，请稍后重试']
  }
}

async function switchRole(nextRole: UserRole) {
  await auth.signIn(nextRole)
  mobileOpen.value = false
  await router.push(roleHome[nextRole])
  ElMessage.success(`已切换至${roleLabel[nextRole]}`)
}
function logout() { auth.signOut(); router.push('/login') }
function submitSearch() {
  const term = searchTerm.value.trim()
  if (!term) return
  const searchTarget: Record<UserRole, string> = {
    doctor: '/doctor/records',
    patient: '/patient/orders',
    admin: '/admin/orders',
  }
  router.push({ path: searchTarget[auth.role], query: { q: term } })
  searchTerm.value = ''
}

</script>

<template>
  <div class="app-shell">
    <div v-if="mobileOpen" class="mobile-backdrop" @click="mobileOpen = false" />
    <aside class="side-rail" :class="{ 'is-open': mobileOpen }">
      <div class="brand-lockup"><div class="brand-mark">智</div><div><div class="brand-name">智医</div><div class="brand-caption">基层医疗服务平台</div></div></div>
      <div class="rail-status"><span class="pulse-dot" /> 系统运行正常 <span class="status-time">在线</span></div>
      <div class="rail-section-label">{{ roleLabel[auth.role] }}</div>
      <nav class="rail-nav"><RouterLink v-for="item in navItems" :key="item.to" :to="item.to" class="rail-link" :class="{ active: route.path === item.to }" @click="mobileOpen = false"><component :is="item.icon" /><span>{{ item.label }}</span><span v-if="route.path === item.to" class="active-bar" /></RouterLink></nav>
      <div class="rail-bottom"><div class="rail-section-label">快捷操作</div><button class="rail-quick" @click="router.push(auth.role === 'doctor' ? '/doctor/diagnosis' : auth.role === 'patient' ? '/patient/assistant' : '/admin/orders')"><MagicStick /><span>{{ auth.role === 'doctor' ? '开始新的诊疗' : auth.role === 'patient' ? '智能助手' : '订单发货' }}</span></button><div class="identity-card"><div class="avatar avatar-small">{{ auth.user?.avatar || '智' }}</div><div class="identity-copy"><strong>{{ auth.user?.name || '演示用户' }}</strong><span>{{ roleLabel[auth.role] }}</span></div><el-dropdown trigger="click" @command="switchRole"><button class="icon-button subtle"><CaretBottom /></button><template #dropdown><el-dropdown-menu><el-dropdown-item v-for="(_, key) in roleLabel" :key="key" :command="key">{{ roleLabel[key as UserRole] }}</el-dropdown-item></el-dropdown-menu></template></el-dropdown></div></div>
    </aside>
    <section class="main-stage">
      <header class="topbar"><div class="topbar-left"><button class="icon-button mobile-menu" @click="mobileOpen = true"><Menu /></button><div class="breadcrumb"><span>智医平台</span><b>/</b><strong>{{ currentTitle }}</strong></div></div><div class="topbar-actions"><label class="global-search"><Search /><input v-model="searchTerm" placeholder="搜索患者、药品或订单" @keyup.enter="submitSearch" /></label><button class="icon-button theme-toggle" :title="theme === 'dark' ? '切换日间模式' : '切换夜间模式'" @click="toggleTheme"><component :is="theme === 'dark' ? Sunny : Moon" /></button><button class="icon-button notification" title="通知" @click="noticeOpen = !noticeOpen"><Bell /><i v-if="unreadCount" class="notice-count">{{ unreadCount > 99 ? '99+' : unreadCount }}</i></button><button class="icon-button" title="设置" @click="openSettings"><Setting /></button><button class="profile-pill" @click="logout"><span class="avatar avatar-tiny">{{ auth.user?.avatar || '智' }}</span><span class="profile-name">{{ auth.user?.name || '演示用户' }}</span><SwitchButton /></button></div><div v-if="noticeOpen" class="notice-popover"><div class="notice-heading"><strong>消息提醒</strong><button class="notice-read-all" @click="markAllNoticesRead">全部已读</button></div><button v-for="notice in notices" :key="notice" class="notice-item" @click="markNoticeRead(notice); noticeOpen = false"><span class="notice-dot" :class="{ read: readNotices.has(notice) }" />{{ notice }}<small>{{ readNotices.has(notice) ? '已读' : '未读' }}</small></button></div></header>
      <main class="page-content"><RouterView v-slot="{ Component }"><Transition name="page-fade" mode="out-in"><component :is="Component" :key="route.fullPath" /></Transition></RouterView></main>
    </section>

    <!-- 设置面板 -->
    <Teleport to="body">
      <div v-if="settingsOpen" class="settings-backdrop" @click.self="saveAndClose">
        <div class="settings-panel">
          <div class="settings-panel-header">
            <h3>个人设置</h3>
            <button class="icon-button" @click="saveAndClose">&times;</button>
          </div>

          <div class="settings-section">
            <h4>账号信息</h4>
            <div class="settings-field">
              <label>角色</label>
              <span class="settings-readonly">{{ roleLabel[auth.role] }}</span>
            </div>
            <div class="settings-field">
              <label>用户名</label>
              <span class="settings-readonly">{{ auth.user?.name || '—' }}</span>
            </div>
            <div class="settings-field">
              <label>姓名</label>
              <input v-model="settingsForm.name" placeholder="请输入姓名" />
            </div>
            <div class="settings-field">
              <label>手机号</label>
              <input v-model="settingsForm.phone" placeholder="请输入手机号" />
            </div>
          </div>

          <div class="settings-section" v-if="auth.role === 'doctor'">
            <h4>执业信息</h4>
            <div class="settings-field">
              <label>科室</label>
              <input v-model="settingsForm.department" placeholder="请输入科室" />
            </div>
            <div class="settings-field">
              <label>专长</label>
              <input v-model="settingsForm.specialty" placeholder="请输入专长领域" />
            </div>
          </div>

          <div class="settings-section">
            <h4>修改密码</h4>
            <div class="settings-field">
              <label>新密码</label>
              <input v-model="settingsForm.password" type="password" placeholder="留空则不修改" />
            </div>
          </div>

          <div class="settings-actions">
            <button class="primary-button" :disabled="saving" @click="saveProfile">
              {{ saving ? '保存中…' : '保存修改' }}
            </button>
            <button class="ghost-button" @click="settingsOpen = false">取消</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
/* ── 设置面板 ── */
.settings-backdrop {
  position: fixed; inset: 0; z-index: 10000; background: rgba(0,0,0,.35);
  display: flex; align-items: center; justify-content: center;
}
.settings-panel {
  background: #fff; border-radius: 14px; width: 440px; max-width: 94vw;
  max-height: 85vh; overflow-y: auto; padding: 28px 28px 20px;
  box-shadow: 0 20px 60px rgba(0,0,0,.2);
  animation: settings-in .25s ease-out;
}
@keyframes settings-in { from { opacity: 0; transform: scale(.95) } to { opacity: 1; transform: scale(1) } }

.settings-panel-header {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px;
}
.settings-panel-header h3 { margin: 0; font-size: 18px; font-weight: 700; }
.settings-panel-header .icon-button {
  background: none; border: none; font-size: 22px; color: var(--text-tertiary); cursor: pointer;
}

.settings-section { margin-bottom: 20px; }
.settings-section h4 { margin: 0 0 12px; font-size: 11px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: .06em; }

.settings-field { margin-bottom: 10px; }
.settings-field label { display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 4px; }
.settings-field input {
  width: 100%; padding: 8px 12px; border: 1px solid var(--border-light); border-radius: 8px;
  font-size: 14px; outline: none; transition: border-color .15s; box-sizing: border-box;
}
.settings-field input:focus { border-color: var(--primary); }
.settings-readonly { font-size: 14px; color: var(--text-primary); padding: 8px 0; }

.settings-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 8px; padding-top: 16px; border-top: 1px solid var(--border-light); }
.settings-actions button { min-width: 90px; }
</style>
