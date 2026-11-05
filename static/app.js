const $ = (id) => document.getElementById(id);

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
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
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
    const res = await fetch(`/api/progress/${jobId}`);
    if (!res.ok) throw new Error("Lost track of the download.");
    const job = await res.json();
    setProgress(job.progress, job.message);
    if (job.status === "error") throw new Error(job.message);
    if (job.status === "done") {
      setProgress(100, `Ready: ${job.filename}`);
      window.location.href = `/api/file/${jobId}`; // triggers the browser's save dialog
      return;
    }
    await new Promise((r) => setTimeout(r, 700));
  }
}
