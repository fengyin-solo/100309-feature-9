<template>
  <section class="page" data-module="patrol">
    <header class="page-head">
      <div>
        <h2>巡检作业管理</h2>
        <p class="page-desc">巡检路线存成模板反复使用：按站点挑模板生成本期任务；巡检发现的问题一键转派责任班组，处置结果回写原任务闭环。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="openTemplateDialog">维护巡检路线模板</button>
        <button class="btn primary" type="button" @click="openGenerateDialog">按模板生成本期任务</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>任务编号</span>
        <input v-model="filters.keyword" placeholder="按任务编号检索" />
      </label>
      <label class="filter-item">
        <span>巡检站点</span>
        <input v-model="filters.site" list="site-options" placeholder="按巡检站点检索" />
      </label>
      <label class="filter-item">
        <span>巡检期次</span>
        <input v-model="filters.period" placeholder="如 2026-10" />
      </label>
      <label class="filter-item">
        <span>任务状态</span>
        <select v-model="filters.status">
          <option value="">全部</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <datalist id="site-options">
      <option v-for="site in siteOptions" :key="site" :value="site" />
    </datalist>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <span v-if="column === '处置状态'" class="status-tag" :class="handleTagClass(row[column])">{{ row[column] || '—' }}</span>
            <span v-else>{{ row[column] ?? '—' }}</span>
          </td>
          <td class="row-actions">
            <template v-for="action in actionsFor(row)" :key="action.key">
              <button
                v-if="action.type === 'link'"
                class="link"
                :class="{ danger: action.danger }"
                type="button"
                @click="onRowAction(action.key, row)"
              >
                {{ action.label }}
              </button>
              <span v-else class="muted-text">{{ action.label }}</span>
            </template>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无巡检任务，可点右上角「按模板生成本期任务」</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条巡检任务记录</span>
      <span v-if="message" :class="messageOk ? 'success-text' : 'error-text'">{{ message }}</span>
    </footer>

    <!-- 按模板生成任务 -->
    <div v-if="dialog === 'generate'" class="modal-mask" @click.self="closeDialog">
      <div class="modal">
        <h3>按模板生成本期巡检任务</h3>
        <p class="modal-tip">同站点同期重复生成只保留一条；该站点没有模板时会给出说明，不会生成空任务。</p>
        <label class="form-item">
          <span>巡检站点<i>*</i></span>
          <input v-model="generateForm.site" list="site-options" placeholder="选择或输入站点名称" />
        </label>
        <label class="form-item">
          <span>巡检期次<i>*</i></span>
          <input v-model="generateForm.period" placeholder="如 2026-10" />
        </label>
        <label class="form-item">
          <span>巡检人员<i>*</i></span>
          <input v-model="generateForm.inspector" placeholder="本期责任人" />
        </label>
        <label class="form-item">
          <span>计划日期</span>
          <input v-model="generateForm.planDate" type="date" />
        </label>
        <div class="matched-template">
          <template v-if="matchedTemplate">
            将套用模板「{{ matchedTemplate['模板名称'] }}」，巡检点顺序：
            <ol>
              <li v-for="point in matchedTemplate['巡检点']" :key="point">{{ point }}</li>
            </ol>
          </template>
          <span v-else-if="generateForm.site" class="error-text">该站点暂无可用模板，请先维护模板</span>
          <span v-else class="muted-text">选择站点后自动匹配该站点的巡检路线模板</span>
        </div>
        <div class="modal-actions">
          <button class="btn" type="button" @click="closeDialog">取消</button>
          <button class="btn primary" type="button" @click="submitGenerate">生成任务</button>
        </div>
      </div>
    </div>

    <!-- 维护模板 -->
    <div v-if="dialog === 'template'" class="modal-mask modal-wide" @click.self="closeDialog">
      <div class="modal">
        <h3>巡检路线模板</h3>
        <table class="data-table template-table">
          <thead>
            <tr><th>模板名称</th><th>适用站点</th><th>巡检点（按顺序）</th><th>备注</th></tr>
          </thead>
          <tbody>
            <tr v-for="tpl in templates" :key="String(tpl.id)">
              <td>{{ tpl['模板名称'] }}</td>
              <td>{{ tpl['适用站点'] }}</td>
              <td class="points-cell">{{ ((tpl['巡检点'] as string[]) || []).join(' → ') }}</td>
              <td>{{ tpl['备注'] || '—' }}</td>
            </tr>
            <tr v-if="!templates.length">
              <td colspan="4" class="empty-state">还没有模板，先在下面保存一条</td>
            </tr>
          </tbody>
        </table>
        <h4 class="form-subtitle">新增模板</h4>
        <label class="form-item">
          <span>模板名称<i>*</i></span>
          <input v-model="templateForm.name" placeholder="如：月度常规巡检模板" />
        </label>
        <label class="form-item">
          <span>适用站点<i>*</i></span>
          <input v-model="templateForm.site" list="site-options" placeholder="一个模板对应一个站点" />
        </label>
        <label class="form-item">
          <span>巡检点<i>*</i></span>
          <textarea v-model="templateForm.points" rows="5" placeholder="每行一个巡检点，按巡检先后顺序填写，如：&#10;门禁与机房环境&#10;开关电源与整流模块&#10;蓄电池组"></textarea>
        </label>
        <label class="form-item">
          <span>备注</span>
          <input v-model="templateForm.remark" placeholder="选填" />
        </label>
        <div class="modal-actions">
          <button class="btn" type="button" @click="closeDialog">关闭</button>
          <button class="btn primary" type="button" @click="submitTemplate">保存模板</button>
        </div>
      </div>
    </div>

    <!-- 转派处置 -->
    <div v-if="dialog === 'dispatch'" class="modal-mask" @click.self="closeDialog">
      <div class="modal">
        <h3>{{ dispatchForm.team ? '重新转派责任班组' : '发现问题 · 一键转派' }}</h3>
        <p class="modal-tip">任务：{{ dispatchForm.taskNo }}（{{ dispatchForm.site }}）</p>
        <label class="form-item">
          <span>发现问题<i>*</i></span>
          <textarea v-model="dispatchForm.problem" rows="3" placeholder="填写巡检发现的问题"></textarea>
        </label>
        <label class="form-item">
          <span>处置责任班组<i>*</i></span>
          <select v-model="dispatchForm.team">
            <option value="" disabled>请选择责任班组</option>
            <option v-for="team in teams" :key="team" :value="team">{{ team }}</option>
          </select>
        </label>
        <div class="modal-actions">
          <button class="btn" type="button" @click="closeDialog">取消</button>
          <button class="btn primary" type="button" @click="submitDispatch">确认转派</button>
        </div>
      </div>
    </div>

    <!-- 处置完成 -->
    <div v-if="dialog === 'finish'" class="modal-mask" @click.self="closeDialog">
      <div class="modal">
        <h3>处置完成 · 结果回写巡检任务</h3>
        <p class="modal-tip">任务：{{ finishForm.taskNo }} ｜ 处置班组：{{ finishForm.team }}</p>
        <label class="form-item">
          <span>发现问题</span>
          <div class="readonly-box">{{ finishForm.problem || '—' }}</div>
        </label>
        <label class="form-item">
          <span>处置措施与结果<i>*</i></span>
          <textarea v-model="finishForm.measure" rows="4" placeholder="填写处置措施与结果，提交后写回原巡检任务并转复查"></textarea>
        </label>
        <div class="modal-actions">
          <button class="btn" type="button" @click="closeDialog">取消</button>
          <button class="btn primary" type="button" @click="submitFinish">提交处置完成</button>
        </div>
      </div>
    </div>

    <!-- 处置轨迹 -->
    <div v-if="dialog === 'trace'" class="modal-mask" @click.self="closeDialog">
      <div class="modal">
        <h3>处置轨迹 · {{ traceForm.taskNo }}</h3>
        <ol v-if="traceForm.records.length" class="trace-list">
          <li v-for="(record, index) in traceForm.records" :key="index">
            <div class="trace-head">
              <span class="status-tag" :class="handleTagClass(record['状态'])">{{ record['状态'] }}</span>
              <strong>{{ record['班组'] || '巡检人员' }}</strong>
              <span class="muted-text">{{ record['时间'] }}</span>
            </div>
            <div v-if="record['问题']">问题：{{ record['问题'] }}</div>
            <div v-if="record['措施']">措施：{{ record['措施'] }}</div>
          </li>
        </ol>
        <p v-else class="empty-state">该任务暂无处置记录</p>
        <div class="modal-actions">
          <button class="btn primary" type="button" @click="closeDialog">知道了</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null | string[]>
