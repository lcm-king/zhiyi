<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Box, Delete, Edit, Plus, Refresh } from '@element-plus/icons-vue'
import {
  createDrug,
  createExamItem,
  deleteDrug,
  deleteExamItem,
  getAdminDrugs,
  getAdminExamItems,
  updateDrug,
  updateExamItem,
} from '@/api'
import type { AdminDrugItem, AdminExamItem } from '@/types'

const activeTab = ref<'drug' | 'exam'>('drug')
const drugs = ref<AdminDrugItem[]>([])
const exams = ref<AdminExamItem[]>([])
const loading = ref(false)
const dialogOpen = ref(false)
const submitting = ref(false)
const editingId = ref<number | null>(null)

const form = reactive({
  name: '',
  specification: '',
  manufacturer: '',
  price: 0,
  stock: 0,
  need_prescription: true,
  category: '',
  description: '',
})

function parseError(e: any): string {
  let msg = e?.message || '操作失败'
  try {
    const parsed = JSON.parse(msg)
    msg = parsed.detail || msg
  } catch { /* 非 JSON 错误直接展示 */ }
  return msg
}

function isDrug(item: AdminDrugItem | AdminExamItem): item is AdminDrugItem {
  return 'specification' in item
}

async function load() {
  loading.value = true
  try {
    const [d, e] = await Promise.all([getAdminDrugs(), getAdminExamItems()])
    drugs.value = d || []
    exams.value = e || []
  } catch (err) {
    ElMessage.error(parseError(err))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.name = ''
  form.specification = ''
  form.manufacturer = ''
  form.price = 0
  form.stock = 0
  form.need_prescription = true
  form.category = ''
  form.description = ''
  dialogOpen.value = true
}

function openEdit(item: AdminDrugItem | AdminExamItem) {
  editingId.value = item.id
  form.name = item.name
  form.price = item.price
  if (isDrug(item)) {
    form.specification = item.specification || ''
    form.manufacturer = item.manufacturer || ''
    form.stock = item.stock
    form.need_prescription = item.need_prescription
    form.category = ''
    form.description = ''
  } else {
    form.specification = ''
    form.manufacturer = ''
    form.stock = 0
    form.need_prescription = false
    form.category = item.category || ''
    form.description = item.description || ''
  }
  dialogOpen.value = true
}

async function submit() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写名称')
    return
  }
  if (!form.price || form.price <= 0) {
    ElMessage.warning('请填写正确的价格')
    return
  }
  if (activeTab.value === 'drug' && form.stock < 0) {
    ElMessage.warning('库存不能为负数')
    return
  }

  submitting.value = true
  try {
    if (activeTab.value === 'drug') {
      const payload = {
        name: form.name.trim(),
        specification: form.specification.trim(),
        manufacturer: form.manufacturer.trim(),
        price: Number(form.price),
        stock: Number(form.stock),
        need_prescription: form.need_prescription,
      }
      if (editingId.value == null) {
        await createDrug(payload)
      } else {
        await updateDrug(editingId.value, payload)
      }
    } else {
      const payload = {
        name: form.name.trim(),
        category: form.category.trim(),
        price: Number(form.price),
        description: form.description.trim(),
      }
      if (editingId.value == null) {
        await createExamItem(payload)
      } else {
        await updateExamItem(editingId.value, payload)
      }
    }
    ElMessage.success(editingId.value == null ? '新增成功' : '已保存修改')
    dialogOpen.value = false
    await load()
  } catch (err) {
    ElMessage.error(parseError(err))
  } finally {
    submitting.value = false
  }
}

async function toggleItem(item: AdminDrugItem | AdminExamItem) {
  try {
    const payload = { is_active: !item.is_active }
    if (isDrug(item)) {
      await updateDrug(item.id, payload)
    } else {
      await updateExamItem(item.id, payload)
    }
    ElMessage.success(item.is_active ? '已下架' : '已上架')
    await load()
  } catch (err) {
    ElMessage.error(parseError(err))
  }
}

async function removeItem(item: AdminDrugItem | AdminExamItem) {
  try {
    await ElMessageBox.confirm(`确认删除「${item.name}」？删除后将从目录中下架。`, '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    if (isDrug(item)) {
      await deleteDrug(item.id)
    } else {
      await deleteExamItem(item.id)
    }
    ElMessage.success('已删除')
    await load()
  } catch (err: any) {
    if (err === 'cancel' || err?.message === 'cancel') return
    ElMessage.error(parseError(err))
  }
}

onMounted(load)
</script>

