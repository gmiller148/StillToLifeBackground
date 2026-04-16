const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

let selectedFile = null;
let currentEventSource = null;

// --- Oscillator target options ---
const OSC_TARGETS = [
  { group: "Depth", options: [
    ["height", "Height"], ["steady", "Steady"], ["focus", "Focus"],
    ["zoom", "Zoom"], ["isometric", "Isometric"], ["dolly", "Dolly"], ["invert", "Invert"],
  ]},
  { group: "Position", options: [
    ["offset-x", "Offset X"], ["offset-y", "Offset Y"],
    ["center-x", "Center X"], ["center-y", "Center Y"],
    ["origin-x", "Origin X"], ["origin-y", "Origin Y"],
  ]},
  { group: "Vignette", options: [
    ["vignette.intensity", "Intensity"], ["vignette.decay", "Decay"],
  ]},
  { group: "Lens", options: [
    ["lens.intensity", "Intensity"], ["lens.decay", "Decay"],
  ]},
  { group: "Blur", options: [
    ["blur.intensity", "Intensity"], ["blur.start", "Start"],
    ["blur.end", "End"], ["blur.exponent", "Exponent"],
  ]},
  { group: "Colors", options: [
    ["colors.saturation", "Saturation"], ["colors.contrast", "Contrast"],
    ["colors.brightness", "Brightness"], ["colors.gamma", "Gamma"],
    ["colors.grayscale", "Grayscale"], ["colors.sepia", "Sepia"],
  ]},
];

// --- Upload ---

function initUpload() {
  const area = $(".upload-area");
  const input = $("#file-input");

  area.addEventListener("click", () => input.click());

  area.addEventListener("dragover", (e) => {
    e.preventDefault();
    area.classList.add("dragover");
  });

  area.addEventListener("dragleave", () => {
    area.classList.remove("dragover");
  });

  area.addEventListener("drop", (e) => {
    e.preventDefault();
    area.classList.remove("dragover");
    if (e.dataTransfer.files.length > 0) {
      handleFile(e.dataTransfer.files[0]);
    }
  });

  input.addEventListener("change", () => {
    if (input.files.length > 0) {
      handleFile(input.files[0]);
    }
  });
}

function handleFile(file) {
  selectedFile = file;
  const preview = $(".preview-container");
  const img = $("#preview-img");
  const fname = $(".filename");

  img.src = URL.createObjectURL(file);
  fname.textContent = file.name;
  preview.style.display = "block";
  $(".config-panel").style.display = "block";
  $(".generate-btn").disabled = false;
}

// --- Section toggling ---

function toggleSection(header) {
  const section = header.closest(".config-section");
  section.classList.toggle("collapsed");
}

// --- Range value displays ---

function initRangeDisplays() {
  $$("input[type='range']").forEach((slider) => {
    const display = $(`[data-for="${slider.id}"]`);
    if (!display) return;

    slider.addEventListener("input", () => {
      display.textContent = slider.value || "--";
    });

    // Initialize display
    if (slider.value && slider.dataset.default === undefined) {
      display.textContent = slider.value;
    }
  });
}

// --- Preset-specific param visibility ---

function updatePresetParams() {
  const style = $("#style").value;
  $$(".preset-params").forEach((el) => {
    const styles = el.dataset.forStyles.split(" ");
    el.style.display = styles.includes(style) ? "block" : "none";
  });
}

// --- FX enable/disable ---

function initFxToggles() {
  $$(".fx-params").forEach((params) => {
    const checkboxId = params.dataset.enable;
    const checkbox = $(`#${checkboxId}`);
    if (!checkbox) return;

    const update = () => {
      params.style.display = checkbox.checked ? "block" : "none";
    };
    checkbox.addEventListener("change", update);
    update();
  });
}

// --- State defaults reset ---

function resetStateDefaults() {
  $$("#state-height, #state-steady, #state-focus, #state-zoom, #state-isometric, #state-dolly, #state-invert, #state-offset-x, #state-offset-y, #state-center-x, #state-center-y, #state-origin-x, #state-origin-y").forEach((el) => {
    el.value = "";
    const display = $(`[data-for="${el.id}"]`);
    if (display) display.textContent = "--";
  });
  $("#state-mirror").checked = true;
}

