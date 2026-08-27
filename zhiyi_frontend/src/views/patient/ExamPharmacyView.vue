<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Calendar, ArrowRight, Filter, Minus, Plus, Search, ShoppingBag, ShoppingCart, MagicStick, PriceTag, Clock, CircleCheck, FirstAidKit, Delete, Close } from '@element-plus/icons-vue'
import { createOrder, getExamItems, getDrugs, addExamToCart, addDrugToCart, getExamCart, getDrugCart, updateDrugCart, removeExamFromCart, removeDrugFromCart } from '@/api'
import { defaultDeliveryAddress, locateCurrentCity } from '@/utils/location'

const route = useRoute()
const router = useRouter()
const activeTab = ref<'exam' | 'drug'>(route.query.tab === 'drug' ? 'drug' : 'exam')
const category = ref('全部项目')
const query = ref('')
const showSearch = ref(false)
const examItems = ref<any[]>([])
const medicines = ref<any[]>([])
const examCart = ref<number[]>([])
const drugCart = ref<Record<number, number>>({})
const deliveryAddress = ref(defaultDeliveryAddress())
const locatedCity = ref<string | null>(null)
const submitting = ref(false)
const loading = ref(false)

onMounted(async () => {
  const geo = await locateCurrentCity()
  if (geo) {
    deliveryAddress.value = geo.address
    locatedCity.value = geo.city
  }
  await loadCatalog()
  await loadCarts()
})

watch(
  () => route.query.tab,
  (tab) => {
    if (tab === 'exam' || tab === 'drug') activeTab.value = tab
  }
)

function setTab(tab: 'exam' | 'drug') {
  activeTab.value = tab
  router.replace({ path: '/patient/exams', query: { tab } }).catch(() => {})
}

async function loadCatalog() {
  loading.value = true
  try {
    const [exams, drugs] = await Promise.all([getExamItems(), getDrugs()])
    examItems.value = Array.isArray(exams) ? exams : []
    medicines.value = Array.isArray(drugs) ? drugs : []
  } catch (e: any) {
    ElMessage.error(e.message || '加载服务目录失败')
  } finally {
    loading.value = false
  }
}

async function loadCarts() {
  try {
    const examCartData = await getExamCart()
    const drugCartData = await getDrugCart()
    examCart.value = (examCartData.items || []).map((i: any) => i.exam_item_id)
    drugCart.value = {}
    for (const item of drugCartData.items || []) {
      drugCart.value[item.drug_id] = item.quantity
    }
  } catch {
    // 未登录或购物车为空时静默忽略
  }
}

const filteredExams = computed(() =>
  examItems.value.filter((item) =>
    (category.value === '全部项目' || item.category === category.value) &&
    (!query.value || `${item.name}${item.description || ''}`.includes(query.value))
  )
)

const filteredDrugs = computed(() =>
  medicines.value.filter((item) =>
    !query.value || `${item.name}${item.generic_name || ''}${item.manufacturer || ''}`.includes(query.value)
  )
)

const examTotal = computed(() =>
  examItems.value
    .filter((item) => examCart.value.includes(item.id))
    .reduce((sum, item) => sum + item.price, 0)
)

const drugTotal = computed(() =>
  medicines.value.reduce((sum, item) => sum + item.price * (drugCart.value[item.id] || 0), 0)
)

const drugCount = computed(() =>
  Object.values(drugCart.value).reduce((sum, qty) => sum + qty, 0)
)