<template>
  <div class="cat-page">
    <div class="cat-head">
      <div>
        <h1>药品与检查目录</h1>
        <p>管理平台可售药品和可预约检查项目</p>
      </div>
      <div class="head-actions">
        <button class="create-btn" @click="openCreate"><Plus /> 新增{{ activeTab === 'drug' ? '药品' : '检查项目' }}</button>
        <button class="refresh-btn" @click="load"><Refresh /> 刷新</button>
      </div>
    </div>

    <div class="tabs">
      <button :class="{ active: activeTab === 'drug' }" @click="activeTab = 'drug'">药品 ({{ drugs.length }})</button>
      <button :class="{ active: activeTab === 'exam' }" @click="activeTab = 'exam'">检查项目 ({{ exams.length }})</button>
    </div>

    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="activeTab === 'drug' && !drugs.length" class="empty">暂无药品数据，点击右上角新增</div>
    <div v-else-if="activeTab === 'exam' && !exams.length" class="empty">暂无检查项目数据，点击右上角新增</div>
    <div v-else class="item-list">
      <template v-if="activeTab === 'drug'">
        <div v-for="item in drugs" :key="item.id" class="item-row">
          <span class="row-icon tone-drug"><Box /></span>
          <div class="item-info">
            <strong>{{ item.name }}</strong>
            <small>{{ (item.specification || '—') + ' · ' + (item.manufacturer || '—') }} · 库存 {{ item.stock }}</small>
          </div>
          <div class="item-meta">
            <span class="rx-tag" :class="{ rx: item.need_prescription }">{{ item.need_prescription ? '处方药' : 'OTC' }}</span>
            <strong class="item-price">¥{{ item.price?.toFixed(2) }}</strong>
            <span class="status-tag" :class="{ on: item.is_active, off: !item.is_active }">{{ item.is_active ? '上架中' : '已下架' }}</span>
          </div>
          <div class="row-actions">
            <button class="btn-edit" title="编辑" @click="openEdit(item)"><Edit /></button>
            <button class="btn-delete" title="删除" @click="removeItem(item)"><Delete /></button>
            <button class="btn-toggle" :class="{ danger: item.is_active }" @click="toggleItem(item)">{{ item.is_active ? '下架' : '上架' }}</button>
          </div>
        </div>
      </template>
      <template v-else>
        <div v-for="item in exams" :key="item.id" class="item-row">
          <span class="row-icon tone-exam"><Box /></span>
          <div class="item-info">
            <strong>{{ item.name }}</strong>
            <small>{{ item.category || '—' }}</small>
          </div>
          <div class="item-meta">
            <strong class="item-price">¥{{ item.price?.toFixed(2) }}</strong>
            <span class="status-tag" :class="{ on: item.is_active, off: !item.is_active }">{{ item.is_active ? '上架中' : '已下架' }}</span>
          </div>
          <div class="row-actions">
            <button class="btn-edit" title="编辑" @click="openEdit(item)"><Edit /></button>
            <button class="btn-delete" title="删除" @click="removeItem(item)"><Delete /></button>
            <button class="btn-toggle" :class="{ danger: item.is_active }" @click="toggleItem(item)">{{ item.is_active ? '下架' : '上架' }}</button>
          </div>
        </div>
      </template>
    </div>

    <el-dialog
      v-model="dialogOpen"
      :title="`${editingId == null ? '新增' : '编辑'}${activeTab === 'drug' ? '药品' : '检查项目'}`"
      width="520px"
      destroy-on-close
    >
      <div class="dialog-form">
        <label class="field">
          <span>名称 <em>*</em></span>
          <input v-model="form.name" type="text" placeholder="请输入名称" maxlength="100" />
        </label>

        <template v-if="activeTab === 'drug'">
          <div class="field-row">
            <label class="field">
              <span>规格</span>
              <input v-model="form.specification" type="text" placeholder="如 20mg × 30 片" maxlength="100" />
            </label>
            <label class="field">
              <span>生产厂家</span>
              <input v-model="form.manufacturer" type="text" placeholder="厂家名称" maxlength="100" />
            </label>
          </div>
          <div class="field-row">
            <label class="field">
              <span>价格（元） <em>*</em></span>
              <input v-model.number="form.price" type="number" min="0" step="0.01" />
            </label>
            <label class="field">
              <span>库存 <em>*</em></span>
              <input v-model.number="form.stock" type="number" min="0" step="1" />
            </label>
          </div>
          <div class="field switch-field">
            <span>是否处方药</span>
            <el-switch v-model="form.need_prescription" active-text="处方药" inactive-text="OTC" />
          </div>
        </template>

        <template v-else>
          <label class="field">
            <span>分类</span>
            <input v-model="form.category" type="text" placeholder="如 影像科 / 超声科 / 检验科" maxlength="50" />
          </label>
          <label class="field">
            <span>价格（元） <em>*</em></span>
            <input v-model.number="form.price" type="number" min="0" step="0.01" />
          </label>
          <label class="field">
            <span>说明</span>
            <textarea v-model="form.description" rows="2" placeholder="项目说明" maxlength="500" />
          </label>
        </template>
      </div>
      <template #footer>
        <button class="btn-cancel" @click="dialogOpen = false">取消</button>
        <button class="btn-submit" :disabled="submitting" @click="submit">
          {{ submitting ? '保存中…' : '保存' }}
        </button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.cat-page { max-width: 860px; margin: 0 auto; padding: 24px; }
