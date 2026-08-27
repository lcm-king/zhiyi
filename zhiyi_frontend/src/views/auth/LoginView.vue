<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import type { Component } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowRight, CircleCheck, FirstAidKit, Lock, MagicStick, Message, Phone, Promotion, User, DataAnalysis, ChatLineSquare } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { roleHome } from '@/router'
import type { UserRole } from '@/types'

type LoginMode = 'sms' | 'password'

const router = useRouter()
const auth = useAuthStore()
const activeRole = ref<UserRole>('doctor')
const mode = ref<'login' | 'register'>('login')
const loginMode = ref<LoginMode>('sms')
const logging = ref(false)
const agreement = ref(false)
const phone = ref('')
const username = ref('')
const captcha = ref('')
const smsCode = ref('')
const password = ref('')
const confirmPassword = ref('')
const countdown = ref(0)
let countdownTimer: number | undefined

const roleOptions: Array<{ key: UserRole; label: string; hint: string; desc: string }> = [
  { key: 'doctor', label: '医生', hint: '智能诊疗工作台', desc: 'AI 辅助诊断，让基层医生拥有三甲医院级别的诊断能力' },
  { key: 'patient', label: '患者', hint: '健康服务中心', desc: '检查预约、在线购药、报告解读与健康档案一站式服务' },
  { key: 'admin', label: '管理员', hint: '平台运营中心', desc: '医生管理、药品目录维护、订单发货与数据运营' },
]
const roleIcons: Record<UserRole, Component> = { doctor: FirstAidKit, patient: User, admin: DataAnalysis }
const activeOption = computed(() => roleOptions.find((item) => item.key === activeRole.value) || roleOptions[0])
const captchaCode = ref('A7K9')

