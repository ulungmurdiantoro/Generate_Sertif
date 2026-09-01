"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

async function api(url, opts = {}) {
  const res = await fetch(url, opts);
  const ct = res.headers.get("content-type") || "";
  const body = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    const detail = body && body.detail ? body.detail : typeof body === "string" ? body : "";
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return body;
}

function flash(message, kind = "err") {
  const el = $("#msg");
  if (!el) return alert(message);
  el.textContent = message;
  el.className = `msg ${kind}`;
  el.hidden = false;
  el.scrollIntoView({ block: "nearest" });
  if (kind === "ok") setTimeout(() => (el.hidden = true), 3500);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

const PAGE = document.body.dataset.page;
if (PAGE === "index") initIndex();
if (PAGE === "editor") initEditor();
if (PAGE === "generate") initGenerate();
if (PAGE === "split") initSplit();

// ============================================================ INDEX

async function initIndex() {
  const list = $("#tpl-list");

  async function refresh() {
    const items = await api("/api/templates");
    list.innerHTML = "";
    if (!items.length) {
      list.innerHTML = `<p class="hint">Belum ada template. Klik "Template Baru".</p>`;
      return;
    }
    for (const t of items) {
      const card = document.createElement("div");
      card.className = "card";
      const bgFront = t.bg_front ? "bg depan ✓" : "bg depan ✗";
      const bgBack = t.bg_back ? " · bg belakang ✓" : "";
      card.innerHTML = `
        <h3></h3>
        <p class="mono"></p>
        <p class="hint">${t.fields.length} field · ${bgFront}${bgBack}</p>
        <div class="row gap">
          <a class="btn" href="/templates/${t.id}">Edit</a>
          <a class="btn primary" href="/templates/${t.id}/generate">Generate</a>
          <button class="btn danger" data-del="${t.id}">Hapus</button>
        </div>`;
      card.querySelector("h3").textContent = t.name;
      card.querySelector(".mono").textContent = t.id;
      list.appendChild(card);
    }
    $$("[data-del]", list).forEach((btn) =>
      btn.addEventListener("click", async () => {
        if (!confirm("Hapus template ini beserta seluruh asetnya?")) return;
        try {
          await api(`/api/templates/${btn.dataset.del}`, { method: "DELETE" });
          refresh();
        } catch (e) {
          flash(e.message);
        }
      })
    );
  }

  $("#btn-new").addEventListener("click", async () => {
    const name = prompt("Nama template:", "Sertifikat Pelatihan");
    if (name === null) return;
    try {
      const t = await api("/api/templates", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name }),
      });
      location.href = `/templates/${t.id}`;
    } catch (e) {
      flash(e.message);
    }
  });

  refresh().catch((e) => flash(e.message));
}

// =========================================================== EDITOR

