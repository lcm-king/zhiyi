<template>
  <div class="assistant-page">
    <!-- 头部 -->
    <div class="assistant-hero">
      <div>
        <h2>智能健康助手</h2>
        <p>AI 预问诊提供健康参考与就医建议，不生成正式诊断；健康咨询基于你的健康档案 + 83 种疾病知识库（RAG）</p>
      </div>
      <span class="ai-badge" :class="{ local: !aiMode }">
        <i class="dot" />
        {{ aiMode ? 'Qwen3.7-max 已接入' : '本地规则模式' }}
      </span>
    </div>

    <!-- 模式切换 -->
    <div class="mode-tabs">
      <button :class="{ active: mode === 'consult' }" @click="switchMode('consult')">
        🩺 AI 预问诊
      </button>
      <button :class="{ active: mode === 'chat' }" @click="switchMode('chat')">
        💬 健康咨询
      </button>
    </div>

    <!-- ============ AI 预问诊 ============ -->
    <div v-if="mode === 'consult'" class="consult-scroll">
      <div class="consult-card">
        <h3>描述你的症状</h3>
        <p>AI 将结合你的健康档案（过敏史、既往史等）给出可能性分析与就医建议。<b>结果仅供健康参考，不构成正式诊断</b>，正式就诊记录需由医生确认后生成。</p>
        <textarea
          v-model="consultInput"
          rows="4"
          maxlength="2000"
          placeholder="例如：最近三天反复头痛，伴有发热 38 度，咳嗽咳痰，乏力……"
        />
        <div class="consult-actions">
          <span class="counter">{{ consultInput.length }}/2000</span>
          <button class="consult-btn" :disabled="consulting || consultInput.trim().length < 5" @click="submitConsult">
            {{ consulting ? 'AI 预问诊中…' : '开始预问诊' }}
          </button>
        </div>
      </div>

      <div v-if="consulting" class="consult-loading">
        <span class="spinner" />
        AI 正在分析你的症状并生成预问诊建议，约 5-20 秒…
      </div>

      <div v-if="consultResult" class="consult-result">
        <div class="result-banner">
          <div>
            <b>✅ AI 预问诊完成</b>
            <span>本结果为健康参考，不构成诊断；如需正式就诊与处方，请由医生确认</span>
          </div>
          <button class="go-health" @click="goHealth">查看健康档案</button>
        </div>

        <div v-if="consultResult.suggested_department || consultResult.urgency" class="result-section">
          <div class="section-title">就医建议</div>
          <div class="triage-row">
            <span v-if="consultResult.suggested_department" class="triage-chip">建议科室：{{ consultResult.suggested_department }}</span>
            <span v-if="consultResult.urgency" class="triage-chip" :class="`urgency-${consultResult.urgency}`">紧急程度：{{ urgencyLabel(consultResult.urgency) }}</span>
          </div>
        </div>

        <div class="result-section">
          <div class="section-title">AI 初步评估</div>
          <div class="final-diagnosis">{{ consultResult.medical_record?.preliminary_diagnosis || '待医生确认' }}</div>
          <div v-if="consultResult.extracted_symptoms?.length" class="symptom-tags">
            <span v-for="s in consultResult.extracted_symptoms" :key="s" class="symptom-tag">{{ s }}</span>
          </div>
        </div>

        <div class="result-section">
          <div class="section-title">AI 评估建议（按可能性排序）</div>
          <div v-for="s in consultResult.suggestions" :key="s.id" class="suggestion-item">
            <div class="suggestion-head">
              <b>{{ s.name }}</b>
              <span class="confidence">可信度 {{ s.confidence }}%</span>
            </div>
            <div class="confidence-bar"><i :style="{ width: `${Math.min(s.confidence, 100)}%` }" /></div>
            <p>{{ s.description }}</p>
            <div v-if="s.tags?.length" class="mini-tags">
              <span v-for="t in s.tags" :key="t">{{ t }}</span>
            </div>
            <div v-if="s.recommended_exams?.length" class="mini-block">
              <b>建议检查：</b>
              <span v-for="e in s.recommended_exams" :key="e.exam_name">{{ e.exam_name }}（{{ e.reason }}）</span>
            </div>
            <div v-if="s.recommended_drugs?.length" class="mini-block">
              <b>用药参考（处方药需医生确认）：</b>
              <span v-for="d in s.recommended_drugs" :key="d.drug_name">{{ d.drug_name }}（{{ d.reason }}）</span>
            </div>
          </div>
        </div>

        <div v-if="consultResult.medication_review" class="result-section">
          <div class="section-title">用药参考</div>
          <div class="review-line" :class="{ warn: !consultResult.medication_review.passed }">
            {{ consultResult.medication_review.passed ? '✅ 未发现明显用药风险' : '⚠️ 存在需要关注的事项' }}
          </div>
          <ul v-if="consultResult.medication_review.warnings?.length" class="review-list">
            <li v-for="w in consultResult.medication_review.warnings" :key="w">{{ w }}</li>
          </ul>
          <ul v-if="consultResult.medication_review.recommendations?.length" class="review-list">
            <li v-for="r in consultResult.medication_review.recommendations" :key="r">💡 {{ r }}</li>
          </ul>
        </div>

        <div v-if="consultResult.follow_up_plan" class="result-section">
          <div class="section-title">随访建议</div>
          <p v-if="consultResult.follow_up_plan.interval_days">
            建议 <b>{{ consultResult.follow_up_plan.interval_days }} 天</b> 后复诊
          </p>
          <div v-if="consultResult.follow_up_plan.watch_items?.length" class="mini-block">
            <b>需观察：</b><span v-for="w in consultResult.follow_up_plan.watch_items" :key="w">{{ w }}</span>
          </div>
          <div v-if="consultResult.follow_up_plan.lifestyle_advice?.length" class="mini-block">
            <b>生活方式：</b><span v-for="l in consultResult.follow_up_plan.lifestyle_advice" :key="l">{{ l }}</span>
          </div>
          <div v-if="consultResult.follow_up_plan.warning_symptoms?.length" class="warning-box">
            <b>出现以下情况请立即就医：</b>
            <span v-for="w in consultResult.follow_up_plan.warning_symptoms" :key="w">{{ w }}</span>
          </div>
        </div>

        <p class="result-disclaimer">以上结果由 AI 结合知识库生成，仅供健康参考，不构成诊断，也不能替代医生面诊；正式就诊与处方需医生确认。如有紧急不适请立即就医。</p>
      </div>
    </div>

    <!-- ============ 健康咨询（聊天） ============ -->
    <template v-else>
      <div v-if="profileSummary" class="profile-card">
        <b>本次咨询结合的健康档案</b>
        <span v-html="renderMarkdown(profileSummary)"></span>
      </div>

      <div ref="chatBox" class="chat-scroll">
        <div v-if="messages.length === 0" class="empty-tip">
          <div class="empty-icon">💬</div>
          <p>你好，我是你的 AI 健康助手。身体哪里不舒服？<br />可以结合你的健康档案给你个性化建议。</p>
          <div class="suggestions">
            <button v-for="q in suggestions" :key="q" class="suggestion-chip" @click="send(q)">
              {{ q }}
            </button>
          </div>
        </div>

        <div v-for="(msg, i) in messages" :key="i" class="msg-row" :class="msg.role">
          <div class="avatar" :class="msg.role">{{ msg.role === 'user' ? '我' : 'AI' }}</div>
          <div class="bubble">
            <div class="bubble-text" v-html="renderMarkdown(msg.content)"></div>
            <div v-if="msg.role === 'assistant' && msg.meta" class="bubble-meta">
              {{ msg.meta }}
            </div>
          </div>
        </div>

        <div v-if="loading" class="msg-row assistant">
          <div class="avatar AI">AI</div>
          <div class="bubble typing">
            <span class="typing-dot" /><span class="typing-dot" /><span class="typing-dot" />
            <em>Qwen 思考中，约 5-10 秒…</em>
          </div>
        </div>
      </div>

      <div class="composer">
        <textarea
          v-model="input"
          rows="1"
          placeholder="输入你的健康问题，如：最近血压偏高，需要注意什么？"
          @keydown.enter.exact.prevent="send()"
        />
        <button class="send-btn" :disabled="loading || !input.trim()" @click="send()">
          发送
        </button>
        <button class="chat-clear" :disabled="!messages.length" @click="clearChat">
          清空记录
        </button>
      </div>
      <p class="disclaimer">{{ disclaimer }}</p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { patientAssist, patientConsult } from '@/api'
