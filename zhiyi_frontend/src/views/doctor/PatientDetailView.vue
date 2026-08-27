<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import { getPatientProfile, getDiagnosisHistory } from '@/api'

const route = useRoute()
const router = useRouter()
const patientId = computed(() => Number(route.params.id))

const profile = ref<any>(null)
const diagnoses = ref<any[]>([])
const loading = ref(true)

const errorMsg = ref('')

onMounted(async () => {
  loading.value = true
  errorMsg.value = ''

  // 分别加载（一个失败不影响另一个）
  try { profile.value = await getPatientProfile(patientId.value) }
  catch { errorMsg.value = '患者档案加载失败' }

  try {
    const d = await getDiagnosisHistory(patientId.value)
    diagnoses.value = Array.isArray(d) ? d : []
  } catch {
    // 诊断历史加载失败不阻塞档案显示
  }

  loading.value = false
})

const diagnosisName = (d: any) =>
  d.final_diagnosis || d.suggestions?.[0]?.name || 'AI 辅助诊断'
</script>

<template>
  <div class="pdp-root">
    <!-- 顶部导航 -->
    <div class="pdp-nav">
      <button class="pdp-back" @click="router.push('/doctor/records')">
        <ArrowLeft /> 返回患者列表
      </button>
    </div>

    <!-- 加载态 -->
    <div v-if="loading" class="pdp-skeleton">
      <div class="skel-hero" />
      <div class="skel-grid"><span /><span /><span /><span /></div>
      <div class="skel-line" />
    </div>

    <template v-else-if="profile">
      <!-- 患者横幅 -->
      <section class="pdp-hero">
        <div class="pdp-hero-bg" />
        <div class="pdp-hero-inner">
          <div class="pdp-avatar-wrap">
            <div class="pdp-avatar">{{ profile.name?.charAt(0) || '患' }}</div>
            <div class="pdp-avatar-ring" />
          </div>
          <div class="pdp-hero-text">
            <h1>{{ profile.name }}</h1>
            <div class="pdp-hero-chips">
              <span class="pdp-chip sex">{{ profile.gender === 'M' ? '♂ 男' : '♀ 女' }} · {{ profile.age }} 岁</span>
              <span class="pdp-chip id">病案号 P{{ String(patientId).padStart(8, '0') }}</span>
            </div>
          </div>
          <button class="pdp-btn-primary" @click="router.push({ path: '/doctor/diagnosis', query: { patientId: String(patientId) } })">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
            前往诊疗
          </button>
        </div>
      </section>

      <!-- 卡片网格 -->
      <div class="pdp-grid">
        <!-- 过敏史 -->
        <div class="pdp-card allergy">
          <div class="pdp-card-icon allergy-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
          </div>
          <h3>过敏史</h3>
          <div class="pdp-tags" v-if="profile.allergies?.length">
            <span v-for="a in profile.allergies" :key="a" class="pdp-tag danger">{{ a }}</span>
          </div>
          <p v-else class="pdp-none">无已知过敏史</p>
        </div>

        <!-- 既往病史 -->
        <div class="pdp-card history">
          <div class="pdp-card-icon history-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
            </svg>
          </div>
          <h3>既往病史</h3>
          <div class="pdp-tags" v-if="profile.past_history?.length">
            <span v-for="h in profile.past_history" :key="h" class="pdp-tag warn">{{ h }}</span>
          </div>
          <p v-else class="pdp-none">无记录</p>
        </div>

        <!-- 家族病史 -->
        <div class="pdp-card family">
          <div class="pdp-card-icon family-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
            </svg>
          </div>
          <h3>家族病史</h3>
          <div class="pdp-tags" v-if="profile.family_history?.length">
            <span v-for="f in profile.family_history" :key="f" class="pdp-tag purple">{{ f }}</span>
          </div>
          <p v-else class="pdp-none">无记录</p>
        </div>

        <!-- 生活方式 -->
        <div class="pdp-card lifestyle" v-if="profile.lifestyle && Object.keys(profile.lifestyle).length">
          <div class="pdp-card-icon lifestyle-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>
            </svg>
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

      <!-- 诊断时间线 -->
      <section class="pdp-timeline">
        <div class="pdp-timeline-head">
          <h2>诊断历史</h2>
          <span class="pdp-count">{{ diagnoses.length }} 条记录</span>
        </div>

        <div v-if="!diagnoses.length" class="pdp-none" style="padding:32px 0">暂无诊断记录</div>

        <div v-for="(d, i) in diagnoses" :key="d.id" class="tl-item" :style="{ animationDelay: `${i * 0.06}s` }">
          <div class="tl-dot-wrap">
            <div class="tl-dot" />
            <div class="tl-line" />
          </div>
          <div class="tl-card">
            <div class="tl-card-top">
              <strong>{{ diagnosisName(d) }}</strong>
              <span class="tl-date">{{ (d.created_at || d.generated_at || '').slice(0, 16) }}</span>
            </div>
            <p class="tl-symptoms" v-if="d.symptoms">主诉：{{ d.symptoms }}</p>
            <div class="tl-extract" v-if="d.extracted_symptoms?.length">
              <span v-for="s in (Array.isArray(d.extracted_symptoms) ? d.extracted_symptoms.slice(0, 6) : [])" :key="s" class="pdp-tag sm blue">{{ s }}</span>
            </div>
          </div>
        </div>
      </section>
    </template>

    <div v-else class="pdp-skeleton">未找到该患者的档案信息</div>
  </div>
