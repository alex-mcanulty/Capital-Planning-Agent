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
const loadingIndicator = document.getElementById('loading');
const responseOutput = document.getElementById('response-output');
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

async function refreshAccessToken() {
    try {
        log('Attempting to refresh access token...', 'info');

        const response = await fetch(`${OIDC_SERVER}/token`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: new URLSearchParams({
                grant_type: 'refresh_token',
                refresh_token: refreshToken,
                client_id: CLIENT_ID
            })
        });

        if (!response.ok) {
            throw new Error('Token refresh failed');
        }

        const tokenData = await response.json();

        // Update tokens (note: refresh token is rotated!)
        accessToken = tokenData.access_token;
        refreshToken = tokenData.refresh_token;
        tokenExpiry = Date.now() + (tokenData.expires_in * 1000);

        log('Access token refreshed successfully (refresh token rotated)', 'success');
        updateTokenDisplay();

        return true;
    } catch (error) {
        log(`Token refresh failed: ${error.message}`, 'error');
        logout();
        return false;
    }
}

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

function logout() {
    accessToken = null;
    refreshToken = null;
    tokenExpiry = null;
    userInfo = null;

    dashboardPage.classList.remove('active');
    loginPage.classList.add('active');

    responseOutput.textContent = '';
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

function showLoading() {
    loadingIndicator.classList.add('show');
    responseOutput.textContent = '';
}

function hideLoading() {
    loadingIndicator.classList.remove('show');
}

async function makeAuthenticatedRequest(method, endpoint, body = null) {
    try {
        showLoading();

        // Check if token is about to expire (within 2 seconds)
        const timeUntilExpiry = tokenExpiry - Date.now();
        if (timeUntilExpiry < 2000) {
            log('Access token expired or expiring soon, refreshing...', 'info');
            const refreshed = await refreshAccessToken();
            if (!refreshed) {
                throw new Error('Failed to refresh token');
            }
        }

        log(`${method} ${endpoint}`, 'info');
        const startTime = Date.now();

        const options = {
            method: method,
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Content-Type': 'application/json'
            }
        };

        if (body) {
            options.body = JSON.stringify(body);
        }

        const response = await fetch(`${API_SERVER}${endpoint}`, options);
        const duration = ((Date.now() - startTime) / 1000).toFixed(2);

        const data = await response.json();

        if (!response.ok) {
            log(`Request failed (${response.status}): ${data.detail || 'Unknown error'}`, 'error');
            responseOutput.textContent = JSON.stringify(data, null, 2);
        } else {
            log(`Request succeeded in ${duration}s`, 'success');
            responseOutput.textContent = JSON.stringify(data, null, 2);
        }

        hideLoading();
        return data;

    } catch (error) {
        log(`Request error: ${error.message}`, 'error');
        responseOutput.textContent = `Error: ${error.message}`;
        hideLoading();
    }
}

async function testEndpoint(method, endpoint) {
    await makeAuthenticatedRequest(method, endpoint);
}

async function testRiskAnalysis() {
    const requestBody = {
        asset_ids: ["asset-001", "asset-002", "asset-003", "asset-004", "asset-005"],
        horizon_months: 12
    };

    log('Testing risk analysis (will take 5+ seconds)...', 'info');
    await makeAuthenticatedRequest('POST', '/risk/analyze', requestBody);
}

async function testInvestmentOptimization() {
    const requestBody = {
        candidates: [
            {
                asset_id: "asset-001",
                intervention_type: "replacement",
                cost: 450000,
                expected_risk_reduction: 0.85
            },
            {
                asset_id: "asset-002",
                intervention_type: "rehabilitation",
                cost: 200000,
                expected_risk_reduction: 0.60
            },
            {
                asset_id: "asset-003",
                intervention_type: "replacement",
                cost: 500000,
                expected_risk_reduction: 0.90
            }
        ],
        budget: 1000000,
        horizon_months: 12
    };

    log('Testing investment optimization (will take 8+ seconds)...', 'info');
    await makeAuthenticatedRequest('POST', '/investments/optimize', requestBody);
}

function checkExistingSession() {
    // Could implement session persistence here
}

// Expose refresh function to UI
window.refreshToken = async function() {
    await refreshAccessToken();
};