import type { PreConsultationResult } from '@/types'
import { renderMarkdown } from '@/utils/markdown'

interface ChatMsg {
  role: 'user' | 'assistant'
  content: string
  meta?: string
}

const router = useRouter()
const mode = ref<'consult' | 'chat'>('consult')

// —— 聊天模式状态 ——
const input = ref('')
const loading = ref(false)
const aiMode = ref(false)
const profileSummary = ref('')
const disclaimer = ref('')
const messages = ref<ChatMsg[]>([])
const CHAT_KEY_PREFIX = 'zhiyi-chat-history'

function chatKey(): string {
  try {
    const user = JSON.parse(localStorage.getItem('zhiyi-user') || '{}')
    return `${CHAT_KEY_PREFIX}-${user.id || 1}`
  } catch {
    return `${CHAT_KEY_PREFIX}-1`
  }
}

function loadMessages(): ChatMsg[] {
  try {
    const raw = localStorage.getItem(chatKey())
    const list = raw ? JSON.parse(raw) : []
    return Array.isArray(list)
      ? list.filter((m: ChatMsg) => m && typeof m.content === 'string')
      : []
  } catch {
    return []
  }
}

function persistMessages() {
  try {
    localStorage.setItem(chatKey(), JSON.stringify(messages.value.slice(-100)))
  } catch {
    // 本地存储不可用或已满时忽略，聊天仍可正常使用
  }
}

