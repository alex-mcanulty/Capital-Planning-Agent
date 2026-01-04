// Chatbot functionality for Capital Planning AI Assistant
const AGENT_SERVER = 'http://localhost:8003';

// Chatbot state (use window scope for logout access)
window.chatHistory = [];
let chatHistory = window.chatHistory;
let isStreaming = false;

// DOM elements
const chatbotMessages = document.getElementById('chatbot-messages');
const chatbotInput = document.getElementById('chatbot-input');
const chatbotSend = document.getElementById('chatbot-send');

// Initialize chatbot
document.addEventListener('DOMContentLoaded', () => {
    chatbotSend.addEventListener('click', sendMessage);
    chatbotInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Add welcome message
    addMessage('assistant', 'Hello! I\'m your Capital Planning AI Assistant. I can help you analyze assets, assess risks, and create optimized investment plans. What would you like to know?');
});

/**
 * Send a message to the agent
 */
async function sendMessage() {
    const message = chatbotInput.value.trim();
    if (!message || isStreaming) return;

    // Add user message to UI
    addMessage('user', message);
    chatbotInput.value = '';

    // Add to history
    chatHistory.push({ role: 'user', content: message });

    // Disable input while streaming
    isStreaming = true;
    chatbotInput.disabled = true;
    chatbotSend.disabled = true;

    try {
        // Create assistant message placeholder
        const assistantMessageId = addMessage('assistant', '', true);

        // Stream response from agent (pass OIDC tokens with each request)
        await streamAgentResponse(message, assistantMessageId);

    } catch (error) {
        console.error('Error sending message:', error);
        addMessage('assistant', `❌ Error: ${error.message}`);
    } finally {
        // Re-enable input
        isStreaming = false;
        chatbotInput.disabled = false;
        chatbotSend.disabled = false;
        chatbotInput.focus();
    }
}

/**
 * Add a message to the chat UI
 */
function addMessage(role, content, isPlaceholder = false) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `chatbot-message chatbot-message-${role}`;

    const messageId = `msg-${Date.now()}-${Math.random()}`;
    messageDiv.id = messageId;

    if (role === 'user') {
        messageDiv.innerHTML = `
            <div class="chatbot-message-label">You</div>
            <div class="chatbot-message-content">${escapeHtml(content)}</div>
        `;
    } else {
        messageDiv.innerHTML = `
            <div class="chatbot-message-label">AI Assistant</div>
            <div class="chatbot-message-content" id="${messageId}-content">${isPlaceholder ? '<span class="chatbot-typing">●●●</span>' : formatMarkdown(content)}</div>
        `;
    }

    chatbotMessages.appendChild(messageDiv);
    chatbotMessages.scrollTop = chatbotMessages.scrollHeight;

    return messageId;
}

/**
 * Add a tool call indicator
 */
function addToolCallIndicator(toolName) {
    const toolDiv = document.createElement('div');
    toolDiv.className = 'chatbot-tool-call';
    toolDiv.innerHTML = `🛠️ Using tool: <strong>${toolName}</strong>`;

    chatbotMessages.appendChild(toolDiv);
    chatbotMessages.scrollTop = chatbotMessages.scrollHeight;
}

/**
 * Stream agent response using SSE
 *
 * OIDC tokens are passed with each request. The agent creates an MCP session
 * at the start of each invocation and deletes it when done.
 */
async function streamAgentResponse(message, assistantMessageId) {
    const response = await fetch(`${AGENT_SERVER}/chat/stream`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            message: message,
            access_token: accessToken,
            refresh_token: refreshToken,
            scopes: userInfo.scopes,
            user_id: userInfo.sub,
            history: chatHistory
        })
    });

    if (!response.ok) {
        throw new Error(`Agent error: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    let buffer = '';
    let currentMessageContent = '';
    let messageStarted = false;

    while (true) {
        const { done, value } = await reader.read();

        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Process complete SSE messages (messages end with double newline)
        const messages = buffer.split('\n\n');
        buffer = messages.pop(); // Keep incomplete message in buffer

        for (const message of messages) {
            if (!message.trim()) continue;

            const lines = message.split('\n');
            let eventType = null;
            let dataLines = [];

            for (const line of lines) {
                if (line.startsWith('event: ')) {
                    eventType = line.substring(7).trim();
                } else if (line.startsWith('data: ')) {
                    dataLines.push(line.substring(6));
                }
            }

            if (!eventType) continue;

            // Join multiple data: lines with newlines to reconstruct original content
            const data = dataLines.join('\n');

            console.log(`[Chatbot] SSE Event: ${eventType}, data length: ${data.length}`);

            if (eventType === 'message_start') {
                console.log('[Chatbot] Message started');
                messageStarted = true;
                updateMessageContent(assistantMessageId, '');
            } else if (eventType === 'message_chunk') {
                console.log(`[Chatbot] Message chunk (${data.length} chars): ${data.substring(0, 100)}...`);
                currentMessageContent = data;
                updateMessageContent(assistantMessageId, currentMessageContent);
            } else if (eventType === 'tool_call') {
                console.log(`[Chatbot] Tool call: ${data}`);
                addToolCallIndicator(data);
            } else if (eventType === 'message_end') {
                console.log('[Chatbot] Message ended');
                // Message complete - add to history
                if (currentMessageContent) {
                    chatHistory.push({
                        role: 'assistant',
                        content: currentMessageContent
                    });
                }
            } else if (eventType === 'error') {
                console.error(`[Chatbot] Error event: ${data}`);
                updateMessageContent(assistantMessageId, `❌ Error: ${data}`);
                throw new Error(data);
            }
        }
    }
}

/**
 * Update the content of an existing message
 */
function updateMessageContent(messageId, content) {
    const contentDiv = document.getElementById(`${messageId}-content`);
    if (contentDiv) {
        contentDiv.innerHTML = formatMarkdown(content);
        chatbotMessages.scrollTop = chatbotMessages.scrollHeight;
    }
}

/**
 * Format markdown-style content to HTML
 */
function formatMarkdown(text) {
    if (!text) return '<span class="chatbot-typing">●●●</span>';

    let html = escapeHtml(text);

    // Headers
    html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
    html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^# (.+)$/gm, '<h2>$1</h2>');

    // Bold
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // Italic
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // Lists
    html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');

    // Line breaks
    html = html.replace(/\n/g, '<br>');

    return html;
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