async function checkout(type: 'exam' | 'drug') {
  submitting.value = true
  try {
    if (type === 'exam') {
      const items = examCart.value.map((id) => ({ exam_item_id: id, quantity: 1 }))
      await createOrder('exam', {
        items,
        hospital_id: 1,
        appointment_time: new Date(Date.now() + 7 * 86400000).toISOString(),
      })
      examCart.value = []
    } else {
      const items = Object.entries(drugCart.value)
        .filter(([_, qty]) => qty > 0)
        .map(([drug_id, quantity]) => ({ drug_id: Number(drug_id), quantity }))
      await createOrder('drug', {
        items,
        address: deliveryAddress.value.trim() || defaultDeliveryAddress(),
      })
      drugCart.value = {}
    }
    ElMessage.success(`${type === 'exam' ? '检查预约' : '药品订单'}已创建，待支付`)
  } catch (e: any) {
    ElMessage.error(e.message || '订单创建失败，请稍后重试')
  } finally {
    submitting.value = false
  }
}

async function addExam(id: number) {
  try {
    if (examCart.value.includes(id)) {
      // 点击「已加入」→ 移除
      await removeExamFromCart(id)
      examCart.value = examCart.value.filter(eid => eid !== id)
      ElMessage.success('已从预约清单移除')
    } else {
      await addExamToCart(id, 1)
      examCart.value.push(id)
      ElMessage.success('已加入预约清单')
    }
  } catch (e: any) {
    ElMessage.error(e.message || '加入预约清单失败')
  }
}

async function addDrug(id: number) {
  const item = medicines.value.find((m) => m.id === id)
  if (item?.need_prescription) {
    ElMessage.warning('处方药需医生确认处方后购买')
    return
  }
  try {
    await addDrugToCart(id, 1)
    drugCart.value[id] = (drugCart.value[id] || 0) + 1
    ElMessage.success('已加入药品购物车')
  } catch (e: any) {
    ElMessage.error(e.message || '加入购物车失败')
  }
}

async function adjustDrug(id: number, delta: number) {
  const current = drugCart.value[id] || 0
  const next = Math.max(0, current + delta)
  if (next === 0) {
    try {
      await removeDrugFromCart(id)
      delete drugCart.value[id]
    } catch (e: any) {
      ElMessage.error(e.message || '移除失败')
    }
  } else {
    try {
      await updateDrugCart(id, next)
      drugCart.value[id] = next
    } catch (e: any) {
      ElMessage.error(e.message || '更新数量失败')
    }
  }
}

// ── 卡片图片（AI 生成的真实医疗摄影照片，存放在 /public/images/）──
const examImageMap: Record<string, string> = {
  '影像科': '/images/exam-ct.jpg',
  '超声科': '/images/exam-ultrasound.jpg',
  '检验科': '/images/exam-lab.jpg',
  '心内科': '/images/exam-cardio.jpg',
  '神经内科': '/images/exam-neuro.jpg',
}
function examImage(item: any) {
  return examImageMap[item.category] || '/images/exam-lab.jpg'
}
// 每款药品独立配图（按药品种类匹配最合适的图片）
const drugImageById: Record<number, string> = {
  1: '/images/drug-tablets.jpg',   // 硝苯地平缓释片
  2: '/images/drug-capsules.jpg',  // 阿莫西林克拉维酸
  3: '/images/drug-pills.jpg',     // 二甲双胍片
  4: '/images/drug-syrup.jpg',     // 布洛芬缓释胶囊
  5: '/images/drug-pharmacy.jpg',  // 对乙酰氨基酚片
  6: '/images/drug-ointment.jpg',  // 阿奇霉素片
  7: '/images/drug-drops.jpg',     // 氯雷他定片
  8: '/images/drug-powder.jpg',    // 蒙脱石散
  9: '/images/drug-inhaler.jpg',   // 奥美拉唑肠溶胶囊
  10: '/images/drug-patch.jpg',    // 螺内酯片
  11: '/images/drug-drops.jpg',    // 甘精胰岛素注射液（冷链）
  12: '/images/drug-syrup.jpg',    // 人血白蛋白（冷链）
  13: '/images/drug-inhaler.jpg',  // 重组乙肝疫苗（冷链）
}
function drugImage(item: any) {
  return drugImageById[item.id] || '/images/drug-pharmacy.jpg'
}
</script>