async function initEditor() {
  const root = $("#editor");
  const id = root.dataset.templateId;
  const fieldTpl = $("#field-tpl");
  let cfg = null;
  let previewPage = 1;

  function fontOptions(select, current) {
    const opts = ['<option value="">(fallback)</option>'].concat(
      (cfg.fonts || []).map((f) => `<option value="${escapeHtml(f)}">${escapeHtml(f)}</option>`)
    );
    select.innerHTML = opts.join("");
    select.value = current || "";
  }

  function addFieldCard(f) {
    const node = fieldTpl.content.firstElementChild.cloneNode(true);
    const set = (k, v) => {
      const el = node.querySelector(`[data-k="${k}"]`);
      if (el) el.value = v;
    };
    set("key", f.key || "");
    set("label", f.label || "");
    set("align", f.align || "left");
    set("x", f.x ?? "");
    set("y", f.y ?? 0);
    set("font_size", f.font_size ?? 24);
    set("font_size_min", f.font_size_min ?? "");
    set("max_width", f.max_width ?? "");
    set("color", f.color || "#191919");
    set("sample", f.sample || "");
    node.querySelector('[data-k="page1"]').checked = (f.pages || [1]).includes(1);
    node.querySelector('[data-k="page2"]').checked = (f.pages || []).includes(2);
    const fontSel = node.querySelector('[data-k="font"]');
    fontOptions(fontSel, f.font);
    node.querySelector('[data-k="remove"]').addEventListener("click", () => node.remove());

    const fontUp = node.querySelector('[data-k="font-upload"]');
    fontUp.addEventListener("change", async () => {
      const file = fontUp.files[0];
      if (!file) return;
      try {
        const prev = (cfg.fonts || []).slice();
        const fd = new FormData();
        fd.append("kind", "font");
        fd.append("file", file);
        const updated = await api(`/api/templates/${id}/assets`, { method: "POST", body: fd });
        cfg.fonts = updated.fonts || [];
        const added = cfg.fonts.find((name) => !prev.includes(name));
        $$('#fields [data-k="font"]').forEach((sel) => fontOptions(sel, sel.value));
        if (added) fontSel.value = added;
        renderFontList();
        fontUp.value = "";
        flash(`Font "${added || file.name}" ditambahkan. Tekan ↻ untuk pratinjau.`, "ok");
      } catch (e) {
        flash(e.message);
        fontUp.value = "";
      }
    });

    $("#fields").appendChild(node);
  }

  function readFields() {
    return $$(".field-card")
      .map((node) => {
        const g = (k) => node.querySelector(`[data-k="${k}"]`);
        const num = (k) => {
          const v = g(k).value.trim();
          return v === "" ? null : Number(v);
        };
        const pages = [];
        if (g("page1").checked) pages.push(1);
        if (g("page2").checked) pages.push(2);
        return {
          key: g("key").value.trim(),
          label: g("label").value.trim(),
          pages: pages.length ? pages : [1],
          x: num("x"),
          y: num("y") ?? 0,
          align: g("align").value,
          font: g("font").value,
          font_size: num("font_size") ?? 24,
          font_size_min: num("font_size_min"),
          max_width: num("max_width"),
          color: g("color").value || "#191919",
          sample: g("sample").value,
        };
      })
      .filter((f) => f.key);
  }

  function renderFontList() {
    const fonts = cfg.fonts || [];
    const count = $("#font-count");
    if (count) count.textContent = fonts.length;
    const ul = $("#font-list");
    if (!ul) return;
    ul.innerHTML = "";
    if (!fonts.length) {
      ul.innerHTML = `<li class="hint">Belum ada font. Upload lewat kolom Font di salah satu field.</li>`;
      return;
    }
    fonts.forEach((name) => {
      const li = document.createElement("li");
      li.innerHTML = `<span class="mono"></span> <button class="x" title="hapus">×</button>`;
      li.querySelector(".mono").textContent = name;
      li.querySelector("button").addEventListener("click", async () => {
        try {
          cfg = await api(`/api/templates/${id}/fonts/${encodeURIComponent(name)}`, { method: "DELETE" });
          fill();
          reloadPreview();
        } catch (e) {
          flash(e.message);
        }
      });
      ul.appendChild(li);
    });
  }

  function fill() {
    $("#tpl-title").textContent = `Editor · ${cfg.name}`;
    $("#f-name").value = cfg.name || "";
    $("#f-cw").value = cfg.canvas_width;
    $("#f-ch").value = cfg.canvas_height;
    $("#f-res").value = cfg.resolution;
    $("#bg-front-name").textContent = cfg.bg_front || "(belum ada)";
    $("#bg-back-name").textContent = cfg.bg_back || "(belum ada)";
    renderFontList();
    $("#fields").innerHTML = "";
    (cfg.fields || []).forEach(addFieldCard);
  }

  async function save() {
    const payload = {
      name: $("#f-name").value.trim() || "Template",
      canvas_width: Number($("#f-cw").value) || 842,
      canvas_height: Number($("#f-ch").value) || 595,
      resolution: Number($("#f-res").value) || 150,
      fields: readFields(),
    };
    cfg = await api(`/api/templates/${id}`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    fill();
    return cfg;
  }

  function reloadPreview() {
    $("#preview-img").src = `/api/templates/${id}/preview?page=${previewPage}&_=${Date.now()}`;
  }

  async function uploadAsset(kind, file) {
    try {
      await save();
    } catch (_) {
      /* lanjut upload walau simpan gagal */
    }
    const fd = new FormData();
    fd.append("kind", kind);
    fd.append("file", file);
    cfg = await api(`/api/templates/${id}/assets`, { method: "POST", body: fd });
    fill();
    reloadPreview();
  }

  // --- wiring ---
  $("#btn-add-field").addEventListener("click", () =>
    addFieldCard({ key: "", pages: [1], align: "left", y: 120, font_size: 24, color: "#191919" })
  );
  $("#btn-save").addEventListener("click", async () => {
    try {
      await save();
      flash("Tersimpan.", "ok");
      reloadPreview();
    } catch (e) {
      flash(e.message);
    }
  });
  $("#btn-refresh").addEventListener("click", async () => {
    try {
      await save();
      reloadPreview();
    } catch (e) {
      flash(e.message);
    }
  });
  $$(".tab").forEach((tab) =>
    tab.addEventListener("click", () => {
      $$(".tab").forEach((x) => x.classList.remove("active"));
      tab.classList.add("active");
      previewPage = Number(tab.dataset.page);
      reloadPreview();
    })
  );
  $("#up-bg-front").addEventListener("change", (e) => {
    if (e.target.files[0]) uploadAsset("bg_front", e.target.files[0]).catch((x) => flash(x.message));
  });
  $("#up-bg-back").addEventListener("change", (e) => {
    if (e.target.files[0]) uploadAsset("bg_back", e.target.files[0]).catch((x) => flash(x.message));
  });

  try {
    cfg = await api(`/api/templates/${id}`);
    fill();
    reloadPreview();
  } catch (e) {
    flash(e.message);
  }
}

// ========================================================= GENERATE

async function initGenerate() {
  const root = $("#generate");
  const id = root.dataset.templateId;
  let cfg = null;
  let dataToken = null;
  let columns = [];

  function guessColumn(column, key) {
    const c = column.toLowerCase();
    const k = key.toLowerCase();
    if (c.includes(k)) return true;
    if (k === "nomor") return c.includes("no") || c.includes("number") || c.includes("nis");
    if (k === "nama") return c.includes("name") || c.includes("peserta");
    return false;
  }

  function renderSample(rows, cols) {
    const table = $("#sample-table");
    table.innerHTML =
      `<tr>${cols.map(() => "<th></th>").join("")}</tr>` +
      rows.map(() => `<tr>${cols.map(() => "<td></td>").join("")}</tr>`).join("");
    $$("#sample-table th").forEach((th, i) => (th.textContent = cols[i]));
    $$("#sample-table tr:not(:first-child)").forEach((tr, ri) => {
      $$("td", tr).forEach((td, ci) => (td.textContent = rows[ri][cols[ci]] ?? ""));
    });
  }

  function buildMapping() {
    const wrap = $("#mapping");
    const ff = $("#filename-field");
    wrap.innerHTML = "";
    ff.innerHTML = "";
    for (const f of cfg.fields) {
      const label = document.createElement("label");
      label.textContent = (f.label || f.key) + " ";
      const sel = document.createElement("select");
      sel.dataset.key = f.key;
      sel.innerHTML =
        `<option value="">— lewati —</option>` +
        columns.map((c) => `<option>${escapeHtml(c)}</option>`).join("");
      const auto = columns.find((c) => guessColumn(c, f.key));
      if (auto) sel.value = auto;
      label.appendChild(sel);
      wrap.appendChild(label);

      const opt = document.createElement("option");
      opt.value = f.key;
      opt.textContent = f.label || f.key;
      ff.appendChild(opt);
    }
  }

  $("#up-data").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      const fd = new FormData();
      fd.append("file", file);
      const info = await api(`/api/templates/${id}/data`, { method: "POST", body: fd });
      dataToken = info.data_token;
      columns = info.columns;
      $("#row-count").textContent = info.rows;
      renderSample(info.sample, columns);
      $("#data-info").hidden = false;
      buildMapping();
      $("#map-panel").hidden = false;
      $("#run-panel").hidden = false;
    } catch (x) {
      flash(x.message);
    }
  });

  $("#btn-run").addEventListener("click", async () => {
    if (!dataToken) return flash("Upload data peserta dulu.");
    const mapping = {};
    $$("#mapping select").forEach((s) => {
      if (s.value) mapping[s.dataset.key] = s.value;
    });
    if (!Object.keys(mapping).length) return flash("Minimal satu kolom harus dipetakan.");

    const runBtn = $("#btn-run");
    const dl = $("#download-link");
    try {
      runBtn.disabled = true;
      dl.hidden = true;
      $("#progress").hidden = false;
      $("#bar-fill").style.width = "0%";
      $("#progress-text").textContent = "Memulai...";

      let job = await api(`/api/templates/${id}/generate`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          data_token: dataToken,
          mapping,
          filename_field: $("#filename-field").value || null,
        }),
      });

      while (job.status === "queued" || job.status === "running") {
        await new Promise((r) => setTimeout(r, 800));
        job = await api(`/api/jobs/${job.id}`);
        $("#bar-fill").style.width = `${job.percent}%`;
        $("#progress-text").textContent = `${job.done}/${job.total} (${job.percent}%)`;
      }

      if (job.status === "done") {
        dl.href = job.download_url;
        dl.hidden = false;
        $("#progress-text").textContent = `Selesai: ${job.done} sertifikat.`;
        flash("Selesai. Klik Unduh ZIP.", "ok");
      } else {
        flash(`Gagal: ${job.message}`);
      }
    } catch (x) {
      flash(x.message);
    } finally {
      runBtn.disabled = false;
    }
  });

  try {
    cfg = await api(`/api/templates/${id}`);
    $("#gen-title").textContent = `Generate · ${cfg.name}`;
  } catch (e) {
    flash(e.message);
  }
}

