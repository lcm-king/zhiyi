<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowRight, Check, Document, Mic, Paperclip, VideoPlay, MagicStick, FirstAidKit, Timer, Loading, Plus, Warning } from '@element-plus/icons-vue'
import type { DiagnosisResult, DiagnosisSuggestion, FollowUpPlan, MedicalRecord, MedicationReview, PatientListItem } from '@/types'
import { runDiagnosis, saveMedicalRecord, createOrder, getPatientProfile, getPatients } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { defaultDeliveryAddress, locateCurrentCity } from '@/utils/location'
import { renderMarkdown } from '@/utils/markdown'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const symptoms = ref('')
const analyzing = ref(false)
const selectedId = ref(1)
const now = ref(Date.now())
const fileInputRef = ref<HTMLInputElement | null>(null)
const uploadedFiles = ref<string[]>([])
const greeting = computed(() => {
  const h = new Date(now.value).getHours()
  if (h < 12) return '早上好'
  if (h < 18) return '下午好'
  return '晚上好'
})
const currentDeliveryAddress = ref(defaultDeliveryAddress())
let timeTimer: ReturnType<typeof setInterval> | null = null

// 语音录入
const isListening = ref(false)

// 语音播报
const isSpeaking = ref(false)
function toggleSpeech() {
  const synth = window.speechSynthesis
  if (!synth) { ElMessage.warning('当前浏览器不支持语音播报，建议使用 Chrome 或 Edge'); return }

  if (synth.speaking) {
    synth.cancel()
    isSpeaking.value = false
    return
  }

  // 构建播报内容
  const parts: string[] = []
  const mr = diagnosisResult.value
  if (mr?.medical_record) {
    const m = mr.medical_record as any
    if (m.chief_complaint) parts.push(`主诉：${m.chief_complaint}`)
    if (m.present_illness) parts.push(`现病史：${m.present_illness}`)
    if (m.past_history) parts.push(`既往史：${m.past_history}`)
    if (m.allergies) parts.push(`过敏史：${m.allergies}`)
    if (m.preliminary_diagnosis) parts.push(`初步诊断：${m.preliminary_diagnosis}`)
    if (m.treatment_plan?.length) parts.push(`治疗方案：${m.treatment_plan.join('；')}`)
  } else if (diagnosisSuggestions.value.length) {
    parts.push(`诊断结果如下：`)
    diagnosisSuggestions.value.slice(0, 3).forEach((s, i) => {
      parts.push(`第${i + 1}项，${s.name}，置信度${s.confidence}%`)
    })
  }
  if (!parts.length) { ElMessage.warning('请先完成诊断，生成病历后再播报'); return }

  const utterance = new SpeechSynthesisUtterance(parts.join('。'))
  utterance.lang = 'zh-CN'
  utterance.rate = 0.9
  utterance.onstart = () => { isSpeaking.value = true }
  utterance.onend = () => { isSpeaking.value = false }
  utterance.onerror = () => { isSpeaking.value = false }
  synth.speak(utterance)
  ElMessage.success('正在语音播报病历…')
}
let recognition: any = null

function toggleVoiceInput() {
  const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!SpeechRecognition) {
    ElMessage.warning('当前浏览器不支持语音识别，建议使用 Chrome 或 Edge')
    return
  }
  if (isListening.value) {
    recognition?.stop()
    return
  }
  recognition = new SpeechRecognition()
  recognition.lang = 'zh-CN'
  recognition.interimResults = false  // 只取最终结果，避免重复触发
  recognition.continuous = false      // 说一句自动停止，避免连续叠加
  recognition.onresult = (event: any) => {
    // 只处理最后一个最终的识别结果
    const last = event.results[event.results.length - 1]
    if (last.isFinal) {
      const transcript = last[0].transcript.trim()
      if (transcript) {
        symptoms.value = symptoms.value ? `${symptoms.value}，${transcript}` : transcript
      }
    }
  }
  recognition.onerror = (event: any) => {
    if (event.error !== 'no-speech') {
      ElMessage.error(`语音识别出错：${event.error}`)
    }
    isListening.value = false
  }
  recognition.onend = () => { isListening.value = false }
  recognition.start()
  isListening.value = true
  ElMessage.success('正在聆听，请描述患者症状…')
}

function triggerFileUpload() {
  fileInputRef.value?.click()
}

function handleFileUpload(e: Event) {
  const target = e.target as HTMLInputElement
  if (!target.files || target.files.length === 0) return
  const file = target.files[0]
  uploadedFiles.value.push(file.name)
  ElMessage.success(`已添加附件：${file.name}`)
  target.value = ''
}

