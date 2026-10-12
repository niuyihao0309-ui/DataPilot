<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue'
import axios from 'axios'
import { marked } from 'marked'

// 后端地址：与现有 App.vue 一致直连；如需改端口只改这一处
const BACKEND = 'http://localhost:8005'
const WS_BACKEND = 'ws://localhost:8005'
const API = BACKEND

interface LogItem {
  type: string
  title: string
  details: any
  timestamp: string
}
interface FileItem {
  name: string
  path: string
  url: string
}
interface Message {
  role: 'user' | 'ai' | 'system'
  content: string
  logs?: LogItem[]
  files?: FileItem[]
  error?: { hint?: string; raw?: string }
  timestamp?: number
}

const inputQuery = ref('')
const messages = ref<Message[]>([])
const status = ref<'idle' | 'running'>('idle')
const socket = ref<WebSocket | null>(null)
const wsState = ref<'connecting' | 'open' | 'closed'>('connecting')
const currentSessionPath = ref('')
const messagesEndRef = ref<HTMLElement | null>(null)
const isSidebarOpen = ref(false)
const fileList = ref<any[]>([])
const currentThreadId = ref(crypto.randomUUID())
const isWelcomeScreen = computed(() => messages.value.length === 0)

const scrollToBottom = async () => {
  await nextTick()
  messagesEndRef.value?.scrollIntoView({ behavior: 'smooth' })
}

const fetchFiles = async () => {
  if (!currentSessionPath.value) return
  try {
    const res = await axios.get(`${API}/api/files`, { params: { path: currentSessionPath.value } })
    if (res.data.files) {
      fileList.value = res.data.files.map((f: any) => ({
        ...f,
        url: `${API}/api/download?path=${encodeURIComponent(f.path)}`
      }))
    }
  } catch (e) {
    console.error('Failed to fetch files', e)
  }
}

const connectWebSocket = () => {
  const ws = new WebSocket(`${WS_BACKEND}/ws/${currentThreadId.value}`)
  ws.onopen = () => { wsState.value = 'open' }
  ws.onmessage = (event) => {
    try { handleSocketMessage(JSON.parse(event.data)) }
    catch (e) { console.error('Error parsing WS message:', e) }
  }
  ws.onclose = () => {
    wsState.value = 'closed'
    setTimeout(connectWebSocket, 3000)
  }
  socket.value = ws
}

const handleSocketMessage = (data: any) => {
  const { type, event, message, data: eventData } = data
  if (type === 'pong') return

  const lastAiMsg = messages.value.slice().reverse().find(m => m.role === 'ai')

  if (event === 'session_created') {
    currentSessionPath.value = eventData.path
    isSidebarOpen.value = true
    fetchFiles()
  } else if (event === 'tool_start') {
    if (currentSessionPath.value) { fetchFiles(); setTimeout(fetchFiles, 2000) }
    if (lastAiMsg) {
      if (!lastAiMsg.logs) lastAiMsg.logs = []
      lastAiMsg.logs.push({
        type: 'tool',
        title: `调用工具 · ${eventData.tool_name}`,
        details: eventData.args,
        timestamp: new Date().toLocaleTimeString()
      })
    }
  } else if (event === 'assistant_call') {
    if (currentSessionPath.value) fetchFiles()
    if (lastAiMsg) {
      if (!lastAiMsg.logs) lastAiMsg.logs = []
      lastAiMsg.logs.push({
        type: 'agent',
        title: `调用助手 · ${eventData.assistant_name}`,
        details: eventData.args,
        timestamp: new Date().toLocaleTimeString()
      })
    }
  } else if (event === 'task_result') {
    if (lastAiMsg) lastAiMsg.content = eventData.result
    else messages.value.push({ role: 'ai', content: eventData.result, timestamp: Date.now() })
    status.value = 'idle'
    fetchFiles()
  } else if (event === 'error') {
    if (lastAiMsg && !lastAiMsg.content) {
      lastAiMsg.content = message
      lastAiMsg.error = { hint: eventData?.hint, raw: eventData?.raw }
    } else {
      messages.value.push({ role: 'system', content: message, timestamp: Date.now() })
    }
    status.value = 'idle'
  }
  scrollToBottom()
}

const selectedFiles = ref<File[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)