type RecordItem = Record<string, string>

const ENDPOINT = '/api/patrol'
const columns = ['任务编号', '巡检站点', '巡检人员', '巡检期次', '计划日期', '巡检路线', '发现问题', '处置班组', '处置状态', '任务状态']
const statuses = ['待巡检', '巡检中', '待处置', '处置中', '待复查', '已关闭']

const rows = ref<Row[]>([])
const total = ref(0)
const templates = ref<Row[]>([])
const teams = ref<string[]>([])
const siteOptions = ref<string[]>([])
const message = ref('')
const messageOk = ref(true)
const filters = reactive({ keyword: '', site: '', period: '', status: '' })

const dialog = ref<'' | 'generate' | 'template' | 'dispatch' | 'finish' | 'trace'>('')

const generateForm = reactive({ site: '', period: currentPeriod(), inspector: '', planDate: '' })
const templateForm = reactive({ name: '', site: '', points: '', remark: '' })
const dispatchForm = reactive({ id: 0, taskNo: '', site: '', problem: '', team: '' })
const finishForm = reactive({ id: 0, taskNo: '', team: '', problem: '', measure: '' })
const traceForm = reactive<{ taskNo: string; records: RecordItem[] }>({ taskNo: '', records: [] })

function currentPeriod() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

const stats = computed(() => [
  { label: '待巡检 / 巡检中', value: countBy(['待巡检', '巡检中']) },
  { label: '待处置 / 处置中', value: countBy(['待处置', '处置中']) },
  { label: '待复查', value: countBy(['待复查']) },
  { label: '已闭环', value: countBy(['已关闭']) },
])

