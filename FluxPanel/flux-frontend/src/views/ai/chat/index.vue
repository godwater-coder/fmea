<template>
    <div class="chat-container">
        <div class="chat-box" ref="chatBox">
            <div
                v-for="(msg, index) in messages"
                :key="index"
                :class="['message', msg.role]"
            >
                <div class="bubble">
                    <span v-html="renderMarkdown(msg.content)"></span>
                </div>
            </div>
        </div>
        <input
            v-model="input"
            @keyup.enter="sendMessage"
            placeholder="输入内容后回车发送"
            class="chat-input"
        />
    </div>
</template>

<script setup name="AiChat">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { marked } from 'marked'

const ws = ref(null)
const input = ref('')
const messages = ref([]) // { role: "user" | "assistant", content: string }
const chatBox = ref(null)

const baseUrl = import.meta.env.VITE_APP_BASE_API
const wsBase = baseUrl.startsWith('https')
    ? baseUrl.replace(/^https/, 'wss')
    : baseUrl.replace(/^http/, 'ws')

onMounted(() => {
    ws.value = new WebSocket(wsBase + '/ws/chat')

    ws.value.onmessage = (event) => {
        const msg = JSON.parse(event.data)
        if (msg.start) {
            messages.value.push({
                role: 'assistant',
                content: ''
            })
        }
        if (msg.role === 'user') {
            messages.value.push(msg) // 用户消息
            scrollToBottom()
        } else if (msg.role === 'assistant') {
            // 动态更新最后一条消息的内容
            const lastMessage = messages.value[messages.value.length - 1]
            if (lastMessage && lastMessage.role === 'assistant') {
                lastMessage.content += msg.content
            }
        }

        if (msg.done) {
            console.log('AI 消息完成')
        }
    }

    ws.value.onclose = () => {
        console.log('WebSocket 连接关闭')
    }
})

onUnmounted(() => {
    if (ws.value) {
        ws.value.close()
    }
})

const sendMessage = () => {
    if (input.value.trim() === '') return
    ws.value.send(input.value)
    input.value = ''
}

const renderMarkdown = (text) => {
    return marked.parse(text)
}

const scrollToBottom = () => {
    nextTick(() => {
        if (chatBox.value) {
            chatBox.value.scrollTop = chatBox.value.scrollHeight
        }
    })
}

watch(messages, () => {
    scrollToBottom()
})
</script>

<style scoped>
.chat-container {
    height: calc(100vh - 150px); /* Full height minus top and bottom margins */
    margin: 20px auto;
    padding: 20px;
    background: #f4f4f9;
    border-radius: 10px;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    display: flex;
    flex-direction: column;
}

.chat-box {
    flex: 1; /* Take up all available space */
    border: 0px solid #ccc;
    padding: 10px;
    overflow-y: auto;
    background: #ffffff;
    border-radius: 10px;
    box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.1);
}

.message {
    display: flex;
    margin: 10px 0;
}

.message.user {
    justify-content: flex-end;
}

.message.assistant {
    justify-content: flex-start;
}

.bubble {
    max-width: 70%;
    padding: 10px 15px;
    border-radius: 20px;
    font-size: 14px;
    line-height: 1.5;
    word-wrap: break-word;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.message.user .bubble {
    background: #007bff;
    color: #ffffff;
    border-bottom-right-radius: 0;
}

.message.assistant .bubble {
    background: #e9ecef;
    color: #333333;
    border-bottom-left-radius: 0;
}

.chat-input {
    margin-top: 10px;
    border: 1px solid #ccc;
    border-radius: 20px;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    font-size: 14px;
    outline: none;
    transition: border-color 0.2s;
    padding: 10px;
    width: 100%;
}
</style>