function refreshCaptcha() {
  captchaCode.value = `${String.fromCharCode(65 + Math.floor(Math.random() * 26))}${Math.floor(100 + Math.random() * 900)}`
}
function switchRole(role: UserRole) { activeRole.value = role; refreshCaptcha() }
async function sendSmsCode() {
  if (!/^1\d{10}$/.test(phone.value)) return ElMessage.warning('请输入正确的 11 位手机号')
  if (countdown.value > 0) return
  try {
    const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'
    const resp = await fetch(`${apiBase}/sms/send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: phone.value }),
    })
    const data = await resp.json()
    if (!resp.ok) throw new Error(parseApiError(data, '发送失败'))
    ElMessage.success(data.message || '验证码已发送')
    countdown.value = 60
    countdownTimer = window.setInterval(() => {
      countdown.value--
      if (countdown.value <= 0) window.clearInterval(countdownTimer)
    }, 1000)
    if (data.code) {
      smsCode.value = data.code
      ElMessage.info('演示环境：验证码已自动填入')
    }
  } catch (e: any) {
    ElMessage.error(e.message || '发送验证码失败')
  }
}
function parseApiError(err: any, fallback: string): string {
  if (typeof err === 'string') return err
  const detail = err?.detail
  // FastAPI 422 验证错误：detail 是数组 [{msg, loc, type}, ...]
  if (Array.isArray(detail)) {
    const msgs = detail.map((d: any) => {
      const field = (d.loc || []).slice(-1)[0] || '字段'
      return `${field}: ${d.msg}`
    })
    return msgs.join('; ')
  }
  // 普通错误：detail 是字符串
  if (typeof detail === 'string') return detail
  return fallback
}

function validateAgreement(): boolean {
  if (!agreement.value) { ElMessage.warning('请先同意服务协议和隐私政策'); return false }
  if (!/^1\d{10}$/.test(phone.value)) { ElMessage.warning('请输入正确的 11 位手机号'); return false }
  if (mode.value === 'register') {
    if (!username.value.trim()) { ElMessage.warning('请输入用户名'); return false }
    if (!smsCode.value || smsCode.value.length < 4) { ElMessage.warning('请输入短信验证码'); return false }
    if (password.value !== confirmPassword.value) { ElMessage.warning('两次输入的密码不一致'); return false }
    if (password.value.length < 8 || password.value.length > 20) { ElMessage.warning('密码长度需要 8-20 位'); return false }
  }
  return true
}
async function submitForm() {
  if (!validateAgreement()) return
  logging.value = true
  if (mode.value === 'register') {
    try {
      const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'
      // 1. 先校验短信验证码
      if (loginMode.value === 'sms') {
        const vResp = await fetch(`${apiBase}/sms/verify`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ phone: phone.value, code: smsCode.value }),
        })
        if (!vResp.ok) {
          const err = await vResp.json()
          throw new Error(parseApiError(err, '验证码校验失败'))
        }
      }
      // 2. 调用真实注册接口
      const regResp = await fetch(`${apiBase}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: username.value.trim(),
          phone: phone.value,
          password: password.value,
          role: activeRole.value,
        }),
      })
      if (!regResp.ok) {
        const err = await regResp.json()
        throw new Error(parseApiError(err, '注册失败'))
      }
      ElMessage.success('注册成功，正在登录…')
      // 3. 注册成功后自动登录
      const loginResp = await fetch(`${apiBase}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: phone.value, password: password.value }),
      })
      const loginData = await loginResp.json()
      if (!loginResp.ok) throw new Error(parseApiError(loginData, '自动登录失败'))
      localStorage.setItem('zhiyi-token', loginData.access_token)
      localStorage.setItem('zhiyi-role', activeRole.value)
      localStorage.setItem('zhiyi-user', JSON.stringify({ id: loginData.user_id || 0, name: phone.value, role: activeRole.value }))
      await router.push(roleHome[activeRole.value])
      ElMessage.success('欢迎加入智医')
    } catch (e: any) {
      ElMessage.error(e.message || '注册失败')
    } finally {
      logging.value = false
    }
    return
  }

  // 登录：SMS 验证码登录
  if (loginMode.value === 'sms') {
    try {
      if (!smsCode.value || smsCode.value.length < 4) {
        ElMessage.warning('请输入短信验证码')
        return
      }
      const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'
      const resp = await fetch(`${apiBase}/auth/sms-login?role=${activeRole.value}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: phone.value, code: smsCode.value }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(parseApiError(data, '登录失败'))
      localStorage.setItem('zhiyi-token', data.access_token)
      localStorage.setItem('zhiyi-role', activeRole.value)
      localStorage.setItem('zhiyi-user', JSON.stringify({ id: data.user_id, name: data.name, role: data.role }))
      await router.push(roleHome[activeRole.value])
      ElMessage.success(`欢迎，${data.name}`)
    } catch (e: any) {
      ElMessage.error(e.message || '登录失败')
    } finally {
      logging.value = false
    }
    return
  }

  // 登录：密码登录
  try {
    const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'
    const resp = await fetch(`${apiBase}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: phone.value, password: password.value }),
    })
    const data = await resp.json()
    if (!resp.ok) throw new Error(parseApiError(data, '登录失败'))
    localStorage.setItem('zhiyi-token', data.access_token)
    localStorage.setItem('zhiyi-role', activeRole.value)
    localStorage.setItem('zhiyi-user', JSON.stringify({ id: data.user_id || 0, name: phone.value, role: activeRole.value }))
    await router.push(roleHome[activeRole.value])
    ElMessage.success('登录成功')
    logging.value = false
    return
  } catch (e: any) {
    ElMessage.error(e.message || '登录失败')
    logging.value = false
  }
}

/** 演示登录 */
async function demoLogin() {
  logging.value = true
  try {
    await auth.signIn(activeRole.value)
    await router.push(roleHome[activeRole.value])
    ElMessage.success(`欢迎进入${activeOption.value.label}工作台`)
  } catch {
    ElMessage.error('后端服务未启动，请先运行 docker compose up -d')
  } finally {
    logging.value = false
  }
}
function showMessage(message: string) { ElMessage.info(message) }
onUnmounted(() => { if (countdownTimer) window.clearInterval(countdownTimer) })
</script>

<template>
  <div class="auth-page">
    <!-- 装饰背景 -->
    <div class="auth-bg">
      <div class="auth-bg-orb orb-1" />
      <div class="auth-bg-orb orb-2" />
      <div class="auth-bg-orb orb-3" />
      <div class="auth-bg-grid" />
    </div>

    <section class="auth-card">
      <!-- 左侧品牌展示区 -->
      <aside class="auth-brand">
        <div class="auth-brand-inner">
          <!-- Logo -->
          <div class="auth-logo">
            <div class="auth-logo-mark">智</div>
            <div>
              <div class="auth-logo-name">智医平台</div>
              <div class="auth-logo-sub">基层医疗 AI 辅助诊疗平台</div>
            </div>
          </div>

          <!-- 品牌标语 -->
          <div class="auth-brand-hero">
            <div class="auth-brand-badge">
              <CircleCheck /> 智慧医疗服务
            </div>
            <h1>让基层医疗<br /><em>更有温度</em></h1>
            <p>连接医生、患者与医疗服务，让每一次诊疗都有清晰依据，让每一份健康记录都值得信赖。</p>
          </div>

          <!-- 特性 -->
          <div class="auth-features">
            <div class="auth-feature-item">
              <div class="auth-feature-icon"><FirstAidKit /></div>
              <div>
                <strong>AI 智能辅助</strong>
                <span>多 Agent 协同诊断</span>
              </div>
            </div>
            <div class="auth-feature-item">
              <div class="auth-feature-icon"><Lock /></div>
              <div>
                <strong>数据安全保护</strong>
                <span>医疗级加密存储</span>
              </div>
            </div>
            <div class="auth-feature-item">
              <div class="auth-feature-icon"><ChatLineSquare /></div>
              <div>
                <strong>协同诊疗服务</strong>
                <span>全流程闭环管理</span>
              </div>
            </div>
          </div>

          <!-- 系统状态 -->
          <div class="auth-status">
            <span class="auth-status-dot" />
            所有核心服务正常运行
            <b>演示环境</b>
          </div>
        </div>

        <!-- 装饰环 -->
        <div class="auth-decor-ring ring-large" />
        <div class="auth-decor-ring ring-small" />
      </aside>

      <!-- 右侧表单区 -->
      <main class="auth-form-panel">
        <div class="auth-form-wrap">
          <!-- 角色选择 -->
          <div class="auth-role-tabs">
            <button
              v-for="item in roleOptions"
              :key="item.key"
              :class="{ active: activeRole === item.key }"
              @click="switchRole(item.key)"
            >
              <component :is="roleIcons[item.key]" />
              <span>{{ item.label }}</span>
            </button>
          </div>

          <!-- 表单标题 -->
          <div class="auth-header">
            <span class="auth-header-kicker">{{ mode === 'register' ? '创建账号' : '安全登录' }}</span>
            <h2>{{ mode === 'register' ? '注册智医账号' : '手机号快捷登录' }}</h2>
            <p>{{ activeOption.desc }}</p>
          </div>

          <!-- 表单 -->
          <form class="auth-form" @submit.prevent="submitForm">
            <!-- 手机号 -->
            <div class="auth-form-group">
              <label><Phone /> 手机号码</label>
              <div class="auth-input-box">
                <Phone />
                <input
                  v-model="phone"
                  type="tel"
                  maxlength="11"
                  placeholder="请输入 11 位手机号"
                  autocomplete="tel"
                />
              </div>
            </div>

            <!-- 图形验证码 -->
            <div v-if="mode === 'login' && loginMode === 'sms'" class="auth-form-group">
              <label><Message /> 图形验证码</label>
              <div class="auth-input-row">
                <div class="auth-input-box">
                  <Message />
                  <input v-model="captcha" maxlength="4" placeholder="请输入验证码" />
                </div>
                <button type="button" class="auth-captcha-btn" @click="refreshCaptcha">
                  <strong>{{ captchaCode }}</strong>
                  <small>点击刷新</small>
                </button>
              </div>
            </div>

            <!-- 短信验证码 (登录) -->
            <div v-if="mode === 'login' && loginMode === 'sms'" class="auth-form-group">
              <label><Promotion /> 短信验证码</label>
              <div class="auth-input-row">
                <div class="auth-input-box">
                  <Promotion />
                  <input v-model="smsCode" maxlength="6" placeholder="请输入 6 位验证码" />
                </div>
                <button
                  type="button"
                  class="auth-sms-btn"
                  :disabled="Boolean(countdown)"
                  @click="sendSmsCode"
                >
                  {{ countdown ? `${countdown}s 后重发` : '获取验证码' }}
                </button>
              </div>
            </div>

            <!-- 密码 (密码登录) -->
            <div v-if="mode === 'login' && loginMode === 'password'" class="auth-form-group">
              <label><Lock /> 登录密码</label>
              <div class="auth-input-box">
                <Lock />
                <input
                  v-model="password"
                  type="password"
                  placeholder="请输入登录密码"
                  autocomplete="current-password"
                />
              </div>
            </div>

            <!-- 注册表单 -->
            <template v-if="mode === 'register'">
              <div class="auth-form-group">
                <label><User /> 用户名</label>
                <div class="auth-input-box">
                  <User />
                  <input
                    v-model="username"
                    type="text"
                    maxlength="20"
                    placeholder="请输入您的姓名"
                    autocomplete="name"
                  />
                </div>
              </div>
              <div class="auth-form-group">
                <label><Lock /> 设置密码</label>
                <div class="auth-input-box">
                  <Lock />
                  <input
                    v-model="password"
                    type="password"
                    placeholder="8-20 位字母、数字或符号"
                    autocomplete="new-password"
                  />
                </div>
              </div>
              <div class="auth-form-group">
                <label><Lock /> 确认密码</label>
                <div class="auth-input-box">
                  <Lock />
                  <input
                    v-model="confirmPassword"
                    type="password"
                    placeholder="请再次输入密码"
                    autocomplete="new-password"
                  />
                </div>
              </div>
              <div class="auth-form-group">
                <label><Promotion /> 短信验证码</label>
                <div class="auth-input-row">
                  <div class="auth-input-box">
                    <Promotion />
                    <input v-model="smsCode" maxlength="6" placeholder="请输入验证码" />
                  </div>
                  <button
                    type="button"
                    class="auth-sms-btn"
                    :disabled="Boolean(countdown)"
                    @click="sendSmsCode"
                  >
                    {{ countdown ? `${countdown}s 后重发` : '获取验证码' }}
                  </button>
                </div>
              </div>
            </template>

            <!-- 协议 -->
            <label class="auth-agreement">
              <input v-model="agreement" type="checkbox" />
              <span>
                我已阅读并同意
                <a href="#" @click.prevent="showMessage('服务协议将在后端接入后展示')">《智医平台服务协议》</a>
                和
                <a href="#" @click.prevent="showMessage('隐私政策将在后端接入后展示')">《用户隐私权政策》</a>
              </span>
            </label>

            <!-- 提交按钮 -->
            <button class="auth-submit" type="submit" :disabled="logging">
              <span v-if="logging" class="auth-spinner" />
              <template v-else>
                {{ mode === 'register' ? '注册并开始使用' : '登录' }}
                <ArrowRight />
              </template>
              <template v-if="logging">
                {{ mode === 'register' ? '正在创建账号…' : '正在安全登录…' }}
              </template>
            </button>
          </form>

          <!-- 底部链接 -->
          <div class="auth-links">
            <button
              v-if="mode === 'login'"
              class="auth-link-btn"
              @click="loginMode = loginMode === 'sms' ? 'password' : 'sms'"
            >
              {{ loginMode === 'sms' ? '账号密码登录' : '手机号快捷登录' }}
            </button>
            <button v-else class="auth-link-btn" @click="mode = 'login'">
              返回登录
            </button>
            <span class="auth-link-divider">|</span>
            <button
              class="auth-link-btn"
              @click="mode = mode === 'login' ? 'register' : 'login'"
            >
              {{ mode === 'login' ? '注册新账号' : '已有账号，去登录' }}
            </button>
          </div>

          <!-- 演示登录直达 -->
          <button class="auth-demo-btn" type="button" :disabled="logging" @click="demoLogin">
            <MagicStick />
            {{ logging ? '登录中…' : `演示登录 · ${activeOption.label}` }}
          </button>

          <!-- 演示提示 -->
          <div class="auth-demo-tip">
            <CircleCheck />
            演示环境，点击上方按钮直接登录，无需输入手机号和验证码
          </div>
        </div>
      </main>
    </section>

    <!-- 页脚 -->
    <footer class="auth-footer">
      © 2026 智医 · 基层医疗全流程服务平台 · 数据仅用于产品演示
    </footer>
  </div>
</template>

<style scoped>
/* ── 页面容器 ── */
.auth-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;
  z-index: 1;
  overflow: hidden;
  padding: 32px 20px;
  background: transparent;
}

/* ── 背景装饰 ── */
.auth-bg {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}

.auth-bg-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.4;
}

.orb-1 {
  width: 500px;
  height: 500px;
  top: -15%;
  right: -10%;
  background: radial-gradient(circle, rgba(59, 130, 246, 0.25), transparent 70%);
}

.orb-2 {
  width: 400px;
  height: 400px;
  bottom: -20%;
  left: -8%;
  background: radial-gradient(circle, rgba(13, 148, 136, 0.2), transparent 70%);
}

.orb-3 {
  width: 300px;
  height: 300px;
  top: 40%;
  left: 45%;
  background: radial-gradient(circle, rgba(99, 102, 241, 0.15), transparent 70%);
}

.auth-bg-grid {
  position: absolute;
  inset: 0;
  opacity: 0.03;
  background-image:
    linear-gradient(var(--gray-400) 1px, transparent 1px),
    linear-gradient(90deg, var(--gray-400) 1px, transparent 1px);
  background-size: 60px 60px;
}

/* ── 登录卡片 ── */
.auth-card {
  width: min(1120px, 100%);
  min-height: 660px;
  display: grid;
  grid-template-columns: minmax(380px, 0.85fr) minmax(480px, 1.15fr);
  position: relative;
  z-index: 1;
  overflow: hidden;
  border-radius: var(--radius-2xl);
  background: var(--bg-surface);
  box-shadow: var(--shadow-xl), 0 0 0 1px var(--border-default);
}

/* ── 左侧品牌区 ── */
.auth-brand {
  position: relative;
  overflow: hidden;
  background: linear-gradient(160deg, #0F2942 0%, #0B1F33 40%, #081829 70%, #061220 100%);
  color: #E8F1FC;
}

.auth-brand::before {
  content: '';
  position: absolute;
  top: -30%;
  right: -30%;
  width: 500px;
  height: 500px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(59, 130, 246, 0.25), transparent 60%);
  pointer-events: none;
}

.auth-brand::after {
  content: '';
  position: absolute;
  inset: 0;
  opacity: 0.06;
  background-image:
    linear-gradient(rgba(147, 197, 253, 0.5) 1px, transparent 1px),
    linear-gradient(90deg, rgba(147, 197, 253, 0.5) 1px, transparent 1px);
  background-size: 40px 40px;
  mask-image: linear-gradient(180deg, #000 40%, transparent 100%);
}

.auth-brand-inner {
  position: relative;
  z-index: 1;
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 48px 44px;
}

.auth-logo {
  display: flex;
  align-items: center;
  gap: 12px;
}

.auth-logo-mark {
  width: 46px;
  height: 46px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 14px;
  font-size: 22px;
  font-weight: 800;
  color: #fff;
  background: linear-gradient(135deg, #60A5FA, #3B82F6, #2563EB);
  box-shadow: 0 8px 24px rgba(37, 99, 235, 0.4);
}

.auth-logo-name {
  font-size: 21px;
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1.1;
}

.auth-logo-sub {
  margin-top: 2px;
  font-size: 10px;
  color: #6B9CC9;
  letter-spacing: 0.03em;
}

.auth-brand-hero {
  margin-top: auto;
  margin-bottom: 40px;
}

.auth-brand-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border: 1px solid rgba(147, 197, 253, 0.25);
  border-radius: var(--radius-full);
  font-size: 10px;
  font-weight: 700;
  color: #93C5FD;
  letter-spacing: 0.04em;
}

.auth-brand-badge svg {
  width: 13px;
  color: #34D399;
}

.auth-brand-hero h1 {
  margin: 20px 0 16px;
  font-size: clamp(36px, 4vw, 50px);
  line-height: 1.12;
  letter-spacing: -0.06em;
  font-weight: 800;
  color: #fff;
}

.auth-brand-hero h1 em {
  font-style: normal;
  background: linear-gradient(135deg, #60A5FA, #93C5FD);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.auth-brand-hero p {
  max-width: 340px;
  font-size: 12px;
  line-height: 1.8;
  color: #7DA1C7;
}

.auth-features {
  display: grid;
  gap: 14px;
  margin-bottom: 36px;
}

.auth-feature-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.auth-feature-icon {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: var(--radius-md);
  background: rgba(59, 130, 246, 0.15);
  border: 1px solid rgba(147, 197, 253, 0.15);
}

.auth-feature-icon svg {
  width: 17px;
  color: #60A5FA;
}

.auth-feature-item strong {
  display: block;
  font-size: 12px;
  font-weight: 700;
  color: #C8DDF5;
}

.auth-feature-item span {
  font-size: 10px;
  color: #6B9CC9;
}

.auth-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border: 1px solid rgba(147, 197, 253, 0.12);
  border-radius: var(--radius-md);
  font-size: 10px;
  color: #7DA1C7;
  background: rgba(255, 255, 255, 0.04);
}

.auth-status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #34D399;
  box-shadow: 0 0 8px rgba(52, 211, 153, 0.5);
  animation: pulse-ring 2s ease-in-out infinite;
}

.auth-status b {
  margin-left: auto;
  color: #93C5FD;
  font-weight: 600;
}

/* 装饰环 */
.auth-decor-ring {
  position: absolute;
  border-radius: 50%;
  border: 1px solid rgba(147, 197, 253, 0.12);
  pointer-events: none;
}

.ring-large {
  width: 520px;
  height: 520px;
  top: 5%;
  right: -280px;
  box-shadow: 0 0 0 30px rgba(96, 165, 250, 0.03), 0 0 0 60px rgba(96, 165, 250, 0.02);
}

.ring-small {
  width: 240px;
  height: 240px;
  bottom: -120px;
  left: -140px;
}

/* ── 右侧表单区 ── */
.auth-form-panel {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 52px;
  background: var(--bg-surface);
}

.auth-form-wrap {
  width: min(100%, 440px);
}

/* 角色选项卡 */
.auth-role-tabs {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
  padding: 4px;
  margin-bottom: 8px;
  border-radius: var(--radius-md);
  background: var(--gray-100);
}

.auth-role-tabs button {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 8px;
  border-radius: var(--radius-sm);
  color: var(--text-tertiary);
  background: transparent;
  font-size: 12px;
  font-weight: 600;
  transition: all var(--transition-fast);
}

.auth-role-tabs button:hover {
  color: var(--text-secondary);
}

.auth-role-tabs button.active {
  color: var(--primary);
  background: var(--bg-surface);
  box-shadow: var(--shadow-sm);
  font-weight: 700;
}

.auth-role-tabs button svg {
  width: 16px;
}

/* 表单标题 */
.auth-header {
  margin: 28px 0 24px;
}

.auth-header-kicker {
  display: inline-block;
  color: var(--primary);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  margin-bottom: 8px;
}

.auth-header h2 {
  margin: 0 0 6px;
  color: var(--text-primary);
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -0.04em;
}

.auth-header p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

/* 表单元素 */
.auth-form {
  display: grid;
  gap: 16px;
}

.auth-form-group {
  display: grid;
  gap: 6px;
}

.auth-form-group > label {
  display: flex;
  align-items: center;
  gap: 5px;
  padding-left: 2px;
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 600;
}

.auth-form-group > label svg {
  width: 13px;
  color: var(--text-tertiary);
}

.auth-input-box {
  display: flex;
  align-items: center;
  gap: 9px;
  height: 46px;
  padding: 0 14px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-tertiary);
  background: var(--bg-surface);
  transition: all var(--transition-fast);
}

.auth-input-box:focus-within {
  border-color: var(--border-focus);
  box-shadow: 0 0 0 3px rgba(147, 197, 253, 0.15);
  background: #fff;
}

.auth-input-box svg {
  width: 16px;
  flex: 0 0 auto;
}

.auth-input-box input {
  width: 100%;
  border: 0;
  outline: 0;
  color: var(--text-primary);
  background: transparent;
  font-size: 13px;
}

.auth-input-box input::placeholder {
  color: var(--text-tertiary);
}

.auth-input-row {
  display: grid;
  grid-template-columns: 1fr 130px;
  gap: 10px;
}

.auth-captcha-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--gray-50);
  font-size: 9px;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.auth-captcha-btn:hover {
  border-color: var(--border-focus);
  background: var(--primary-soft);
}

.auth-captcha-btn strong {
  font-size: 18px;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: 3px;
  font-family: var(--font-mono);
}

.auth-sms-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--primary);
  background: var(--primary-soft);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.auth-sms-btn:hover:not(:disabled) {
  background: var(--primary-light);
  border-color: var(--border-focus);
}

.auth-sms-btn:disabled {
  color: var(--text-tertiary);
  background: var(--gray-100);
  cursor: not-allowed;
}

/* 协议 */
.auth-agreement {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding-top: 4px;
  cursor: pointer;
}

.auth-agreement input[type="checkbox"] {
  margin-top: 2px;
  width: 15px;
  height: 15px;
  accent-color: var(--primary);
  cursor: pointer;
}

.auth-agreement span {
  color: var(--text-tertiary);
  font-size: 11px;
  line-height: 1.6;
}

.auth-agreement a {
  color: var(--primary);
  font-weight: 600;
}

.auth-agreement a:hover {
  text-decoration: underline;
}

/* 提交按钮 */
.auth-submit {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 48px;
  width: 100%;
  border: none;
  border-radius: var(--radius-md);
  color: #fff;
  background: linear-gradient(135deg, #3B82F6, #2563EB);
  font-size: 14px;
  font-weight: 700;
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.3);
  transition: all var(--transition-fast);
  cursor: pointer;
}

.auth-submit:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 8px 24px rgba(37, 99, 235, 0.4);
  background: linear-gradient(135deg, #60A5FA, #3B82F6);
}

.auth-submit:disabled {
  opacity: 0.7;
  cursor: wait;
}

.auth-submit svg {
  width: 18px;
  transition: transform var(--transition-fast);
}

.auth-submit:hover:not(:disabled) svg {
  transform: translateX(2px);
}

.auth-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: rotate 0.6s linear infinite;
}

@keyframes rotate {
  to { transform: rotate(360deg); }
}

/* 底部链接 */
.auth-links {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-top: 20px;
}

.auth-link-btn {
  padding: 4px 8px;
  border: none;
  color: var(--text-secondary);
  background: transparent;
  font-size: 12px;
  font-weight: 600;
  transition: color var(--transition-fast);
  cursor: pointer;
}

.auth-link-btn:hover {
  color: var(--primary);
}

.auth-link-divider {
  color: var(--border-default);
  font-size: 14px;
}

/* 演示提示 */
.auth-demo-tip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 24px;
  padding: 10px;
  border-radius: var(--radius-sm);
  background: var(--primary-soft);
  color: var(--primary-hover);
  font-size: 11px;
  font-weight: 500;
}

.auth-demo-tip svg {
  width: 14px;
  color: var(--success);
}

/* 演示登录按钮 */
.auth-demo-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  height: 48px;
  margin-top: 20px;
  border: 2px dashed #93C5FD;
  border-radius: var(--radius-md);
  color: var(--primary);
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.04), rgba(37, 99, 235, 0.02));
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.auth-demo-btn:hover:not(:disabled) {
  border-color: var(--primary);
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.1), rgba(37, 99, 235, 0.06));
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.15);
}

.auth-demo-btn:disabled {
  opacity: 0.6;
  cursor: wait;
}

.auth-demo-btn svg {
  width: 18px;
}

/* 页脚 */
.auth-footer {
  position: relative;
  z-index: 1;
  margin-top: 24px;
  color: var(--text-tertiary);
  font-size: 11px;
  text-align: center;
}

/* ── 响应式 ── */
@media (max-width: 850px) {
  .auth-page {
    padding: 0;
    justify-content: flex-start;
  }

  .auth-card {
    min-height: 100vh;
    grid-template-columns: 1fr;
    border-radius: 0;
  }

  .auth-brand {
    min-height: 300px;
  }

  .auth-brand-inner {
    padding: 32px 28px 28px;
  }

  .auth-brand-hero {
    margin: 28px 0 20px;
  }

  .auth-brand-hero h1 {
    font-size: 30px;
  }

  .auth-brand-hero p,
  .auth-features {
    display: none;
  }

  .auth-form-panel {
    padding: 32px 28px;
  }

  .auth-footer {
    display: none;
  }
}

@media (max-width: 480px) {
  .auth-brand {
    min-height: 240px;
  }

  .auth-brand-inner {
    padding: 24px 20px;
  }

  .auth-brand-hero {
    margin: 18px 0 0;
  }

  .auth-brand-hero h1 {
    font-size: 26px;
  }

  .auth-form-panel {
    padding: 24px 18px 40px;
  }

  .auth-role-tabs button {
    font-size: 11px;
    padding: 8px 4px;
  }

  .auth-header h2 {
    font-size: 22px;
  }

  .auth-input-row {
    grid-template-columns: 1fr 110px;
  }
}
</style>