<template>
  <div class="booking-page">
    <!-- 页头 -->
    <div class="page-heading">
      <div>
        <div class="eyebrow">预约与购药 / 服务目录</div>
        <h1 class="page-title">预约与购药</h1>
        <p class="page-subtitle">把检查、处方和配送安排在同一个清晰的服务链路里。</p>
      </div>
      <div class="booking-cart-summary">
        <ShoppingCart />
        <span>{{ activeTab === 'exam' ? examCart.length : drugCount }}</span> 件待处理
      </div>
    </div>

    <!-- Tab 切换 -->
    <div class="booking-tabs">
      <button :class="{ active: activeTab === 'exam' }" @click="setTab('exam')">
        <Calendar /> 检查预约
        <span>{{ examCart.length }}</span>
      </button>
      <button :class="{ active: activeTab === 'drug' }" @click="setTab('drug')">
        <ShoppingBag /> 在线购药
        <span>{{ drugCount }}</span>
      </button>
    </div>

    <!-- ========== 检查预约 ========== -->
    <div v-if="activeTab === 'exam'" class="booking-layout">
      <main>
        <!-- 工具栏 -->
        <div class="catalogue-toolbar">
          <div class="catalogue-search">
            <Search />
            <input v-model="query" placeholder="搜索检查项目" />
          </div>
          <div class="category-chips">
            <button
              v-for="cat in ['全部项目', '影像科', '超声科', '检验科', '心电图室']"
              :key="cat"
              :class="{ active: category === cat }"
              @click="category = cat"
            >
              {{ cat }}
            </button>
          </div>
          <button class="ghost-button" @click="showSearch = !showSearch"><Filter /> {{ showSearch ? '收起搜索' : '更多筛选' }}</button>
        </div>

        <!-- 搜索框 -->
        <div v-if="showSearch" class="search-bar">
          <input v-model="query" type="text" placeholder="输入名称或关键词搜索..." class="search-input" />
          <span class="search-hint">{{ activeTab === 'exam' ? filteredExams.length : filteredDrugs.length }} 个结果</span>
        </div>

        <!-- 列表标题 -->
        <div class="catalogue-heading">
          <div>
            <div class="section-kicker"><span class="signal-line" />可预约服务</div>
            <h2>可预约检查</h2>
          </div>
          <span class="catalogue-count">{{ filteredExams.length }} 个项目</span>
        </div>

        <!-- 检查项目网格 -->
        <div v-if="loading" class="loading-tip">正在加载检查项目…</div>
        <div v-else class="exam-grid">
          <article v-for="item in filteredExams" :key="item.id" class="exam-card">
            <div class="exam-card-bg">
              <img :src="examImage(item)" :alt="item.name" class="exam-card-img" loading="lazy" />
            </div>
            <div class="exam-card-body">
              <div class="exam-card-badge">{{ item.category }}</div>
              <h3>{{ item.name }}</h3>
              <div class="exam-card-meta">
                <span class="exam-card-duration">{{ item.description || '约 20 分钟' }}</span>
              </div>
              <div class="exam-card-bottom">
                <strong>&yen;{{ item.price }}</strong>
                <button
                  class="exam-cart-btn"
                  :class="{ added: examCart.includes(item.id) }"
                  @click="addExam(item.id)"
                >
                  {{ examCart.includes(item.id) ? '已加入' : '+ 预约' }}
                </button>
              </div>
            </div>
          </article>
        </div>
      </main>

      <!-- 预约清单侧栏 -->
      <aside class="cart-sidebar">
        <div class="section-title cart-sidebar-title">
          <div>
            <div class="section-kicker"><span class="signal-line" />我的预约计划</div>
            <h2>预约清单</h2>
          </div>
          <span class="cart-badge">{{ examCart.length }}</span>
        </div>

        <div v-if="examCart.length" class="cart-items">
          <div
            v-for="item in examItems.filter((exam) => examCart.includes(exam.id))"
            :key="item.id"
            class="cart-item"
          >
            <div class="cart-item-icon"><FirstAidKit /></div>
            <div class="cart-item-info">
              <strong>{{ item.name }}</strong>
              <small>{{ item.category }}</small>
            </div>
            <b>&yen;{{ item.price }}</b>
            <button class="cart-remove-btn" title="移除" @click="addExam(item.id)"><Close /></button>
          </div>
        </div>
        <div v-else class="empty-note">还没有选择检查项目</div>

        <div class="cart-total">
          <span>合计自费金额</span>
          <strong>&yen;{{ examTotal }}</strong>
        </div>

        <div class="cart-insurance-note">
          <CircleCheck /> 医保统筹支付部分将在结算时自动扣除
        </div>

        <button
          class="primary-button cart-checkout-btn"
          :disabled="!examCart.length || submitting"
          @click="checkout('exam')"
        >
          {{ submitting ? '创建中…' : '提交预约' }} <ArrowRight />
        </button>
      </aside>
    </div>

    <!-- ========== 在线购药 ========== -->
    <div v-else class="drug-layout">
      <main>
        <!-- 药房横幅 -->
        <div class="drug-hero">
          <div class="drug-hero-content">
            <div class="eyebrow light"><span class="drug-hero-dot" />药房服务网络</div>
            <h2>把处方交给我们，<br /><em>安心送到家。</em></h2>
            <p>智医中心药房已完成处方审核，常用药品预计 24 小时内送达。</p>
            <button class="secondary-button drug-upload-btn" @click="showSearch = !showSearch; activeTab = 'drug'">
              <Plus /> {{ showSearch ? '收起搜索' : '搜索药品' }}
            </button>
          </div>
          <div class="drug-hero-decor" />
        </div>

        <!-- 药品列表标题 -->
        <div class="catalogue-heading">
          <div>
            <div class="section-kicker"><span class="signal-line" />为你推荐</div>
            <h2>常用药品</h2>
          </div>
          <span class="catalogue-count">库存实时同步</span>
        </div>

        <!-- 药品网格 -->
        <div v-if="loading" class="loading-tip">正在加载药品目录…</div>
        <div v-else class="drug-grid">
          <article v-for="item in filteredDrugs" :key="item.id" class="drug-card">
            <div class="drug-card-bg">
              <img :src="drugImage(item)" :alt="item.name" class="drug-card-img" loading="lazy" />
              <span v-if="item.stock < 50" class="drug-stock-badge">库存紧张</span>
            </div>
            <div class="drug-card-body">
              <div class="drug-card-badges">
                <span class="drug-card-badge">{{ item.need_prescription ? '💊 处方药' : '💊 非处方药' }}</span>
                <span v-if="item.need_cold_chain" class="drug-card-badge cold">❄ 需冷链</span>
              </div>
              <h3>{{ item.name }}</h3>
              <p class="drug-spec">{{ item.specification }}</p>
              <div class="drug-card-bottom">
                <strong>&yen;{{ item.price }}</strong>
                <div v-if="item.need_prescription" class="rx-need">需医生处方</div>
                <div v-else class="drug-qty-control">
                  <button @click="adjustDrug(item.id, -1)">−</button>
                  <span>{{ drugCart[item.id] || 0 }}</span>
                  <button class="qty-plus" @click="addDrug(item.id)">+</button>
                </div>
              </div>
            </div>
          </article>
        </div>
      </main>

      <!-- 药品购物车侧栏 -->
      <aside class="cart-sidebar">
        <div class="section-title cart-sidebar-title">
          <div>
            <div class="section-kicker"><span class="signal-line" />药品购物车</div>
            <h2>药品购物车</h2>
          </div>
          <span class="cart-badge">{{ drugCount }}</span>
        </div>

        <div v-if="drugCount" class="cart-items">
          <div
            v-for="item in medicines.filter((drug) => drugCart[drug.id])"
            :key="item.id"
            class="drug-cart-item"
          >
            <div class="drug-cart-item-info">
              <strong>{{ item.name }}</strong>
              <small>&yen;{{ item.price }} / {{ item.specification }}</small>
            </div>
            <div class="drug-cart-qty">
              <button class="qty-btn" @click="adjustDrug(item.id, -1)"><Minus /></button>
              <span class="qty-value">{{ drugCart[item.id] }}</span>
              <button class="qty-btn" @click="adjustDrug(item.id, 1)"><Plus /></button>
              <button class="cart-remove-btn" title="移除" @click="adjustDrug(item.id, -drugCart[item.id])"><Close /></button>
            </div>
          </div>
        </div>
        <div v-else class="empty-note">购物车是空的</div>

        <div class="cart-total">
          <span>订单合计</span>
          <strong>&yen;{{ drugTotal.toFixed(2) }}</strong>
        </div>
        <div class="cart-address">
          <label>配送地址</label>
          <input v-model="deliveryAddress" type="text" placeholder="请输入收货地址" />
          <span v-if="locatedCity" class="cart-address-tip">已自动定位到{{ locatedCity }}（可修改）</span>
        </div>
        <div class="cart-insurance-note">
          <MagicStick /> AI 处方审核已开启
        </div>

        <button
          class="primary-button cart-checkout-btn"
          :disabled="!drugCount || submitting"
          @click="checkout('drug')"
        >
          {{ submitting ? '创建中…' : '提交订单' }} <ArrowRight />
        </button>
      </aside>
    </div>

  </div>
