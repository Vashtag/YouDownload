const $ = (id) => document.getElementById(id);

// Where the helper (app.py) is running. When this page is served by the helper
// itself, use the same origin; on GitHub Pages, default to the local helper.
const DEFAULT_HELPER = "http://127.0.0.1:5000";
const servedByHelper = location.protocol === "http:" && /^(127\.0\.0\.1|localhost)$/.test(location.hostname);

function loadHelperUrl() {
  if (servedByHelper) return location.origin;
  try {
    return localStorage.getItem("helperUrl") || DEFAULT_HELPER;
  } catch {
    return DEFAULT_HELPER;
  }
}
let API = loadHelperUrl();
let helperOk = false;

function setHelperState(state, text) {
  $("helper").className = `helper ${state}`;
  $("helper-text").textContent = text;
}

async function checkHelper() {
  try {
    const res = await fetch(`${API}/api/health`, { cache: "no-store" });
    const data = await res.json();
    helperOk = true;
    $("setup").hidden = true;
    setHelperState(
      data.ffmpeg ? "ok" : "warn",
      data.ffmpeg ? "Helper connected" : "Helper connected, but ffmpeg is missing (MP3 and HD video need it)"
    );
  } catch {
    if (helperOk || $("helper").classList.contains("checking")) {
      setHelperState("down", "Helper not running");
    }
    helperOk = false;
    $("setup").hidden = false;
  }
}

checkHelper();
setInterval(checkHelper, 4000);

$("settings-btn").addEventListener("click", () => {
  $("settings").hidden = !$("settings").hidden;
  $("helper-url").value = API;
});
$("save-settings").addEventListener("click", () => {
  const v = $("helper-url").value.trim().replace(/\/+$/, "") || DEFAULT_HELPER;
  API = v;
  try {
    localStorage.setItem("helperUrl", v);
  } catch {}
  $("settings").hidden = true;
  setHelperState("checking", "Looking for the YouDownload helper...");
  checkHelper();
});

let current = null; // video info from /api/info
let kind = "video";
let busy = false;

function showError(msg) {
  $("error").textContent = msg;
  $("error").hidden = !msg;
}

function fmtDuration(s) {
  if (!s) return "";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(Math.floor(s % 60)).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

async function postJSON(url, body) {
  let res;
  try {
    res = await fetch(API + url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    });
  } catch {
    throw new Error("Can't reach the YouDownload helper. Make sure app.py is running (see setup above).");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

$("url-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  showError("");
  $("result").hidden = true;
  const btn = $("fetch-btn");
  btn.disabled = true;
  btn.textContent = "Loading...";
  try {
    current = await postJSON("/api/info", { url: $("url").value });
    renderInfo(current);
  } catch (err) {
    showError(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Get options";
  }
});

function renderInfo(info) {
  $("thumb").src = info.thumbnail || "";
  $("thumb").hidden = !info.thumbnail;
  $("title").textContent = info.title || "Untitled";
  $("meta").textContent = [info.uploader, fmtDuration(info.duration)].filter(Boolean).join(" · ");

  const q = $("quality");
  q.innerHTML = "";
  if (info.qualities.length === 0) {
    q.add(new Option("Best available", "9999"));
  }
  for (const { height, label } of info.qualities) {
    q.add(new Option(label, height));
  }
  // Default to 1080p (or the best below it) rather than a huge 4K file.
  const def = info.qualities.find((x) => x.height <= 1080);
  if (def) q.value = def.height;

  $("progress").hidden = true;
  $("result").hidden = false;
}

document.querySelectorAll(".tab").forEach((tab) =>
  tab.addEventListener("click", () => {
    kind = tab.dataset.kind;
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
    document.querySelectorAll(".panel").forEach((p) => (p.hidden = p.dataset.panel !== kind));
  })
);

$("download-btn").addEventListener("click", async () => {
  if (!current || busy) return;
  busy = true;
  showError("");
  const btn = $("download-btn");
  btn.disabled = true;
  setProgress(0, "Starting...");
  $("progress").hidden = false;

  try {
    const body = { url: current.url, kind };
    if (kind === "video") body.height = $("quality").value;
    else body.bitrate = $("bitrate").value;
    const { job_id } = await postJSON("/api/download", body);
    await poll(job_id);
  } catch (err) {
    showError(err.message);
    $("progress").hidden = true;
  } finally {
    busy = false;
    btn.disabled = false;
  }
});

function setProgress(pct, msg) {
  $("bar-fill").style.width = `${pct}%`;
  $("status").textContent = msg;
}

async function poll(jobId) {
  while (true) {
    const res = await fetch(`${API}/api/progress/${jobId}`);
    if (!res.ok) throw new Error("Lost track of the download.");
    const job = await res.json();
    setProgress(job.progress, job.message);
    if (job.status === "error") throw new Error(job.message);
    if (job.status === "done") {
      setProgress(100, `Ready: ${job.filename}`);
      window.location.href = `${API}/api/file/${jobId}`; // triggers the browser's save dialog
      return;
    }
    await new Promise((r) => setTimeout(r, 700));
  }
}