// --- Oscillators ---

let oscCounter = 0;

function addOscillator() {
  const idx = oscCounter++;
  const row = document.createElement("div");
  row.className = "osc-row";
  row.dataset.index = idx;

  // Wave type select
  const typeSelect = document.createElement("select");
  typeSelect.className = "osc-type";
  ["sine", "cosine", "triangle", "linear", "set", "add"].forEach((t) => {
    const opt = document.createElement("option");
    opt.value = t;
    opt.textContent = t.charAt(0).toUpperCase() + t.slice(1);
    typeSelect.appendChild(opt);
  });

  // Target select with optgroups
  const targetSelect = document.createElement("select");
  targetSelect.className = "osc-target";
  OSC_TARGETS.forEach((g) => {
    const group = document.createElement("optgroup");
    group.label = g.group;
    g.options.forEach(([val, label]) => {
      const opt = document.createElement("option");
      opt.value = val;
      opt.textContent = label;
      group.appendChild(opt);
    });
    targetSelect.appendChild(group);
  });

  // Wave params (sine/cosine/triangle)
  const waveParams = document.createElement("div");
  waveParams.className = "osc-wave-params";
  waveParams.innerHTML = `
    <input type="number" class="osc-amplitude" value="1.0" step="0.1" placeholder="Amp" title="Amplitude">
    <input type="number" class="osc-bias" value="0" step="0.1" placeholder="Bias" title="Bias">
    <input type="number" class="osc-cycles" value="1" step="0.5" placeholder="Cycles" title="Cycles">
    <input type="number" class="osc-phase" value="0" step="0.05" placeholder="Phase" title="Phase">
  `;

  // Linear params
  const linearParams = document.createElement("div");
  linearParams.className = "osc-linear-params";
  linearParams.style.display = "none";
  linearParams.innerHTML = `
    <input type="number" class="osc-start" value="0" step="0.1" placeholder="Start" title="Start time">
    <input type="number" class="osc-end" value="1" step="0.1" placeholder="End" title="End time">
    <input type="number" class="osc-low" value="0" step="0.1" placeholder="Low" title="Low value">
    <input type="number" class="osc-high" value="1" step="0.1" placeholder="High" title="High value">
    <input type="number" class="osc-exponent" value="1" step="0.1" placeholder="Exp" title="Exponent">
  `;

  // Set/Add params
  const setAddParams = document.createElement("div");
  setAddParams.className = "osc-setadd-params";
  setAddParams.style.display = "none";
  setAddParams.innerHTML = `
    <input type="number" class="osc-value" value="0" step="0.1" placeholder="Value" title="Value">
  `;

  // Remove button
  const removeBtn = document.createElement("button");
  removeBtn.className = "osc-remove";
  removeBtn.textContent = "\u00d7";
  removeBtn.onclick = () => row.remove();

  // Toggle param visibility based on type
  typeSelect.addEventListener("change", () => {
    const t = typeSelect.value;
    waveParams.style.display = ["sine", "cosine", "triangle"].includes(t) ? "flex" : "none";
    linearParams.style.display = t === "linear" ? "flex" : "none";
    setAddParams.style.display = ["set", "add"].includes(t) ? "flex" : "none";
  });

  row.appendChild(typeSelect);
  row.appendChild(targetSelect);
  row.appendChild(waveParams);
  row.appendChild(linearParams);
  row.appendChild(setAddParams);
  row.appendChild(removeBtn);

  $("#osc-list").appendChild(row);
}

