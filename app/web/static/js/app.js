/* ==========================================================================
   Schedule Forensics frontend
   --------------------------------------------------------------------------
   Vanilla JS, no build step. Hooks up:
     - upload-page drag/drop and single/comparative mode toggle
     - analysis-page tab switching
     - AI streaming via SSE fetch from /ai-analyze
     - Chart.js charts for slippage, manipulation gauge, float histogram
     - Tabulator.js tables for critical path, slippage, duration changes,
       float transitions, and the all-tasks explorer
   ========================================================================== */

(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", () => {
    initUploadPage();
    initAnalysisPage();
    initSettingsPage();
  });

  /* -------------------------------- Upload -------------------------------- */

  function initUploadPage() {
    const form = document.getElementById("upload-form");
    if (!form) return;

    const dropzoneLater = document.getElementById("dropzone-later");
    const laterInput = dropzoneLater
      ? dropzoneLater.querySelector('input[name="later_file"]')
      : null;
    const modeOptions = form.querySelectorAll(".mode-option");

    modeOptions.forEach((opt) => {
      opt.addEventListener("click", () => {
        modeOptions.forEach((o) => o.classList.remove("active"));
        opt.classList.add("active");
        const mode = opt.dataset.mode;
        const radio = opt.querySelector('input[type="radio"]');
        if (radio) radio.checked = true;
        if (mode === "comparative") {
          form.classList.add("comparative");
          if (dropzoneLater) dropzoneLater.style.display = "";
          if (laterInput) laterInput.setAttribute("required", "required");
        } else {
          form.classList.remove("comparative");
          if (dropzoneLater) dropzoneLater.style.display = "none";
          if (laterInput) laterInput.removeAttribute("required");
        }
      });
    });

    // Drag-and-drop visual + filename display
    form.querySelectorAll(".dropzone").forEach((zone) => {
      const input = zone.querySelector('input[type="file"]');
      const nameDiv = zone.querySelector(".dropzone-filename");

      ["dragover", "dragenter"].forEach((ev) =>
        zone.addEventListener(ev, (e) => {
          e.preventDefault();
          zone.classList.add("drag-over");
        })
      );
      ["dragleave", "drop"].forEach((ev) =>
        zone.addEventListener(ev, (e) => {
          e.preventDefault();
          zone.classList.remove("drag-over");
        })
      );
      zone.addEventListener("drop", (e) => {
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) {
          input.files = e.dataTransfer.files;
          updateFilename();
        }
      });
      if (input) input.addEventListener("change", updateFilename);

      function updateFilename() {
        if (nameDiv && input.files && input.files[0]) {
          nameDiv.textContent = input.files[0].name;
        }
      }
    });

    // Loading spinner on submit
    form.addEventListener("submit", () => {
      const btn = document.getElementById("analyze-btn");
      if (btn) btn.classList.add("loading");
    });
  }

  /* ------------------------------- Analysis ------------------------------- */

  function initAnalysisPage() {
    const tabButtons = document.querySelectorAll(".tab-btn");
    if (!tabButtons.length) return;

    tabButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const tab = btn.dataset.tab;
        tabButtons.forEach((b) => b.classList.toggle("active", b === btn));
        document.querySelectorAll(".tab-panel").forEach((p) => {
          p.classList.toggle("active", p.id === `tab-${tab}`);
        });
      });
    });

    const dataEl = document.getElementById("results-data");
    if (!dataEl) return;
    let results;
    try {
      results = JSON.parse(dataEl.textContent);
    } catch (e) {
      console.error("Failed to parse results JSON", e);
      return;
    }

    initAI();
    initCriticalPathTable(results);
    initAllTasksTable(results);

    if (results.comparison) {
      initSlippageTable(results);
      initDurationChangesTable(results);
      initSlippageChart(results);
    }
    if (results.manipulation) {
      initManipulationGauge(results);
    }
    if (results.float_analysis) {
      initFloatHistogram(results);
      initFloatTables(results);
    }
  }

  /* --------------------------------- AI ----------------------------------- */

  function initAI() {
    const btn = document.getElementById("ai-generate-btn");
    const out = document.getElementById("ai-output");
    const req = document.getElementById("ai-request");
    if (!btn || !out) return;

    btn.addEventListener("click", async () => {
      btn.classList.add("loading");
      btn.disabled = true;
      out.innerHTML = "";

      const formData = new FormData();
      formData.append(
        "request",
        (req && req.value && req.value.trim()) ||
          "Provide a forensic executive summary."
      );

      try {
        const resp = await fetch("/ai-analyze", {
          method: "POST",
          body: formData,
        });
        if (!resp.ok || !resp.body) {
          const text = await resp.text();
          out.textContent = `Error: ${text || resp.statusText}`;
          return;
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let idx;
          while ((idx = buffer.indexOf("\n\n")) !== -1) {
            const frame = buffer.slice(0, idx);
            buffer = buffer.slice(idx + 2);
            if (frame.startsWith("data: ")) {
              const json = frame.slice(6);
              try {
                const msg = JSON.parse(json);
                if (msg.chunk) {
                  out.textContent += msg.chunk;
                  out.scrollTop = out.scrollHeight;
                } else if (msg.error) {
                  out.textContent += `\n[ERROR] ${msg.error}`;
                } else if (msg.done) {
                  return;
                }
              } catch (e) {
                /* ignore malformed frames */
              }
            }
          }
        }
      } catch (err) {
        out.textContent = `Network error: ${err.message}`;
      } finally {
        btn.classList.remove("loading");
        btn.disabled = false;
      }
    });
  }

  /* ------------------------------ Tabulator ------------------------------- */

  function hasTabulator() {
    return typeof window.Tabulator !== "undefined";
  }

  function initCriticalPathTable(results) {
    const el = document.getElementById("critical-path-table");
    if (!el || !hasTabulator()) return;
    const cpm = results.cpm;
    const schedule = results.later_schedule || results.prior_schedule || {};
    const taskByUid = {};
    (schedule.tasks || []).forEach((t) => (taskByUid[t.uid] = t));
    const rows = (cpm && cpm.critical_path_uids ? cpm.critical_path_uids : [])
      .map((uid) => {
        const t = taskByUid[uid] || { uid };
        return {
          uid: t.uid,
          name: t.name || "—",
          start: t.start || "—",
          finish: t.finish || "—",
          duration: t.duration,
          percent_complete: t.percent_complete,
          total_slack: t.total_slack,
          predecessors: (t.predecessors || []).join(", "),
        };
      });

    new Tabulator(el, {
      data: rows,
      layout: "fitColumns",
      height: 520,
      columns: [
        { title: "UID", field: "uid", width: 70 },
        { title: "Name", field: "name", widthGrow: 3, formatter: progressFormatter },
        { title: "Start", field: "start", width: 170 },
        { title: "Finish", field: "finish", width: 170 },
        {
          title: "Dur (d)",
          field: "duration",
          width: 90,
          formatter: (cell) => numFmt(cell.getValue(), 1),
        },
        {
          title: "% Done",
          field: "percent_complete",
          width: 90,
          formatter: (cell) => numFmt(cell.getValue(), 0),
        },
        {
          title: "TF (d)",
          field: "total_slack",
          width: 80,
          formatter: (cell) => numFmt(cell.getValue(), 1),
        },
        { title: "Predecessors", field: "predecessors", widthGrow: 2 },
      ],
    });
  }

  function progressFormatter(cell) {
    const data = cell.getRow().getData();
    const pct = Number(data.percent_complete || 0);
    let color = "var(--text)";
    if (pct >= 100) color = "var(--good)";
    else if (pct > 0) color = "var(--warn)";
    return `<span style="color:${color}">${cell.getValue()}</span>`;
  }

  function numFmt(val, decimals) {
    if (val === null || val === undefined || val === "") return "—";
    const n = Number(val);
    return isNaN(n) ? String(val) : n.toFixed(decimals);
  }

  function initAllTasksTable(results) {
    const el = document.getElementById("all-tasks-table");
    if (!el || !hasTabulator()) return;
    const schedule = results.later_schedule || results.prior_schedule || {};
    const rows = (schedule.tasks || []).map((t) => ({
      uid: t.uid,
      id: t.id,
      name: t.name,
      wbs: t.wbs,
      duration: t.duration,
      start: t.start,
      finish: t.finish,
      percent_complete: t.percent_complete,
      total_slack: t.total_slack,
      critical: t.critical ? "Y" : "",
      summary: t.summary ? "Y" : "",
      milestone: t.milestone ? "Y" : "",
    }));

    const table = new Tabulator(el, {
      data: rows,
      layout: "fitDataStretch",
      height: 600,
      pagination: true,
      paginationSize: 50,
      columns: [
        { title: "UID", field: "uid", width: 70, sorter: "number" },
        { title: "ID", field: "id", width: 60, sorter: "number" },
        { title: "Name", field: "name", widthGrow: 3, headerFilter: "input" },
        { title: "WBS", field: "wbs", width: 120, headerFilter: "input" },
        { title: "Start", field: "start", width: 170 },
        { title: "Finish", field: "finish", width: 170 },
        {
          title: "Duration",
          field: "duration",
          width: 90,
          formatter: (cell) => numFmt(cell.getValue(), 1),
          sorter: "number",
        },
        {
          title: "% Done",
          field: "percent_complete",
          width: 90,
          formatter: (cell) => numFmt(cell.getValue(), 0),
          sorter: "number",
        },
        {
          title: "TF",
          field: "total_slack",
          width: 80,
          formatter: (cell) => numFmt(cell.getValue(), 1),
          sorter: "number",
        },
        { title: "CP", field: "critical", width: 60 },
        { title: "Sum", field: "summary", width: 60 },
        { title: "MS", field: "milestone", width: 60 },
      ],
    });

    const search = document.getElementById("task-search");
    if (search) {
      search.addEventListener("input", () => {
        const term = search.value.toLowerCase();
        table.setFilter((row) => {
          return (
            (row.name || "").toLowerCase().includes(term) ||
            (row.wbs || "").toLowerCase().includes(term)
          );
        });
      });
    }

    const exportBtn = document.getElementById("export-tasks-csv");
    if (exportBtn) {
      exportBtn.addEventListener("click", () =>
        table.download("csv", "schedule_tasks.csv")
      );
    }
  }

  function initSlippageTable(results) {
    const el = document.getElementById("slippage-table");
    if (!el || !hasTabulator()) return;
    const deltas = (results.comparison.task_deltas || [])
      .filter(
        (d) =>
          d.finish_slip_days !== null &&
          d.finish_slip_days !== undefined &&
          Math.abs(d.finish_slip_days) > 0.01
      )
      .sort((a, b) => (b.finish_slip_days || 0) - (a.finish_slip_days || 0));

    new Tabulator(el, {
      data: deltas,
      layout: "fitColumns",
      height: 420,
      columns: [
        { title: "UID", field: "uid", width: 70 },
        { title: "Task", field: "name", widthGrow: 3 },
        {
          title: "Start Slip (d)",
          field: "start_slip_days",
          width: 140,
          formatter: (c) => signedFmt(c.getValue()),
          sorter: "number",
        },
        {
          title: "Finish Slip (d)",
          field: "finish_slip_days",
          width: 140,
          formatter: (c) => signedFmt(c.getValue()),
          sorter: "number",
        },
        {
          title: "Δ Duration (d)",
          field: "duration_change_days",
          width: 140,
          formatter: (c) => signedFmt(c.getValue()),
          sorter: "number",
        },
      ],
    });
  }

  function signedFmt(v) {
    if (v === null || v === undefined || v === "") return "—";
    const n = Number(v);
    if (isNaN(n)) return String(v);
    const color = n > 0 ? "var(--bad)" : n < 0 ? "var(--good)" : "var(--text)";
    const sign = n > 0 ? "+" : "";
    return `<span style="color:${color}">${sign}${n.toFixed(1)}</span>`;
  }

  function initDurationChangesTable(results) {
    const el = document.getElementById("duration-changes-table");
    if (!el || !hasTabulator()) return;
    const rows = (results.comparison.task_deltas || [])
      .filter(
        (d) =>
          d.duration_change_days !== null &&
          d.duration_change_days !== undefined &&
          d.duration_change_days !== 0
      )
      .sort(
        (a, b) =>
          Math.abs(b.duration_change_days || 0) -
          Math.abs(a.duration_change_days || 0)
      );

    new Tabulator(el, {
      data: rows,
      layout: "fitColumns",
      height: 360,
      columns: [
        { title: "UID", field: "uid", width: 70 },
        { title: "Task", field: "name", widthGrow: 3 },
        {
          title: "Δ Duration (d)",
          field: "duration_change_days",
          width: 160,
          formatter: (c) => signedFmt(c.getValue()),
          sorter: "number",
        },
      ],
    });
  }

  function initFloatTables(results) {
    const fa = results.float_analysis;
    if (!fa) return;
    const becameEl = document.getElementById("became-critical-table");
    const droppedEl = document.getElementById("dropped-off-critical-table");

    if (becameEl && hasTabulator()) {
      const rows = (fa.task_changes || []).filter((t) => t.became_critical);
      new Tabulator(becameEl, {
        data: rows,
        layout: "fitColumns",
        height: 320,
        columns: [
          { title: "UID", field: "uid", width: 70 },
          { title: "Task", field: "name", widthGrow: 3 },
          {
            title: "Prior TF",
            field: "prior_total_float",
            width: 110,
            formatter: (c) => numFmt(c.getValue(), 1),
          },
          {
            title: "Later TF",
            field: "later_total_float",
            width: 110,
            formatter: (c) => numFmt(c.getValue(), 1),
          },
        ],
      });
    }
    if (droppedEl && hasTabulator()) {
      const rows = (fa.task_changes || []).filter((t) => t.dropped_off_critical);
      new Tabulator(droppedEl, {
        data: rows,
        layout: "fitColumns",
        height: 320,
        columns: [
          { title: "UID", field: "uid", width: 70 },
          { title: "Task", field: "name", widthGrow: 3 },
          {
            title: "Prior TF",
            field: "prior_total_float",
            width: 110,
            formatter: (c) => numFmt(c.getValue(), 1),
          },
          {
            title: "Later TF",
            field: "later_total_float",
            width: 110,
            formatter: (c) => numFmt(c.getValue(), 1),
          },
        ],
      });
    }
  }

  /* ------------------------------ Charts --------------------------------- */

  function hasChart() {
    return typeof window.Chart !== "undefined";
  }

  function initSlippageChart(results) {
    const canvas = document.getElementById("slippage-chart");
    if (!canvas || !hasChart()) return;
    const top10 = (results.comparison.task_deltas || [])
      .filter((d) => (d.finish_slip_days || 0) > 0)
      .sort((a, b) => (b.finish_slip_days || 0) - (a.finish_slip_days || 0))
      .slice(0, 10);

    new Chart(canvas.getContext("2d"), {
      type: "bar",
      data: {
        labels: top10.map((d) => truncate(d.name || `#${d.uid}`, 28)),
        datasets: [
          {
            label: "Finish slip (days)",
            data: top10.map((d) => d.finish_slip_days),
            backgroundColor: "rgba(255, 92, 108, 0.75)",
            borderColor: "rgba(255, 92, 108, 1)",
            borderWidth: 1,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        plugins: {
          legend: { labels: { color: "#e6ebf2" } },
        },
        scales: {
          x: {
            ticks: { color: "#8690a3" },
            grid: { color: "rgba(255,255,255,0.06)" },
          },
          y: {
            ticks: { color: "#8690a3" },
            grid: { color: "rgba(255,255,255,0.06)" },
          },
        },
      },
    });
  }

  function initManipulationGauge(results) {
    const canvas = document.getElementById("manipulation-gauge");
    if (!canvas || !hasChart()) return;
    const score = Number(results.manipulation.overall_score || 0);
    const remainder = Math.max(0, 100 - score);
    const color =
      score >= 40 ? "#ff5c6c" : score >= 20 ? "#f5b83d" : "#3dd68c";

    new Chart(canvas.getContext("2d"), {
      type: "doughnut",
      data: {
        labels: ["Score", "Remaining"],
        datasets: [
          {
            data: [score, remainder],
            backgroundColor: [color, "rgba(255,255,255,0.06)"],
            borderWidth: 0,
          },
        ],
      },
      options: {
        responsive: true,
        rotation: -90,
        circumference: 180,
        cutout: "70%",
        plugins: {
          legend: { display: false },
          tooltip: { enabled: false },
        },
      },
    });
  }

  function initFloatHistogram(results) {
    const canvas = document.getElementById("float-histogram");
    if (!canvas || !hasChart()) return;
    const changes = (results.float_analysis.task_changes || [])
      .map((c) => c.float_delta)
      .filter((v) => v !== null && v !== undefined);
    if (changes.length === 0) return;

    // Simple bucketing
    const buckets = {
      "< -10d": 0,
      "-10 to -5d": 0,
      "-5 to -1d": 0,
      "-1 to +1d": 0,
      "+1 to +5d": 0,
      "+5 to +10d": 0,
      "> +10d": 0,
    };
    changes.forEach((v) => {
      if (v < -10) buckets["< -10d"]++;
      else if (v < -5) buckets["-10 to -5d"]++;
      else if (v < -1) buckets["-5 to -1d"]++;
      else if (v <= 1) buckets["-1 to +1d"]++;
      else if (v <= 5) buckets["+1 to +5d"]++;
      else if (v <= 10) buckets["+5 to +10d"]++;
      else buckets["> +10d"]++;
    });

    new Chart(canvas.getContext("2d"), {
      type: "bar",
      data: {
        labels: Object.keys(buckets),
        datasets: [
          {
            label: "Tasks",
            data: Object.values(buckets),
            backgroundColor: "rgba(74, 158, 255, 0.75)",
            borderColor: "rgba(74, 158, 255, 1)",
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: { legend: { labels: { color: "#e6ebf2" } } },
        scales: {
          x: {
            ticks: { color: "#8690a3" },
            grid: { color: "rgba(255,255,255,0.06)" },
          },
          y: {
            ticks: { color: "#8690a3" },
            grid: { color: "rgba(255,255,255,0.06)" },
          },
        },
      },
    });
  }

  function truncate(s, n) {
    if (!s) return "";
    return s.length > n ? s.slice(0, n - 1) + "…" : s;
  }

  /* ------------------------------ Settings ------------------------------- */

  function initSettingsPage() {
    // No client-side state yet — Phase 4 settings are env-var driven.
  }
})();