.cat-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
.cat-head h1 { font-size: 22px; font-weight: 700; margin-bottom: 4px; }
.cat-head p { margin: 0; color: var(--text-secondary); font-size: 14px; }
.head-actions { display: flex; gap: 8px; }
.create-btn, .refresh-btn { display: flex; align-items: center; gap: 4px; padding: 7px 14px; border-radius: 8px; cursor: pointer; font-size: 12px; }
.create-btn { background: var(--primary, #2563EB); color: #fff; border: none; }
.create-btn:hover { opacity: .9; }
.refresh-btn { border: 1px solid var(--border-light); background: #fff; }

.tabs { display: flex; gap: 8px; margin-bottom: 16px; }
.tabs button { padding: 7px 18px; border-radius: 8px; border: 1px solid var(--border-light); background: #fff; font-size: 13px; cursor: pointer; }
.tabs button.active { background: var(--primary); color: #fff; border-color: var(--primary); }

.item-list { display: flex; flex-direction: column; gap: 8px; }
.item-row { display: flex; align-items: center; gap: 12px; background: #fff; border-radius: 12px; padding: 14px 16px; border: 1px solid var(--border-light); }
.row-icon { width: 34px; height: 34px; display: grid; place-items: center; border-radius: 10px; flex: 0 0 auto; }
.row-icon svg { width: 17px; height: 17px; }
.row-icon.tone-drug { background: #EFF6FF; color: #2563EB; }
.row-icon.tone-exam { background: #F0FDFA; color: #0D9488; }
.item-info { flex: 1; min-width: 0; }
.item-info strong { display: block; font-size: 14px; }
.item-info small { font-size: 12px; color: var(--text-tertiary); }
.item-meta { display: flex; align-items: center; gap: 8px; }
.item-price { font-size: 16px; font-weight: 800; }
.rx-tag { font-size: 11px; padding: 2px 8px; border-radius: 5px; background: #DCFCE7; color: #16A34A; }
.rx-tag.rx { background: #FEF3C7; color: #B45309; }
.status-tag { font-size: 11px; padding: 2px 8px; border-radius: 5px; }
.status-tag.on { background: #DCFCE7; color: #16A34A; }
.status-tag.off { background: #FEE2E2; color: #DC2626; }
.row-actions { display: flex; align-items: center; gap: 6px; }
.btn-edit, .btn-delete { display: grid; place-items: center; width: 30px; height: 30px; border-radius: 7px; border: 1px solid var(--border-light); background: #fff; cursor: pointer; }
.btn-edit svg { width: 14px; color: var(--primary); }
.btn-delete svg { width: 14px; color: #DC2626; }
.btn-toggle { padding: 6px 14px; border-radius: 7px; border: 1px solid var(--border-light); background: #fff; font-size: 12px; cursor: pointer; font-weight: 600; }
.btn-toggle.danger { color: #DC2626; border-color: #FECACA; }
.empty { text-align: center; padding: 60px; color: var(--text-tertiary); font-size: 14px; }

.dialog-form { display: flex; flex-direction: column; gap: 14px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field span { font-size: 13px; color: var(--text-secondary); }
.field em { color: #DC2626; font-style: normal; }
.field input, .field textarea { padding: 8px 12px; border: 1px solid var(--border-light); border-radius: 8px; font-size: 13px; outline: none; font-family: inherit; box-sizing: border-box; width: 100%; }
.field input:focus, .field textarea:focus { border-color: var(--primary, #2563EB); }
.field textarea { resize: vertical; }
.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.switch-field { flex-direction: row; align-items: center; justify-content: space-between; }
.btn-cancel { padding: 8px 18px; border: 1px solid var(--border-light); background: #fff; border-radius: 8px; font-size: 13px; cursor: pointer; }
.btn-submit { padding: 8px 18px; border: none; background: var(--primary, #2563EB); color: #fff; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; }
.btn-submit:disabled { opacity: .6; cursor: not-allowed; }

@media (max-width: 640px) {
  .item-row { flex-wrap: wrap; }
  .row-actions { width: 100%; justify-content: flex-end; }
  .field-row { grid-template-columns: 1fr; }
}
</style>
