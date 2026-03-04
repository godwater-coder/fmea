<template>
  <div style="padding: 16px">
    <el-card>
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center; gap: 12px">
          <span>FMEA 问答</span>
          <el-link
            type="primary"
            :underline="false"
            href="http://127.0.0.1:8080/api/v1/question-answer"
            target="_blank"
          >
            后端接口
          </el-link>
        </div>
      </template>

      <el-form label-position="top" @submit.prevent>
        <el-form-item label="问题">
          <el-input
            v-model="question"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }"
            placeholder="例如：RPN最低的失效模式是什么？"
            @keydown.enter.exact.prevent="submit"
          />
        </el-form-item>

        <div style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap">
          <el-button type="primary" :loading="loading" @click="submit">提问</el-button>
          <el-button :disabled="loading" @click="reset">清空</el-button>
          <el-button type="danger" plain :disabled="loading" @click="clearDb">清空数据库</el-button>
          <el-text v-if="apiBase" type="info">API Base：{{ apiBase }}</el-text>
        </div>

        <el-alert
          v-if="error"
          style="margin-top: 12px"
          type="error"
          :closable="true"
          show-icon
          :title="error"
        />

        <div v-if="result" style="margin-top: 16px">
          <el-divider content-position="left">回答</el-divider>
          <el-card shadow="never">
            <div style="white-space: pre-wrap">{{ result.answer }}</div>
            <div v-if="result.answer_file" style="margin-top: 8px">
              <el-text type="info">答案文件：{{ result.answer_file }}</el-text>
            </div>
          </el-card>

          <el-divider content-position="left">上下文（摘要）</el-divider>
          <el-collapse>
            <el-collapse-item
              v-for="(item, idx) in (result.context || [])"
              :key="idx"
              :title="`#${idx + 1}`"
              :name="String(idx)"
            >
              <div style="white-space: pre-wrap">{{ item }}</div>
            </el-collapse-item>
          </el-collapse>

          <el-divider content-position="left">原始检索结果（JSON）</el-divider>
          <el-input
            :model-value="prettyContextRaw"
            type="textarea"
            :autosize="{ minRows: 6, maxRows: 16 }"
            readonly
          />
        </div>
      </el-form>
    </el-card>
  </div>
</template>

<script setup name="FmeaQa">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const question = ref('')
const loading = ref(false)
const error = ref('')
const result = ref(null)

const apiBase = computed(() => {
  // 推荐：开发环境使用 Vite 代理（见 VITE_FMEA_API_BASE=/fmea-api）
  // 生产环境可改为同域反代路径，或直接指向后端地址。
  const v = import.meta.env.VITE_FMEA_API_BASE
  if (v && String(v).trim()) return String(v).trim().replace(/\/$/, '')

  // 兜底：默认取当前 host 的 8080 端口
  const { protocol, hostname } = window.location
  return `${protocol}//${hostname}:8080`
})

const prettyContextRaw = computed(() => {
  if (!result.value) return ''
  try {
    return JSON.stringify(result.value.context_raw ?? null, null, 2)
  } catch {
    return String(result.value.context_raw ?? '')
  }
})

async function submit() {
  const q = String(question.value || '').trim()
  if (!q) {
    error.value = '请输入问题'
    return
  }

  loading.value = true
  error.value = ''
  result.value = null

  try {
    const resp = await fetch(`${apiBase.value}/api/v1/question-answer`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ question: q })
    })

    const text = await resp.text()
    let data
    try {
      data = text ? JSON.parse(text) : null
    } catch {
      data = text
    }

    if (!resp.ok) {
      // kg-rag 后端错误返回遵循 RFC7807-ish：{title, detail, status}
      const detail = data && typeof data === 'object' ? (data.detail || data.title) : ''
      throw new Error(detail ? String(detail) : `请求失败：HTTP ${resp.status}`)
    }

    result.value = data
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

function reset() {
  question.value = ''
  error.value = ''
  result.value = null
}

async function clearDb() {
  try {
    await ElMessageBox.confirm(
      '将清空 Neo4j 中本项目导入的 FMEA 数据与索引（不可恢复）。确定继续吗？',
      '确认清空',
      {
        confirmButtonText: '清空',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
  } catch {
    return
  }

  loading.value = true
  error.value = ''
  try {
    const resp = await fetch(`${apiBase.value}/api/v1/clear-fmea-graph`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirm: true })
    })

    const text = await resp.text()
    let data
    try {
      data = text ? JSON.parse(text) : null
    } catch {
      data = text
    }

    if (!resp.ok) {
      const detail = data && typeof data === 'object' ? (data.detail || data.title) : ''
      throw new Error(detail ? String(detail) : `请求失败：HTTP ${resp.status}`)
    }

    reset()
    ElMessage.success('已清空数据库（FMEA 图谱）')
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}
</script>