function countBy(targets: string[]) {
  return rows.value.filter((row) => targets.includes(String(row['任务状态'] ?? ''))).length
}

const matchedTemplate = computed(() => {
  const site = generateForm.site.trim()
  if (!site) return null
  return templates.value.find((tpl) => String(tpl['适用站点']) === site) ?? null
})

function handleTagClass(status: unknown) {
  return {
    'tag-wait': status === '待处置',
    'tag-doing': status === '处置中',
    'tag-done': status === '已处置',
  }
}

interface RowAction { key: string; label: string; type: 'link' | 'text'; danger?: boolean }

function actionsFor(row: Row): RowAction[] {
  const status = String(row['任务状态'] ?? '')
  const hasTeam = Boolean(String(row['处置班组'] ?? '').trim())
  switch (status) {
    case '待巡检':
      return [{ key: '开始巡检', label: '开始巡检', type: 'link' }]
    case '巡检中':
      return [
        { key: '转派处置', label: '发现问题转派', type: 'link', danger: true },
        { key: '提交巡检', label: '正常提交', type: 'link' },
      ]
    case '待处置':
      return [
        { key: '转派处置', label: hasTeam ? '重新转派' : '转派处置', type: 'link', danger: !hasTeam },
        ...(hasTeam ? [{ key: '班组接单', label: '班组接单', type: 'link' } as RowAction] : []),
        { key: 'trace', label: '处置轨迹', type: 'link' },
      ]
    case '处置中':
      return [
        { key: '处置完成', label: '处置完成回写', type: 'link' },
        { key: '转派处置', label: '重新转派', type: 'link' },
        { key: 'trace', label: '处置轨迹', type: 'link' },
      ]
    case '待复查':
      return [{ key: '复查关闭', label: '复查关闭', type: 'link' }, { key: 'trace', label: '处置轨迹', type: 'link' }]
    case '已关闭':
      return [{ key: 'trace', label: '处置轨迹', type: 'link' }, { key: 'closed', label: '已闭环', type: 'text' }]
    default:
      return []
  }
}

