---
name: auth-flow
description: Define the authentication flow for different types of projects, including web apps, mobile apps, and APIs. This skill covers best practices for secure authentication, token management, and session handling with chrome-devtools-mcp.
user-invocable: false
disable-model-invocation: false
---

# Authentication Flow Skill

## Frontend Web App Authentication Flow

> This flow is designed for **chrome-devtools-mcp**, which controls a persistent Chrome browser instance. Unlike Playwright, chrome-devtools-mcp does NOT have a `storageState` API — authentication persists automatically via Chrome's profile storage as long as you use the same browser instance.

---

## Step 0: Check Login State

Before attempting any login, navigate to the target app and check if already authenticated.

```
1. navigate_page → target app URL
2. take_screenshot → inspect current state
3. Check for login indicators:
   - Redirected to /login, /signin, or /auth?
   - Login form visible?
   - User menu / avatar visible (= already logged in)?
```

If already logged in → **skip to reproduction steps**. No need to re-authenticate.

---

## Step 1: Email / Phone + Password Login

- Detect login form (full page or modal)
- Check **Project Context** for supported login methods and test credentials
- Fill in credentials using `fill` or `fill_form`
- Submit form and wait for redirect

```
1. navigate_page → /login (or app URL that redirects to login)
2. wait_for → login form selector
3. fill → email/username field with test credential
4. fill → password field with test credential
5. click → submit button
6. wait_for → post-login indicator (user menu selector, avatar, or URL pattern like '/home')
   ⚠️ 不要在 click 後立即呼叫 take_screenshot — 頁面跳轉期間 take_screenshot 會等待頁面穩定，
      可能觸發數十秒 timeout。必須先用 wait_for 確認跳轉完成後再截圖。
7. take_screenshot → confirm login success
```

**If login fails:**
- Check console errors with `list_console_messages`
- Check network errors with `list_network_requests`
- Verify credentials in Project Context are correct

---

## Step 2: OAuth Login (Google, Facebook, Apple)

OAuth flows open a popup window. Use page switching tools to handle it.

```
1. navigate_page → app login page
2. click → OAuth provider button (e.g. "Continue with Google")
3. list_pages → find the new OAuth popup page
4. select_page → switch to OAuth popup
5. fill → OAuth email field
6. click → Next
7. fill → OAuth password field
8. click → Sign in / Allow
9. wait_for → popup to close (or redirect back to app)
10. select_page → switch back to main app page
11. wait_for → post-login element
12. take_screenshot → confirm login success
```

---

## Step 3: Auth State Persistence (chrome-devtools-mcp)

### How it works

chrome-devtools-mcp uses a **persistent Chrome profile** (not a new incognito session each time). This means:

- **Cookies, localStorage, sessionStorage** are preserved across MCP sessions
- Once logged in, the session remains until it expires or the server invalidates it
- **No explicit save/load needed** — unlike Playwright's `storageState`

### Verifying persistence

At the start of each analyze session:

```
1. navigate_page → app URL
2. take_screenshot
3. If user menu / avatar is visible → session still active, proceed
4. If login page is shown → session expired, perform login again (Step 1 or 2)
```

### When sessions expire

Some apps use short-lived JWTs or force logout after inactivity. If the session expires mid-analysis:

```
1. Detect redirect to login page (URL change or login form appearing)
2. Perform login flow again (Step 1 or 2)
3. navigate_page back to the page you were on
4. Continue reproduction steps
```

### Cookie-based vs. Token-based apps

| Auth type | Persistence | Notes |
|-----------|------------|-------|
| Cookie session | Automatic via Chrome profile | Most reliable |
| localStorage JWT | Automatic via Chrome profile | Persists until cleared |
| sessionStorage JWT | Lost when tab closes | Re-login needed per session |
| In-memory token | Lost on refresh | Re-login needed after navigate |

If the app uses sessionStorage or in-memory tokens, keep the same tab open throughout the session — avoid closing or refreshing the page unnecessarily.

---

## Step 4: Multi-tenant / Role-based Login

For apps with multiple user roles (admin, user, viewer):

- Check **Project Context** for role-specific test credentials
- Log in as the role most relevant to the bug being reproduced
- If bug affects multiple roles, reproduce with each role separately

---

## Credentials

Test credentials are defined in **Project Context** under the `credentials` or `test_accounts` section. Never hardcode credentials in this skill. Always read from Project Context.

If credentials are not found in Project Context:

1. Check `.env` file in project root for `TEST_EMAIL`, `TEST_PASSWORD`, etc.
2. Ask the user to provide credentials — **do not guess or fabricate**