</template>

<style scoped>
.booking-page { position: relative; }

.loading-tip {
  padding: 40px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 13px;
}

/* 购物车摘要 */
.booking-cart-summary {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-tertiary);
  font-size: 12px;
  font-weight: 600;
}

.booking-cart-summary svg {
  width: 18px;
  color: var(--primary);
}

.booking-cart-summary span {
  color: var(--primary);
  font-weight: 800;
}

/* Tab 切换 */
.booking-tabs {
  display: flex;
  gap: 2px;
  padding: 4px;
  margin-bottom: 20px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--gray-100);
  width: fit-content;
}

.booking-tabs button {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: center;
  min-width: 150px;
  padding: 10px 16px;
  border-radius: var(--radius-sm);
  color: var(--text-tertiary);
  background: transparent;
  font-size: 12px;
  font-weight: 600;
  transition: all var(--transition-fast);
  cursor: pointer;
}

.booking-tabs button svg { width: 16px; }

.booking-tabs button span {
  padding: 2px 7px;
  border-radius: var(--radius-full);
  font-size: 10px;
  color: var(--text-tertiary);
  background: var(--gray-200);
}

.booking-tabs button.active {
  color: var(--primary);
  background: var(--bg-surface);
  box-shadow: var(--shadow-sm);
}

