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
    initTaskFocusPage();
    initDcmaDrilldown();
  });

  /* -------------------------------- Upload -------------------------------- */

  function initUploadPage() {
    const form = document.getElementById("upload-form");
    if (!form) return;

    const dropzonePrior = document.getElementById("dropzone-prior");
    const dropzoneLater = document.getElementById("dropzone-later");
    const dropzoneTrend = document.getElementById("dropzone-trend");
    const priorInput = dropzonePrior
      ? dropzonePrior.querySelector('input[name="prior_file"]')
      : null;
    const laterInput = dropzoneLater
      ? dropzoneLater.querySelector('input[name="later_file"]')
      : null;
    const trendInput = dropzoneTrend
      ? dropzoneTrend.querySelector('input[name="schedule_files"]')
      : null;
    const modeOptions = form.querySelectorAll(".mode-option");

    function applyMode(mode) {
      if (mode === "single") {
        if (dropzonePrior) dropzonePrior.style.display = "";
        if (dropzoneLater) dropzoneLater.style.display = "none";
        if (dropzoneTrend) dropzoneTrend.style.display = "none";
        if (priorInput) priorInput.setAttribute("required", "required");
        if (laterInput) laterInput.removeAttribute("required");
        if (trendInput) trendInput.removeAttribute("required");
      } else if (mode === "comparative") {
        if (dropzonePrior) dropzonePrior.style.display = "";
        if (dropzoneLater) dropzoneLater.style.display = "";
        if (dropzoneTrend) dropzoneTrend.style.display = "none";
        if (priorInput) priorInput.setAttribute("required", "required");
        if (laterInput) laterInput.setAttribute("required", "required");
        if (trendInput) trendInput.removeAttribute("required");
      } else if (mode === "trend") {
        if (dropzonePrior) dropzonePrior.style.display = "none";
        if (dropzoneLater) dropzoneLater.style.display = "none";
        if (dropzoneTrend) dropzoneTrend.style.display = "";
        if (priorInput) priorInput.removeAttribute("required");
        if (laterInput) laterInput.removeAttribute("required");
        if (trendInput) trendInput.setAttribute("required", "required");
      }
    }

    modeOptions.forEach((opt) => {
      opt.addEventListener("click", () => {
        modeOptions.forEach((o) => o.classList.remove("active"));
        opt.classList.add("active");
        const mode = opt.dataset.mode;
        const radio = opt.querySelector('input[type="radio"]');
        if (radio) radio.checked = true;
        applyMode(mode);
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
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
          input.files = e.dataTransfer.files;
          updateFilename();
        }
      });
      if (input) input.addEventListener("change", updateFilename);

      function updateFilename() {
        if (!nameDiv || !input.files || !input.files.length) return;
        if (input.files.length === 1) {
          nameDiv.textContent = input.files[0].name;
        } else {
          const names = Array.from(input.files).map((f) => f.name).join(", ");
          nameDiv.textContent = `${input.files.length} files: ${names}`;
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
    if (results.trend) {
      initTrendCharts(results);
    }
    initGanttView(results);
    initFieldSelector(results);
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

    function nameList(uids) {
      return (uids || [])
        .map((uid) => {
          const t = taskByUid[uid];
          return t && t.name ? `${t.name} (UID: ${uid})` : `UID: ${uid}`;
        })
        .join("; ");
    }

    const rows = (cpm && cpm.critical_path_uids ? cpm.critical_path_uids : [])
      .map((uid) => {
        const t = taskByUid[uid] || { uid };
        return {
          uid: t.uid,
          name: t.name || "—",
          wbs: t.wbs || "",
          start: t.start || null,
          finish: t.finish || null,
          duration: t.duration,
          percent_complete: t.percent_complete,
          total_slack: t.total_slack,
          free_slack: t.free_slack,
          predecessors: nameList(t.predecessors),
          successors: nameList(t.successors),
        };
      });

    new Tabulator(el, {
      data: rows,
      layout: "fitColumns",
      height: 520,
      columns: [
        { title: "UID", field: "uid", width: 70 },
        { title: "Name", field: "name", widthGrow: 3, formatter: progressFormatter },
        { title: "WBS", field: "wbs", width: 110 },
        { title: "Start", field: "start", width: 110, formatter: shortDate },
        { title: "Finish", field: "finish", width: 110, formatter: shortDate },
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
        {
          title: "FF (d)",
          field: "free_slack",
          width: 80,
          formatter: (cell) => numFmt(cell.getValue(), 1),
        },
        { title: "Predecessors", field: "predecessors", widthGrow: 2 },
        { title: "Successors", field: "successors", widthGrow: 2 },
      ],
    });
  }

  function shortDate(cell) {
    var v = cell.getValue ? cell.getValue() : cell;
    if (!v) return "";
    var s = String(v);
    if (s.includes("T")) s = s.split("T")[0];
    var p = s.split("-");
    if (p.length === 3) return parseInt(p[1]) + "/" + parseInt(p[2]) + "/" + p[0];
    return s;
  }
  // Standalone version for non-Tabulator use (tooltips, Gantt, etc.)
  function shortDateValue(v) {
    if (!v) return "";
    var s = String(v);
    if (s.includes("T")) s = s.split("T")[0];
    var p = s.split("-");
    if (p.length === 3) return parseInt(p[1]) + "/" + parseInt(p[2]) + "/" + p[0];
    return s;
  }

  function focusButtonFormatter(cell) {
    const uid = cell.getValue();
    return `<button class="btn-focus" data-task-uid="${uid}">Focus</button>`;
  }
  function focusButtonClick(e, cell) {
    const uid = cell.getValue();
    if (uid === null || uid === undefined) return;
    window.location.href = `/task-focus?uid=${encodeURIComponent(uid)}`;
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
    const priorSchedule = results.prior_schedule || {};
    const priorByUid = {};
    (priorSchedule.tasks || []).forEach((t) => (priorByUid[t.uid] = t));
    const deltaByUid = {};
    if (results.comparison && results.comparison.task_deltas) {
      results.comparison.task_deltas.forEach((d) => (deltaByUid[d.uid] = d));
    }

    const rows = (schedule.tasks || []).map((t) => {
      const d = deltaByUid[t.uid] || {};
      return {
        focus: t.uid,
        uid: t.uid,
        id: t.id,
        name: t.name,
        wbs: t.wbs,
        outline_level: t.outline_level,
        duration: t.duration,
        start: t.start,
        finish: t.finish,
        actual_start: t.actual_start,
        actual_finish: t.actual_finish,
        baseline_start: t.baseline_start,
        baseline_finish: t.baseline_finish,
        baseline_duration: t.baseline_duration,
        percent_complete: t.percent_complete,
        remaining_duration: t.remaining_duration,
        total_slack: t.total_slack,
        free_slack: t.free_slack,
        constraint_type: t.constraint_type,
        constraint_date: t.constraint_date,
        deadline: t.deadline,
        priority: t.priority,
        resource_names: t.resource_names,
        notes: t.notes,
        critical: t.critical ? "Y" : "",
        summary: t.summary ? "Y" : "",
        milestone: t.milestone ? "Y" : "",
        start_slip_days: d.start_slip_days,
        finish_slip_days: d.finish_slip_days,
        duration_change_days: d.duration_change_days,
        total_slack_delta: d.total_slack_delta,
      };
    });

    const dateFmt = shortDate;
    const numFmt1 = (cell) => numFmt(cell.getValue(), 1);
    const signedFmt1 = (cell) => signedFmt(cell.getValue());

    const columns = [
      { title: "UID", field: "uid", width: 70, sorter: "number" },
      { title: "ID", field: "id", width: 60, sorter: "number" },
      { title: "Name", field: "name", widthGrow: 3, headerFilter: "input" },
      { title: "WBS", field: "wbs", width: 120, headerFilter: "input", visible: false },
      { title: "Outline", field: "outline_level", width: 80, visible: false },
      { title: "Start", field: "start", width: 130, formatter: dateFmt },
      { title: "Finish", field: "finish", width: 130, formatter: dateFmt },
      { title: "Actual Start", field: "actual_start", width: 130, formatter: dateFmt, visible: false },
      { title: "Actual Finish", field: "actual_finish", width: 130, formatter: dateFmt, visible: false },
      { title: "Baseline Start", field: "baseline_start", width: 130, formatter: dateFmt, visible: false },
      { title: "Baseline Finish", field: "baseline_finish", width: 130, formatter: dateFmt, visible: false },
      { title: "Baseline Dur", field: "baseline_duration", width: 100, formatter: numFmt1, visible: false },
      { title: "Duration", field: "duration", width: 90, formatter: numFmt1, sorter: "number" },
      { title: "Remaining", field: "remaining_duration", width: 100, formatter: numFmt1, visible: false },
      { title: "% Done", field: "percent_complete", width: 90, formatter: (c) => numFmt(c.getValue(), 0), sorter: "number" },
      { title: "TF", field: "total_slack", width: 80, formatter: numFmt1, sorter: "number" },
      { title: "FF", field: "free_slack", width: 80, formatter: numFmt1, sorter: "number", visible: false },
      { title: "Constraint", field: "constraint_type", width: 130, visible: false },
      { title: "Constraint Date", field: "constraint_date", width: 130, formatter: dateFmt, visible: false },
      { title: "Deadline", field: "deadline", width: 130, formatter: dateFmt, visible: false },
      { title: "Priority", field: "priority", width: 80, visible: false },
      { title: "Resources", field: "resource_names", widthGrow: 2, visible: false },
      { title: "Notes", field: "notes", widthGrow: 3, visible: false },
      { title: "CP", field: "critical", width: 60 },
      { title: "Sum", field: "summary", width: 60, visible: false },
      { title: "MS", field: "milestone", width: 60, visible: false },
      { title: "Start Slip", field: "start_slip_days", width: 100, formatter: signedFmt1, sorter: "number", visible: false },
      { title: "Finish Slip", field: "finish_slip_days", width: 100, formatter: signedFmt1, sorter: "number", visible: false },
      { title: "Δ Duration", field: "duration_change_days", width: 110, formatter: signedFmt1, sorter: "number", visible: false },
      { title: "Δ Float", field: "total_slack_delta", width: 100, formatter: signedFmt1, sorter: "number", visible: false },
    ];

    const table = new Tabulator(el, {
      data: rows,
      layout: "fitDataStretch",
      height: 600,
      pagination: true,
      paginationSize: 100,
      paginationSizeSelector: [25, 50, 100, 250, 500, true],
      columns,
    });
    window.__ALL_TASKS_TABLE__ = table;

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

    const m = results.manipulation || {};
    const rawScore = m.overall_score;
    const isNull = rawScore === null || rawScore === undefined;
    const score = isNull ? 0 : Number(rawScore);
    const remainder = Math.max(0, 100 - score);

    // Fuse-inspired 4-band color scale.
    // Null / single-file mode -> gray "N/A" gauge.
    let color;
    if (isNull) {
      color = "rgba(255, 255, 255, 0.18)";
    } else if (score <= 25) {
      color = "#3dd68c"; // green
    } else if (score <= 50) {
      color = "#f5b83d"; // yellow
    } else if (score <= 75) {
      color = "#ff944d"; // orange
    } else {
      color = "#ff5c6c"; // red
    }

    // Subtitle: "X findings across Y tasks (Z deduplicated)"
    const subtitleEl = document.getElementById("manipulation-gauge-subtitle");
    if (subtitleEl) {
      if (isNull) {
        subtitleEl.textContent =
          "N/A — Comparative analysis required. " +
          (m.change_count || 0) + " single-file findings shown below.";
      } else {
        const findings = m.change_count || 0;
        const tasks = m.detail_task_count || 0;
        const dedup = m.deduplicated_count || 0;
        subtitleEl.textContent =
          findings + " findings across " + tasks + " tasks (" +
          dedup + " deduplicated, scored " + score.toFixed(1) + "/100)";
      }
    }

    // Replace the numeric label next to the gauge when the score is null.
    const labelEl = document.getElementById("manipulation-gauge-label");
    if (labelEl) {
      labelEl.textContent = isNull ? "N/A" : (score.toFixed(1) + "/100");
      labelEl.classList.toggle("gauge-null", isNull);
    }

    new Chart(canvas.getContext("2d"), {
      type: "doughnut",
      data: {
        labels: ["Score", "Remaining"],
        datasets: [
          {
            data: isNull ? [1, 0] : [score, remainder],
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

  /* --------------------------- Trend charts ------------------------------ */

  function initTrendCharts(results) {
    const trend = results.trend;
    if (!trend || !hasChart()) return;
    const points = trend.data_points || [];
    if (!points.length) return;

    const labels = points.map((p) => p.update_label);
    const axis = {
      x: {
        ticks: { color: "#8690a3" },
        grid: { color: "rgba(255,255,255,0.06)" },
      },
      y: {
        ticks: { color: "#8690a3" },
        grid: { color: "rgba(255,255,255,0.06)" },
      },
    };
    const legend = { labels: { color: "#e6ebf2" } };

    // Completion drift: days of slip from the first update's finish.
    const compCanvas = document.getElementById("trend-completion-chart");
    if (compCanvas) {
      const baselineFinish = points[0].project_finish
        ? new Date(points[0].project_finish).getTime()
        : null;
      const driftDays = points.map((p) => {
        if (!p.project_finish || baselineFinish === null) return null;
        return (new Date(p.project_finish).getTime() - baselineFinish) / 86400000;
      });
      new Chart(compCanvas.getContext("2d"), {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: "Drift from initial finish (cal days)",
              data: driftDays,
              borderColor: "#ff5c6c",
              backgroundColor: "rgba(255,92,108,0.2)",
              tension: 0.2,
              fill: true,
            },
          ],
        },
        options: { responsive: true, plugins: { legend }, scales: axis },
      });
    }

    // Float trend (min + avg)
    const floatCanvas = document.getElementById("trend-float-chart");
    if (floatCanvas) {
      new Chart(floatCanvas.getContext("2d"), {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: "Min total float (d)",
              data: points.map((p) => p.total_float_min),
              borderColor: "#ff5c6c",
              tension: 0.2,
            },
            {
              label: "Avg total float (d)",
              data: points.map((p) => p.total_float_avg),
              borderColor: "#4a9eff",
              tension: 0.2,
            },
          ],
        },
        options: { responsive: true, plugins: { legend }, scales: axis },
      });
    }

    // SPI + BEI
    const spiCanvas = document.getElementById("trend-spi-chart");
    if (spiCanvas) {
      new Chart(spiCanvas.getContext("2d"), {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: "SPI",
              data: points.map((p) => p.spi),
              borderColor: "#3dd68c",
              tension: 0.2,
            },
            {
              label: "BEI",
              data: points.map((p) => p.bei),
              borderColor: "#f5b83d",
              tension: 0.2,
            },
          ],
        },
        options: { responsive: true, plugins: { legend }, scales: axis },
      });
    }

    // Manipulation score
    const manipCanvas = document.getElementById("trend-manip-chart");
    if (manipCanvas) {
      new Chart(manipCanvas.getContext("2d"), {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: "Manipulation score",
              data: points.map((p) => p.manipulation_score),
              borderColor: "#f5b83d",
              backgroundColor: "rgba(245,184,61,0.2)",
              tension: 0.2,
              fill: true,
            },
          ],
        },
        options: {
          responsive: true,
          plugins: { legend },
          scales: { ...axis, y: { ...axis.y, min: 0, max: 100 } },
        },
      });
    }

    // Stacked task status over time
    const statusCanvas = document.getElementById("trend-status-chart");
    if (statusCanvas) {
      new Chart(statusCanvas.getContext("2d"), {
        type: "bar",
        data: {
          labels,
          datasets: [
            {
              label: "Complete",
              data: points.map((p) => p.tasks_complete),
              backgroundColor: "rgba(61,214,140,0.75)",
            },
            {
              label: "In progress",
              data: points.map((p) => p.tasks_in_progress),
              backgroundColor: "rgba(245,184,61,0.75)",
            },
            {
              label: "Not started",
              data: points.map((p) => p.tasks_not_started),
              backgroundColor: "rgba(255,255,255,0.08)",
            },
          ],
        },
        options: {
          responsive: true,
          plugins: { legend },
          scales: {
            x: { ...axis.x, stacked: true },
            y: { ...axis.y, stacked: true },
          },
        },
      });
    }
  }

  /* ------------------------------ Settings ------------------------------- */

  function initSettingsPage() {
    // No client-side state yet — Phase 4 settings are env-var driven.
  }

  /* ------------------------- DCMA drill-down ----------------------------- */

  function initDcmaDrilldown() {
    document.querySelectorAll(".dcma-clickable").forEach((row) => {
      row.addEventListener("click", () => {
        const num = row.dataset.dcmaRow;
        const details = document.querySelector(
          `tr[data-dcma-details="${num}"]`
        );
        if (!details) return;
        if (details.style.display === "none") {
          details.style.display = "";
          const toggle = row.querySelector(".drill-toggle");
          if (toggle) toggle.textContent = "▾";
        } else {
          details.style.display = "none";
          const toggle = row.querySelector(".drill-toggle");
          if (toggle) toggle.textContent = "▸";
        }
      });
    });
  }

  /* ------------------------- Field selector ------------------------------ */

  const FIELD_SELECTOR_STORAGE_KEY = "schedule-forensics-visible-fields";

  function initFieldSelector(results) {
    const btn = document.getElementById("field-selector-btn");
    const panel = document.getElementById("field-selector-panel");
    const grid = document.getElementById("field-checkbox-grid");
    const table = window.__ALL_TASKS_TABLE__;
    if (!btn || !panel || !grid || !table) return;

    btn.addEventListener("click", () => {
      panel.style.display = panel.style.display === "none" ? "" : "none";
    });

    // Load persisted selection
    let saved = null;
    try {
      const raw = window.localStorage.getItem(FIELD_SELECTOR_STORAGE_KEY);
      saved = raw ? JSON.parse(raw) : null;
    } catch (e) {
      saved = null;
    }

    const cols = table.getColumns();
    cols.forEach((col) => {
      const def = col.getDefinition();
      if (!def.field || def.field === "focus") return;

      // Apply saved visibility
      if (saved && typeof saved[def.field] === "boolean") {
        if (saved[def.field]) col.show();
        else col.hide();
      }

      const label = document.createElement("label");
      label.className = "field-checkbox";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = col.isVisible();
      input.dataset.field = def.field;
      input.addEventListener("change", () => {
        if (input.checked) col.show();
        else col.hide();
        saveFieldSelection();
      });
      const span = document.createElement("span");
      span.textContent = def.title || def.field;
      label.appendChild(input);
      label.appendChild(span);
      grid.appendChild(label);
    });

    function saveFieldSelection() {
      const state = {};
      table.getColumns().forEach((c) => {
        const d = c.getDefinition();
        if (d.field && d.field !== "focus") {
          state[d.field] = c.isVisible();
        }
      });
      try {
        window.localStorage.setItem(
          FIELD_SELECTOR_STORAGE_KEY,
          JSON.stringify(state)
        );
      } catch (e) {
        /* quota or privacy mode — ignore */
      }
    }
  }

  /* ---------------------------- Gantt view ------------------------------- */

  function initGanttView(results) {
    const container = document.getElementById("gantt-container");
    if (!container) return;
    const leftEl = document.getElementById("gantt-left");
    const rightEl = document.getElementById("gantt-right");
    if (!leftEl || !rightEl) return;

    const schedule = results.later_schedule || results.prior_schedule || {};
    const priorSchedule = results.prior_schedule || {};
    const priorByUid = {};
    (priorSchedule.tasks || []).forEach((t) => (priorByUid[t.uid] = t));

    const tasks = (schedule.tasks || []).filter((t) => t.start && t.finish);
    if (!tasks.length) {
      container.innerHTML =
        '<p class="muted">No tasks with dates to render.</p>';
      return;
    }

    // Determine time range
    let minT = Infinity;
    let maxT = -Infinity;
    tasks.forEach((t) => {
      const s = new Date(t.start).getTime();
      const f = new Date(t.finish).getTime();
      if (s < minT) minT = s;
      if (f > maxT) maxT = f;
    });
    const DAY_MS = 86400000;
    const totalDays = Math.max(1, Math.ceil((maxT - minT) / DAY_MS));
    const pxPerDay = 6;
    const rowHeight = 24;
    const width = Math.max(600, totalDays * pxPerDay + 80);
    const height = tasks.length * rowHeight + 40;
    const statusDateStr = (schedule.project_info || {}).status_date;
    const statusX = statusDateStr
      ? ((new Date(statusDateStr).getTime() - minT) / DAY_MS) * pxPerDay
      : null;

    // Build left-side task list (indented)
    leftEl.innerHTML = "";
    tasks.forEach((t) => {
      const row = document.createElement("div");
      row.className = "gantt-row-left";
      row.style.paddingLeft = `${(t.outline_level || 0) * 16 + 8}px`;
      row.style.height = `${rowHeight}px`;
      let icon = "";
      if (t.milestone) icon = "◆ ";
      if (t.summary) icon = "▣ ";
      const strong = t.summary ? "font-weight:600;" : "";
      row.innerHTML =
        `<span style="${strong}" title="${escapeHtml(t.name || "")}">` +
        `${icon}${escapeHtml(truncate(t.name || `Task ${t.uid}`, 48))}</span>`;
      row.dataset.uid = t.uid;
      row.addEventListener("click", () => {
        window.location.href = `/task-focus?uid=${t.uid}`;
      });
      leftEl.appendChild(row);
    });

    // Build right-side SVG
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", width);
    svg.setAttribute("height", height);
    svg.setAttribute("class", "gantt-svg");

    // Month gridlines + labels
    const firstDate = new Date(minT);
    firstDate.setDate(1);
    const lastDate = new Date(maxT);
    const cursor = new Date(firstDate);
    while (cursor <= lastDate) {
      const x = ((cursor.getTime() - minT) / DAY_MS) * pxPerDay;
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", x);
      line.setAttribute("y1", 0);
      line.setAttribute("x2", x);
      line.setAttribute("y2", height);
      line.setAttribute("stroke", "rgba(255,255,255,0.06)");
      svg.appendChild(line);
      const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.setAttribute("x", x + 4);
      label.setAttribute("y", 14);
      label.setAttribute("fill", "#8690a3");
      label.setAttribute("font-size", "11");
      const monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
      label.textContent = `${monthNames[cursor.getMonth()]} ${cursor.getFullYear()}`;
      svg.appendChild(label);
      cursor.setMonth(cursor.getMonth() + 1);
    }

    // Task bars
    tasks.forEach((t, i) => {
      const y = 24 + i * rowHeight + 4;
      const s = new Date(t.start).getTime();
      const f = new Date(t.finish).getTime();
      const x = ((s - minT) / DAY_MS) * pxPerDay;
      const w = Math.max(2, ((f - s) / DAY_MS) * pxPerDay);
      const prior = priorByUid[t.uid];
      if (prior && prior.start && prior.finish) {
        const ps = new Date(prior.start).getTime();
        const pf = new Date(prior.finish).getTime();
        const px = ((ps - minT) / DAY_MS) * pxPerDay;
        const pw = Math.max(2, ((pf - ps) / DAY_MS) * pxPerDay);
        const ghost = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        ghost.setAttribute("x", px);
        ghost.setAttribute("y", y);
        ghost.setAttribute("width", pw);
        ghost.setAttribute("height", rowHeight - 8);
        ghost.setAttribute("fill", "rgba(255,255,255,0.1)");
        ghost.setAttribute("stroke", "rgba(255,255,255,0.2)");
        ghost.setAttribute("stroke-dasharray", "3,3");
        svg.appendChild(ghost);
      }

      if (t.milestone) {
        const size = 6;
        const poly = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
        poly.setAttribute(
          "points",
          `${x},${y + rowHeight / 2 - 4} ${x + size},${y + rowHeight / 2 - 4 - size} ${x + size * 2},${y + rowHeight / 2 - 4} ${x + size},${y + rowHeight / 2 - 4 + size}`
        );
        poly.setAttribute("fill", "#f5b83d");
        svg.appendChild(poly);
      } else if (t.summary) {
        const bar = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        bar.setAttribute("x", x);
        bar.setAttribute("y", y);
        bar.setAttribute("width", w);
        bar.setAttribute("height", 4);
        bar.setAttribute("fill", "#e6ebf2");
        svg.appendChild(bar);
      } else {
        const pct = Number(t.percent_complete || 0) / 100;
        const bar = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        bar.setAttribute("x", x);
        bar.setAttribute("y", y);
        bar.setAttribute("width", w);
        bar.setAttribute("height", rowHeight - 8);
        bar.setAttribute("rx", 2);
        let color = "#5a6578";
        if (t.critical) color = "#ff5c6c";
        else if (pct >= 1) color = "#3dd68c";
        else if (pct > 0) color = "#4a9eff";
        bar.setAttribute("fill", color);
        bar.setAttribute("opacity", "0.85");
        svg.appendChild(bar);

        if (pct > 0 && pct < 1) {
          const done = document.createElementNS("http://www.w3.org/2000/svg", "rect");
          done.setAttribute("x", x);
          done.setAttribute("y", y);
          done.setAttribute("width", w * pct);
          done.setAttribute("height", rowHeight - 8);
          done.setAttribute("rx", 2);
          done.setAttribute("fill", "#3dd68c");
          svg.appendChild(done);
        }

        // Tooltip
        const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
        title.textContent = `${t.name || "Task " + t.uid}\n${shortDateValue(t.start)} → ${shortDateValue(t.finish)}`;
        bar.appendChild(title);
      }
    });

    if (statusX !== null) {
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", statusX);
      line.setAttribute("y1", 0);
      line.setAttribute("x2", statusX);
      line.setAttribute("y2", height);
      line.setAttribute("stroke", "#4a9eff");
      line.setAttribute("stroke-width", "1.5");
      line.setAttribute("stroke-dasharray", "4,3");
      svg.appendChild(line);
    }

    rightEl.innerHTML = "";
    rightEl.appendChild(svg);

    // Synchronized vertical scrolling
    leftEl.addEventListener("scroll", () => {
      rightEl.scrollTop = leftEl.scrollTop;
    });
    rightEl.addEventListener("scroll", () => {
      leftEl.scrollTop = rightEl.scrollTop;
    });
  }

  function escapeHtml(s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  /* ---------------------- Task focus (separate page) --------------------- */

  function initTaskFocusPage() {
    const btn = document.getElementById("task-ai-btn");
    const out = document.getElementById("task-ai-output");
    if (!btn || !out) return;

    btn.addEventListener("click", async () => {
      btn.classList.add("loading");
      btn.disabled = true;
      out.innerHTML = "";
      try {
        const fd = new FormData();
        fd.append(
          "request",
          "Explain this task's driving chain in plain English. " +
            "Describe what is currently controlling its start date, " +
            "which predecessors have slack, and what would happen if " +
            "the target slipped by one day."
        );
        const resp = await fetch("/ai-analyze", { method: "POST", body: fd });
        if (!resp.ok || !resp.body) {
          out.textContent = `Error: ${resp.statusText}`;
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
              try {
                const msg = JSON.parse(frame.slice(6));
                if (msg.chunk) out.textContent += msg.chunk;
                if (msg.error) out.textContent += `\n[ERROR] ${msg.error}`;
              } catch (e) {
                /* ignore */
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
})();
