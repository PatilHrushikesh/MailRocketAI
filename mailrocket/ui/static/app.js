(() => {
  "use strict";

  const SCALAR_KEYS = ["subject", "body", "company_name"];
  const INT_KEYS = ["match_percentage", "experience_gap", "mail_sent"];
  const TRISTATE_KEYS = ["should_apply"];
  const BOOL_KEYS = ["final_decision"];
  const LIST_KEYS = ["contact_email", "contact_number", "application_link"];

  const toast = document.getElementById("toast");
  let toastTimer = null;

  function showToast(message, ok = true) {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.remove("is-ok", "is-err");
    toast.classList.add(ok ? "is-ok" : "is-err");
    toast.hidden = false;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.hidden = true; }, 2400);
  }

  function collect(form) {
    const fd = new FormData(form);
    const out = {};

    for (const k of SCALAR_KEYS) {
      const v = fd.get(k);
      if (v !== null) out[k] = String(v);
    }
    for (const k of INT_KEYS) {
      const v = fd.get(k);
      if (v === null || v === "") continue;
      const n = Number(v);
      if (Number.isFinite(n)) out[k] = n;
    }
    for (const k of TRISTATE_KEYS) {
      const v = fd.get(k);
      if (v === "" || v === null) continue;
      out[k] = v === "true";
    }
    for (const k of BOOL_KEYS) {
      out[k] = fd.get(k) === "true";
    }
    for (const k of LIST_KEYS) {
      const raw = fd.get(k);
      if (raw === null) continue;
      const items = String(raw)
        .split(/[,\n]/)
        .map((s) => s.trim())
        .filter(Boolean);
      out[k] = items;
    }
    return out;
  }

  async function saveAnalysis(form) {
    const id = form.dataset.analysisId;
    if (!id) return;

    const body = collect(form);
    const btn = document.querySelector('[data-action="save"]');
    const originalLabel = btn ? btn.textContent : null;
    if (btn) { btn.disabled = true; btn.textContent = "Saving..."; }

    try {
      const r = await fetch(`/api/analyses/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const detail = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(detail.detail || `HTTP ${r.status}`);
      }
      const data = await r.json();
      showToast(`Saved ${data.fields.length} field(s)`, true);
      form.classList.remove("is-dirty");
    } catch (err) {
      console.error(err);
      showToast(`Save failed: ${err.message}`, false);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = originalLabel || "Save"; }
    }
  }

  function getForm() {
    return document.querySelector("form.analysis-form");
  }

  function isFormDirty() {
    const form = getForm();
    return !!(form && form.classList.contains("is-dirty"));
  }

  function trackFormDirty() {
    const form = getForm();
    if (!form) return;
    const markDirty = () => form.classList.add("is-dirty");
    form.addEventListener("input", markDirty);
    form.addEventListener("change", markDirty);
    window.addEventListener("beforeunload", (ev) => {
      if (form.classList.contains("is-dirty")) {
        ev.preventDefault();
        ev.returnValue = "";
      }
    });
  }

  document.addEventListener("click", (ev) => {
    const target = ev.target;
    if (!(target instanceof HTMLElement)) return;
    if (target.closest('[data-action="save"]')) {
      ev.preventDefault();
      const form = getForm();
      if (form) saveAnalysis(form);
    } else if (target.closest('[data-action="reset"]')) {
      ev.preventDefault();
      const form = getForm();
      if (form && form.classList.contains("is-dirty")
          && !confirm("Discard unsaved changes and reload?")) return;
      reloadNow();
    } else if (target.closest("#manual-reload")) {
      ev.preventDefault();
      reloadNow();
    }
  });

  document.addEventListener("keydown", (ev) => {
    if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "s") {
      const form = getForm();
      if (!form) return;
      ev.preventDefault();
      saveAnalysis(form);
    }
  });

  /* ---------- Auto-refresh ---------- */
  const STORAGE_KEY = "mr.autoRefresh.seconds";
  let refreshTimerStart = 0;
  let refreshIntervalSeconds = 0;
  let countdownHandle = null;

  function reloadNow() {
    const form = getForm();
    if (form && form.classList.contains("is-dirty")) {
      if (!confirm("You have unsaved analysis changes. Reload anyway?")) return;
    }
    window.location.reload();
  }

  function fmtRemaining(s) {
    if (s <= 0) return "now";
    if (s < 60) return s + "s";
    const m = Math.floor(s / 60);
    const r = s % 60;
    return r ? `${m}m ${r}s` : `${m}m`;
  }

  function setStatus(text, dirty = false) {
    const el = document.getElementById("auto-refresh-status");
    if (!el) return;
    el.textContent = text;
    el.classList.toggle("is-paused", !!dirty);
  }

  function stopAutoRefresh() {
    if (countdownHandle !== null) {
      clearInterval(countdownHandle);
      countdownHandle = null;
    }
    setStatus("");
  }

  function startAutoRefresh(seconds) {
    stopAutoRefresh();
    refreshIntervalSeconds = seconds;
    if (!seconds) return;
    refreshTimerStart = Date.now();
    const tick = () => {
      const elapsed = Math.floor((Date.now() - refreshTimerStart) / 1000);
      const remaining = refreshIntervalSeconds - elapsed;
      if (isFormDirty()) {
        refreshTimerStart = Date.now() - Math.min(elapsed, refreshIntervalSeconds - 1) * 1000;
        setStatus("paused (unsaved)", true);
        return;
      }
      if (document.visibilityState === "hidden") {
        setStatus(`in ${fmtRemaining(remaining)} (bg)`);
        return;
      }
      if (remaining <= 0) {
        setStatus("reloading...");
        clearInterval(countdownHandle);
        countdownHandle = null;
        window.location.reload();
        return;
      }
      setStatus(`in ${fmtRemaining(remaining)}`);
    };
    tick();
    countdownHandle = setInterval(tick, 1000);
  }

  function initAutoRefresh() {
    const select = document.getElementById("auto-refresh-select");
    if (!select) return;

    let saved = parseInt(localStorage.getItem(STORAGE_KEY) || "0", 10);
    if (!Number.isFinite(saved) || saved < 0) saved = 0;
    const allowed = Array.from(select.options).map((o) => parseInt(o.value, 10));
    if (!allowed.includes(saved)) saved = 0;
    select.value = String(saved);

    select.addEventListener("change", () => {
      const v = parseInt(select.value, 10) || 0;
      localStorage.setItem(STORAGE_KEY, String(v));
      startAutoRefresh(v);
    });

    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible" && refreshIntervalSeconds > 0) {
        startAutoRefresh(refreshIntervalSeconds);
      }
    });

    startAutoRefresh(saved);
  }

  function initListFilters() {
    const forms = document.querySelectorAll("form.list-filters[data-autosubmit]");
    if (!forms.length) return;

    document.documentElement.classList.add("js-on");

    forms.forEach((form) => {
      let pending = null;

      const submit = () => {
        // Drop empty fields so the URL stays clean (e.g. ?status=all
        // rather than ?status=all&min_match=&company=).
        form.querySelectorAll("input, select").forEach((el) => {
          if (el.type !== "hidden" && el.value === "") el.disabled = true;
        });
        form.submit();
      };

      const debounced = () => {
        if (pending) clearTimeout(pending);
        pending = setTimeout(submit, 350);
      };

      form.addEventListener("change", (e) => {
        // <select> changes feel snappier with no debounce.
        if (e.target.tagName === "SELECT") {
          if (pending) { clearTimeout(pending); pending = null; }
          submit();
        } else {
          debounced();
        }
      });

      // Submit immediately on Enter inside number/text inputs.
      form.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          if (pending) { clearTimeout(pending); pending = null; }
          submit();
        }
      });
    });
  }

  trackFormDirty();
  initAutoRefresh();
  initListFilters();
})();