.booking-tabs button.active span {
  color: #fff;
  background: var(--primary);
}

/* ── 布局 ── */
.booking-layout,
.drug-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 20px;
  align-items: start;
}

/* ── 工具栏 ── */
.catalogue-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.catalogue-search {
  width: 220px;
  height: 36px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  color: var(--text-tertiary);
  background: var(--gray-50);
  transition: all var(--transition-fast);
}

.catalogue-search:focus-within {
  border-color: var(--border-focus);
  box-shadow: 0 0 0 2px rgba(147, 197, 253, 0.15);
}

.catalogue-search input {
  width: 100%;
  border: 0;
  outline: 0;
  color: var(--text-primary);
  background: transparent;
  font-size: 12px;
}

.category-chips {
  display: flex;
  flex: 1;
  gap: 4px;
}

.category-chips button {
  padding: 6px 10px;
  border: 0;
  border-radius: var(--radius-sm);
  color: var(--text-tertiary);
  background: transparent;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.category-chips button.active {
  color: var(--primary);
  background: var(--primary-soft);
}

/* 列表标题 */
.catalogue-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 16px;
}

.catalogue-heading h2 {
  margin: 4px 0 0;
  color: var(--text-primary);
  font-size: 18px;
  font-weight: 800;
}

.catalogue-count {
  color: var(--text-tertiary);
  font-size: 11px;
}