function resetFilters() {
  Object.assign(filters, { keyword: '', site: '', period: '', status: '' })
  void reload()
}

function closeDialog() {
  dialog.value = ''
}

function openGenerateDialog() {
  Object.assign(generateForm, { site: '', period: currentPeriod(), inspector: '', planDate: '' })
  dialog.value = 'generate'
}

async function openTemplateDialog() {
  await loadTemplates()
  Object.assign(templateForm, { name: '', site: '', points: '', remark: '' })
  dialog.value = 'template'
}

function onRowAction(key: string, row: Row) {
  if (key === 'trace') {
    traceForm.taskNo = String(row['任务编号'])
    traceForm.records = ((row['处置记录'] as unknown as RecordItem[] | undefined) ?? [])
    dialog.value = 'trace'
    return
  }
  if (key === '转派处置') {
    Object.assign(dispatchForm, {
      id: Number(row.id),
      taskNo: String(row['任务编号']),
      site: String(row['巡检站点']),
      problem: String(row['发现问题'] ?? ''),
      team: String(row['处置班组'] ?? ''),
    })
    dialog.value = 'dispatch'
    return
  }
  if (key === '处置完成') {
    Object.assign(finishForm, {
      id: Number(row.id),
      taskNo: String(row['任务编号']),
      team: String(row['处置班组'] ?? ''),
      problem: String(row['发现问题'] ?? ''),
      measure: String(row['处置措施'] ?? ''),
    })
    dialog.value = 'finish'
    return
  }
  void runSimpleAction(key, row)
}

async function runSimpleAction(action: string, row: Row, extra: Record<string, string> = {}) {
  await postAction(Number(row.id), { action, ...extra })
}

async function postAction(id: number, values: Record<string, string>) {
  try {
    const response = await request(`${ENDPOINT}/${id}/actions`, {
      method: 'POST',
      body: JSON.stringify(values),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.detail || payload.message || '操作未生效')
    }
    flash(payload.message, true)
    closeDialog()
    await reload()
  } catch (error) {
    flash(error instanceof Error ? error.message : '操作失败', false)
  }
}