// 从 API 获取的动态诊断结果
const diagnosisResult = ref<DiagnosisResult | null>(null)
const diagnosisSuggestions = ref<DiagnosisSuggestion[]>([])
const diagnosisId = ref<number | null>(null)
const medicationReview = ref<MedicationReview | null>(null)
const medicalRecord = ref<MedicalRecord | null>(null)
const followUpPlan = ref<FollowUpPlan | null>(null)
const agentLogs = ref<string[]>([])
const checkedSigns = ref<string[]>([])
const patientProfile = ref<any>(null)
const patients = ref<PatientListItem[]>([])
const currentPatientId = ref<number | null>(null)
const loadingPatients = ref(false)

onMounted(async () => {
  const geo = await locateCurrentCity()
  if (geo) currentDeliveryAddress.value = geo.address
  now.value = Date.now()
  timeTimer = setInterval(() => { now.value = Date.now() }, 1000)
  loadingPatients.value = true
  try {
    patients.value = await getPatients()
    if (patients.value.length > 0) {
      // 优先使用路由 query 指定的患者，否则默认第一位
      const targetId = Number(route.query.patientId) || patients.value[0].id
      currentPatientId.value = targetId
      await loadPatientProfile(targetId)
    }
  } catch (e: any) {
    ElMessage.error(e.message || '加载患者列表失败')
  } finally {
    loadingPatients.value = false
  }
})

onUnmounted(() => {
  if (timeTimer) { clearInterval(timeTimer); timeTimer = null }
})

async function loadPatientProfile(patientId: number) {
  try {
    patientProfile.value = await getPatientProfile(patientId)
  } catch (e: any) {
    ElMessage.error(e.message || '加载患者档案失败')
  }
}

async function onSelectPatient(event: Event) {
  const target = event.target as HTMLSelectElement
  const patientId = Number(target.value)
  if (!patientId) return
  currentPatientId.value = patientId
  await loadPatientProfile(patientId)
  // 切换患者后清空上一次诊断结果，避免混淆
  diagnosisResult.value = null
  diagnosisSuggestions.value = []
  diagnosisId.value = null
  medicalRecord.value = null
  medicationReview.value = null
  followUpPlan.value = null
  agentLogs.value = []
}

const selected = computed(() =>
  diagnosisSuggestions.value.find((item) => item.id === selectedId.value) || diagnosisSuggestions.value[0]
)
const signs = computed(() => {
  if (medicalRecord.value?.physical_examination?.focused_exam?.length) {
    return medicalRecord.value.physical_examination.focused_exam
  }
  return ['双肺底湿啰音', '颈静脉充盈 / 怒张', '双下肢轻度浮肿']
})

async function diagnose() {
  if (!symptoms.value.trim()) return ElMessage.warning('请先输入患者主诉或症状')
  if (!currentPatientId.value) return ElMessage.warning('请先选择患者')
  analyzing.value = true
  try {
    const result = await runDiagnosis(currentPatientId.value, symptoms.value)
    diagnosisResult.value = result
    if (result?.suggestions?.length) {
      diagnosisSuggestions.value = result.suggestions.map((s: any) => ({
        id: s.id,
        name: s.name,
        confidence: s.confidence,
        description: s.description,
        tags: s.tags || [],
        tone: s.tone || ['blue', 'amber', 'violet'][s.id % 3],
        is_primary: !!s.is_primary,
        differential_diagnoses: s.differential_diagnoses || [],
        recommended_exams: s.recommended_exams || [],
        recommended_drugs: s.recommended_drugs || [],
      }))
      diagnosisId.value = result.id
      selectedId.value = result.suggestions[0].id
      medicationReview.value = result.medication_review || null
      medicalRecord.value = result.medical_record || null
      followUpPlan.value = result.follow_up_plan || null
      agentLogs.value = result.agent_logs || []
      checkedSigns.value = []
      if (result.from_mock) {
        ElMessage.warning(`当前为本地模拟诊断（后端未连接），共匹配 ${result.suggestions.length} 种疑似疾病`)
      } else if (!result.use_ai) {
        ElMessage.warning(`诊断完成：共匹配 ${result.suggestions.length} 种疑似疾病（当前使用本地规则引擎，未启用 Qwen 大模型）`)
      } else {
        ElMessage.success(`诊断完成，共匹配 ${result.suggestions.length} 种疑似疾病（Qwen3.7-max AI 推理）`)
      }
    } else {
      ElMessage.warning('未匹配到相关疾病，请补充更多症状描述')
    }
  } catch (e: any) {
    ElMessage.error(e.message || '诊断服务异常，请稍后重试')
  } finally {
    analyzing.value = false
  }
}