/* ── 检查项目网格 ── */
.exam-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

.exam-card {
  border-radius: 16px; overflow: hidden; background: #fff;
  border: 1px solid var(--border-light); box-shadow: var(--shadow-xs);
  transition: all .2s; cursor: pointer; display: flex; flex-direction: column;
}
.exam-card:hover { box-shadow: 0 8px 30px rgba(0,0,0,.1); transform: translateY(-2px); }

.exam-card-bg {
  height: 140px; position: relative; overflow: hidden;
  background: var(--gray-100);
}
.exam-card-img {
  width: 100%; height: 100%; object-fit: cover; display: block;
}

.exam-card-body { padding: 16px 18px 18px; flex: 1; display: flex; flex-direction: column; }
.exam-card-badge {
  display: inline-block; padding: 2px 10px; border-radius: 12px;
  background: var(--primary-soft); color: var(--primary);
  font-size: 12px; font-weight: 600; align-self: flex-start; margin-bottom: 8px;
}
.exam-card-body h3 { margin: 0 0 6px; font-size: 15px; font-weight: 700; color: var(--text-primary); }
.exam-card-meta { flex: 1; }
.exam-card-duration { font-size: 13px; color: var(--text-tertiary); }
.exam-card-bottom {
  display: flex; align-items: center; justify-content: space-between; margin-top: 14px;
  padding-top: 12px; border-top: 1px solid var(--border-light);
}
.exam-card-bottom strong { font-size: 20px; font-weight: 800; color: var(--text-primary); }
.exam-cart-btn {
  padding: 6px 16px; border-radius: 8px; border: 1px solid var(--primary);
  background: transparent; color: var(--primary); font-size: 13px; font-weight: 600; cursor: pointer;
  transition: all .15s;
}
.exam-cart-btn:hover { background: var(--primary); color: #fff; }
.exam-cart-btn.added { background: var(--success); color: #fff; border-color: var(--success); }

/* ── 药品横幅 ── */
.drug-hero {
  padding: 32px 28px;
  border-radius: var(--radius-lg);
  background: linear-gradient(135deg, #0F2942, #0B1F33);
  color: #E8F1FC;
  position: relative;
  overflow: hidden;
  margin-bottom: 24px;
}

.drug-hero-content {
  position: relative;
  z-index: 1;
}

.drug-hero .eyebrow {
  color: #93C5FD;
}

.drug-hero-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #34D399;
}

.drug-hero h2 {
  margin: 14px 0 10px;
  font-size: 28px;
  line-height: 1.2;
  font-weight: 800;
}

.drug-hero h2 em {
  font-style: normal;
  background: linear-gradient(135deg, #60A5FA, #93C5FD);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.drug-hero p {
  max-width: 400px;
  margin: 0 0 18px;
  font-size: 12px;
  color: #7DA1C7;
  line-height: 1.7;
}

.drug-upload-btn {
  background: rgba(255, 255, 255, 0.1) !important;
  color: #fff !important;
  border: 1px solid rgba(147, 197, 253, 0.3) !important;
}

.drug-upload-btn:hover {
  background: rgba(255, 255, 255, 0.15) !important;
}

.drug-hero-decor {
  position: absolute;
  right: -80px;
  top: -60px;
  width: 300px;
  height: 300px;
  border-radius: 50%;
  border: 1px solid rgba(147, 197, 253, 0.1);
  box-shadow: 0 0 0 40px rgba(96, 165, 250, 0.03);
}

/* ── 药品网格 ── */
.drug-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}

.drug-card {
  border-radius: 16px; overflow: hidden; background: #fff;
  border: 1px solid var(--border-light); box-shadow: var(--shadow-xs);
  transition: all .2s; cursor: pointer; display: flex; flex-direction: column;
}
.drug-card:hover { box-shadow: 0 8px 30px rgba(0,0,0,.1); transform: translateY(-2px); }

.drug-card-bg {
  height: 130px; position: relative; overflow: hidden;
  background: var(--gray-100);
}
.drug-card-img {
  width: 100%; height: 100%; object-fit: cover; display: block;
}
.drug-stock-badge {
  position: absolute; top: 10px; right: 12px; padding: 2px 8px;
  border-radius: 10px; background: rgba(255,255,255,.9);
  color: #DC2626; font-size: 11px; font-weight: 700;
}

.drug-card-body { padding: 14px 16px 16px; flex: 1; display: flex; flex-direction: column; }
.drug-card-badge {
  font-size: 12px; color: var(--primary); font-weight: 600; margin-bottom: 6px;
}
.drug-card-badge.cold { background: #E0F2FE; color: #0369A1; }
.drug-card-badges { display: flex; gap: 4px; flex-wrap: wrap; }
.drug-card-body h3 { margin: 0 0 4px; font-size: 15px; font-weight: 700; }
.drug-spec { margin: 0; font-size: 13px; color: var(--text-tertiary); flex: 1; }
.drug-card-bottom {
  display: flex; align-items: center; justify-content: space-between;
  margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border-light);
}
.drug-card-bottom strong { font-size: 18px; font-weight: 800; color: var(--text-primary); }
.drug-qty-control {
  display: flex; align-items: center; gap: 6px;
}
.drug-qty-control button {
  width: 28px; height: 28px; border-radius: 6px; border: 1px solid var(--border-light);
  background: #fff; font-size: 16px; font-weight: 600; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all .15s;
}
.drug-qty-control button:hover { background: var(--primary-soft); border-color: var(--primary); }
.drug-qty-control .qty-plus { background: var(--primary); color: #fff; border-color: var(--primary); }
.drug-qty-control span { min-width: 20px; text-align: center; font-weight: 600; font-size: 14px; }
.rx-need {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border-radius: 6px;
  background: #FEF3C7;
  color: #B45309;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

/* ── 购物车侧栏 ── */
.cart-sidebar {
  position: sticky;
  top: calc(var(--topbar-height) + 28px);
  padding: 22px 20px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  background: var(--bg-surface);
  box-shadow: var(--shadow-card);
}

.cart-sidebar-title {
  margin-bottom: 18px;
}

.cart-badge {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--primary);
  color: #fff;
  font-size: 11px;
  font-weight: 800;
}

.cart-items {
  display: grid;
  gap: 10px;
  margin-bottom: 16px;
}

.cart-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  background: var(--gray-50);
}

.cart-item-icon {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-sm);
  background: var(--primary-soft);
}

.cart-item-icon svg { width: 15px; color: var(--primary); }

.cart-item-info {
  flex: 1;
  min-width: 0;
}

.cart-item-info strong {
  display: block;
  font-size: 12px;
  color: var(--text-primary);
}

.cart-item-info small {
  font-size: 10px;
  color: var(--text-tertiary);
}

.cart-item > b {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  flex-shrink: 0;
}

.cart-remove-btn {
  width: 22px; height: 22px;
  display: grid; place-items: center;
  border: 1px solid var(--border-light);
  border-radius: 4px;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  flex-shrink: 0;
  transition: all var(--transition-fast);
}
.cart-remove-btn:hover {
  background: #FEE2E2;
  color: #DC2626;
  border-color: #FCA5A5;
}
.cart-remove-btn svg { width: 10px; }

.cart-total {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 0;
  border-top: 2px solid var(--border-default);
}

.cart-total span {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.cart-total strong {
  font-size: 22px;
  font-weight: 800;
  color: var(--text-primary);
}

.cart-insurance-note {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--success-light);
  color: var(--success);
  font-size: 10px;
  font-weight: 600;
  margin-bottom: 14px;
}

.cart-insurance-note svg { width: 14px; }

.cart-address {
  display: grid;
  gap: 6px;
  margin-bottom: 14px;
  padding: 10px 12px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  background: var(--gray-50);
}

.cart-address label {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-secondary);
}

