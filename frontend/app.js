// Configuration
const OIDC_SERVER = 'http://localhost:8000';
const API_SERVER = 'http://localhost:8001';
const CLIENT_ID = 'capital-planning-client';

// State management
let accessToken = null;
let refreshToken = null;
let tokenExpiry = null;
let userInfo = null;

// DOM elements
const loginPage = document.getElementById('login-page');
const dashboardPage = document.getElementById('dashboard-page');
const loginForm = document.getElementById('login-form');
const loginError = document.getElementById('login-error');
const activityLog = document.getElementById('activity-log');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loginForm.addEventListener('submit', handleLogin);
    checkExistingSession();
});

function fillCredentials(username, password) {
    document.getElementById('username').value = username;
    document.getElementById('password').value = password;
}

async function handleLogin(e) {
    e.preventDefault();

    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;

    try {
        hideError();

        // Step 1: Get authorization code
        const authorizeResponse = await fetch(
            `${OIDC_SERVER}/authorize?username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}&client_id=${CLIENT_ID}&response_type=code`
        );

        if (!authorizeResponse.ok) {
            throw new Error('Authentication failed');
        }

        const authorizeData = await authorizeResponse.json();
        const code = authorizeData.code;

        // Step 2: Exchange code for tokens
        const tokenResponse = await fetch(`${OIDC_SERVER}/token`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: new URLSearchParams({
                grant_type: 'authorization_code',
                code: code,
                client_id: CLIENT_ID
            })
        });

        if (!tokenResponse.ok) {
            throw new Error('Failed to obtain tokens');
        }

        const tokenData = await tokenResponse.json();

        // Store tokens
        accessToken = tokenData.access_token;
        refreshToken = tokenData.refresh_token;
        tokenExpiry = Date.now() + (tokenData.expires_in * 1000);

        // Get user info
        await fetchUserInfo();

        // Show dashboard
        showDashboard();

    } catch (error) {
        showError(error.message);
    }
}

async function fetchUserInfo() {
    const response = await fetch(`${OIDC_SERVER}/userinfo`, {
        headers: {
            'Authorization': `Bearer ${accessToken}`
        }
    });

    if (!response.ok) {
        throw new Error('Failed to fetch user info');
    }

    userInfo = await response.json();
}

// Token refresh is now handled by the MCP server's global heartbeat
// Frontend tokens are only used to establish the initial MCP session
// which is created when the user sends their first chat message

function showDashboard() {
    loginPage.classList.remove('active');
    dashboardPage.classList.add('active');

    updateTokenDisplay();
    startTokenExpiryMonitor();
}

function updateTokenDisplay() {
    document.getElementById('user-name').textContent = userInfo.name;
    document.getElementById('token-user').textContent = userInfo.sub;
    document.getElementById('token-scopes').textContent = userInfo.scopes.join(', ');

    const expiresIn = Math.round((tokenExpiry - Date.now()) / 1000);
    document.getElementById('token-expires').textContent = `${expiresIn}s (${new Date(tokenExpiry).toLocaleTimeString()})`;
    document.getElementById('has-refresh-token').textContent = refreshToken ? 'Yes' : 'No';
}

function startTokenExpiryMonitor() {
    setInterval(() => {
        if (accessToken) {
            updateTokenDisplay();
        }
    }, 1000);
}

async function logout() {
    // Delete MCP session if one exists
    if (window.mcpSessionId) {
        try {
            await fetch(`http://localhost:8002/sessions/${window.mcpSessionId}`, {
                method: 'DELETE'
            });
            console.log('[App] MCP session deleted');
        } catch (error) {
            console.error('[App] Failed to delete MCP session:', error);
        }
        window.mcpSessionId = null;
    }

    // Clear chatbot state
    if (window.chatHistory) {
        window.chatHistory = [];
    }
    const chatbotMessages = document.getElementById('chatbot-messages');
    if (chatbotMessages) {
        chatbotMessages.innerHTML = '';
    }

    accessToken = null;
    refreshToken = null;
    tokenExpiry = null;
    userInfo = null;

    dashboardPage.classList.remove('active');
    loginPage.classList.add('active');

    activityLog.innerHTML = '';
}

function showError(message) {
    loginError.textContent = message;
    loginError.classList.add('show');
}

function hideError() {
    loginError.classList.remove('show');
}

function log(message, type = 'info') {
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;

    const timestamp = document.createElement('div');
    timestamp.className = 'timestamp';
    timestamp.textContent = new Date().toLocaleTimeString();

    const msg = document.createElement('div');
    msg.className = 'message';
    msg.textContent = message;

    entry.appendChild(timestamp);
    entry.appendChild(msg);

    activityLog.insertBefore(entry, activityLog.firstChild);

    // Keep only last 50 entries
    while (activityLog.children.length > 50) {
        activityLog.removeChild(activityLog.lastChild);
    }
}

function checkExistingSession() {
    // Could implement session persistence here
}

// Manual token refresh removed - MCP server's global heartbeat handles token lifecycle