async function saveRecord() {
  if (!diagnosisId.value) return ElMessage.warning('请先完成诊断')
  if (!currentPatientId.value) return ElMessage.warning('请先选择患者')
  const selected = diagnosisSuggestions.value.find((s) => s.id === selectedId.value)
  if (!selected) return
  try {
    await saveMedicalRecord({
      diagnosis_id: diagnosisId.value,
      patient_id: diagnosisResult.value?.patient_id || currentPatientId.value,
      doctor_id: authStore.user?.id || 1,
      final_diagnosis: selected.name,
      treatment_plan: JSON.stringify(selected.recommended_drugs?.map((d) => d.drug_name) || []),
    })
    ElMessage.success({
      message: `病历已保存至「${patientProfile.value?.name || '患者'}」的档案`,
      duration: 4000,
      showClose: true,
    })
  } catch (e: any) {
    ElMessage.error(e.message || '病历保存失败')
  }
}

async function bookExam(exam: any) {
  try {
    const examItemId = exam.exam_item_id || exam.id
    if (!examItemId) {
      ElMessage.warning('该检查项目暂无对应预约 ID，请手动前往检查预约模块')
      return
    }
    await createOrder('exam', {
      items: [{ exam_item_id: examItemId, quantity: 1 }],
      hospital_id: 1,
      appointment_time: new Date(Date.now() + 86400000).toISOString(),
      patient_id: currentPatientId.value,
    })
    ElMessage.success(`已为您创建「${exam.exam_name || exam.name}」检查预约，请前往检查预约模块支付`)
  } catch (e: any) {
    ElMessage.error(e.message || '预约创建失败')
  }
}

async function addDrugToCart(drug: any) {
  try {
    const drugId = drug.drug_id || drug.id
    if (!drugId) {
      ElMessage.warning('该药品暂无对应 ID，请手动前往药品购物车')
      return
    }
    await createOrder('drug', {
      items: [{ drug_id: drugId, quantity: 1 }],
      address: currentDeliveryAddress.value || defaultDeliveryAddress(),
      patient_id: currentPatientId.value,
    })
    ElMessage.success(`已将「${drug.drug_name || drug.name}」加入药品购物车`)
  } catch (e: any) {
    ElMessage.error(e.message || '加入购物车失败')
  }
}

function toggleSign(sign: string) {
  checkedSigns.value = checkedSigns.value.includes(sign)
    ? checkedSigns.value.filter((item) => item !== sign)
    : [...checkedSigns.value, sign]
}

function addKeyword(keyword: string) {
  symptoms.value += `${symptoms.value ? '，' : ''}${keyword}`
}
</script>