function collectOscillators() {
  const rows = $$("#osc-list .osc-row");
  if (rows.length === 0) return null;

  const oscillators = [];
  rows.forEach((row) => {
    const type = row.querySelector(".osc-type").value;
    const target = row.querySelector(".osc-target").value;
    const osc = { type, target };

    if (["sine", "cosine", "triangle"].includes(type)) {
      osc.amplitude = parseFloat(row.querySelector(".osc-amplitude").value) || 1;
      osc.bias = parseFloat(row.querySelector(".osc-bias").value) || 0;
      osc.cycles = parseFloat(row.querySelector(".osc-cycles").value) || 1;
      osc.phase = parseFloat(row.querySelector(".osc-phase").value) || 0;
    } else if (type === "linear") {
      osc.start = parseFloat(row.querySelector(".osc-start").value) || 0;
      osc.end = parseFloat(row.querySelector(".osc-end").value) || 1;
      osc.low = parseFloat(row.querySelector(".osc-low").value) || 0;
      osc.high = parseFloat(row.querySelector(".osc-high").value) || 1;
      osc.exponent = parseFloat(row.querySelector(".osc-exponent").value) || 1;
    } else if (["set", "add"].includes(type)) {
      osc.value = parseFloat(row.querySelector(".osc-value").value) || 0;
    }

    oscillators.push(osc);
  });

  return JSON.stringify(oscillators);
}

// --- Build config ---

function buildConfig() {
  const style = $("#style").value;
  const [w, h] = $("#resolution").value.split("x").map(Number);

  const config = {
    style,
    intensity: parseFloat($("#intensity").value),
    width: w,
    height: h,
    fps: parseInt($("#fps").value),
    duration: parseInt($("#duration").value),
    crf: parseInt($("#crf").value),
    render_quality: parseFloat($("#render-quality").value),
  };

  // Preset reverse
  if ($("#preset-reverse").checked) config.preset_reverse = true;

  // Style-specific params
  if (style === "dolly") {
    config.preset_depth = parseFloat($("#preset-depth").value);
    config.preset_phase = parseFloat($("#preset-phase").value);
    config.preset_smooth = $("#preset-smooth").checked;
    config.preset_loop = $("#preset-loop").checked;
  } else if (style === "orbital") {
    config.preset_depth = parseFloat($("#orbital-depth").value);
    config.preset_zoom = parseFloat($("#orbital-zoom").value);
  } else if (style === "horizontal" || style === "vertical") {
    config.preset_phase = parseFloat($("#hv-phase").value);
    config.preset_steady = parseFloat($("#hv-steady").value);
    config.preset_isometric = parseFloat($("#hv-isometric").value);
    config.preset_smooth = $("#preset-smooth").checked;
    config.preset_loop = $("#preset-loop").checked;
  } else if (style === "circle") {
    config.circle_amp_x = parseFloat($("#circle-amp-x").value);
    config.circle_amp_y = parseFloat($("#circle-amp-y").value);
    config.circle_amp_z = parseFloat($("#circle-amp-z").value);
    config.circle_phase_x = parseFloat($("#circle-phase-x").value);
    config.circle_phase_y = parseFloat($("#circle-phase-y").value);
    config.circle_phase_z = parseFloat($("#circle-phase-z").value);
    config.preset_steady = parseFloat($("#circle-steady").value);
    config.preset_isometric = parseFloat($("#circle-isometric").value);
  } else if (style === "zoom") {
    config.preset_phase = parseFloat($("#zoom-phase").value);
    config.preset_isometric = parseFloat($("#zoom-isometric").value);
    config.preset_smooth = $("#preset-smooth").checked;
    config.preset_loop = $("#preset-loop").checked;
  }

  // State overrides (only include if slider has been touched)
  const stateFields = [
    ["state-height", "state_height"], ["state-steady", "state_steady"],
    ["state-focus", "state_focus"], ["state-zoom", "state_zoom"],
    ["state-isometric", "state_isometric"], ["state-dolly", "state_dolly"],
    ["state-invert", "state_invert"],
    ["state-offset-x", "state_offset_x"], ["state-offset-y", "state_offset_y"],
    ["state-center-x", "state_center_x"], ["state-center-y", "state_center_y"],
    ["state-origin-x", "state_origin_x"], ["state-origin-y", "state_origin_y"],
  ];
  stateFields.forEach(([elemId, configKey]) => {
    const el = $(`#${elemId}`);
    if (el.value !== "") {
      config[configKey] = parseFloat(el.value);
    }
  });

  // Mirror (only send if unchecked, since default is mirror)
  if (!$("#state-mirror").checked) {
    config.state_mirror = false;
  }

  // Post-processing
  if ($("#vignette-enable").checked) {
    config.vignette_enable = true;
    config.vignette_intensity = parseFloat($("#vignette-intensity").value);
    config.vignette_decay = parseFloat($("#vignette-decay").value);
  }
  if ($("#lens-enable").checked) {
    config.lens_enable = true;
    config.lens_intensity = parseFloat($("#lens-intensity").value);
    config.lens_decay = parseFloat($("#lens-decay").value);
    config.lens_quality = parseInt($("#lens-quality").value);
  }
  if ($("#blur-enable").checked) {
    config.blur_enable = true;
    config.blur_intensity = parseFloat($("#blur-intensity").value);
    config.blur_start = parseFloat($("#blur-start").value);
    config.blur_end = parseFloat($("#blur-end").value);
    config.blur_exponent = parseFloat($("#blur-exponent").value);
    config.blur_quality = parseInt($("#blur-quality").value);
    config.blur_directions = parseInt($("#blur-directions").value);
  }
  if ($("#inpaint-enable").checked) {
    config.inpaint_enable = true;
    config.inpaint_limit = parseFloat($("#inpaint-limit").value);
    if ($("#inpaint-black").checked) config.inpaint_black = true;
  }
  if ($("#colors-enable").checked) {
    config.colors_enable = true;
    config.colors_saturation = parseFloat($("#colors-saturation").value);
    config.colors_contrast = parseFloat($("#colors-contrast").value);
    config.colors_brightness = parseFloat($("#colors-brightness").value);
    config.colors_gamma = parseFloat($("#colors-gamma").value);
    config.colors_grayscale = parseFloat($("#colors-grayscale").value);
    config.colors_sepia = parseFloat($("#colors-sepia").value);
  }

  // Oscillators
  const oscillators = collectOscillators();
  if (oscillators) config.oscillators = oscillators;

  // Optional output params
  const ssaa = $("#ssaa");
  if (ssaa.value !== "") config.ssaa = parseFloat(ssaa.value);
  const speed = $("#speed");
  if (speed.value !== "") config.speed = parseFloat(speed.value);

  return config;
}

