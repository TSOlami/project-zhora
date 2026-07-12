// --- Markdown rendering + code-fence extraction ------------------------
// A fenced code block becomes an "artifact": pulled out of the bubble into
// Canvas, with a reference card left in its place. Not a full CommonMark
// implementation - covers what chat responses actually use.

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function renderInline(text) {
  let s = escapeHtml(text);
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*])\*([^*\s][^*]*?)\*(?!\*)/g, "$1<em>$2</em>");
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return s;
}

const BLOCK_STARTERS = [/^(#{1,6})\s+/, /^\s*>\s?/, /^\s*([-*])\s+/, /^\s*\d+\.\s+/];
function isBlockStart(line) {
  return BLOCK_STARTERS.some((re) => re.test(line));
}

function renderTextBlock(text) {
  const lines = text.split("\n");
  let html = "";
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (/^\s*$/.test(line)) {
      i++;
      continue;
    }
    const headerMatch = line.match(/^(#{1,6})\s+(.*)$/);
    if (headerMatch) {
      const level = headerMatch[1].length;
      html += `<h${level}>${renderInline(headerMatch[2])}</h${level}>`;
      i++;
      continue;
    }
    if (/^\s*>\s?/.test(line)) {
      const quoteLines = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        quoteLines.push(lines[i].replace(/^\s*>\s?/, ""));
        i++;
      }
      html += `<blockquote>${renderTextBlock(quoteLines.join("\n"))}</blockquote>`;
      continue;
    }
    if (/^\s*([-*])\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*([-*])\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*([-*])\s+/, ""));
        i++;
      }
      html += "<ul>" + items.map((it) => `<li>${renderInline(it)}</li>`).join("") + "</ul>";
      continue;
    }
    if (/^\s*\d+\.\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ""));
        i++;
      }
      html += "<ol>" + items.map((it) => `<li>${renderInline(it)}</li>`).join("") + "</ol>";
      continue;
    }
    const paraLines = [];
    while (i < lines.length && !/^\s*$/.test(lines[i]) && !isBlockStart(lines[i])) {
      paraLines.push(lines[i]);
      i++;
    }
    html += `<p>${paraLines.map(renderInline).join("<br>")}</p>`;
  }
  return html;
}

// Splits raw text into alternating text/code segments. A fence still open at
// the end of the string (mid-stream) becomes {type:"code", open:true} rather
// than being left as literal ``` text.
function splitContent(text) {
  const segments = [];
  const fenceRe = /```(\w*)\n?([\s\S]*?)```/g;
  let lastIndex = 0;
  let match;
  while ((match = fenceRe.exec(text)) !== null) {
    if (match.index > lastIndex) segments.push({ type: "text", value: text.slice(lastIndex, match.index) });
    segments.push({ type: "code", lang: match[1] || "", code: match[2], open: false });
    lastIndex = fenceRe.lastIndex;
  }
  const rest = text.slice(lastIndex);
  const openIdx = rest.indexOf("```");
  if (openIdx !== -1) {
    const before = rest.slice(0, openIdx);
    if (before) segments.push({ type: "text", value: before });
    const afterMarker = rest.slice(openIdx + 3);
    const newlineIdx = afterMarker.indexOf("\n");
    const lang = newlineIdx === -1 ? afterMarker : afterMarker.slice(0, newlineIdx);
    const code = newlineIdx === -1 ? "" : afterMarker.slice(newlineIdx + 1);
    segments.push({ type: "code", lang: lang.trim(), code, open: true });
  } else if (rest) {
    segments.push({ type: "text", value: rest });
  }
  return segments;
}

// --- Artifact store -------------------------------------------------------
let allArtifacts = [];
let nextArtifactId = 1;
let currentArtifactId = null;
let canvasMode = "code"; // "code" | "preview"

function resetArtifacts() {
  allArtifacts = [];
  currentArtifactId = null;
  canvasMode = "code";
  resetCanvas();
}

const LANG_EXT = {
  python: "py", py: "py", javascript: "js", js: "js", typescript: "ts", ts: "ts",
  html: "html", css: "css", json: "json", bash: "sh", sh: "sh", shell: "sh",
  java: "java", c: "c", cpp: "cpp", "c++": "cpp", csharp: "cs", cs: "cs",
  go: "go", rust: "rs", ruby: "rb", php: "php", sql: "sql", yaml: "yml", yml: "yml",
  markdown: "md", md: "md", xml: "xml",
};

function artifactFilename(artifact) {
  const ext = LANG_EXT[(artifact.lang || "").toLowerCase()] || "txt";
  return `artifact-${artifact.id}.${ext}`;
}

function renderArtifactCard(artifact) {
  const label = artifact.lang || "code";
  const lineCount = artifact.code ? artifact.code.split("\n").length : 0;
  const status = artifact.open ? "Writing&hellip;" : `${lineCount} line${lineCount === 1 ? "" : "s"}`;
  return (
    `<div class="artifact-card" data-artifact-id="${artifact.id}">` +
    `<span class="artifact-card-icon"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg></span>` +
    `<span class="artifact-card-body"><span class="artifact-card-label">${escapeHtml(label)}</span>` +
    `<span class="artifact-card-status">${status}</span></span>` +
    `</div>`
  );
}