<template>
  <div class="doctor-page">
    <!-- 页头 -->
    <div class="page-heading">
      <div>
        <div class="eyebrow">临床智能辅助 / 今日工作台</div>
        <h1 class="page-title">{{ greeting }}，{{ authStore.user?.name || '医生' }}。</h1>
        <p class="page-subtitle">AI 已准备好协助你完成今天的每一次判断。当前工作流将自动沉淀为可追溯的结构化病历。</p>
      </div>
      <div class="doctor-meta">
        <div class="doctor-meta-date">
          <strong>{{ new Date(now).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) }}</strong>
          <span>{{ ['周日','周一','周二','周三','周四','周五','周六'][new Date(now).getDay()] }} · {{ new Date(now).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}</span>
        </div>
        <div class="doctor-meta-status">
          <span class="doctor-status-dot" />
          系统正常
        </div>
      </div>
    </div>

    <!-- 患者横幅 -->
    <div class="patient-banner">
      <div class="patient-banner-main">
        <div class="patient-avatar-lg">
          <span>{{ patientProfile?.name?.[0] || '患' }}</span>
        </div>
        <div class="patient-info">
          <div class="patient-info-top">
            <h2>{{ patientProfile?.name || '患者' }}</h2>
            <select
              class="patient-selector"
              :value="currentPatientId ?? ''"
              :disabled="loadingPatients || patients.length === 0"
              @change="onSelectPatient"
            >
              <option v-if="loadingPatients" value="">加载患者中…</option>
              <option v-else-if="patients.length === 0" value="">暂无患者</option>
              <option v-for="p in patients" :key="p.id" :value="p.id">
                {{ p.name }} · {{ p.gender === 'M' ? '男' : '女' }} · {{ p.phone }}
              </option>
            </select>
            <span class="chip chip-blue">{{ patientProfile?.gender === 'M' ? '男' : '女' }} · {{ patientProfile?.age || '-' }} 岁</span>
            <span class="chip chip-teal">
              <MagicStick /> 慢病高风险
            </span>
          </div>
          <div class="patient-info-meta">
            <span><b>病案号</b> P{{ String(currentPatientId ?? '').padStart(8, '0') }}</span>
            <span><b>既往史</b> {{ patientProfile?.past_history?.join(' · ') || '无已知既往史' }}</span>
            <span class="patient-warning"><b>过敏史</b> {{ patientProfile?.allergies?.join('、') || '无' }}</span>
          </div>
        </div>
      </div>
      <div class="patient-banner-actions">
        <button class="ghost-button" @click="router.push('/doctor/records')">
          <Document /> 既往记录
        </button>
        <button class="primary-button" @click="router.push(`/doctor/records/${currentPatientId}`)">
          <ArrowRight /> 查看档案
        </button>
      </div>
    </div>

    <!-- 主内容网格 -->
    <div class="doctor-grid">
      <!-- 左列：症状分析 + 诊断建议 -->
      <div class="doctor-col-main">
        <!-- 症状分析卡片 -->
        <section class="surface-card analysis-card">
          <div class="section-title">
            <div>
              <div class="section-kicker"><span class="signal-line" />核心工作流</div>
              <h2>症状智能分析</h2>
            </div>
            <button
              class="ghost-button"
              :class="{ 'is-recording': isListening }"
              @click="toggleVoiceInput"
            >
              <Mic />
              {{ isListening ? '聆听中…点击停止' : '语音录入' }}
            </button>
          </div>

          <div class="symptom-editor">
            <textarea
              v-model="symptoms"
              rows="5"
              placeholder="描述患者当前主诉、症状与病史信息…"
            />
            <div class="symptom-editor-footer">
              <div class="symptom-editor-tools">
                <button class="mini-tool-btn" @click="triggerFileUpload">
                  <Paperclip /> 添加资料
                </button>
                <input ref="fileInputRef" type="file" accept=".jpg,.png,.pdf,.doc,.docx" style="display:none" @change="handleFileUpload" />
                <span class="symptom-char-count">{{ symptoms.length }} / 1000</span>
              </div>
              <button
                class="primary-button diagnose-btn"
                :disabled="analyzing"
                @click="diagnose"
              >
                <Loading v-if="analyzing" class="loading-spin" />
                <MagicStick v-else />
                {{ analyzing ? '智能分析中…' : '开始诊断' }}
              </button>
            </div>
          </div>

          <div class="keyword-suggestions">
            <span>快速补充</span>
            <button v-for="keyword in ['持续咳嗽', '呼吸困难', '心悸', '乏力', '发热', '胸痛', '腹痛']" :key="keyword" class="keyword-btn" @click="addKeyword(keyword)">
              + {{ keyword }}
            </button>
          </div>

          <!-- Agent 工作流日志 -->
          <div v-if="agentLogs.length" class="agent-logs">
            <div v-for="(log, idx) in agentLogs" :key="idx" class="agent-log-item">
              <span class="agent-log-dot" />
              {{ log }}
            </div>
          </div>
        </section>

        <!-- 诊断建议列表 -->
        <section class="diagnosis-section">
          <div class="section-title">
            <div>
              <div class="section-kicker"><span class="signal-line" />智能诊断建议</div>
              <h2>推荐诊断方案</h2>
            </div>
            <span class="diagnosis-note">基于医学知识库 RAG 检索与多 Agent 推理</span>
          </div>

          <div v-if="medicationReview && medicationReview.warnings.length" class="warning-banner">
            <Warning />
            <div>
              <strong>用药安全提醒</strong>
              <p v-for="w in medicationReview.warnings" :key="w">{{ w }}</p>
            </div>
          </div>

          <div class="diagnosis-list">
            <div
              v-for="item in diagnosisSuggestions"
              :key="item.id"
              class="diagnosis-card"
              :class="{ selected: selectedId === item.id }"
              @click="selectedId = item.id"
            >
              <div class="diagnosis-card-main">
                <div class="diagnosis-card-icon" :class="`tone-${item.tone}`">
                  <FirstAidKit />
                </div>
                <div class="diagnosis-card-info">
                  <div class="diagnosis-card-header">
                    <div class="diagnosis-name-row">
                      <span v-if="item.is_primary" class="primary-badge">AI 首选诊断</span>
                      <h3>{{ item.name }}</h3>
                    </div>
                    <div class="diagnosis-confidence" :class="`tone-${item.tone}`">
                      <strong>{{ item.confidence }}<small>%</small></strong>
                      <span>置信度</span>
                    </div>
                  </div>
                  <p>{{ item.description }}</p>
                  <div class="diagnosis-tags">
                    <span v-for="tag in item.tags" :key="tag" class="diagnosis-tag">{{ tag }}</span>
                  </div>

                  <!-- 鉴别诊断 -->
                  <div v-if="item.differential_diagnoses?.length" class="diagnosis-sub-section">
                    <strong>鉴别诊断</strong>
                    <div class="diagnosis-pills">
                      <span v-for="d in item.differential_diagnoses" :key="d" class="diff-pill">{{ d }}</span>
                    </div>
                  </div>

                  <!-- 推荐检查 -->
                  <div v-if="item.recommended_exams?.length" class="diagnosis-sub-section">
                    <strong>推荐检查</strong>
                    <div class="exam-list">
                      <div v-for="exam in item.recommended_exams" :key="exam.exam_name" class="exam-item">
                        <span class="exam-priority" :class="`priority-${exam.priority}`">{{ exam.priority === 'high' ? '高' : '常' }}</span>
                        <span class="exam-name">{{ exam.exam_name }}</span>
                        <button class="text-button-sm" @click.stop="bookExam(exam)"><Plus /> 预约</button>
                      </div>
                    </div>
                  </div>

                  <!-- 推荐用药 -->
                  <div v-if="item.recommended_drugs?.length" class="diagnosis-sub-section">
                    <strong>推荐用药</strong>
                    <div class="drug-list">
                      <div v-for="drug in item.recommended_drugs" :key="drug.drug_name" class="drug-item">
                        <span class="drug-name">{{ drug.drug_name }}</span>
                        <span v-if="drug.warning" class="drug-warning">{{ drug.warning }}</span>
                        <button class="text-button-sm" @click.stop="addDrugToCart(drug)"><Plus /> 加购</button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div class="diagnosis-card-action">
                <template v-if="selectedId === item.id">
                  <Check class="diagnosis-check-icon" />
                  已选择
                </template>
                <template v-else>
                  查看详情
                  <ArrowRight />
                </template>
              </div>
            </div>
          </div>
        </section>
      </div>

      <!-- 右列：结构化病历预览 -->
      <section class="record-panel">
        <div class="record-panel-header">
          <div>
            <div class="section-kicker"><span class="signal-line" />结构化病历预览</div>
            <h2>病历预览</h2>
          </div>
          <button class="icon-button" :title="isSpeaking ? '停止播报' : '语音播报'" @click="toggleSpeech" :style="isSpeaking ? 'color:#DC2626' : ''">
            <VideoPlay />
          </button>
        </div>

        <div class="record-content">
          <!-- 主诉 -->
          <div class="record-section">
            <div class="record-section-icon"><span>主</span></div>
            <div>
              <h4>主诉</h4>
              <p>{{ medicalRecord?.chief_complaint || symptoms }}</p>
            </div>
          </div>

          <!-- 现病史 -->
          <div class="record-section">
            <div class="record-section-icon"><span>现</span></div>
            <div>
              <h4>现病史</h4>
              <p>{{ medicalRecord?.present_illness || '点击「开始诊断」生成 AI 现病史' }}</p>
            </div>
          </div>

          <!-- 既往史 & 过敏史 -->
          <div class="record-section">
            <div class="record-section-icon"><span>史</span></div>
            <div>
              <h4>既往史 / 过敏史</h4>
              <p><b>既往史：</b>{{ medicalRecord?.past_history || '待补充' }}</p>
              <p><b>过敏史：</b>{{ medicalRecord?.allergies || '无已知过敏史' }}</p>
            </div>
          </div>

          <!-- AI体格检查建议 -->
          <div class="record-section">
            <div class="record-section-icon"><span>检</span></div>
            <div>
              <h4>AI 辅助体格检查建议</h4>
              <div class="record-signs">
                <button
                  v-for="sign in signs"
                  :key="sign"
                  :class="{ checked: checkedSigns.includes(sign) }"
                  @click="toggleSign(sign)"
                >
                  <FirstAidKit />
                  <span>{{ sign }}</span>
                  <Check v-if="checkedSigns.includes(sign)" class="sign-confirmed" />
                </button>
              </div>
            </div>
          </div>

          <!-- 鉴别诊断 -->
          <div class="record-section">
            <div class="record-section-icon"><span>鉴</span></div>
            <div>
              <h4>鉴别诊断</h4>
              <div v-if="medicalRecord?.differential_diagnosis?.length" class="diagnosis-pills">
                <span v-for="d in medicalRecord.differential_diagnosis" :key="d" class="diff-pill">{{ d }}</span>
              </div>
              <p v-else>点击「开始诊断」后生成</p>
            </div>
          </div>

          <!-- 初步诊断 -->
          <div class="record-section">
            <div class="record-section-icon"><span>诊</span></div>
            <div>
              <h4>初步诊断</h4>
              <p>{{ medicalRecord?.preliminary_diagnosis || '等待 AI 诊断结果' }}</p>
            </div>
          </div>

          <!-- 治疗方案 -->
          <div class="record-section">
            <div class="record-section-icon"><span>治</span></div>
            <div>
              <h4>治疗方案</h4>
              <ul v-if="medicalRecord?.treatment_plan?.length">
                <li v-for="t in medicalRecord.treatment_plan" :key="t" v-html="renderMarkdown(t)"></li>
              </ul>
              <p v-else>等待 AI 生成治疗方案</p>
            </div>
          </div>

          <!-- 随访计划 -->
          <div v-if="followUpPlan" class="record-section">
            <div class="record-section-icon"><span>随</span></div>
            <div>
              <h4>随访计划（{{ followUpPlan.interval_days }} 天后复诊）</h4>
              <p><b>观察指标：</b><span v-html="renderMarkdown(followUpPlan.watch_items.join('、'))"></span></p>
              <p><b>生活方式：</b><span v-html="renderMarkdown(followUpPlan.lifestyle_advice.join('、'))"></span></p>
              <p class="warning-text"><b>警示症状：</b><span v-html="renderMarkdown(followUpPlan.warning_symptoms.join('、'))"></span></p>
            </div>
          </div>
        </div>

        <div class="record-footer">
          <button class="primary-button record-submit" :disabled="!diagnosisId" @click="saveRecord">
            <Document /> 确认并存入电子病历
          </button>
        </div>
      </section>
    </div>

    <!-- AI 状态浮动条 -->
    <div class="ai-status-bar">
      <div class="ai-status-avatar"><MagicStick /></div>
      <span>AI 正在根据检查结果实时同步建议</span>
      <div class="ai-status-dots">
        <span /><span /><span />
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 诊断子区域 */
.diagnosis-sub-section {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--border-light);
}