// --- Generate ---

async function handleGenerate() {
  if (!selectedFile) return;

  const btn = $(".generate-btn");
  btn.disabled = true;

  const config = buildConfig();
  const form = new FormData();
  form.append("image", selectedFile);
  form.append("config", JSON.stringify(config));

  try {
    const resp = await fetch("/api/jobs", { method: "POST", body: form });
    if (!resp.ok) {
      const err = await resp.json();
      showToast(err.detail || "Upload failed", "error");
      btn.disabled = false;
      return;
    }

    const job = await resp.json();
    showProgress();
    connectSSE(job.id);
  } catch (e) {
    showToast("Network error: " + e.message, "error");
    btn.disabled = false;
  }
}

// --- SSE Progress ---

function showProgress() {
  $(".progress-section").style.display = "block";
  $(".progress-bar-fill").style.width = "0%";
  $(".progress-bar-fill").classList.remove("indeterminate");
  $(".progress-message").textContent = "Starting...";
}

function hideProgress() {
  $(".progress-section").style.display = "none";
  $(".generate-btn").disabled = false;
}

function connectSSE(jobId) {
  if (currentEventSource) {
    currentEventSource.close();
  }

  const es = new EventSource(`/api/jobs/${jobId}/progress`);
  currentEventSource = es;

  es.addEventListener("progress", (e) => {
    const data = JSON.parse(e.data);
    const bar = $(".progress-bar-fill");
    if (data.percent >= 0) {
      bar.classList.remove("indeterminate");
      bar.style.width = data.percent + "%";
    } else {
      bar.classList.add("indeterminate");
    }
    $(".progress-message").textContent = data.message || data.stage || "Processing...";
  });

  es.addEventListener("complete", (e) => {
    es.close();
    currentEventSource = null;
    hideProgress();
    showToast("Wallpaper generated!", "success");
    loadGallery();
  });

  es.addEventListener("error", (e) => {
    // Check if this is an SSE error event with data (from our server)
    if (e.data) {
      const data = JSON.parse(e.data);
      showToast(data.message || "Processing failed", "error");
    }
    es.close();
    currentEventSource = null;
    hideProgress();
    loadGallery();
  });
}

// --- Gallery ---