.cart-address input {
  width: 100%;
  height: 32px;
  padding: 0 10px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  background: var(--bg-surface);
  font-size: 12px;
  outline: 0;
  transition: border-color var(--transition-fast);
}

.cart-address input:focus {
  border-color: var(--border-focus);
  box-shadow: 0 0 0 2px rgba(147, 197, 253, 0.15);
}

.cart-address-tip {
  font-size: 11px;
  color: var(--color-success, #16a34a);
}

.cart-checkout-btn {
  width: 100%;
  min-height: 44px;
}

/* ── 药品购物车数量 ── */
.drug-cart-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  background: var(--gray-50);
  margin-bottom: 8px;
}

.drug-cart-item-info {
  flex: 1;
  min-width: 0;
}

.drug-cart-item-info strong {
  display: block;
  font-size: 12px;
  color: var(--text-primary);
}

.drug-cart-item-info small {
  font-size: 10px;
  color: var(--text-tertiary);
}

.drug-cart-qty {
  display: flex;
  align-items: center;
  gap: 4px;
}

.qty-btn {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.qty-btn:hover {
  border-color: var(--border-focus);
}

.qty-btn svg { width: 12px; }

.qty-value {
  min-width: 28px;
  text-align: center;
  font-size: 13px;
  font-weight: 700;
}

/* ── 响应式 ── */
@media (max-width: 1050px) {
  .booking-layout,
  .drug-layout {
    grid-template-columns: 1fr;
  }

  .cart-sidebar {
    position: static;
  }
}

@media (max-width: 700px) {
  .catalogue-search {
    width: 100%;
  }

  .category-chips {
    overflow-x: auto;
    order: 3;
  }

  .booking-tabs {
    width: 100%;
  }

  .booking-tabs button {
    min-width: 0;
    flex: 1;
  }

  .exam-grid,
  .drug-grid {
    grid-template-columns: 1fr 1fr;
  }

  .drug-hero h2 {
    font-size: 22px;
  }
}

@media (max-width: 460px) {
  .exam-grid,
  .drug-grid {
    grid-template-columns: 1fr;
  }
}

/* ── 我的订单 ── */
.my-orders-section { margin-top: 32px; }
.order-list { display: flex; flex-direction: column; gap: 8px; }
.order-card {
  display: flex; align-items: center; gap: 20px; padding: 14px 18px;
  background: #fff; border-radius: 12px; border: 1px solid var(--border-light);
}
.order-card-left { display: flex; align-items: center; gap: 10px; min-width: 180px; }
.order-type-tag {
  padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 700;
}
.order-type-tag.exam { background: #DBEAFE; color: #2563EB; }
.order-type-tag.drug { background: #DCFCE7; color: #16A34A; }
.order-card-left strong { font-size: 14px; }
.order-card-left small { display: block; font-size: 11px; color: var(--text-tertiary); }
.order-card-mid { flex: 1; display: flex; flex-wrap: wrap; gap: 4px; }
.order-item-name {
  font-size: 12px; color: var(--text-secondary); padding: 2px 6px;
  background: var(--gray-100); border-radius: 4px;
}
.order-card-right { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }
.order-card-right strong { font-size: 16px; }
.order-pay-btn {
  padding: 5px 16px; border: none; border-radius: 8px;
  background: var(--primary); color: #fff; font-size: 12px; font-weight: 600;
  cursor: pointer; transition: all .15s;
}
.order-pay-btn:hover { background: var(--primary-hover); }
.order-pay-btn:disabled { background: var(--gray-400); cursor: not-allowed; }
.order-paid { font-size: 12px; color: var(--success); font-weight: 600; }
</style>