.diagnosis-sub-section strong {
  display: block;
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.diagnosis-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.diff-pill {
  padding: 3px 8px;
  border-radius: var(--radius-full);
  background: var(--gray-100);
  color: var(--text-secondary);
  font-size: 10px;
}

.warning-banner {
  display: flex;
  gap: 10px;
  padding: 12px 14px;
  margin-bottom: 14px;
  border-radius: var(--radius-md);
  background: #FEF2F2;
  color: #B91C1C;
  font-size: 12px;
}

.warning-banner svg {
  width: 18px;
  flex-shrink: 0;
}

.warning-banner strong {
  display: block;
  margin-bottom: 4px;
}

.warning-banner p {
  margin: 2px 0;
}

.agent-logs {
  margin-top: 14px;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  background: var(--gray-50);
  border: 1px solid var(--border-light);
}

.agent-log-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--text-secondary);
  margin: 4px 0;
}

.agent-log-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--success);
}

.exam-list, .drug-list {
  display: grid;
  gap: 6px;
}

.exam-item, .drug-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
}

.exam-priority {
  padding: 1px 5px;
  border-radius: var(--radius-sm);
  font-size: 10px;
  font-weight: 700;
}

.exam-priority.priority-high {
  background: #FEE2E2;
  color: #B91C1C;
}