</template>

<style scoped>
/* ── variables ── */
.pdp-root { max-width: 960px; margin: 0 auto; padding: 20px 24px 40px; }

/* nav */
.pdp-nav { margin-bottom: 20px; }
.pdp-back {
  display: inline-flex; align-items: center; gap: 6px; background: none; border: none;
  color: var(--text-secondary); font-size: 13px; cursor: pointer; padding: 6px 0;
  transition: color .2s;
}
.pdp-back:hover { color: var(--primary); }

/* skeleton shimmer */
.pdp-skeleton { display: flex; flex-direction: column; gap: 20px; padding: 12px 0; }
.skel-hero { height: 88px; border-radius: 14px; background: linear-gradient(90deg, #f0f2f5 25%, #e4e7ec 50%, #f0f2f5 75%); background-size: 200% 100%; animation: shimmer 1.4s infinite; }
.skel-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.skel-grid span { height: 120px; border-radius: 14px; background: linear-gradient(90deg, #f0f2f5 25%, #e4e7ec 50%, #f0f2f5 75%); background-size: 200% 100%; animation: shimmer 1.4s infinite; }
.skel-line { height: 200px; border-radius: 14px; background: linear-gradient(90deg, #f0f2f5 25%, #e4e7ec 50%, #f0f2f5 75%); background-size: 200% 100%; animation: shimmer 1.4s infinite; }
@keyframes shimmer { 0% { background-position: 200% 0 } 100% { background-position: -200% 0 } }

/* hero */
.pdp-hero {
  position: relative; border-radius: 16px; overflow: hidden; margin-bottom: 24px;
  background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 50%, #7c3aed 100%);
}
.pdp-hero-bg {
  position: absolute; inset: 0; opacity: .12;
  background: radial-gradient(circle at 20% 50%, #fff 0%, transparent 60%),
              radial-gradient(circle at 80% 30%, #60a5fa 0%, transparent 50%);
  animation: hero-glow 4s ease-in-out infinite alternate;
}
@keyframes hero-glow {
  0% { opacity: .08; transform: scale(1) }
  100% { opacity: .18; transform: scale(1.05) }
}
.pdp-hero-inner {
  position: relative; z-index: 1; display: flex; align-items: center; gap: 18px;
  padding: 28px 32px; flex-wrap: wrap;
}
.pdp-avatar-wrap { position: relative; flex-shrink: 0; }
.pdp-avatar {
  width: 64px; height: 64px; border-radius: 50%; background: rgba(255,255,255,.18);
  display: flex; align-items: center; justify-content: center;
  font-size: 28px; font-weight: 700; color: #fff; backdrop-filter: blur(8px);
}
.pdp-avatar-ring {
  position: absolute; inset: -4px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.25);
  animation: ring-pulse 2.5s ease-in-out infinite;
}
@keyframes ring-pulse {
  0%, 100% { border-color: rgba(255,255,255,.2); transform: scale(1) }
  50%      { border-color: rgba(255,255,255,.45); transform: scale(1.06) }
}
.pdp-hero-text h1 { margin: 0 0 4px; font-size: 24px; color: #fff; font-weight: 700; }
.pdp-hero-chips { display: flex; gap: 8px; flex-wrap: wrap; }
.pdp-chip {
  display: inline-block; padding: 3px 12px; border-radius: 20px; font-size: 12px;
  font-weight: 500; backdrop-filter: blur(8px);
}
.pdp-chip.sex { background: rgba(255,255,255,.18); color: #e0f2fe; }
.pdp-chip.id { background: rgba(255,255,255,.12); color: #cbd5e1; }

.pdp-btn-primary {
  margin-left: auto; display: inline-flex; align-items: center; gap: 6px;
  padding: 10px 22px; border: none; border-radius: 10px;
  background: rgba(255,255,255,.18); color: #fff; font-size: 14px; font-weight: 600;
  cursor: pointer; backdrop-filter: blur(4px); transition: all .25s;
}
.pdp-btn-primary:hover { background: rgba(255,255,255,.28); transform: translateY(-1px); }

/* card grid */
.pdp-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }

.pdp-card {
  position: relative; border-radius: 14px; padding: 22px 22px 18px;
  background: #fff; border: 1px solid var(--border-light, #e8ecf1);
  transition: transform .2s, box-shadow .2s; overflow: hidden;
}
.pdp-card::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
}
.pdp-card.allergy::before { background: linear-gradient(90deg, #ef4444, #f97316); }
.pdp-card.history::before { background: linear-gradient(90deg, #f59e0b, #eab308); }
.pdp-card.family::before  { background: linear-gradient(90deg, #8b5cf6, #a855f7); }
.pdp-card.lifestyle::before { background: linear-gradient(90deg, #10b981, #34d399); }

.pdp-card:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,.06); }

.pdp-card-icon {
  width: 38px; height: 38px; border-radius: 10px; display: flex; align-items: center;
  justify-content: center; margin-bottom: 12px;
}
.pdp-card-icon svg { width: 20px; height: 20px; }
.allergy-icon { background: #fef2f2; color: #ef4444; }
.history-icon { background: #fffbeb; color: #f59e0b; }
.family-icon { background: #f5f3ff; color: #8b5cf6; }
.lifestyle-icon { background: #ecfdf5; color: #10b981; }

.pdp-card h3 { margin: 0 0 12px; font-size: 14px; font-weight: 600; color: var(--text-primary); }

.pdp-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.pdp-tag {
  display: inline-block; padding: 4px 12px; border-radius: 6px; font-size: 12px; font-weight: 500;
}
.pdp-tag.danger { background: #fef2f2; color: #dc2626; }
.pdp-tag.warn   { background: #fffbeb; color: #d97706; }
.pdp-tag.purple { background: #f5f3ff; color: #7c3aed; }
.pdp-tag.blue   { background: #eff6ff; color: #2563eb; }
.pdp-tag.sm { padding: 2px 8px; font-size: 11px; }

.pdp-none { color: var(--text-tertiary); font-size: 13px; margin: 0; }

.lifestyle .pdp-lifestyle-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.pdp-life-item { display: flex; flex-direction: column; gap: 2px; }
.pdp-life-key { font-size: 10px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: .04em; }
.pdp-life-val { font-size: 13px; color: var(--text-primary); font-weight: 500; }

/* timeline */
.pdp-timeline { border-radius: 14px; background: #fff; border: 1px solid var(--border-light, #e8ecf1); padding: 24px 28px; }
.pdp-timeline-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 22px; }
.pdp-timeline-head h2 { margin: 0; font-size: 18px; font-weight: 700; }
.pdp-count { font-size: 13px; color: var(--text-tertiary); }

.tl-item {
  display: flex; gap: 16px; padding-bottom: 0;
  animation: tl-in .45s ease-out both;
}
@keyframes tl-in { from { opacity: 0; transform: translateX(-8px) } to { opacity: 1; transform: translateX(0) } }

.tl-dot-wrap { display: flex; flex-direction: column; align-items: center; flex-shrink: 0; width: 20px; }
.tl-dot {
  width: 12px; height: 12px; border-radius: 50%; background: var(--primary);
  box-shadow: 0 0 0 4px rgba(37,99,235,.12);
  animation: dot-breathe 2s ease-in-out infinite; flex-shrink: 0; margin-top: 5px;
}
@keyframes dot-breathe {
  0%, 100% { box-shadow: 0 0 0 4px rgba(37,99,235,.12) }
  50%      { box-shadow: 0 0 0 8px rgba(37,99,235,.04) }
}
.tl-line { width: 2px; flex: 1; min-height: 16px; background: linear-gradient(180deg, var(--primary), #e0e7ff); }
.tl-item:last-child .tl-line { background: transparent; }

.tl-card {
  flex: 1; background: #f8fafc; border-radius: 10px; padding: 14px 16px;
  margin-bottom: 14px; border: 1px solid #eef2f6;
  transition: border-color .2s, box-shadow .2s;
}
.tl-card:hover { border-color: #c7d2fe; box-shadow: 0 2px 8px rgba(37,99,235,.06); }
.tl-card-top { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; flex-wrap: wrap; gap: 4px; }
.tl-card-top strong { font-size: 14px; color: var(--text-primary); }
.tl-date { font-size: 11px; color: var(--text-tertiary); white-space: nowrap; }
.tl-symptoms { margin: 0 0 8px; font-size: 13px; color: var(--text-secondary); line-height: 1.5; }
.tl-extract { display: flex; flex-wrap: wrap; gap: 4px; }

@media (max-width: 640px) {
  .pdp-grid { grid-template-columns: 1fr; }
  .pdp-hero-inner { flex-direction: column; align-items: flex-start; }
  .pdp-btn-primary { margin-left: 0; }
  .tl-card-top { flex-direction: column; }
}
</style>
