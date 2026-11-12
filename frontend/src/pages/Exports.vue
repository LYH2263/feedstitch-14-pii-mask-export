<script setup>
import { computed, onMounted, ref } from 'vue'
import { getJSON, postJSON, putJSON } from '../api'

const MASK_TYPES = [
  { value: 'none', label: 'none（不脱敏）' },
  { value: 'keep_edges', label: 'keep_edges（保留首尾，中间打码）' },
  { value: 'blank', label: 'blank（置空）' },
  { value: 'hash', label: 'hash（sha256 摘要）' },
]

const rules = ref([])
const batches = ref([])
const last = ref(null)
const detail = ref(null)
const detailRows = ref([])
const err = ref('')
const busy = ref(false)
const savedField = ref('')

async function loadRules() {
  rules.value = await getJSON('/api/export/rules')
}

async function loadBatches() {
  batches.value = await getJSON('/api/export/batches')
}

async function saveRule(rule) {
  err.value = ''
  savedField.value = ''
  try {
    await putJSON(`/api/export/rules/${encodeURIComponent(rule.field)}`, {
      mask_type: rule.mask_type,
      keep_head: Number(rule.keep_head) || 0,
      keep_tail: Number(rule.keep_tail) || 0,
    })
    savedField.value = rule.field
    await loadRules()
  } catch (e) {
    err.value = String(e.message || e)
  }
}

async function runExport() {
  err.value = ''
  busy.value = true
  try {
    last.value = await postJSON('/api/export/batches', {})
    await loadBatches()
    await openBatch(last.value.id)
  } catch (e) {
    err.value = String(e.message || e)
  } finally {
    busy.value = false
  }
}

async function openBatch(id) {
  detail.value = await getJSON(`/api/export/batches/${id}`)
  detailRows.value = await getJSON(`/api/export/batches/${id}/rows`)
}

function reconciled(b) {
  return (
    b.candidate_count === b.exported_count + b.skipped_count + b.failed_count &&
    b.report?.manifest_count === b.candidate_count &&
    b.report?.canonical_count === b.candidate_count
  )
}

const detailReconcile = computed(() => {
  if (!detail.value) return ''
  const b = detail.value
  return `候选 ${b.candidate_count} = 导出 ${b.exported_count} + 跳过 ${b.skipped_count} + 失败 ${b.failed_count}`
    + `；Canonical 总数 ${b.report?.canonical_count}；清单条数 ${b.report?.manifest_count}`
})

onMounted(async () => {
  try {
    await Promise.all([loadRules(), loadBatches()])
  } catch (e) {
    err.value = String(e.message || e)
  }
})
</script>
<template>
  <div class="page">
    <h1>脱敏导出</h1>
    <p class="muted">
      配置字段脱敏规则 → 发起导出批次（写出脱敏文件 + 批次清单）→ 与 Canonical 对账。
      导出只读主数据，Canonical 页始终为明文。
    </p>
    <p v-if="err" class="tag danger">{{ err }}</p>

    <div class="panel">
      <h3>脱敏规则</h3>
      <p class="muted">业务键 business_key 始终明文保留用于对账；其余字段可按下表配置，保存后下一批次生效。</p>
      <table>
        <thead>
          <tr><th>字段</th><th>规则</th><th>保留首</th><th>保留尾</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="r in rules" :key="r.field">
            <td class="mono">{{ r.field }}</td>
            <td>
              <select v-model="r.mask_type">
                <option v-for="t in MASK_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
              </select>
            </td>
            <td><input type="number" min="0" max="64" v-model.number="r.keep_head" :disabled="r.mask_type !== 'keep_edges'" style="width:4.5rem" /></td>
            <td><input type="number" min="0" max="64" v-model.number="r.keep_tail" :disabled="r.mask_type !== 'keep_edges'" style="width:4.5rem" /></td>
            <td>
              <button class="secondary" @click="saveRule(r)">保存</button>
              <span v-if="savedField === r.field" class="tag ok" style="margin-left:0.5rem">已保存</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="panel">
      <h3>发起导出</h3>
      <button :disabled="busy" @click="runExport">{{ busy ? '导出中…' : '导出当前 Canonical' }}</button>
      <template v-if="last">
        <p style="margin-top:0.75rem">
          批次 #{{ last.id }} · <span class="tag" :class="last.status === 'ok' ? 'ok' : 'danger'">{{ last.status }}</span> ·
          候选 {{ last.candidate_count }} / 导出 {{ last.exported_count }} / 跳过 {{ last.skipped_count }} / 失败 {{ last.failed_count }}
          <span class="tag" :class="reconciled(last) ? 'ok' : 'danger'" style="margin-left:0.5rem">
            {{ reconciled(last) ? '对账一致' : '对账不符' }}
          </span>
        </p>
        <p class="mono muted">文件 {{ last.report?.file }} · Canonical 总数 {{ last.report?.canonical_count }} · 清单条数 {{ last.report?.manifest_count }}</p>
      </template>
    </div>

    <div class="panel">
      <h3>导出批次</h3>
      <table>
        <thead>
          <tr>
            <th>ID</th><th>状态</th><th>候选</th><th>导出</th><th>跳过</th><th>失败</th><th>对账</th><th>时间</th><th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="b in batches" :key="b.id">
            <td>{{ b.id }}</td>
            <td><span class="tag" :class="b.status === 'ok' ? 'ok' : 'danger'">{{ b.status }}</span></td>
            <td>{{ b.candidate_count }}</td>
            <td>{{ b.exported_count }}</td>
            <td>{{ b.skipped_count }}</td>
            <td>{{ b.failed_count }}</td>
            <td><span class="tag" :class="reconciled(b) ? 'ok' : 'danger'">{{ reconciled(b) ? '一致' : '不符' }}</span></td>
            <td class="mono">{{ b.created_at }}</td>
            <td>
              <button class="secondary" @click="openBatch(b.id)">清单</button>
              <a v-if="b.file_path" :href="`/api/export/batches/${b.id}/download`" style="margin-left:0.5rem">下载</a>
            </td>
          </tr>
          <tr v-if="!batches.length"><td colspan="9" class="muted">暂无批次</td></tr>
        </tbody>
      </table>
    </div>

    <div class="panel" v-if="detail">
      <h3>批次 #{{ detail.id }} 清单</h3>
      <p class="mono muted">{{ detailReconcile }}</p>
      <p class="mono muted">规则快照：{{ JSON.stringify(detail.rules) }}</p>
      <table>
        <thead>
          <tr><th>业务键</th><th>处置</th><th>脱敏后字段摘要</th><th>备注</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in detailRows" :key="r.id">
            <td class="mono">{{ r.business_key || '(空)' }}</td>
            <td>
              <span class="tag" :class="r.disposition === 'exported' ? 'ok' : (r.disposition === 'failed' ? 'danger' : 'warn')">
                {{ r.disposition }}
              </span>
            </td>
            <td class="mono">{{ r.masked ? JSON.stringify(r.masked) : '—' }}</td>
            <td class="muted">{{ r.note || '' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
