# Upload Flow

> This skill describes file upload automation in semantic, tool-agnostic terms.
> Map each step to the appropriate tool available in your current session
> (chrome-devtools-mcp, Playwright MCP, etc.).
>
> Key constraint: programmatic file injection at the OS/DOM level does **not** trigger
> React's synthetic `onChange` event. Every upload step here includes a dispatcher
> phase to fire the synthetic event after the file is attached.

---

## Step 0: Detect Upload Requirement

Before running reproduction steps, scan the `reproduction_steps` field for any of:
- "上傳圖片 / 影片 / 文件"
- "click upload", "attach file", "select media"
- Any reference to `<input type="file">` or a file picker

If a file upload is required → determine the **file type** needed (image vs video vs other) and follow the matching step below.

If no file upload is needed → skip this skill entirely.

---

## Step 1: Image Upload (No Fixture Required)

Use in-browser canvas to generate a synthetic image `File` object and inject it directly into the React component's state. **No file fixture is needed.**

### 1.1 — Identify the file input

```
take_snapshot
→ locate input[type=file] in the element tree
```

If the input is hidden (custom upload button):
```
evaluate_script: document.querySelector('input[type=file]').style.display = 'block'
take_snapshot
→ locate now-visible input[type=file]
```

If no `<input type="file">` exists (drag-and-drop zone only) → skip to Step 3 (Unsupported scenario).

### 1.2 — Generate image File in-browser and dispatch change event

Run a single `evaluate_script` block that:
1. Creates a canvas and draws a minimal valid image
2. Converts it to a `Blob` → `File`
3. Sets `Object.defineProperty` on the input's `files` property
4. Dispatches a native `change` event (which React's synthetic event system intercepts)

```javascript
// evaluate_script
(async () => {
  const canvas = document.createElement('canvas');
  canvas.width = 100;
  canvas.height = 100;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#4A90E2';
  ctx.fillRect(0, 0, 100, 100);

  const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg'));
  const file = new File([blob], 'test-image.jpg', { type: 'image/jpeg' });

  const input = document.querySelector('input[type=file]');
  const dt = new DataTransfer();
  dt.items.add(file);

  Object.defineProperty(input, 'files', { value: dt.files, configurable: true });

  input.dispatchEvent(new Event('change', { bubbles: true }));
})();
```

### 1.3 — Verify upload triggered

After the script runs:
```
take_screenshot
```
Check that:
- A preview image / thumbnail appears in the UI
- OR the app navigated to the expected next page
- OR the relevant store value changed (verify with `evaluate_script` if needed)

If none of the above → the `onChange` handler may use a different selector or event type. Try `input` event instead of `change`:
```javascript
input.dispatchEvent(new Event('input', { bubbles: true }));
```

---

## Step 2: Video Upload (Fixture Required)

Real video files cannot be generated in-browser. Use `upload_file` to attach the fixture, then dispatch the synthetic event.

### 2.1 — Locate test fixture

Read **Project Context** → `Test Fixtures Path`.

```
list_directory(test_fixtures_path)
→ find a .mp4 / .mov / .webm file
```

If `test_fixtures_path` is not configured, or no video file exists:
- Stop reproduction
- Record in `Browser Reproduction Issues`:
  ```
  Reproduction requires a video test fixture.
  test_fixtures_path is not configured (or no .mp4/.mov/.webm file found).
  Reporter must provide: a short video file (≤ 30s) at test_fixtures_path/test-video.mp4
  ```
- Set status to `need_more_info` and trigger Checkpoint

### 2.2 — Identify the file input

Same as Step 1.1 above. If hidden, make it visible with `evaluate_script`.

If no `<input type="file">` → skip to Step 3 (Unsupported scenario).

### 2.3 — Attach file and dispatch change event

```
upload_file(uid=<input_uid>, filePath=<absolute_path_to_video>)
```

Then immediately dispatch the synthetic event:
```javascript
// evaluate_script
const input = document.querySelector('input[type=file]');
input.dispatchEvent(new Event('change', { bubbles: true }));
```

> ⚠️ `upload_file` alone is not sufficient for React apps. The tool sets the file at
> the OS/DOM level but React's synthetic event system does not observe it. The
> `evaluate_script` dispatch is always required as the second step.

### 2.4 — Verify upload triggered

Same verification as Step 1.3.

---

## Step 3: Unsupported Scenario (Drag & Drop Zone, No File Input)

If the upload UI is a pure drag-and-drop zone with no underlying `<input type="file">`:

- Mark as `⚠️ high-risk` in the report
- Record in `Browser Reproduction Issues`:
  ```
  Upload zone is drag-and-drop only (no input[type=file] found).
  Automated file injection is not possible for this scenario.
  ```
- Trigger Checkpoint and wait for human to perform the upload step manually

---

## Step 4: Post-Upload State Check

After any successful upload (Steps 1–2), before continuing with reproduction:

1. Take a screenshot to confirm upload preview / navigation occurred
2. If the app should navigate to a new page after upload, wait for navigation to complete before proceeding
3. If using `evaluate_script` to check React store state:
   ```javascript
   // Example: check zustand store (app-specific, adjust selector)
   window.__STORE__?.getState()
   ```

Do not proceed with the next reproduction step until the upload state is confirmed.

---

## Notes

| Upload type | Method | Fixture needed |
|-------------|--------|----------------|
| Image (JPEG, PNG, WebP) | Canvas in-browser → DataTransfer → dispatchEvent | ❌ No |
| Video (MP4, MOV, WebM) | `upload_file` → dispatchEvent | ✅ Yes (`test_fixtures_path`) |
| Document (PDF, etc.) | `upload_file` → dispatchEvent | ✅ Yes |
| Drag & Drop zone | ❌ Not automatable | — |
