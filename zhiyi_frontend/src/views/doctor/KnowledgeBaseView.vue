<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, MagicStick, Clock, ArrowRight } from '@element-plus/icons-vue'
import { renderMarkdown } from '@/utils/markdown'

interface QAItem { id: number; question: string; answer: string; created_at?: string }

const query = ref('')
const loading = ref(false)
const answers = ref<QAItem[]>([])
const recent = ref<QAItem[]>([])
const suggestions = ['高血压的一线用药有哪些', '小儿发热如何处理', '糖尿病饮食指导', 'COPD 急性加重治疗方案']

function loadRecent() {
  try { recent.value = JSON.parse(localStorage.getItem('zhiyi-qa-recent') || '[]') }
  catch { recent.value = [] }
}

async function ask() {
  const q = query.value.trim()
  if (!q || loading.value) return
  loading.value = true
  try {
    const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'
    const token = localStorage.getItem('zhiyi-token') || ''
    const resp = await fetch(`${apiBase}/diagnosis/qa`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ patient_id: 1, question: q }),
    })
    const data = await resp.json()
    const item: QAItem = { id: Date.now(), question: q, answer: data.answer || data.message || '无法获取回答', created_at: new Date().toISOString() }
    answers.value.unshift(item)
    recent.value.unshift(item)
    if (recent.value.length > 10) recent.value.length = 10
    localStorage.setItem('zhiyi-qa-recent', JSON.stringify(recent.value.slice(0, 10)))
    query.value = ''
  } catch (e: any) {
    ElMessage.error(e.message || '查询失败')
  } finally { loading.value = false }
}

function clearRecent() { recent.value = []; localStorage.removeItem('zhiyi-qa-recent'); ElMessage.success('已清空') }

onMounted(loadRecent)
</script>
<template>
  <div class="kb-page">
    <div class="kb-head">
      <h1>医学知识库</h1>
      <p>AI 驱动的临床决策支持，即时检索最新诊疗指南与药物信息</p>
    </div>
    <div class="kb-search">
      <el-input v-model="query" placeholder="输入临床问题，例如：高血压患者的降压目标" prefix-icon="Search" clearable @keyup.enter="ask" size="large" />
      <button class="btn-ask" :disabled="loading" @click="ask"><MagicStick /> {{ loading ? '查询中…' : '智能检索' }}</button>
    </div>
    <div class="kb-suggestions">
      <span v-for="s in suggestions" :key="s" class="sug-tag" @click="query = s; ask()">{{ s }}</span>
    </div>
    <div v-if="recent.length" class="kb-section">
      <div class="section-head">
        <h3><Clock /> 最近提问</h3>
        <button class="link-btn" @click="clearRecent">清空</button>
      </div>
      <div v-for="r in recent" :key="r.id" class="qa-item">
        <div class="qa-q"><strong>Q:</strong> {{ r.question }}</div>
        <div class="qa-a"><strong>A:</strong><div class="md-body" v-html="renderMarkdown(r.answer)"></div></div>
      </div>
    </div>
    <div v-if="answers.length" class="kb-section">
      <div class="section-head"><h3>提问结果</h3></div>
      <div v-for="a in answers" :key="a.id" class="qa-item active">
        <div class="qa-q"><strong>Q:</strong> {{ a.question }}</div>
        <div class="qa-a"><strong>A:</strong><div class="md-body" v-html="renderMarkdown(a.answer)"></div></div>
      </div>
    </div>
    <div v-if="!answers.length && !recent.length" class="empty">输入问题开始检索医学知识</div>
  </div>
</template>
<style scoped>
.kb-page { max-width: 760px; margin: 0 auto; padding: 24px; }
.kb-head h1 { font-size: 22px; font-weight: 700; margin-bottom: 4px; }
.kb-head p { margin: 0; color: var(--text-secondary); font-size: 14px; }
.kb-search { display: flex; gap: 10px; margin: 20px 0 12px; }
.btn-ask { display: flex; align-items: center; gap: 4px; padding: 0 24px; border: none; border-radius: 10px; background: var(--primary); color: #fff; font-size: 14px; font-weight: 600; cursor: pointer; white-space: nowrap; }
.btn-ask:disabled { opacity: .6; cursor: not-allowed; }
.kb-suggestions { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 24px; }
.sug-tag { font-size: 12px; padding: 4px 12px; border-radius: 20px; background: var(--primary-soft); color: var(--primary); cursor: pointer; transition: all .15s; }
.sug-tag:hover { background: var(--primary); color: #fff; }
.kb-section { margin-bottom: 20px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.section-head h3 { display: flex; align-items: center; gap: 6px; font-size: 15px; }
.link-btn { background: none; border: none; color: var(--primary); font-size: 12px; cursor: pointer; }
.qa-item { background: #fff; border-radius: 12px; padding: 14px; margin-bottom: 8px; border: 1px solid var(--border-light); }
.qa-item.active { border-color: var(--primary); background: var(--primary-soft); }
.qa-q { font-size: 13px; margin-bottom: 6px; color: var(--text-secondary); }
.qa-a { font-size: 13px; line-height: 1.6; }
.empty { text-align: center; padding: 60px; color: var(--text-tertiary); font-size: 14px; }

/* ===== Markdown 渲染样式 ===== */
.qa-a :deep(.md-body) { margin-top: 6px; }
.qa-a :deep(.md-body p) { margin: 6px 0; }
.qa-a :deep(.md-body h1),
.qa-a :deep(.md-body h2),
.qa-a :deep(.md-body h3),
.qa-a :deep(.md-body h4) { margin: 12px 0 6px; font-weight: 700; line-height: 1.4; }
.qa-a :deep(.md-body h1) { font-size: 17px; }
.qa-a :deep(.md-body h2) { font-size: 16px; }
.qa-a :deep(.md-body h3) { font-size: 15px; }
.qa-a :deep(.md-body h4) { font-size: 14px; }
.qa-a :deep(.md-body ul),
.qa-a :deep(.md-body ol) { margin: 6px 0; padding-left: 22px; }
.qa-a :deep(.md-body li) { margin: 4px 0; }
.qa-a :deep(.md-body code) { background: rgba(0, 0, 0, .07); padding: 1px 6px; border-radius: 4px; font-size: 12.5px; font-family: Consolas, Menlo, monospace; }
.qa-a :deep(.md-body pre) { background: #0f172a; color: #e2e8f0; padding: 12px 14px; border-radius: 10px; overflow-x: auto; margin: 8px 0; }
.qa-a :deep(.md-body pre code) { background: none; color: inherit; padding: 0; font-size: 12.5px; }
.qa-a :deep(.md-body blockquote) { border-left: 3px solid var(--primary); margin: 8px 0; padding: 6px 12px; background: rgba(59, 130, 246, .07); border-radius: 0 10px 10px 0; }
.qa-a :deep(.md-body blockquote p) { margin: 4px 0; }
.qa-a :deep(.md-body table) { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 12.5px; }
.qa-a :deep(.md-body th),
.qa-a :deep(.md-body td) { border: 1px solid var(--border-light); padding: 7px 10px; text-align: left; }
.qa-a :deep(.md-body th) { background: rgba(59, 130, 246, .1); font-weight: 600; }
.qa-a :deep(.md-body .md-table-wrap) { overflow-x: auto; }
.qa-a :deep(.md-body a) { color: var(--primary); }
.qa-a :deep(.md-body hr) { border: none; border-top: 1px solid var(--border-light); margin: 12px 0; }
</style>
