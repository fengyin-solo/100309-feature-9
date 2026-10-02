<template>
  <section class="page" data-module="patrol">
    <header class="page-head">
      <div>
        <h2>巡检作业管理</h2>
        <p class="page-desc">巡检路线存成模板反复用：按站点挑模板生成本期任务，发现问题一键转派责任班组，处置结果自动写回任务。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="togglePanel('generate')">按模板生成任务</button>
        <button class="btn" type="button" @click="togglePanel('template')">巡检路线模板库</button>
        <button class="btn" type="button" @click="exportRows">导出巡检作业清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <section v-if="activePanel === 'generate'" class="panel">
      <h3 class="panel-title">按模板生成本期巡检任务</h3>
      <form class="filter-bar" @submit.prevent="generateTask">
        <label class="filter-item">
          <span>巡检站点</span>
          <input v-model="generateForm.巡检站点" placeholder="站点名称，需先有路线模板" required />
        </label>
        <label class="filter-item">
          <span>巡检期次</span>
          <input v-model="generateForm.巡检期次" type="month" required />
        </label>
        <label class="filter-item">
          <span>巡检人员</span>
          <input v-model="generateForm.巡检人员" placeholder="不填则待指派" />
        </label>
        <label class="filter-item">
          <span>路线模板</span>
          <select v-model="generateForm.模板编号">
            <option value="">自动选择该站点的模板</option>
            <option v-for="tpl in siteTemplates" :key="String(tpl.id)" :value="tpl.模板编号">
              {{ tpl.模板编号 }} · {{ tpl.模板名称 }}
            </option>
          </select>
        </label>
        <button class="btn primary" type="submit">生成本期任务</button>
      </form>
      <p class="panel-hint">同一站点同一期次只会保留一条任务；站点没有可用模板时会提示先登记模板，不会生成空任务。</p>
    </section>

    <section v-if="activePanel === 'template'" class="panel">
      <h3 class="panel-title">巡检路线模板库</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in templateColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="tpl in templates" :key="String(tpl.id)">
            <td>{{ tpl.模板编号 }}</td>
            <td>{{ tpl.模板名称 }}</td>
            <td>{{ tpl.适用站点 }}</td>
            <td>{{ tpl.责任班组 || '—' }}</td>
            <td>{{ formatPoints(tpl) }}</td>
            <td>{{ tpl.备注 || '—' }}</td>
          </tr>
          <tr v-if="!templates.length">
            <td :colspan="templateColumns.length" class="empty-state">暂无路线模板，请先在下方登记</td>
          </tr>
        </tbody>
      </table>
      <form class="filter-bar" @submit.prevent="createTemplate">
        <label class="filter-item">
          <span>模板名称</span>
          <input v-model="templateForm.模板名称" placeholder="如：标准机房巡检路线" required />
        </label>
        <label class="filter-item">
          <span>适用站点</span>
          <input v-model="templateForm.适用站点" placeholder="站点名称" required />
        </label>
        <label class="filter-item">
          <span>责任班组</span>
          <input v-model="templateForm.责任班组" placeholder="转派时的默认班组" />
        </label>
        <label class="filter-item">
          <span>巡检点（按顺序，用顿号或换行分隔）</span>
          <input v-model="templateForm.巡检点" placeholder="机房环境、开关电源、蓄电池组" required />
        </label>
        <button class="btn primary" type="submit">登记模板</button>
      </form>
    </section>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无巡检作业数据，可用模板生成本期任务</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条巡检作业记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, any>

const ENDPOINT = '/api/patrol'
const columns = ["任务编号", "巡检站点", "巡检人员", "巡检期次", "计划日期", "巡检路线", "发现问题", "处置班组", "处置状态", "处置措施", "任务状态"]
const actions = ["开始巡检", "提交巡检", "转派处置", "处置完成", "发起复查"]
const templateColumns = ["模板编号", "模板名称", "适用站点", "责任班组", "巡检点顺序", "备注"]
const stats = [{"label": "待巡检站点", "value": 0}, {"label": "已巡检站点", "value": 0}, {"label": "待复查站点", "value": 0}]

const rows = ref<Row[]>([])
const templates = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const activePanel = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = ["任务编号", "巡检站点", "巡检期次"]
const generateForm = ref<Record<string, string>>({ 巡检站点: '', 巡检期次: '', 巡检人员: '', 模板编号: '' })
const templateForm = ref<Record<string, string>>({ 模板名称: '', 适用站点: '', 责任班组: '', 巡检点: '' })

const siteTemplates = computed(() =>
  templates.value.filter((tpl) => !generateForm.value.巡检站点 || tpl.适用站点 === generateForm.value.巡检站点),
)

function togglePanel(panel: string) {
  activePanel.value = activePanel.value === panel ? '' : panel
}

function formatPoints(tpl: Row) {
  const points = Array.isArray(tpl.巡检点列表) ? tpl.巡检点列表 : []
  return points.length ? points.join(' → ') : '—'
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function buildQuery() {
  const query = new URLSearchParams()
  if (filters.value.任务编号) query.set('keyword', filters.value.任务编号)
  if (filters.value.巡检站点) query.set('site', filters.value.巡检站点)
  if (filters.value.巡检期次) query.set('period', filters.value.巡检期次)
  return query.toString()
}

function resetFilters() {
  filters.value = {}
  void reload()
}

async function generateTask() {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/generate`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...generateForm.value } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      errorMessage.value = payload.message || '本期巡检任务生成失败'
      return
    }
    noticeMessage.value = payload.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '本期巡检任务生成失败'
  }
}

async function createTemplate() {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/templates`, {
      method: 'POST',
      body: JSON.stringify({
        values: {
          模板名称: templateForm.value.模板名称,
          适用站点: templateForm.value.适用站点,
          责任班组: templateForm.value.责任班组,
          巡检点列表: templateForm.value.巡检点,
        },
      }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      errorMessage.value = payload.message || '路线模板登记失败'
      return
    }
    noticeMessage.value = payload.message
    templateForm.value = { 模板名称: '', 适用站点: '', 责任班组: '', 巡检点: '' }
    await loadTemplates()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '路线模板登记失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  const values: Record<string, string> = { action }
  if (action === '转派处置') {
    const team = window.prompt(`把「${row.任务编号}」发现的问题转派给哪个责任班组？`, String(row.处置班组 || ''))
    if (team === null) return
    values.处置班组 = team.trim()
  }
  if (action === '提交巡检') {
    const problem = window.prompt(`请填写「${row.任务编号}」本次巡检发现的问题（没有可留空）`, String(row.发现问题 || ''))
    if (problem === null) return
    values.发现问题 = problem.trim()
  }
  if (action === '处置完成') {
    const result = window.prompt(`请填写「${row.任务编号}」的处置结果，将写回巡检任务`, '')
    if (result === null) return
    values.处置结果 = result.trim()
  }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      errorMessage.value = payload.message || '巡检作业动作未生效'
      return
    }
    noticeMessage.value = payload.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '巡检作业操作失败'
  }
}

async function loadTemplates() {
  try {
    const response = await request(`${ENDPOINT}/templates`)
    if (!response.ok) {
      throw new Error('巡检路线模板读取失败')
    }
    const payload = await response.json()
    templates.value = payload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '巡检路线模板读取失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = buildQuery()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('巡检任务列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '巡检作业列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadTemplates()
})
</script>

<style scoped>
.panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
}
.panel-title {
  margin: 0 0 10px;
  font-size: 14px;
}
.panel-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--muted);
}
.filter-item select {
  min-width: 180px;
}
.notice-text {
  color: #067647;
}
</style>