function clearChat() {
  messages.value = []
  try {
    localStorage.removeItem(chatKey())
  } catch {
    // 忽略清理失败
  }
}

onMounted(() => {
  messages.value = loadMessages()
})

watch(messages, persistMessages, { deep: true })
const chatBox = ref<HTMLElement | null>(null)

// —— AI 预问诊模式状态 ——
const consultInput = ref('')
const consulting = ref(false)
const consultResult = ref<PreConsultationResult | null>(null)

const suggestions = [
  '最近血压有点高，日常要注意什么？',
  '我有高血压和冠心病，运动时需要注意什么？',
  '经常头晕头痛，可能是什么原因？',
  '糖尿病患者的饮食应该怎么控制？',
]

function switchMode(next: 'consult' | 'chat') {
  mode.value = next
  if (next === 'chat') {
    void scrollBottom()
  }
}

function goHealth() {
  router.push('/patient/health')
}

function urgencyLabel(u?: string) {
  const map: Record<string, string> = { low: '低', medium: '中', high: '高' }
  return map[u || ''] || u || '低'
}

async function scrollBottom() {
  await nextTick()
  chatBox.value?.scrollTo({ top: chatBox.value.scrollHeight, behavior: 'smooth' })
}

async function submitConsult() {
  const text = consultInput.value.trim()
  if (!text || consulting.value) return
  if (text.length < 5) {
    ElMessage.warning('请至少输入 5 个字描述你的症状')
    return
  }
  consulting.value = true
  consultResult.value = null
  try {
    const res = await patientConsult(text)
    consultResult.value = res
    aiMode.value = !!res.use_ai
    ElMessage.success('AI 预问诊完成，已生成健康参考')
  } catch (e: any) {
    let msg = e?.message || '服务暂时不可用'
    try {
      const parsed = JSON.parse(msg)
      msg = parsed.detail || msg
    } catch { /* 非 JSON 错误直接展示 */ }
    ElMessage.error(`预问诊失败：${msg}`)
  } finally {
    consulting.value = false
  }
}

async function send(question?: string) {
  const text = (question ?? input.value).trim()
  if (!text || loading.value) return
  messages.value.push({ role: 'user', content: text })
  input.value = ''
  loading.value = true
  await scrollBottom()
  try {
    const res = await patientAssist(text)
    aiMode.value = res.use_ai
    profileSummary.value = res.profile_summary || ''
    disclaimer.value = res.disclaimer || ''
    messages.value.push({
      role: 'assistant',
      content: res.answer,
      meta: res.use_ai ? 'Qwen3.7-max · RAG 知识库' : '本地规则引擎',
    })
  } catch (e: any) {
    let msg = e?.message || '服务暂时不可用'
    try {
      const parsed = JSON.parse(msg)
      msg = parsed.detail || msg
    } catch { /* 非 JSON 错误直接展示 */ }
    messages.value.push({ role: 'assistant', content: `抱歉，回答失败：${msg}` })
    ElMessage.error('智能助手调用失败，请稍后重试')
  } finally {
    loading.value = false
    await scrollBottom()
  }
}
</script>