.exam-priority.priority-normal {
  background: #E0F2FE;
  color: #0369A1;
}

.exam-name, .drug-name {
  flex: 1;
  color: var(--text-secondary);
}

.drug-warning {
  color: var(--danger);
  font-size: 10px;
}

.text-button-sm {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px 8px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  color: var(--primary);
  font-size: 10px;
  cursor: pointer;
}

.text-button-sm:hover {
  background: var(--primary-soft);
}

.text-button-sm svg {
  width: 10px;
}

.warning-text {
  color: var(--danger);
}

.record-section ul {
  margin: 0;
  padding-left: 16px;
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.8;
}

.record-submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* ── 页面容器 ── */
.doctor-page {
  position: relative;
  padding-bottom: 20px;
}

/* ── 医生元信息 ── */
.doctor-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
}

.doctor-meta-date {
  display: grid;
  grid-template-columns: auto auto;
  column-gap: 10px;
  align-items: center;
  color: var(--text-tertiary);
  font-size: 11px;
  font-family: var(--font-mono);
}

.doctor-meta-date strong {
  color: var(--text-primary);
  font-size: 28px;
  font-weight: 800;
  letter-spacing: -0.06em;
  grid-row: span 2;
}

.doctor-meta-status {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: var(--radius-full);
  background: var(--success-light);
  color: var(--success);
  font-size: 10px;
  font-weight: 600;
}

.doctor-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--success);
}

/* ── 患者横幅 ── */
.patient-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 24px;
  margin-bottom: 20px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  background: var(--bg-surface);
  box-shadow: var(--shadow-card);
}

.patient-banner-main {
  display: flex;
  align-items: center;
  gap: 16px;
}

.patient-avatar-lg {
  width: 56px;
  height: 56px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 16px;
  background: linear-gradient(135deg, #60A5FA, #3B82F6);
  box-shadow: 0 6px 16px rgba(37, 99, 235, 0.25);
}

.patient-avatar-lg span {
  color: #fff;
  font-size: 20px;
  font-weight: 800;
}

.patient-info-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.patient-info-top h2 {
  margin: 0;
  font-size: 17px;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: -0.025em;
}

.patient-selector {
  padding: 5px 10px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  outline: none;
  max-width: 220px;
}

.patient-selector:focus {
  border-color: var(--border-focus);
  box-shadow: 0 0 0 3px rgba(147, 197, 253, 0.1);
}

.patient-selector:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.patient-info-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 6px;
  font-size: 11px;
  color: var(--text-tertiary);
}