// ============================================================ SPLIT

async function initSplit() {
  let token = null;
  let columns = [];
  let pdfPages = 0;
  let dataRows = null;
  let hasTextLayer = null;

  const ppd = () => Math.max(1, Number($("#sp-ppd").value) || 1);
  const startNo = () => Number($("#sp-start").value) || 1;

  function currentSource() {
    return $("#sp-source").value;
  }

  function syncSourceUI() {
    const src = currentSource();
    $("#sp-col-wrap").hidden = src !== "data";
    $("#sp-text-opts").hidden = src !== "pdf_text";
    recalcMath();
  }

  function recalcMath() {
    const el = $("#sp-math");
    if (!pdfPages) {
      el.textContent = "";
      return;
    }
    if (pdfPages % ppd() !== 0) {
      el.textContent = `⚠ ${pdfPages} halaman tidak habis dibagi ${ppd()}.`;
      return;
    }
    const docs = pdfPages / ppd();
    let msg = `${pdfPages} halaman ÷ ${ppd()} = ${docs} dokumen.`;
    if (currentSource() === "data" && dataRows != null) {
      msg +=
        dataRows === docs
          ? ` Cocok dengan ${dataRows} baris nama ✓`
          : ` ⚠ tidak cocok dengan ${dataRows} baris nama.`;
    }
    el.textContent = msg;
  }

  function renderTable(tableSel, wrapSel, rows, cols, cellFn) {
    const table = $(tableSel);
    table.innerHTML =
      `<tr>${cols.map(() => "<th></th>").join("")}</tr>` +
      rows.map(() => `<tr>${cols.map(() => "<td></td>").join("")}</tr>`).join("");
    $$(`${tableSel} th`).forEach((th, i) => (th.textContent = cols[i]));
    $$(`${tableSel} tr:not(:first-child)`).forEach((tr, ri) => {
      $$("td", tr).forEach((td, ci) => (td.textContent = cellFn(rows[ri], cols[ci], ci)));
    });
    $(wrapSel).hidden = false;
  }

  $("#sp-ppd").addEventListener("input", recalcMath);
  $("#sp-start").addEventListener("input", recalcMath);
  $("#sp-source").addEventListener("change", syncSourceUI);

  $("#sp-inspect").addEventListener("click", async () => {
    const pdf = $("#sp-pdf").files[0];
    if (!pdf) return flash("Pilih PDF gabungan dulu.");
    const btn = $("#sp-inspect");
    try {
      btn.disabled = true;
      const fd = new FormData();
      fd.append("pdf", pdf);
      if ($("#sp-data").files[0]) fd.append("data", $("#sp-data").files[0]);
      const info = await api("/api/split/upload", { method: "POST", body: fd });

      token = info.token;
      pdfPages = info.pdf_pages;
      dataRows = info.data_rows;
      columns = info.data_columns || [];
      hasTextLayer = null;

      let text = `PDF: ${pdfPages} halaman.`;
      if (dataRows != null) text += `  Daftar nama: ${dataRows} baris.`;
      const infoEl = $("#sp-info");
      infoEl.textContent = text;
      infoEl.hidden = false;

      if (columns.length) {
        const sel = $("#sp-col");
        sel.innerHTML = columns.map((c) => `<option>${escapeHtml(c)}</option>`).join("");
        const guess = columns.find((c) => /nama|name|peserta/i.test(c));
        if (guess) sel.value = guess;
        renderTable("#sp-sample-table", "#sp-sample", info.data_sample || [], columns,
          (row, col) => row[col] ?? "");
        $("#sp-source").value = "data";
      } else {
        $("#sp-sample").hidden = true;
        if (currentSource() === "data") $("#sp-source").value = "sequence";
      }

      $("#sp-opts").hidden = false;
      $("#sp-run-panel").hidden = false;
      syncSourceUI();
    } catch (e) {
      flash(e.message);
    } finally {
      btn.disabled = false;
    }
  });

  $("#sp-try").addEventListener("click", async () => {
    if (!token) return flash("Tekan Periksa dulu.");
    const btn = $("#sp-try");
    const note = $("#sp-try-note");
    try {
      btn.disabled = true;
      note.textContent = "Membaca...";
      const res = await api("/api/split/preview-names", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          token,
          text_anchor: $("#sp-anchor").value || "",
          text_regex: $("#sp-regex").value || "",
          pages_per_doc: ppd(),
          filename_prefix: $("#sp-prefix").value || "",
          start_number: startNo(),
          limit: 10,
        }),
      });
      hasTextLayer = res.has_text_layer;
      if (!res.has_text_layer) {
        note.textContent =
          "⚠ PDF ini tidak punya teks yang bisa dibaca. Pakai daftar Excel/CSV atau nomor urut.";
        $("#sp-try-wrap").hidden = true;
        return;
      }
      const ok = res.rows.filter((r) => r.name).length;
      note.textContent = `Contoh ${res.rows.length} dari ${res.doc_count} dokumen — ${ok} nama terbaca. Cek tabel di bawah, sesuaikan frasa/regex bila perlu.`;
      renderTable("#sp-try-table", "#sp-try-wrap", res.rows, ["Dok", "Nama terbaca", "Nama berkas"],
        (row, _col, ci) => (ci === 0 ? row.doc : ci === 1 ? row.name || "—" : row.filename));
    } catch (e) {
      note.textContent = "";
      flash(e.message);
    } finally {
      btn.disabled = false;
    }
  });

  $("#sp-run").addEventListener("click", async () => {
    if (!token) return flash("Tekan Periksa dulu.");
    const btn = $("#sp-run");
    const status = $("#sp-status");
    const src = currentSource();
    if (src === "pdf_text" && hasTextLayer === false) {
      return flash("PDF tidak punya teks yang bisa dibaca. Pilih sumber nama lain.");
    }
    const body = {
      token,
      name_source: src,
      name_column: src === "data" ? $("#sp-col").value : null,
      text_anchor: $("#sp-anchor").value || "",
      text_regex: $("#sp-regex").value || "",
      pages_per_doc: ppd(),
      filename_prefix: $("#sp-prefix").value || "",
      start_number: startNo(),
    };
    try {
      btn.disabled = true;
      status.textContent = "Memproses...";
      const res = await fetch("/api/split/run", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
          detail = (await res.json()).detail || detail;
        } catch (_) {
          /* keep default */
        }
        throw new Error(detail);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `split_${token.slice(0, 8)}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
      status.textContent = "Selesai — ZIP terunduh.";
      flash("Selesai. ZIP sudah diunduh.", "ok");
    } catch (e) {
      status.textContent = "";
      flash(e.message);
    } finally {
      btn.disabled = false;
    }
  });
}