const sendMessage = async () => {
  if ((!inputQuery.value.trim() && selectedFiles.value.length === 0) || status.value === 'running') return
  const query = inputQuery.value
  inputQuery.value = ''
  status.value = 'running'
  autoResize()

  messages.value.push({ role: 'user', content: query, timestamp: Date.now() })
  const aiMsg: Message = { role: 'ai', content: '', logs: [], files: [], timestamp: Date.now() }
  messages.value.push(aiMsg)
  scrollToBottom()

  const lastAiMsg = aiMsg

  if (selectedFiles.value.length > 0) {
    try {
      const formData = new FormData()
      formData.append('thread_id', currentThreadId.value)
      selectedFiles.value.forEach(f => formData.append('files', f))
      await axios.post(`${API}/api/upload`, formData, { headers: { 'Content-Type': 'multipart/form-data' } })
      lastAiMsg.logs = lastAiMsg.logs || []
      lastAiMsg.logs.push({ type: 'success', title: `已上传 ${selectedFiles.value.length} 个文件`, details: null, timestamp: new Date().toLocaleTimeString() })
      selectedFiles.value = []
    } catch (e: any) {
      lastAiMsg.logs = lastAiMsg.logs || []
      lastAiMsg.logs.push({ type: 'error', title: '文件上传失败', details: e.message, timestamp: new Date().toLocaleTimeString() })
    }
  }

  try {
    const res = await axios.post(`${API}/api/task`, { query, thread_id: currentThreadId.value })
    if (res.data?.thread_id) currentThreadId.value = res.data.thread_id
  } catch (error: any) {
    messages.value.push({ role: 'system', content: `请求失败：${error.message}`, timestamp: Date.now() })
    status.value = 'idle'
  }
}

const triggerFileUpload = () => fileInputRef.value?.click()
const handleFileChange = (e: Event) => {
  const t = e.target as HTMLInputElement
  if (t.files?.length) {
    selectedFiles.value = [...selectedFiles.value, ...Array.from(t.files)]
    t.value = ''
  }
}
const removeFile = (i: number) => selectedFiles.value.splice(i, 1)

const autoResize = () => {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 180) + 'px'
}

const renderMarkdown = (text: string) => {
  if (!text) return ''
  return marked.parse(text) as string
}

const newSession = () => {
  messages.value = []
  fileList.value = []
  currentSessionPath.value = ''
  isSidebarOpen.value = false
  status.value = 'idle'
  currentThreadId.value = crypto.randomUUID()
  socket.value?.close()
  connectWebSocket()
}

const quickQuestions = [
  '把 drugs 表的前 10 行数据展示给我',
  '查询库存最少的 10 种药品',
  '统计各治疗领域的药品数量',
  '生成一份库存预警清单 Markdown'
]

const askQuick = (q: string) => {
  inputQuery.value = q
  sendMessage()
}

onMounted(connectWebSocket)
onUnmounted(() => socket.value?.close())
</script>