.patient-info-meta b {
  color: var(--text-secondary);
  font-weight: 600;
}

.patient-warning,
.patient-warning b {
  color: var(--danger);
}

.patient-banner-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

/* ── 主网格 ── */
.doctor-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(340px, 0.9fr);
  gap: 20px;
  align-items: start;
}

.doctor-col-main {
  display: grid;
  gap: 20px;
}

/* ── 症状分析卡片 ── */
.analysis-card {
  padding: 22px 24px;
}

.symptom-editor {
  margin-top: 18px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--gray-50);
  transition: all var(--transition-fast);
}

.symptom-editor:focus-within {
  border-color: var(--border-focus);
  box-shadow: 0 0 0 3px rgba(147, 197, 253, 0.1);
  background: #fff;
}

.symptom-editor textarea {
  display: block;
  width: 100%;
  min-height: 120px;
  padding: 16px;
  border: 0;
  outline: 0;
  color: var(--text-primary);
  background: transparent;
  font-size: 13px;
  line-height: 1.8;
  resize: vertical;
}

.symptom-editor textarea::placeholder {
  color: var(--text-tertiary);
}

.symptom-editor-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-top: 1px solid var(--border-light);
  background: var(--bg-surface);
}

.symptom-editor-tools {
  display: flex;
  align-items: center;
  gap: 12px;
}

.mini-tool-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  background: var(--bg-surface);
  font-size: 11px;
  font-weight: 600;
  transition: all var(--transition-fast);
  cursor: pointer;
}

.mini-tool-btn:hover {
  border-color: var(--border-focus);
  color: var(--primary);
}

.mini-tool-btn svg {
  width: 14px;
}

.symptom-char-count {
  color: var(--text-tertiary);
  font-size: 10px;
  font-family: var(--font-mono);
}

.diagnose-btn {
  min-height: 38px;
  padding: 0 20px;
}

.loading-spin {
  animation: rotate 0.8s linear infinite;
}

@keyframes rotate {
  to { transform: rotate(360deg); }
}

/* 关键词建议 */
.keyword-suggestions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.keyword-suggestions > span {
  color: var(--text-tertiary);
  font-size: 11px;
  font-weight: 600;
}

.keyword-btn {
  padding: 5px 12px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-full);
  color: var(--primary);
  background: var(--primary-soft);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.keyword-btn:hover {
  border-color: var(--border-focus);
  background: var(--primary-light);
}

/* ── 诊断建议列表 ── */
.diagnosis-section {
  margin-top: 4px;
}

.diagnosis-note {
  color: var(--text-tertiary);
  font-size: 10px;
}

.diagnosis-list {
  display: grid;
  gap: 12px;
  margin-top: 16px;
}

.diagnosis-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  background: var(--bg-surface);
  cursor: pointer;
  transition: all var(--transition-base);
}

.diagnosis-card:hover {
  border-color: var(--border-focus);
  box-shadow: var(--shadow-md);
}

.diagnosis-card.selected {
  border-color: var(--primary);
  background: var(--primary-soft);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.08);
}

.diagnosis-card-main {
  display: flex;
  gap: 14px;
  flex: 1;
  min-width: 0;
}

.diagnosis-card-icon {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: var(--radius-md);
}

.diagnosis-card-icon svg {
  width: 20px;
}