<style scoped>
.assistant-page {
  max-width: 860px;
  margin: 0 auto;
  height: calc(100vh - 170px);
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.assistant-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: linear-gradient(135deg, #2f6df6, #5b8cff);
  color: #fff;
  border-radius: 14px;
  padding: 18px 22px;
}
.assistant-hero h2 { margin: 0; font-size: 19px; }
.assistant-hero p { margin: 4px 0 0; font-size: 12.5px; opacity: .92; }

.ai-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: rgba(255, 255, 255, .18);
  border: 1px solid rgba(255, 255, 255, .35);
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 12px;
  white-space: nowrap;
}
.ai-badge .dot { width: 7px; height: 7px; border-radius: 50%; background: #5ef09a; box-shadow: 0 0 6px #5ef09a; }
.ai-badge.local { background: rgba(255,255,255,.1); }
.ai-badge.local .dot { background: #ffd166; box-shadow: 0 0 6px #ffd166; }

/* 模式切换 */
.mode-tabs {
  display: flex;
  gap: 8px;
}
.mode-tabs button {
  border: 1px solid var(--border-light);
  background: #fff;
  color: var(--text-secondary);
  border-radius: 10px;
  padding: 8px 18px;
  font-size: 13.5px;
  cursor: pointer;
  transition: all .15s;
}
.mode-tabs button.active {
  background: #2f6df6;
  border-color: #2f6df6;
  color: #fff;
}

.profile-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: #f0f6ff;
  border: 1px solid #d4e4ff;
  border-radius: 10px;
  padding: 10px 14px;
  font-size: 12.5px;
  color: #33507e;
}
.profile-card b { font-size: 12px; color: #2f6df6; }

/* ===== AI 预问诊 ===== */
.consult-scroll {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.consult-card {
  background: #fff;
  border: 1px solid var(--border-light);
  border-radius: 14px;
  padding: 18px 20px;
}
.consult-card h3 { margin: 0 0 6px; font-size: 16px; }
.consult-card p { margin: 0 0 12px; font-size: 12.5px; color: var(--text-secondary); line-height: 1.6; }
.consult-card textarea {
  width: 100%;
  border: 1px solid #d8e0ea;
  border-radius: 10px;
  padding: 12px;
  font-size: 14px;
  font-family: inherit;
  line-height: 1.6;
  resize: vertical;
  outline: none;
  box-sizing: border-box;
}
.consult-card textarea:focus { border-color: #2f6df6; }
.consult-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
}
.counter { font-size: 12px; color: var(--text-tertiary); }
.consult-btn {
  background: #2f6df6;
  color: #fff;
  border: none;
  border-radius: 9px;
  padding: 9px 22px;
  font-size: 14px;
  cursor: pointer;
}
.consult-btn:disabled { opacity: .5; cursor: not-allowed; }

.consult-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  justify-content: center;
  padding: 24px;
  color: var(--text-secondary);
  font-size: 13.5px;
  background: #f7f9fc;
  border-radius: 12px;
}
.spinner {
  width: 18px; height: 18px;
  border: 2.5px solid #dbe3f0;
  border-top-color: #2f6df6;
  border-radius: 50%;
  animation: spin .8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg) } }

.consult-result {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-bottom: 20px;
}