<template>
  <div class="bz-app">
    <!-- 顶栏 -->
    <header class="bz-topbar">
      <div class="bz-brand">
        <span class="bz-brand-text">数据分析 · 智能体工作台</span>
      </div>
      <div class="bz-topbar-right">
        <span class="bz-status" :class="wsState">
          <i class="dot"></i>
          {{ wsState === 'open' ? '已连接' : wsState === 'connecting' ? '连接中' : '重连中' }}
        </span>
        <button class="bz-ghost-btn" @click="newSession">新会话</button>
      </div>
    </header>

    <div class="bz-body">
      <!-- 主对话区 -->
      <main class="bz-main">
        <div class="bz-scroll">
          <!-- 欢迎屏：标题 + 可点击常问问题 -->
          <div v-if="isWelcomeScreen" class="bz-welcome">
            <h1>有什么可以帮您？</h1>
            <p>输入指令，智能体将调用数据库、检索与文档工具完成任务。</p>
            <div class="bz-quick">
              <button v-for="q in quickQuestions" :key="q" class="bz-quick-btn" @click="askQuick(q)">
                {{ q }}
              </button>
            </div>
          </div>

          <div v-else class="bz-thread">
            <div v-for="(msg, index) in messages" :key="index" class="bz-msg" :class="msg.role">
              <!-- 用户 -->
              <div v-if="msg.role === 'user'" class="bz-user-row">
                <div class="bz-bubble">{{ msg.content }}</div>
              </div>

              <!-- 系统 -->
              <div v-else-if="msg.role === 'system'" class="bz-system">{{ msg.content }}</div>

              <!-- AI -->
              <div v-else class="bz-ai-row">
                <div class="bz-ai-main">
                  <!-- 执行过程 -->
                  <details v-if="msg.logs && msg.logs.length" class="bz-process"
                           :open="status === 'running' && index === messages.length - 1">
                    <summary>
                      <span v-if="status === 'running' && index === messages.length - 1" class="bz-spinner"></span>
                      <span v-else class="bz-check">✓</span>
                      执行过程 · {{ msg.logs.length }} 步
                    </summary>
                    <div class="bz-steps">
                      <div v-for="(log, i) in msg.logs" :key="i" class="bz-step">
                        <div class="bz-step-title">{{ log.title }}</div>
                        <pre v-if="log.details">{{ JSON.stringify(log.details, null, 2) }}</pre>
                      </div>
                    </div>
                  </details>

                  <!-- 思考中占位 -->
                  <div v-if="!msg.content && status === 'running'" class="bz-thinking">
                    <span class="bz-spinner"></span> 正在处理…
                  </div>

                  <!-- 正文 -->
                  <div v-if="msg.content" class="bz-markdown" v-html="renderMarkdown(msg.content)"></div>

                  <!-- 错误详情 -->
                  <div v-if="msg.error?.raw" class="bz-error">
                    <strong>{{ msg.error.hint || '执行出错' }}</strong>
                    <pre>{{ msg.error.raw }}</pre>
                  </div>
                </div>
              </div>
            </div>
            <div ref="messagesEndRef"></div>
          </div>
        </div>

        <!-- 输入区 -->
        <footer class="bz-composer">
          <div v-if="selectedFiles.length" class="bz-attachments">
            <span v-for="(f, i) in selectedFiles" :key="i" class="bz-chip">
              {{ f.name }}
              <button @click="removeFile(i)">×</button>
            </span>
          </div>
          <p class="bz-composer-hint">可生成文件</p>
          <div class="bz-input-bar">
            <input ref="fileInputRef" type="file" multiple hidden @change="handleFileChange" />
            <button class="bz-icon-btn" @click="triggerFileUpload" :disabled="status === 'running'" title="上传文件">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
            </button>
            <textarea
              ref="textareaRef"
              v-model="inputQuery"
              @input="autoResize"
              @keydown.enter.exact.prevent="sendMessage"
              rows="1"
              placeholder="输入指令，Enter 发送…"
              :disabled="status === 'running'"
            ></textarea>
            <button class="bz-send" @click="sendMessage"
                    :disabled="(!inputQuery.trim() && !selectedFiles.length) || status === 'running'">
              发送
            </button>
          </div>
        </footer>
      </main>

      <!-- 右侧文件面板 -->
      <aside v-if="isSidebarOpen" class="bz-sidebar">
        <div class="bz-sidebar-head">
          <span>会话文件</span>
          <div class="bz-sidebar-actions">
            <button class="bz-icon-btn sm" @click="fetchFiles" title="刷新">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
            </button>
            <button class="bz-icon-btn sm" @click="isSidebarOpen = false" title="关闭">×</button>
          </div>
        </div>
        <div class="bz-filelist">
          <p v-if="!fileList.length" class="bz-empty">暂无生成文件</p>
          <a v-for="f in fileList" :key="f.path" :href="f.url" :download="f.name" target="_blank" class="bz-file">
            <span class="bz-file-name">{{ f.name }}</span>
            <span class="bz-file-size">{{ (f.size / 1024).toFixed(1) }} KB</span>
          </a>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.bz-app {
  --bg: #f4f5f7;
  --surface: #ffffff;
  --border: #e6e8eb;
  --text: #1f2733;
  --text-2: #6b7684;
  --accent: #1d4ed8;
  --accent-soft: #eef2ff;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, "Segoe UI", "Microsoft YaHei", Roboto, Helvetica, Arial, sans-serif;
  font-size: 14px;
}