async function submitGenerate() {
  try {
    const response = await request(`${ENDPOINT}/generate`, {
      method: 'POST',
      body: JSON.stringify({
        values: {
          巡检站点: generateForm.site.trim(),
          巡检期次: generateForm.period.trim(),
          巡检人员: generateForm.inspector.trim(),
          计划日期: generateForm.planDate,
        },
      }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.detail || payload.message)
    }
    // 重复生成时后端返回已有任务，同样按提示信息展示。
    flash(payload.message, true)
    closeDialog()
    await reload()
  } catch (error) {
    flash(error instanceof Error ? error.message : '生成失败', false)
  }
}

async function submitTemplate() {
  try {
    const response = await request(`${ENDPOINT}/templates`, {
      method: 'POST',
      body: JSON.stringify({
        values: {
          模板名称: templateForm.name.trim(),
          适用站点: templateForm.site.trim(),
          巡检点: templateForm.points,
          备注: templateForm.remark.trim(),
        },
      }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.detail || payload.message)
    }
    flash(payload.message, true)
    Object.assign(templateForm, { name: '', site: '', points: '', remark: '' })
    await loadTemplates()
  } catch (error) {
    flash(error instanceof Error ? error.message : '模板保存失败', false)
  }
}

function submitDispatch() {
  if (!dispatchForm.problem.trim() || !dispatchForm.team) {
    flash('请填写发现的问题并选择处置责任班组', false)
    return
  }
  void postAction(dispatchForm.id, {
    action: '转派处置',
    发现问题: dispatchForm.problem.trim(),
    处置班组: dispatchForm.team,
  })
}

function submitFinish() {
  if (!finishForm.measure.trim()) {
    flash('请填写处置措施与结果', false)
    return
  }
  void postAction(finishForm.id, { action: '处置完成', 处置措施: finishForm.measure.trim() })
}

function flash(text: string, ok: boolean) {
  message.value = text
  messageOk.value = ok
}

async function loadTemplates() {
  const response = await request(`${ENDPOINT}/templates`)
  const payload = await response.json()
  templates.value = payload.items ?? []
}

async function loadOptions() {
  const [optionsResp, sitesResp] = await Promise.all([
    request(`${ENDPOINT}/options`),
    request('/api/site?size=200'),
  ])
  if (optionsResp.ok) {
    const payload = await optionsResp.json()
    teams.value = payload.teams ?? []
  }
  if (sitesResp.ok) {
    const payload = await sitesResp.json()
    siteOptions.value = (payload.items ?? [])
      .map((item: Row) => String(item['基站名称'] ?? ''))
      .filter(Boolean)
  }
  await loadTemplates()
  // 模板里出现的站点也补进站点候选，避免示例站点选不到。
  const extra = templates.value.map((tpl) => String(tpl['适用站点'] ?? ''))
  siteOptions.value = Array.from(new Set([...siteOptions.value, ...extra])).filter(Boolean)
}

async function reload() {
  const query = new URLSearchParams({
    size: '200',
    ...(filters.keyword ? { keyword: filters.keyword.trim() } : {}),
    ...(filters.site ? { site: filters.site.trim() } : {}),
    ...(filters.period ? { period: filters.period.trim() } : {}),
    ...(filters.status ? { status: filters.status } : {}),
  }).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('巡检任务列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    flash(error instanceof Error ? error.message : '巡检作业列表读取失败', false)
  }
}

onMounted(async () => {
  try {
    await loadOptions()
  } catch (error) {
    flash(error instanceof Error ? error.message : '基础数据加载失败', false)
  }
  await reload()
})
</script>

<style scoped>
.muted-text { color: var(--muted); font-size: 12px; }
.success-text { color: #067647; }
.link.danger { color: #b42318; }

.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.modal {
  width: 480px;
  max-height: 86vh;
  overflow-y: auto;
  background: #fff;
  border-radius: 10px;
  padding: 20px 22px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.2);
}
.modal-wide .modal { width: 760px; }
.modal h3 { margin: 0 0 6px; font-size: 16px; }
.modal-tip { margin: 0 0 12px; color: var(--muted); font-size: 12px; }
.form-subtitle { margin: 16px 0 8px; font-size: 14px; }
.form-item { display: block; margin-bottom: 12px; font-size: 13px; }
.form-item > span { display: block; margin-bottom: 4px; color: #334155; }
.form-item i { color: #b42318; font-style: normal; margin-left: 2px; }
.form-item input,
.form-item select,
.form-item textarea {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 7px 9px;
  font: inherit;
}
.form-item textarea { resize: vertical; }
.readonly-box {
  background: #f8fafc;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 7px 9px;
  color: #334155;
  font-size: 13px;
}
.matched-template {
  border: 1px dashed var(--border);
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 12px;
  color: #334155;
  margin-bottom: 12px;
}
.matched-template ol { margin: 6px 0 0; padding-left: 18px; }
.matched-template li { margin: 2px 0; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }

.template-table { margin-bottom: 8px; }
.points-cell { max-width: 300px; }

.status-tag {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 12px;
  background: #e2e8f0;
  color: #475569;
}
.tag-wait { background: #fee4e2; color: #b42318; }
.tag-doing { background: #fef0c7; color: #b54708; }
.tag-done { background: #d1fadf; color: #067647; }

.trace-list { list-style: none; margin: 0; padding: 0; }
.trace-list li {
  border-left: 3px solid var(--brand);
  padding: 6px 10px;
  margin-bottom: 10px;
  background: #f8fafc;
  border-radius: 0 6px 6px 0;
  font-size: 13px;
}
.trace-head { display: flex; gap: 8px; align-items: center; margin-bottom: 4px; }
</style>