// Renders raw message text into a bubble: markdown for prose, reference
// cards for code fences (the code itself lives only in Canvas, not here).
// Re-run on every streamed chunk - matches/updates artifacts by position
// within this row so a live-streaming code block keeps its identity instead
// of getting a new id (and dropping out of Canvas) on every re-render.
function renderMessageContent(row, bubble, rawText) {
  const segments = splitContent(rawText);
  const oldArtifacts = row._artifacts || [];
  const newArtifacts = [];
  let codeIndex = 0;
  let html = "";

  segments.forEach((seg) => {
    if (seg.type === "text") {
      html += renderTextBlock(seg.value);
      return;
    }
    let artifact = oldArtifacts[codeIndex];
    if (!artifact) {
      artifact = { id: nextArtifactId++, row };
      allArtifacts.push(artifact);
    }
    artifact.lang = seg.lang;
    artifact.code = seg.code;
    artifact.open = !!seg.open;
    newArtifacts.push(artifact);
    html += renderArtifactCard(artifact);
    codeIndex++;
  });

  for (let i = codeIndex; i < oldArtifacts.length; i++) {
    const idx = allArtifacts.indexOf(oldArtifacts[i]);
    if (idx !== -1) allArtifacts.splice(idx, 1);
  }

  row._artifacts = newArtifacts;
  row._rawText = rawText;
  bubble.innerHTML = html;
  bubble.querySelectorAll(".artifact-card").forEach((card) => {
    card.onclick = () => openArtifact(Number(card.dataset.artifactId));
  });

  const openArt = newArtifacts.find((a) => a.open);
  if (openArt) openArtifact(openArt.id);
}

// --- Canvas panel -----------------------------------------------------
const canvasPanel = document.getElementById("canvas-panel");
const canvasTitle = document.getElementById("canvas-title");
const canvasNav = document.getElementById("canvas-nav");
const canvasPrevBtn = document.getElementById("canvas-prev");
const canvasNextBtn = document.getElementById("canvas-next");
const canvasDot = document.getElementById("canvas-dot");
const canvasCodeTab = document.getElementById("canvas-tab-code");
const canvasPreviewTab = document.getElementById("canvas-tab-preview");
const canvasContent = document.getElementById("canvas-content");
const canvasCode = document.getElementById("canvas-code");
const canvasPreviewFrame = document.getElementById("canvas-preview-frame");
const CANVAS_EMPTY_HTML = canvasCode.innerHTML;

function resetCanvas() {
  canvasPanel.classList.add("hidden");
  canvasCode.innerHTML = CANVAS_EMPTY_HTML;
  canvasPreviewFrame.srcdoc = "";
  if (canvasDot) canvasDot.classList.add("hidden");
}

function openArtifact(id) {
  currentArtifactId = id;
  renderCanvas();
}

function renderCanvas() {
  const artifact = allArtifacts.find((a) => a.id === currentArtifactId);
  if (!artifact) {
    resetCanvas();
    return;
  }
  canvasPanel.classList.remove("hidden");
  if (canvasDot) canvasDot.classList.remove("hidden");
  canvasTitle.textContent = artifactFilename(artifact);

  const idx = allArtifacts.indexOf(artifact);
  canvasNav.textContent = allArtifacts.length > 1 ? `${idx + 1} / ${allArtifacts.length}` : "";
  canvasPrevBtn.disabled = idx <= 0;
  canvasNextBtn.disabled = idx >= allArtifacts.length - 1;

  const isHtml = /^html?$/i.test(artifact.lang);
  canvasPreviewTab.classList.toggle("hidden", !isHtml);
  if (!isHtml && canvasMode === "preview") canvasMode = "code";
  canvasCodeTab.classList.toggle("active", canvasMode === "code");
  canvasPreviewTab.classList.toggle("active", canvasMode === "preview");
  canvasContent.classList.toggle("hidden", canvasMode !== "code");
  canvasPreviewFrame.classList.toggle("hidden", canvasMode !== "preview");

  if (canvasMode === "preview") {
    canvasPreviewFrame.srcdoc = artifact.code;
  } else if (window.hljs) {
    const lang = window.hljs.getLanguage(artifact.lang) ? artifact.lang : undefined;
    canvasCode.innerHTML = window.hljs.highlight(artifact.code, { language: lang, ignoreIllegals: true }).value;
  } else {
    canvasCode.textContent = artifact.code;
  }
}

canvasCodeTab.onclick = () => {
  canvasMode = "code";
  renderCanvas();
};
canvasPreviewTab.onclick = () => {
  canvasMode = "preview";
  renderCanvas();
};
canvasPrevBtn.onclick = () => {
  const idx = allArtifacts.findIndex((a) => a.id === currentArtifactId);
  if (idx > 0) openArtifact(allArtifacts[idx - 1].id);
};
canvasNextBtn.onclick = () => {
  const idx = allArtifacts.findIndex((a) => a.id === currentArtifactId);
  if (idx !== -1 && idx < allArtifacts.length - 1) openArtifact(allArtifacts[idx + 1].id);
};
document.getElementById("canvas-btn").onclick = () => {
  if (canvasPanel.classList.contains("hidden")) {
    if (currentArtifactId == null && allArtifacts.length) openArtifact(allArtifacts[allArtifacts.length - 1].id);
    else canvasPanel.classList.remove("hidden");
  } else {
    canvasPanel.classList.add("hidden");
  }
};
document.getElementById("canvas-close").onclick = () => canvasPanel.classList.add("hidden");
document.getElementById("canvas-copy").onclick = () => {
  const artifact = allArtifacts.find((a) => a.id === currentArtifactId);
  if (artifact) navigator.clipboard.writeText(artifact.code);
};
document.getElementById("canvas-download").onclick = () => {
  const artifact = allArtifacts.find((a) => a.id === currentArtifactId);
  if (!artifact) return;
  const blob = new Blob([artifact.code], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = artifactFilename(artifact);
  a.click();
  URL.revokeObjectURL(url);
};