/* 顶栏 */
.bz-topbar {
  height: 56px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 20px; background: var(--surface);
  border-bottom: 1px solid var(--border);
}
.bz-brand { display: flex; align-items: center; }
.bz-brand-text { font-size: 15px; font-weight: 600; color: var(--text); }
.bz-topbar-right { display: flex; align-items: center; gap: 14px; }
.bz-status { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-2); }
.bz-status .dot { width: 7px; height: 7px; border-radius: 50%; background: #cbd2d9; }
.bz-status.open .dot { background: #22c55e; }
.bz-status.connecting .dot { background: #f59e0b; }
.bz-status.closed .dot { background: #ef4444; }
.bz-ghost-btn {
  padding: 7px 14px; border-radius: 7px; cursor: pointer;
  border: 1px solid var(--border); background: var(--surface); color: var(--text);
  font-size: 13px; transition: .15s;
}
.bz-ghost-btn:hover { border-color: var(--accent); color: var(--accent); }

/* 主体 */
.bz-body { flex: 1; display: flex; min-height: 0; }
.bz-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.bz-scroll { flex: 1; overflow-y: auto; padding: 28px 20px; }

/* 欢迎屏 */
.bz-welcome { max-width: 760px; margin: 12vh auto 0; text-align: center; }
.bz-welcome h1 { font-size: 26px; font-weight: 600; margin: 0 0 8px; }
.bz-welcome p { color: var(--text-2); margin: 0; }
.bz-quick { margin-top: 26px; display: flex; flex-wrap: wrap; gap: 10px; justify-content: center; }
.bz-quick-btn {
  padding: 9px 16px; border-radius: 999px; cursor: pointer; font-size: 13px;
  border: 1px solid var(--border); background: var(--surface); color: var(--text); transition: .15s;
}
.bz-quick-btn:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }

/* 会话流 */
.bz-thread { max-width: 760px; margin: 0 auto; display: flex; flex-direction: column; gap: 22px; }
.bz-user-row { display: flex; justify-content: flex-end; }
.bz-bubble {
  max-width: 78%; background: var(--accent); color: #fff;
  padding: 10px 15px; border-radius: 12px 12px 3px 12px; line-height: 1.6; white-space: pre-wrap;
}
.bz-system { text-align: center; color: var(--text-2); font-size: 12px; }
.bz-ai-row { display: flex; }
.bz-ai-main { flex: 1; min-width: 0; }

/* 执行过程 */
.bz-process { margin-bottom: 10px; border: 1px solid var(--border); border-radius: 9px; background: var(--surface); overflow: hidden; }
.bz-process summary {
  cursor: pointer; list-style: none; padding: 9px 13px;
  font-size: 12.5px; color: var(--text-2); display: flex; align-items: center; gap: 8px; user-select: none;
}
.bz-process summary::-webkit-details-marker { display: none; }
.bz-check { color: #22c55e; font-weight: 700; }
.bz-steps { border-top: 1px solid var(--border); padding: 6px 13px 10px; }
.bz-step { padding: 7px 0; border-bottom: 1px dashed var(--border); }
.bz-step:last-child { border-bottom: none; }
.bz-step-title { font-size: 12.5px; color: var(--text); }
.bz-step pre {
  margin: 6px 0 0; background: #f7f8fa; border-radius: 6px; padding: 8px 10px;
  font-size: 11.5px; color: var(--text-2); overflow-x: auto;
}

.bz-thinking { display: flex; align-items: center; gap: 8px; color: var(--text-2); font-size: 13px; }
.bz-spinner {
  width: 12px; height: 12px; border: 2px solid var(--border); border-top-color: var(--accent);
  border-radius: 50%; animation: bz-spin .8s linear infinite; flex-shrink: 0;
}
@keyframes bz-spin { to { transform: rotate(360deg); } }

/* 正文 markdown */
.bz-markdown { line-height: 1.75; font-size: 14px; overflow-x: auto; }
.bz-markdown :deep(h1), .bz-markdown :deep(h2), .bz-markdown :deep(h3) { font-weight: 600; margin: 16px 0 8px; }
.bz-markdown :deep(p) { margin: 8px 0; }
.bz-markdown :deep(code) { background: var(--accent-soft); padding: 1px 5px; border-radius: 4px; font-size: 12.5px; }
.bz-markdown :deep(pre) { background: #f7f8fa; border: 1px solid var(--border); padding: 12px 14px; border-radius: 8px; overflow-x: auto; }
.bz-markdown :deep(pre code) { background: none; padding: 0; }
.bz-markdown :deep(table) { border-collapse: collapse; width: 100%; min-width: 1000px; margin: 12px 0; font-size: 13px; }
.bz-markdown :deep(th), .bz-markdown :deep(td) { border: 1px solid var(--border); padding: 8px 11px; text-align: left; vertical-align: top; }
.bz-markdown :deep(th) { background: var(--accent-soft); font-weight: 600; }
.bz-markdown :deep(tr:nth-child(even) td) { background: #fafbfc; }
.bz-markdown :deep(a) { color: var(--accent); }
.bz-markdown :deep(ul), .bz-markdown :deep(ol) { padding-left: 22px; margin: 8px 0; }

.bz-error { margin-top: 10px; border: 1px solid #fecaca; background: #fef2f2; border-radius: 8px; padding: 10px 12px; }
.bz-error strong { color: #b91c1c; font-size: 13px; }
.bz-error pre { margin: 6px 0 0; font-size: 11.5px; color: #991b1b; white-space: pre-wrap; }

/* 输入区 */
.bz-composer { flex-shrink: 0; padding: 12px 20px 18px; background: linear-gradient(transparent, var(--bg) 30%); }
.bz-composer-hint { max-width: 760px; margin: 0 auto 6px; font-size: 12px; color: var(--text-2); }
.bz-attachments { max-width: 760px; margin: 0 auto 8px; display: flex; flex-wrap: wrap; gap: 8px; }
.bz-chip {
  display: flex; align-items: center; gap: 6px; background: var(--surface);
  border: 1px solid var(--border); border-radius: 7px; padding: 4px 8px; font-size: 12px;
}
.bz-chip button { border: none; background: none; cursor: pointer; color: var(--text-2); font-size: 14px; line-height: 1; }
.bz-input-bar {
  max-width: 760px; margin: 0 auto; display: flex; align-items: flex-end; gap: 8px;
  background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 8px 10px;
  transition: border-color .15s, box-shadow .15s;
}
.bz-input-bar:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.bz-input-bar textarea {
  flex: 1; border: none; outline: none; resize: none; background: transparent;
  color: var(--text); font-family: inherit; font-size: 14px; line-height: 1.5; max-height: 180px; padding: 6px 2px;
}
.bz-icon-btn {
  border: none; background: none; cursor: pointer; color: var(--text-2);
  width: 34px; height: 34px; border-radius: 8px; display: grid; place-items: center; transition: .15s; flex-shrink: 0;
}
.bz-icon-btn:hover:not(:disabled) { background: var(--accent-soft); color: var(--accent); }
.bz-icon-btn:disabled { opacity: .4; cursor: default; }
.bz-icon-btn.sm { width: 26px; height: 26px; font-size: 16px; }
.bz-send {
  border: none; cursor: pointer; background: var(--accent); color: #fff;
  padding: 8px 18px; border-radius: 8px; font-size: 13px; font-weight: 500; transition: .15s; flex-shrink: 0;
}
.bz-send:hover:not(:disabled) { background: #1e40af; }
.bz-send:disabled { background: #c7ced6; cursor: default; }

/* 侧栏 */
.bz-sidebar {
  width: 280px; flex-shrink: 0; background: var(--surface);
  border-left: 1px solid var(--border); display: flex; flex-direction: column;
}
.bz-sidebar-head {
  height: 48px; flex-shrink: 0; padding: 0 14px; display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid var(--border); font-weight: 600; font-size: 13px;
}
.bz-sidebar-actions { display: flex; gap: 4px; }
.bz-filelist { flex: 1; overflow-y: auto; padding: 10px; }
.bz-empty { color: var(--text-2); text-align: center; font-size: 12.5px; margin-top: 30px; }
.bz-file {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 9px 11px; border-radius: 8px; text-decoration: none; color: var(--text); transition: .15s;
}
.bz-file:hover { background: var(--accent-soft); }
.bz-file-name { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bz-file-size { font-size: 11px; color: var(--text-2); flex-shrink: 0; }

.bz-scroll::-webkit-scrollbar, .bz-filelist::-webkit-scrollbar { width: 8px; }
.bz-scroll::-webkit-scrollbar-thumb, .bz-filelist::-webkit-scrollbar-thumb { background: #d5dae0; border-radius: 4px; }
</style>
