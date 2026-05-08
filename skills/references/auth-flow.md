# Authentication Flow

> This skill describes login steps in semantic, tool-agnostic terms.
> Map each step to the appropriate tool available in your current session
> (chrome-devtools-mcp, Playwright MCP, etc.).

---

## Step 0: Check Current Login State

Before attempting login, inspect the current page:

1. Navigate to the target app homepage
2. Observe the page:
   - User menu / avatar / profile visible → **already logged in**, skip to reproduction steps
   - Login button, login form, or redirect to a login page → **not logged in**, proceed to Step 1

---

## Step 1: Email / Phone + Password Login

Read test credentials from **Project Context** → `Auth Config`.

**Flow:**

1. Reach the login entry point — this may be a dedicated route (`/login`), a modal triggered by a header button, or a multi-step form. Determine the correct path by reading the target project, do not assume a fixed route.
2. Wait for the login form to appear (full-page or modal).
3. Enter the username (email or phone number).
4. Enter the password.
5. Submit the form.
6. **Wait for login to complete** — confirm a post-login indicator appears (user menu, avatar, dashboard, etc.) before taking any screenshot or continuing.
   - ⚠️ Do not screenshot or navigate immediately after submitting. The page may still be in mid-redirect; acting before the redirect completes causes long waits or incorrect state capture.
7. Confirm the current page shows an authenticated state.

**If login fails:**
- Check for console errors
- Check for 4xx/5xx network requests
- Verify credentials in Project Context are correct

---

## Step 2: OAuth Login (Google, Facebook, Apple, etc.)

OAuth flows typically open a popup window:

1. Click the OAuth login button (e.g. "Continue with Google")
2. Switch focus to the popup window
3. Fill in OAuth credentials and complete authorization in the popup
4. Wait for the popup to close and control to return to the main page
5. Switch focus back to the main page
6. Confirm authenticated state

---

## Step 3: Auth State Persistence

chrome-devtools-mcp uses a **persistent Chrome profile** (not incognito). Cookies and localStorage survive across sessions — no explicit save/load needed. Run Step 0 at the start of each session to confirm state.

| Auth type | Persistence | Notes |
|-----------|-------------|-------|
| Cookie session | ✅ Automatic | Most reliable |
| localStorage JWT | ✅ Automatic | Survives until storage is cleared |
| sessionStorage JWT | ❌ Lost on tab close | Keep the same tab open throughout |
| In-memory token | ❌ Lost on refresh | Avoid unnecessary navigations |

If the app uses sessionStorage or in-memory tokens, keep the same tab open for the entire session.

---

## Credentials

Always read test credentials from **Project Context** → `Auth Config`. Never hardcode or guess.

If credentials are absent from Project Context:
1. Check the target project root `.env` for `TEST_EMAIL`, `TEST_PASSWORD`, etc.
2. If still not found → mark status as `need_more_info` and ask the user to provide credentials.
