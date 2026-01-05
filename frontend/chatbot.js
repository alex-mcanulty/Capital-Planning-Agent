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

    // Reset and set structured output to loading state
    resetStructuredOutput();
    setStructuredOutputStatus('loading', 'Processing...');

    try {
        // Create assistant message placeholder
        const assistantMessageId = addMessage('assistant', '', true);

        // Stream response from agent (pass OIDC tokens with each request)
        await streamAgentResponse(message, assistantMessageId);

    } catch (error) {
        console.error('Error sending message:', error);
        addMessage('assistant', `❌ Error: ${error.message}`);
        setStructuredOutputStatus('error', 'Error');
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
 * Add a tool call indicator above the assistant message
 */
function addToolCallIndicator(toolName, assistantMessageId) {
    const toolDiv = document.createElement('div');
    toolDiv.className = 'chatbot-tool-call';
    toolDiv.innerHTML = `🛠️ Using tool: <strong>${toolName}</strong>`;

    // Insert before the assistant message element so tool calls appear above
    const assistantMessage = document.getElementById(assistantMessageId);
    if (assistantMessage) {
        chatbotMessages.insertBefore(toolDiv, assistantMessage);
    } else {
        chatbotMessages.appendChild(toolDiv);
    }
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
                addToolCallIndicator(data, assistantMessageId);
            } else if (eventType === 'message_end') {
                console.log('[Chatbot] Message ended');
                // Message complete - add to history
                if (currentMessageContent) {
                    chatHistory.push({
                        role: 'assistant',
                        content: currentMessageContent
                    });
                }
                // Update status to show extraction is happening
                setStructuredOutputStatus('loading', 'Extracting...');
                showStructuredOutputSpinner();
            } else if (eventType === 'structured_response') {
                console.log('[Chatbot] Structured response received');
                try {
                    const structuredData = JSON.parse(data);
                    displayStructuredOutput(structuredData);
                } catch (e) {
                    console.error('[Chatbot] Failed to parse structured response:', e);
                }
            } else if (eventType === 'error') {
                console.error(`[Chatbot] Error event: ${data}`);
                updateMessageContent(assistantMessageId, `❌ Error: ${data}`);
                setStructuredOutputStatus('error', 'Error');
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

/**
 * Fill the chat input with a test query (called from onclick)
 */
function fillChatInput(element) {
    const query = element.getAttribute('data-query');
    if (query && chatbotInput) {
        chatbotInput.value = query;
        chatbotInput.focus();
    }
}

// =============================================================================
// Structured Output Display
// =============================================================================

const structuredOutputContent = document.getElementById('structured-output-content');
const structuredOutputStatus = document.getElementById('structured-output-status');

/**
 * Set the status indicator for structured output panel
 */
function setStructuredOutputStatus(status, text) {
    structuredOutputStatus.className = 'structured-output-status';
    if (status) {
        structuredOutputStatus.classList.add(status);
    }
    structuredOutputStatus.textContent = text;
}

/**
 * Reset structured output panel to waiting state
 */
function resetStructuredOutput() {
    setStructuredOutputStatus('', 'Waiting...');
    structuredOutputContent.innerHTML = `
        <div class="structured-output-placeholder">
            Structured analysis results will appear here after the agent completes its response.
        </div>
    `;
}

/**
 * Show a spinner in the structured output panel during extraction
 */
function showStructuredOutputSpinner() {
    structuredOutputContent.innerHTML = `
        <div class="structured-output-loading">
            <div class="so-spinner"></div>
            <div class="so-loading-text">Analyzing response and extracting structured data...</div>
        </div>
    `;
}

/**
 * Display structured output data in the panel
 */
function displayStructuredOutput(data) {
    setStructuredOutputStatus('ready', 'Ready');

    let html = '';

    // Summary section
    if (data.summary) {
        html += `
            <div class="so-section">
                <div class="so-section-title">Summary</div>
                <div class="so-summary">${escapeHtml(data.summary)}</div>
            </div>
        `;
    }

    // High Risk Assets section
    if (data.high_risk_assets && data.high_risk_assets.length > 0) {
        html += `
            <div class="so-section">
                <div class="so-section-title">High Risk Assets (${data.high_risk_assets.length})</div>
                <div class="so-risk-list">
                    ${data.high_risk_assets.map(asset => {
                        const riskClass = asset.risk_score >= 70 ? 'high' : (asset.risk_score >= 40 ? 'medium' : 'low');
                        return `
                            <div class="so-risk-item">
                                <div class="so-risk-item-header">
                                    <span class="so-risk-item-name">${escapeHtml(asset.asset_name)}</span>
                                    <span class="so-risk-score ${riskClass}">${asset.risk_score.toFixed(1)}</span>
                                </div>
                                <div class="so-risk-item-details">
                                    ${escapeHtml(asset.asset_type)} · PoF: ${(asset.probability_of_failure * 100).toFixed(1)}%
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        `;
    }

    // Investment Plan section
    if (data.investment_plan) {
        const plan = data.investment_plan;
        html += `
            <div class="so-section">
                <div class="so-section-title">Investment Plan</div>
                <div class="so-plan-summary">
                    <div class="so-plan-stat">
                        <div class="so-plan-stat-value">$${formatCurrency(plan.total_cost)}</div>
                        <div class="so-plan-stat-label">Total Cost</div>
                    </div>
                    <div class="so-plan-stat">
                        <div class="so-plan-stat-value">${plan.num_assets_addressed}</div>
                        <div class="so-plan-stat-label">Assets</div>
                    </div>
                    ${plan.budget_utilization !== null ? `
                        <div class="so-plan-stat">
                            <div class="so-plan-stat-value">${(plan.budget_utilization * 100).toFixed(0)}%</div>
                            <div class="so-plan-stat-label">Budget Used</div>
                        </div>
                    ` : ''}
                    <div class="so-plan-stat">
                        <div class="so-plan-stat-value">${plan.total_risk_reduction.toFixed(2)}</div>
                        <div class="so-plan-stat-label">Risk Reduced</div>
                    </div>
                </div>
            </div>
        `;
    }

    // Selected Investments section
    if (data.selected_investments && data.selected_investments.length > 0) {
        html += `
            <div class="so-section">
                <div class="so-section-title">Selected Investments (${data.selected_investments.length})</div>
                <div class="so-intervention-list">
                    ${data.selected_investments.map(inv => `
                        <div class="so-intervention-item">
                            <span class="so-intervention-name">${escapeHtml(inv.asset_name)} - ${escapeHtml(inv.intervention_type)}</span>
                            <span class="so-intervention-cost">$${formatCurrency(inv.cost)}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    // Key Findings section
    if (data.key_findings && data.key_findings.length > 0) {
        html += `
            <div class="so-section">
                <div class="so-section-title">Key Findings</div>
                <ul class="so-findings-list">
                    ${data.key_findings.map(finding => `<li>${escapeHtml(finding)}</li>`).join('')}
                </ul>
            </div>
        `;
    }

    // Limitations section
    if (data.limitations) {
        html += `
            <div class="so-section">
                <div class="so-section-title">Limitations</div>
                <div style="font-size: 12px; color: #666; font-style: italic;">
                    ${escapeHtml(data.limitations)}
                </div>
            </div>
        `;
    }

    // If no data was rendered, show a message
    if (!html) {
        html = '<div class="structured-output-placeholder">No structured data available.</div>';
    }

    structuredOutputContent.innerHTML = html;
}

/**
 * Format currency values (thousands with K, millions with M)
 */
function formatCurrency(value) {
    if (value >= 1000000) {
        return (value / 1000000).toFixed(1) + 'M';
    } else if (value >= 1000) {
        return (value / 1000).toFixed(0) + 'K';
    }
    return value.toFixed(0);
}