.result-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: linear-gradient(135deg, #e8f7ee, #f2fbf6);
  border: 1px solid #bfe6cf;
  border-radius: 12px;
  padding: 14px 18px;
}
.result-banner b { color: #1d7a44; font-size: 15px; }
.result-banner span { display: block; margin-top: 3px; font-size: 12px; color: #3d6b50; }
.go-health {
  flex: none;
  background: #1d9e56;
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 8px 16px;
  font-size: 13px;
  cursor: pointer;
}

.result-section {
  background: #fff;
  border: 1px solid var(--border-light);
  border-radius: 12px;
  padding: 16px 18px;
}
.triage-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.triage-chip {
  display: inline-flex;
  align-items: center;
  padding: 5px 12px;
  border-radius: 999px;
  background: #f0f6ff;
  border: 1px solid #d4e4ff;
  color: #33507e;
  font-size: 12.5px;
}
.triage-chip.urgency-low { background: #ecfdf5; border-color: #bbe7d0; color: #1d7a44; }
.triage-chip.urgency-medium { background: #fffbeb; border-color: #f3ddb0; color: #b45309; }
.triage-chip.urgency-high { background: #fef2f2; border-color: #f3caca; color: #b3403a; }
.section-title {
  font-size: 13px;
  font-weight: 700;
  color: #2f6df6;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.section-title::before {
  content: '';
  width: 3px; height: 14px;
  background: #2f6df6;
  border-radius: 2px;
}
.final-diagnosis {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 8px;
}
.symptom-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.symptom-tag {
  background: #eef3ff;
  color: #2f6df6;
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 12px;
}

.suggestion-item { padding: 12px 0; border-top: 1px dashed #e6ebf2; }
.suggestion-item:first-child { border-top: none; padding-top: 2px; }
.suggestion-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.suggestion-head b { font-size: 14.5px; }
.confidence { font-size: 12px; color: #2f6df6; font-weight: 600; white-space: nowrap; }
.confidence-bar {
  height: 5px;
  background: #eef1f6;
  border-radius: 3px;
  margin: 7px 0 8px;
  overflow: hidden;
}
.confidence-bar i { display: block; height: 100%; background: linear-gradient(90deg, #2f6df6, #5b8cff); border-radius: 3px; }
.suggestion-item p { margin: 0 0 8px; font-size: 12.5px; color: var(--text-secondary); line-height: 1.6; }
.mini-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.mini-tags span {
  background: #f3f5f9;
  border-radius: 6px;
  padding: 2px 8px;
  font-size: 11.5px;
  color: var(--text-secondary);
}
.mini-block { display: flex; flex-wrap: wrap; gap: 6px 10px; font-size: 12.5px; margin-top: 6px; }
.mini-block b { color: var(--text-primary); font-weight: 600; }
.mini-block span { color: var(--text-secondary); }

.review-line { font-size: 13.5px; margin-bottom: 6px; }
.review-line.warn { color: #d97706; font-weight: 600; }
.review-list { margin: 4px 0 0; padding-left: 18px; font-size: 12.5px; color: var(--text-secondary); line-height: 1.8; }

.warning-box {
  margin-top: 8px;
  background: #fdf3f3;
  border: 1px solid #f3caca;
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 12.5px;
  color: #b3403a;
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
}

.result-disclaimer {
  margin: 0;
  text-align: center;
  font-size: 11.5px;
  color: var(--text-tertiary);
}

/* ===== 聊天模式 ===== */
.chat-scroll {
  flex: 1;
  overflow-y: auto;
  background: #fff;
  border: 1px solid var(--border-light);
  border-radius: 14px;
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.empty-tip {
  margin: auto;
  text-align: center;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.7;
}
.empty-icon { font-size: 40px; margin-bottom: 6px; }
.suggestions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin-top: 14px;
}
.suggestion-chip {
  background: #f2f6ff;
  border: 1px solid #dbe7ff;
  color: #2f6df6;
  border-radius: 999px;
  padding: 7px 14px;
  font-size: 12.5px;
  cursor: pointer;
  transition: all .15s;
}
.suggestion-chip:hover { background: #2f6df6; color: #fff; border-color: #2f6df6; }

.msg-row { display: flex; gap: 10px; align-items: flex-start; }
.msg-row.user { flex-direction: row-reverse; }
.avatar {
  flex: none;
  width: 34px; height: 34px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 700;
}
.avatar.user { background: #2f6df6; color: #fff; }
.avatar.AI { background: #10b981; color: #fff; }
.bubble {
  max-width: 78%;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}
.msg-row.user .bubble { background: #2f6df6; color: #fff; border-top-right-radius: 4px; }
.msg-row.assistant .bubble { background: #f5f7fb; color: var(--text-primary); border-top-left-radius: 4px; }
.bubble-meta { margin-top: 6px; font-size: 11px; color: var(--text-tertiary); }
.msg-row.user .bubble-meta { color: rgba(255,255,255,.75); }

/* ===== Markdown 渲染样式 ===== */
.bubble-text { white-space: normal; }
.bubble-text :deep(p) { margin: 4px 0; }
.bubble-text :deep(h1),
.bubble-text :deep(h2),
.bubble-text :deep(h3),
.bubble-text :deep(h4) { margin: 8px 0 4px; font-weight: 700; line-height: 1.4; }
.bubble-text :deep(h1) { font-size: 17px; }
.bubble-text :deep(h2) { font-size: 16px; }
.bubble-text :deep(h3) { font-size: 15px; }
.bubble-text :deep(h4) { font-size: 14px; }
.bubble-text :deep(ul),
.bubble-text :deep(ol) { margin: 4px 0; padding-left: 22px; }
.bubble-text :deep(li) { margin: 3px 0; }
.bubble-text :deep(code) { background: rgba(0,0,0,.07); padding: 1px 6px; border-radius: 4px; font-size: 12.5px; font-family: Consolas, Menlo, monospace; }
.bubble-text :deep(pre) { background: #0f172a; color: #e2e8f0; padding: 10px 12px; border-radius: 10px; overflow-x: auto; margin: 6px 0; }
.bubble-text :deep(pre code) { background: none; color: inherit; padding: 0; font-size: 12.5px; }
.bubble-text :deep(blockquote) { border-left: 3px solid #2f6df6; margin: 6px 0; padding: 4px 12px; background: rgba(47,109,246,.06); border-radius: 0 10px 10px 0; }
.bubble-text :deep(blockquote p) { margin: 3px 0; }
.bubble-text :deep(a) { color: #2f6df6; }
.bubble-text :deep(hr) { border: none; border-top: 1px solid #e2e8f0; margin: 8px 0; }
.bubble-text :deep(table) { border-collapse: collapse; width: 100%; margin: 6px 0; font-size: 12.5px; }
.bubble-text :deep(th),
.bubble-text :deep(td) { border: 1px solid #dfe5ee; padding: 5px 8px; text-align: left; }
.bubble-text :deep(th) { background: #eef3ff; font-weight: 600; }
.bubble-text :deep(.md-table-wrap) { overflow-x: auto; }
.msg-row.user .bubble-text :deep(a) { color: #fff; text-decoration: underline; }
.msg-row.user .bubble-text :deep(code) { background: rgba(255,255,255,.22); color: #fff; }
.msg-row.user .bubble-text :deep(th) { background: rgba(255,255,255,.16); }
.msg-row.user .bubble-text :deep(th),
.msg-row.user .bubble-text :deep(td) { border-color: rgba(255,255,255,.35); }

.typing { display: flex; align-items: center; gap: 6px; color: var(--text-tertiary); }
.typing-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: #b6c2d6;
  animation: blink 1.2s infinite;
}
.typing-dot:nth-child(2) { animation-delay: .2s; }
.typing-dot:nth-child(3) { animation-delay: .4s; }
.typing em { font-style: normal; font-size: 12px; margin-left: 4px; }
@keyframes blink { 0%, 80%, 100% { opacity: .3 } 40% { opacity: 1 } }

.composer {
  display: flex;
  gap: 10px;
  background: #fff;
  border: 1px solid var(--border-light);
  border-radius: 12px;
  padding: 10px;
}
.composer textarea {
  flex: 1;
  border: none;
  outline: none;
  resize: none;
  font-size: 14px;
  font-family: inherit;
  line-height: 1.5;
  max-height: 90px;
  padding: 6px 8px;
}
.send-btn {
  align-self: flex-end;
  background: #2f6df6;
  color: #fff;
  border: none;
  border-radius: 9px;
  padding: 9px 20px;
  font-size: 14px;
  cursor: pointer;
  transition: opacity .15s;
}
.send-btn:disabled { opacity: .5; cursor: not-allowed; }

.chat-clear {
  align-self: flex-end;
  padding: 8px 12px;
  border: 1px solid var(--border-light);
  border-radius: 9px;
  color: var(--text-tertiary);
  background: var(--bg-surface);
  font-size: 12px;
  cursor: pointer;
  transition: all .15s;
}
.chat-clear:hover:not(:disabled) { color: var(--danger); border-color: var(--danger-light); }
.chat-clear:disabled { opacity: .5; cursor: not-allowed; }
html.dark .chat-clear { background: var(--bg-surface); border-color: var(--border-default); }

.disclaimer {
  margin: 0;
  text-align: center;
  font-size: 11.5px;
  color: var(--text-tertiary);
}
</style>
