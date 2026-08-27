<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { User, CircleCheck, CircleClose, Refresh, Plus, Close, Delete } from '@element-plus/icons-vue'
import { createDoctor, deleteDoctor } from '@/api'

interface Doctor {
  id: number
  user_id?: number
  name: string
  phone: string
  title?: string
  department?: string
  is_active: boolean
}

const doctors = ref<Doctor[]>([])
const loading = ref(true)
const showCreate = ref(false)
const submitting = ref(false)

const form = reactive({
  name: '',
  username: '',
  phone: '',
  password: '',
  department: '',
})

async function loadDoctors() {
  loading.value = true
  try {
    const token = localStorage.getItem('zhiyi-token') || ''
    const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'
    const resp = await fetch(`${apiBase}/admin/doctors`, { headers: { Authorization: `Bearer ${token}` } })
    doctors.value = resp.ok ? await resp.json() : []
  } catch { ElMessage.error('加载失败') }
  finally { loading.value = false }
}

async function toggleDoctor(doc: Doctor) {
  try {
    const token = localStorage.getItem('zhiyi-token') || ''
    const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'
    const userId = doc.user_id || doc.id
    const resp = await fetch(`${apiBase}/admin/doctors/${userId}/toggle`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    })
    if (resp.ok) { ElMessage.success(`${doc.is_active ? '已禁用' : '已启用'} ${doc.name}`); await loadDoctors() }
    else throw new Error('操作失败')
  } catch (e: any) { ElMessage.error(e.message || '操作失败') }
}