.diagnosis-card-icon.tone-blue { background: #DBEAFE; color: #2563EB; }
.diagnosis-card-icon.tone-amber { background: #FEF3C7; color: #D97706; }
.diagnosis-card-icon.tone-violet { background: #EDE9FE; color: #7C3AED; }
.diagnosis-card-icon.tone-emerald { background: #D1FAE5; color: #059669; }
.diagnosis-card-icon.tone-rose { background: #FFE4E6; color: #E11D48; }

.diagnosis-card-info {
  flex: 1;
  min-width: 0;
}

.diagnosis-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.diagnosis-card-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}

.diagnosis-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.diagnosis-name-row h3 {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.primary-badge {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  box-shadow: 0 2px 6px rgba(99, 102, 241, 0.35);
}

.diagnosis-confidence {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 6px 12px;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
  min-width: 60px;
}

.diagnosis-confidence.tone-blue { background: #DBEAFE; }
.diagnosis-confidence.tone-amber { background: #FEF3C7; }
.diagnosis-confidence.tone-violet { background: #EDE9FE; }
.diagnosis-confidence.tone-emerald { background: #D1FAE5; }
.diagnosis-confidence.tone-rose { background: #FFE4E6; }

.diagnosis-confidence strong {
  font-size: 20px;
  font-weight: 800;
  color: var(--text-primary);
  line-height: 1;
}

.diagnosis-confidence strong small {
  font-size: 11px;
}

.diagnosis-confidence span {
  font-size: 9px;
  color: var(--text-tertiary);
  margin-top: 2px;
}

.diagnosis-card-info p {
  margin: 6px 0 10px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.diagnosis-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.diagnosis-tag {
  padding: 3px 8px;
  border-radius: var(--radius-full);
  background: var(--gray-100);
  color: var(--text-secondary);
  font-size: 10px;
  font-weight: 600;
}

.diagnosis-card-action {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  white-space: nowrap;
  transition: all var(--transition-fast);
}

.diagnosis-card.selected .diagnosis-card-action {
  color: var(--primary);
  background: rgba(37, 99, 235, 0.08);
}

.diagnosis-check-icon {
  width: 14px;
  color: var(--primary);
}

.diagnosis-card-action svg {
  width: 13px;
}

/* ── 病历预览面板 ── */
.record-panel {
  position: sticky;
  top: calc(var(--topbar-height) + 28px);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  background: var(--bg-surface);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}

.record-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px 16px;
  border-bottom: 1px solid var(--border-light);
}

.record-panel-header h2 {
  margin: 4px 0 0;
  font-size: 17px;
  font-weight: 800;
  color: var(--text-primary);
}

.record-content {
  padding: 8px 0;
}

.record-section {
  display: flex;
  gap: 14px;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-light);
}

.record-section:last-child {
  border-bottom: 0;
}

.record-section-icon {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: var(--radius-sm);
  background: var(--primary-soft);
}

.record-section-icon span {
  color: var(--primary);
  font-size: 12px;
  font-weight: 800;
}

.record-section h4 {
  margin: 0 0 6px;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-primary);
}

.record-section p {
  margin: 0;
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.8;
}

/* 体征检查 */
.record-signs {
  display: grid;
  gap: 6px;
}

.record-signs button {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  font-size: 11px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
  text-align: left;
}

.record-signs button:hover {
  border-color: var(--border-focus);
}

.record-signs button.checked {
  border-color: var(--success);
  background: var(--success-light);
  color: var(--success);
}

.record-signs button svg {
  width: 14px;
  flex-shrink: 0;
}

.record-signs button span {
  flex: 1;
}

.sign-confirmed {
  color: var(--success);
  width: 14px;
}

/* 影像 */
.record-imaging-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.record-imaging-header h4 {
  margin: 0;
}

.record-imaging-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.imaging-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 20px 12px;
  border: 2px dashed var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-tertiary);
  transition: all var(--transition-fast);
  cursor: pointer;
}

.imaging-placeholder:hover {
  border-color: var(--border-focus);
  background: var(--primary-soft);
}

.imaging-placeholder svg {
  width: 24px;
}

.imaging-placeholder small {
  font-size: 10px;
}

/* 病历底部 */
.record-footer {
  padding: 16px 24px;
  border-top: 1px solid var(--border-light);
}

.record-submit {
  width: 100%;
  min-height: 42px;
}

/* ── AI 状态浮动条 ── */
.ai-status-bar {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 20px;
  border: 1px solid rgba(147, 197, 253, 0.3);
  border-radius: var(--radius-full);
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(12px);
  box-shadow: var(--shadow-lg);
  font-size: 12px;
  color: var(--text-secondary);
}

.ai-status-avatar {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: linear-gradient(135deg, #60A5FA, #3B82F6);
}

.ai-status-avatar svg {
  width: 15px;
  color: #fff;
}

.ai-status-dots {
  display: flex;
  gap: 4px;
}

.ai-status-dots span {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--primary);
  animation: blink 1.4s ease-in-out infinite;
}

.ai-status-dots span:nth-child(2) { animation-delay: 0.2s; }
.ai-status-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes blink {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; transform: translateY(-2px); }
}

/* ── 响应式 ── */
@media (max-width: 1150px) {
  .doctor-grid {
    grid-template-columns: 1fr;
  }

  .record-panel {
    position: static;
  }

  .ai-status-bar {
    display: none;
  }
}

@media (max-width: 650px) {
  .patient-banner {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .patient-banner-actions {
    width: 100%;
  }

  .patient-banner-actions .ghost-button {
    display: none;
  }

  .patient-banner-actions .primary-button {
    width: 100%;
    justify-content: center;
  }

  .patient-info-meta {
    gap: 4px 12px;
  }

  .diagnosis-card {
    flex-direction: column;
  }

  .diagnosis-card-action {
    align-self: flex-end;
  }

  .record-imaging-grid {
    grid-template-columns: 1fr;
  }
}

/* ── 语音录入按钮动画 ── */
.ghost-button.is-recording {
  color: #DC2626;
  border-color: #DC2626;
  animation: mic-pulse 1.2s ease-in-out infinite;
}
@keyframes mic-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.4); }
  50%      { box-shadow: 0 0 0 6px rgba(220, 38, 38, 0); }
}
</style>
