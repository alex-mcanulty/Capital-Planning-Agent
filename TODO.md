# Token Refresh & Session Management Improvements

## Critical Issues

### Issue #9: Active Session is Global (CRITICAL - SECURITY)
**Location:** `mcp_server/main.py` lines 66-111

**Problem:** Single `_active_session_id` for entire MCP server. Multiple browser windows/users overwrite each other's active session, causing wrong tokens to be used.

**Impact:** Security issue - User A's tool calls may use User B's tokens.

**Fix:** Track active sessions per-client, not globally. Agent should pass session_id with each request.

---

### Issue #1: Race Condition in Token Refresh (CRITICAL)
**Location:** `mcp_server/token_manager.py` - no locking on `_sessions`

**Problem:** Concurrent heartbeat + API call both try to refresh same session's tokens simultaneously. Both use old refresh token, OIDC detects reuse and rejects.

**Impact:** "Refresh token has been revoked" errors under concurrent load.

**Fix:** Add asyncio.Lock per-session to prevent concurrent refresh attempts.

---

### Issue #7: Logout Doesn't Revoke Tokens at OIDC (HIGH)
**Location:** `mcp_server/main.py` delete_session, `oidc_server/main.py`

**Problem:** MCP deletes session locally but doesn't notify OIDC to revoke the refresh token. Old tokens remain valid at OIDC.

**Impact:** Token reuse detection triggers on re-login within 30 seconds.

**Fix:** Add token revocation endpoint to OIDC, call it on logout.

---

### Issue #4: Heartbeat Continues After Session Deletion (HIGH)
**Location:** `mcp_server/token_manager.py` lines 312-363

**Problem:** If logout occurs mid-heartbeat, heartbeat may still hold reference to deleted session and attempt refresh.

**Impact:** Orphaned refresh attempts, potential token reuse detection.

**Fix:** Check session still exists before each refresh in heartbeat loop.

---

## Medium Issues

### Issue #14: No Cleanup of Failed Sessions
**Location:** `mcp_server/token_manager.py` lines 356-361

**Problem:** When heartbeat refresh fails, session stays in memory forever. Continues failing every 25 seconds.

**Impact:** Memory leak, log spam, wasted OIDC requests.

**Fix:** Delete sessions after N consecutive failures, or mark as "needs re-auth".

---

### Issue #5: Token Expiration Timing is Tight
**Location:** `oidc_server/config.py`, `mcp_server/config.py`

**Problem:** Only 5 seconds buffer between heartbeat (25s) and refresh token expiry (30s). Network delays can cause expiration.

**Impact:** Intermittent token expiration under load or slow network.

**Fix:** Reduce heartbeat interval to 20s, or increase refresh token lifetime to 60s.

---

### Issue #6: Token Update Not Atomic
**Location:** `mcp_server/token_manager.py` lines 238-253

**Problem:** Multiple session fields updated sequentially without transaction. Concurrent reads can see partial state.

**Impact:** Inconsistent token state under concurrent access.

**Fix:** Use a session-level lock, or replace entire session object atomically.

---

### Issue #3: Session Activation Race
**Location:** `mcp_server/main.py` lines 76-84

**Problem:** No atomic check-and-set for activation. Concurrent activate + delete can leave active_session pointing to deleted session.

**Impact:** "Session not found" errors after concurrent operations.

**Fix:** Use lock around activation/deletion, or check session exists when getting active session.

---

## Lower Priority Issues

### Issue #11: Concurrent Heartbeat Execution Not Protected
**Problem:** Theoretical possibility of overlapping heartbeat cycles if refresh takes >25s.

**Fix:** Add flag to skip heartbeat if previous cycle still running.

---

### Issue #15: Logout Endpoint Delete Race
**Problem:** Multiple logout requests for same session can cause 404 on second request.

**Fix:** Make delete idempotent (return 200 even if already deleted).

---

### Issue #16: Frontend Logout Doesn't Wait for Backend
**Location:** `frontend/app.js` lines 130-162

**Problem:** Frontend clears local state even if backend delete fails.

**Fix:** Only clear local state after confirmed backend deletion.

---

### Issue #17: Session Creation Doesn't Validate Token Expiry
**Location:** `mcp_server/main.py` lines 429-455

**Problem:** Tokens not validated on session creation. Expired or malformed tokens accepted.

**Fix:** Validate JWT signature and expiry before creating session.

---

### Issue #12: Session List Iteration with Concurrent Deletion
**Problem:** Heartbeat iterates session list while deletions may occur.

**Fix:** Already using `list()` snapshot - verify no mutation of session objects during iteration.

---

### Issue #18: Frontend/Backend Token State Desync
**Problem:** Frontend shows token valid while backend may have failed refresh.

**Fix:** Add endpoint to check session health, poll from frontend.

---

## Implementation Priority

1. **Issue #9** - Global active session (security, breaks multi-window)
2. **Issue #1** - Race condition in refresh (causes immediate failures)
3. **Issue #7** - Token revocation on logout (causes re-login failures)
4. **Issue #4** - Heartbeat after deletion (contributes to reuse detection)
5. **Issue #14** - Failed session cleanup (memory/log hygiene)
6. **Issue #5** - Timing buffer (reliability under load)
7. Remaining issues as time permits

## Testing Scenarios

After fixes, verify:
- [ ] Two browser windows logged in as same user - both work independently
- [ ] Two browser windows logged in as different users - isolation maintained
- [ ] Logout and immediate re-login - no token reuse errors
- [ ] Logout during active agent workflow - clean termination
- [ ] Network delay during heartbeat - tokens still refresh successfully
- [ ] OIDC server briefly unavailable - graceful degradation and recovery