async function removeDoctor(doc: Doctor) {
  try {
    await ElMessageBox.confirm(`确认删除医生「${doc.name}」？删除后账号将被禁用。`, '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await deleteDoctor(doc.user_id || doc.id)
    ElMessage.success(`医生「${doc.name}」已删除`)
    await loadDoctors()
  } catch (e: any) {
    ElMessage.error(e.message || '删除失败')
  }
}

function openCreate() {
  form.name = ''
  form.username = ''
  form.phone = ''
  form.password = ''
  form.department = ''
  showCreate.value = true
}

function closeCreate() {
  if (submitting.value) return
  showCreate.value = false
}

async function submitCreate() {
  if (!form.name.trim()) return ElMessage.warning('请输入医生姓名')
  if (!form.username.trim()) return ElMessage.warning('请输入用户名')
  if (!/^1\d{10}$/.test(form.phone)) return ElMessage.warning('请输入 11 位有效手机号')
  if (form.password.length < 8) return ElMessage.warning('密码至少 8 位')
  submitting.value = true
  try {
    await createDoctor({
      username: form.username.trim(),
      phone: form.phone.trim(),
      password: form.password,
      name: form.name.trim(),
      department: form.department.trim(),
      hospital_id: 1,
    })
    ElMessage.success(`医生账号「${form.name.trim()}」创建成功`)
    showCreate.value = false
    await loadDoctors()
  } catch (e: any) {
    ElMessage.error(e.message || '创建失败')
  } finally {
    submitting.value = false
  }
}

onMounted(loadDoctors)
</script>
<template>
  <div class="adm-page">
    <div class="adm-head">
      <div>
        <h1>医生管理</h1>
        <p>管理平台注册医生账号，控制权限与状态</p>
      </div>
      <div class="head-actions">
        <button class="create-btn" @click="openCreate"><Plus /> 新增医生</button>
        <button class="refresh-btn" @click="loadDoctors"><Refresh /> 刷新</button>
      </div>
    </div>
    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="!doctors.length" class="empty">暂无医生数据，点击右上角「新增医生」创建</div>
    <div v-else class="doc-list">
      <div v-for="d in doctors" :key="d.id" class="doc-row">
        <div class="doc-avatar">{{ d.name?.charAt(0) || 'D' }}</div>
        <div class="doc-info">
          <strong>{{ d.name }}</strong>
          <small>{{ d.phone || '—' }} · {{ d.department || d.title || '普通医生' }}</small>
        </div>
        <div class="doc-status">
          <span v-if="d.is_active" class="status active"><CircleCheck /> 已激活</span>
          <span v-else class="status inactive"><CircleClose /> 已禁用</span>
        </div>
        <div class="doc-actions">
          <button class="btn-toggle" :class="{ danger: d.is_active }" @click="toggleDoctor(d)">
            {{ d.is_active ? '禁用' : '启用' }}
          </button>
          <button class="btn-delete" @click="removeDoctor(d)"><Delete /> 删除</button>
        </div>
      </div>
    </div>

    <!-- 新增医生弹窗 -->
    <div v-if="showCreate" class="modal-mask" @click.self="closeCreate">
      <div class="modal">
        <div class="modal-head">
          <h3>新增医生</h3>
          <button class="modal-close" @click="closeCreate"><Close /></button>
        </div>
        <div class="modal-body">
          <label class="field">
            <span>姓名 <em>*</em></span>
            <input v-model="form.name" type="text" placeholder="如：张伟" maxlength="20" />
          </label>
          <label class="field">
            <span>用户名 <em>*</em></span>
            <input v-model="form.username" type="text" placeholder="登录用户名，如 doctor_zhang" maxlength="30" />
          </label>
          <label class="field">
            <span>手机号 <em>*</em></span>
            <input v-model="form.phone" type="tel" placeholder="11 位手机号" maxlength="11" />
          </label>
          <label class="field">
            <span>密码 <em>*</em></span>
            <input v-model="form.password" type="password" placeholder="至少 8 位" maxlength="20" />
          </label>
          <label class="field">
            <span>科室</span>
            <input v-model="form.department" type="text" placeholder="如：心血管内科" maxlength="30" />
          </label>
        </div>
        <div class="modal-foot">
          <button class="btn-cancel" @click="closeCreate">取消</button>
          <button class="btn-submit" :disabled="submitting" @click="submitCreate">
            {{ submitting ? '创建中…' : '创建账号' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
<style scoped>
.adm-page { max-width: 760px; margin: 0 auto; padding: 24px; }
.adm-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.adm-head h1 { font-size: 22px; font-weight: 700; margin-bottom: 4px; }
.adm-head p { margin: 0; color: var(--text-secondary); font-size: 14px; }
.head-actions { display: flex; gap: 8px; }
.create-btn, .refresh-btn { display: flex; align-items: center; gap: 4px; padding: 7px 14px; border-radius: 8px; cursor: pointer; font-size: 12px; }
.create-btn { background: var(--primary, #2563EB); color: #fff; border: none; }
.create-btn:hover { opacity: .9; }
.refresh-btn { border: 1px solid var(--border-light); background: #fff; }
.doc-list { display: flex; flex-direction: column; gap: 8px; }
.doc-row { display: flex; align-items: center; gap: 14px; background: #fff; border-radius: 12px; padding: 16px 18px; border: 1px solid var(--border-light); }
.doc-avatar { width: 42px; height: 42px; border-radius: 50%; background: var(--primary); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: 700; }
.doc-info { flex: 1; }
.doc-info strong { display: block; font-size: 14px; }
.doc-info small { font-size: 12px; color: var(--text-tertiary); }
.doc-status { font-size: 12px; }
.status { display: flex; align-items: center; gap: 4px; }
.status.active { color: #16A34A; }
.status.inactive { color: #999; }
.btn-toggle { padding: 6px 16px; border-radius: 7px; border: 1px solid var(--border-light); background: #fff; font-size: 12px; cursor: pointer; font-weight: 600; }
.btn-toggle.danger { color: #DC2626; border-color: #FECACA; }
.btn-toggle:hover { background: var(--gray-50); }
.doc-actions { display: flex; align-items: center; gap: 8px; }
.btn-delete { display: inline-flex; align-items: center; gap: 4px; padding: 6px 14px; border-radius: 7px; border: 1px solid #FECACA; background: #fff; color: #DC2626; font-size: 12px; font-weight: 600; cursor: pointer; }
.btn-delete:hover { background: #FEF2F2; }
.btn-delete svg { width: 12px; }
.empty { text-align: center; padding: 60px; color: var(--text-tertiary); font-size: 14px; }

.modal-mask { position: fixed; inset: 0; background: rgba(15, 23, 42, .45); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal { width: 420px; max-width: 94vw; background: #fff; border-radius: 14px; overflow: hidden; box-shadow: 0 20px 60px rgba(0,0,0,.2); }
.modal-head { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border-light); }
.modal-head h3 { font-size: 16px; margin: 0; }
.modal-close { border: none; background: none; cursor: pointer; color: var(--text-tertiary); display: flex; }
.modal-body { padding: 18px 20px; display: flex; flex-direction: column; gap: 14px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field span { font-size: 13px; color: var(--text-secondary); }
.field em { color: #DC2626; font-style: normal; }
.field input { height: 38px; padding: 0 12px; border: 1px solid var(--border-light); border-radius: 8px; font-size: 13px; outline: none; }
.field input:focus { border-color: var(--primary, #2563EB); }
.modal-foot { display: flex; justify-content: flex-end; gap: 10px; padding: 14px 20px; border-top: 1px solid var(--border-light); }
.btn-cancel { padding: 8px 18px; border: 1px solid var(--border-light); background: #fff; border-radius: 8px; font-size: 13px; cursor: pointer; }
.btn-submit { padding: 8px 18px; border: none; background: var(--primary, #2563EB); color: #fff; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; }
.btn-submit:disabled { opacity: .6; cursor: not-allowed; }
</style>