async function loadGallery() {
  try {
    const resp = await fetch("/api/jobs");
    if (!resp.ok) return;
    const jobs = await resp.json();
    renderGallery(jobs);
  } catch (e) {
    console.error("Failed to load gallery:", e);
  }
}

function renderGallery(jobs) {
  const grid = $(".gallery-grid");
  const empty = $(".gallery-empty");

  if (jobs.length === 0) {
    grid.innerHTML = "";
    empty.style.display = "block";
    return;
  }

  empty.style.display = "none";
  grid.innerHTML = jobs.map((job) => {
    const date = new Date(job.created_at).toLocaleDateString();
    const size = job.video_size_bytes ? formatBytes(job.video_size_bytes) : "";
    const meta = [date, size, job.config.style].filter(Boolean).join(" \u00b7 ");

    let actions = "";
    if (job.status === "completed") {
      actions = `
        <button onclick="previewVideo('${job.id}')">Preview</button>
        <button onclick="downloadVideo('${job.id}')">Download</button>
        <button onclick="installWallpaper('${job.id}')">${job.installed_as_wallpaper ? "Reinstall" : "Set Wallpaper"}</button>
        <button class="danger" onclick="deleteJob('${job.id}')">Delete</button>
      `;
    } else if (job.status === "failed") {
      actions = `<button class="danger" onclick="deleteJob('${job.id}')">Delete</button>`;
    }

    let errorHtml = "";
    if (job.status === "failed" && job.error) {
      const safeError = escapeHtml(job.error.split("\n").slice(-2).join(" "));
      errorHtml = `<div class="error-msg">${safeError}</div>`;
    }

    return `
      <div class="job-card">
        <img class="thumb" src="/api/jobs/${job.id}/thumbnail" alt="" loading="lazy"
             onerror="this.style.display='none'">
        <div class="info">
          <div class="name">${escapeHtml(job.original_filename)}</div>
          <div class="meta">
            <span class="status-badge ${job.status}">${job.status}</span>
            ${meta}
          </div>
        </div>
        ${errorHtml}
        <div class="actions">${actions}</div>
      </div>
    `;
  }).join("");
}

// --- Actions ---

function previewVideo(jobId) {
  const modal = $("#preview-modal");
  const video = $("#preview-video");
  video.src = `/api/jobs/${jobId}/preview`;
  modal.style.display = "flex";
  video.play();
}

function closePreview() {
  const modal = $("#preview-modal");
  const video = $("#preview-video");
  video.pause();
  video.src = "";
  modal.style.display = "none";
}

function downloadVideo(jobId) {
  window.open(`/api/jobs/${jobId}/video`, "_blank");
}

async function installWallpaper(jobId) {
  try {
    const resp = await fetch(`/api/jobs/${jobId}/install`, { method: "POST" });
    const data = await resp.json();
    if (resp.ok) {
      showToast(data.message, "success");
      loadGallery();
    } else {
      showToast(data.detail || "Install failed", "error");
    }
  } catch (e) {
    showToast("Network error: " + e.message, "error");
  }
}

async function deleteJob(jobId) {
  if (!confirm("Delete this job and its files?")) return;
  try {
    const resp = await fetch(`/api/jobs/${jobId}`, { method: "DELETE" });
    if (resp.ok) {
      showToast("Deleted", "success");
      loadGallery();
    } else {
      const data = await resp.json();
      showToast(data.detail || "Delete failed", "error");
    }
  } catch (e) {
    showToast("Network error: " + e.message, "error");
  }
}

// --- Toast ---

function showToast(message, type = "success") {
  const toast = $(".toast");
  toast.textContent = message;
  toast.className = "toast " + type + " show";
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => {
    toast.classList.remove("show");
  }, 4000);
}

// --- Helpers ---

function formatBytes(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1048576).toFixed(1) + " MB";
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// --- Init ---

document.addEventListener("DOMContentLoaded", () => {
  initUpload();
  initRangeDisplays();
  initFxToggles();
  updatePresetParams();

  $("#style").addEventListener("change", updatePresetParams);
  $(".generate-btn").addEventListener("click", handleGenerate);

  loadGallery();
  setInterval(loadGallery, 10000);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closePreview();
  });
});
