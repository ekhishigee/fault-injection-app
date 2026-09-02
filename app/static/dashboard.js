(function () {
  const RESOURCE = ["cpu", "memory", "disk"];
  const APP = ["http_500", "slow_api", "health_fail"];
  const SERVICE_FAULTS = { target: "app_down", nginx: "nginx_down" };

  const params = new URLSearchParams(window.location.search);
  const token = params.get("token") || readCookie("demo_token");
  const headers = { "Content-Type": "application/json" };
  if (token) headers["X-Demo-Token"] = token;

  const resourceBody = document.getElementById("resource-faults");
  const appBody = document.getElementById("app-faults");
  const serviceBody = document.getElementById("services");
  const historyBody = document.getElementById("history");
  if (!resourceBody) return;

  document.getElementById("reset").addEventListener("click", function () {
    post("/faults/reset");
  });

  refresh();
  setInterval(refresh, 4000);
  setInterval(tickElapsed, 1000);

  function refresh() {
    fetch("/api/status", { headers: headers })
      .then(parseJson)
      .then(render)
      .catch(function (err) {
        showError(err.message || String(err));
      });
  }

  function render(data) {
    showError("");
    const sys = data.system || {};
    const catalog = data.catalog || {};
    setGauge("cpu", sys.cpu_percent);
    setGauge("memory", sys.memory_percent);
    setGauge("disk", sys.disk_percent);
    setText("disk-path", sys.disk_path ? "(" + sys.disk_path + ")" : "");
    setText("runtime", data.runtime || "–");
    setText("updated", "updated " + new Date().toLocaleTimeString());

    fillFaultTable(resourceBody, RESOURCE, data.faults || {}, catalog);
    fillFaultTable(appBody, APP, data.faults || {}, catalog);
    fillServices(data.services || {}, data.faults || {}, catalog);
    fillHistory(data.events || [], catalog);
  }

  function fillFaultTable(tbody, ids, faults, catalog) {
    tbody.innerHTML = "";
    ids.forEach(function (id) {
      const fault = faults[id] || { label: id, status: "IDLE" };
      const info = catalog[id] || {};
      const tr = document.createElement("tr");
      tr.innerHTML =
        "<td><strong>" + escapeHtml(fault.label || id) + "</strong>" + extra(fault) + "</td>" +
        "<td><span class=\"badge " + fault.status + "\">" + escapeHtml(fault.status) + "</span></td>" +
        "<td class=\"detail\">" + escapeHtml(info.alarm || "") + "<br>" + escapeHtml(info.expect_alarm || "") + "</td>" +
        "<td class=\"last-result-cell\">" + lastResult(fault) + "</td>" +
        "<td class=\"actions\"></td>";
      const actions = tr.lastChild;
      const trigger = button("Trigger", function () {
        post("/faults/" + id + "/start");
      }, "primary");
      trigger.disabled = fault.status === "ACTIVE" || fault.status === "RECOVERING";
      const stop = button("Stop", function () {
        post("/faults/" + id + "/stop");
      });
      stop.disabled = fault.status === "IDLE";
      actions.appendChild(trigger);
      actions.appendChild(stop);
      tbody.appendChild(tr);
    });
  }

  function fillServices(services, faults, catalog) {
    serviceBody.innerHTML = "";
    ["target", "nginx"].forEach(function (name) {
      const svc = services[name] || { status: "unknown" };
      const faultId = SERVICE_FAULTS[name];
      const fault = faults[faultId] || {};
      const info = catalog[faultId] || {};
      const running = svc.status === "running";
      const tr = document.createElement("tr");
      tr.innerHTML =
        "<td><strong>" + (name === "target" ? "Demo Target" : "Nginx") + "</strong></td>" +
        "<td><span class=\"badge " + (running ? "running" : "stopped") + "\">" +
        (running ? "Running" : "Stopped") + "</span></td>" +
        "<td class=\"detail\">" + escapeHtml(info.alarm || "") + "<br>" + escapeHtml(info.expect_alarm || "") + "</td>" +
        "<td class=\"last-result-cell\">" + lastResult(fault) + "</td>" +
        "<td class=\"actions\"></td>";
      const actions = tr.lastChild;
      actions.appendChild(button("Stop", function () {
        post("/services/" + name + "/stop");
      }, "danger"));
      actions.appendChild(button("Start", function () {
        post("/services/" + name + "/start");
      }, "primary"));
      actions.appendChild(button("Restart", function () {
        post("/services/" + name + "/restart");
      }));
      serviceBody.appendChild(tr);
    });
  }

  function fillHistory(events, catalog) {
    historyBody.innerHTML = "";
    if (!events.length) {
      historyBody.innerHTML = "<tr><td colspan=\"5\" class=\"muted\">No faults recorded yet. Trigger one to see the outcome here.</td></tr>";
      return;
    }
    events.forEach(function (event) {
      const info = catalog[event.fault_id] || {};
      const label = event.fault_id === "*" ? "All faults" : (info.label || event.fault_id);
      const tr = document.createElement("tr");
      tr.innerHTML =
        "<td>" + formatTime(event.created_at) + "</td>" +
        "<td>" + escapeHtml(label) + "</td>" +
        "<td>" + escapeHtml(event.action) + "</td>" +
        "<td><span class=\"badge " + resultClass(event.result) + "\">" + escapeHtml(displayResult(event.result)) + "</span></td>" +
        "<td class=\"detail\">" + escapeHtml(event.detail || event.source || "") + "</td>";
      historyBody.appendChild(tr);
    });
  }

  function extra(fault) {
    if (fault.status === "FAILED" && fault.error) {
      return "<div class=\"detail\">" + escapeHtml(fault.error) + "</div>";
    }
    return "";
  }

  function elapsedHtml(fault) {
    if (fault.status !== "ACTIVE" || !fault.started_at) return "";
    return (
      "<span class=\"elapsed\" data-started-at=\"" + fault.started_at + "\">" +
      formatElapsed(fault.started_at) +
      "</span>"
    );
  }

  function tickElapsed() {
    document.querySelectorAll(".elapsed[data-started-at]").forEach(function (el) {
      el.textContent = formatElapsed(el.getAttribute("data-started-at"));
    });
  }

  function formatElapsed(startedAt) {
    var seconds = Math.max(0, Math.floor(Date.now() / 1000 - Number(startedAt)));
    var hours = Math.floor(seconds / 3600);
    var minutes = Math.floor((seconds % 3600) / 60);
    var rest = seconds % 60;
    if (hours > 0) {
      return pad(hours) + ":" + pad(minutes) + ":" + pad(rest);
    }
    return pad(minutes) + ":" + pad(rest);
  }

  function pad(value) {
    return String(value).padStart(2, "0");
  }

  function lastResult(fault) {
    const event = fault.last_event;
    if (!event && fault.status !== "ACTIVE") return "—";
    const word = displayResult(event ? event.result : "started");
    const when = event && fault.status !== "ACTIVE"
      ? "<span class=\"last-when\">" + formatTime(event.created_at) + "</span>"
      : "";
    return (
      "<div class=\"last-result\">" +
      "<span class=\"badge " + resultClass(word) + "\">" + escapeHtml(word) + "</span>" +
      elapsedHtml(fault) +
      when +
      "</div>"
    );
  }

  function displayResult(result) {
    if (result === "recovered" || result === "auto_recovered") return "stopped";
    return result;
  }

  function resultClass(result) {
    if (result === "started") return "ACTIVE";
    if (result === "failed") return "FAILED";
    return "IDLE";
  }

  function setGauge(name, value) {
    setText(name, formatPct(value));
    const bar = document.getElementById(name + "-bar");
    if (bar) bar.style.width = value == null ? "0%" : Math.max(0, Math.min(100, value)) + "%";
  }

  function post(url) {
    fetch(url, { method: "POST", headers: headers })
      .then(parseJson)
      .then(render)
      .catch(function (err) {
        showError(err.message || String(err));
      });
  }

  function parseJson(response) {
    return response.json().then(function (body) {
      if (!response.ok) {
        throw new Error(body.error || ("HTTP " + response.status));
      }
      return body;
    });
  }

  function button(label, onClick, kind) {
    const el = document.createElement("button");
    el.type = "button";
    el.textContent = label;
    if (kind) el.className = kind;
    el.addEventListener("click", onClick);
    return el;
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function formatPct(value) {
    return value == null ? "–" : value + "%";
  }

  function formatTime(epoch) {
    if (!epoch) return "";
    return new Date(epoch * 1000).toLocaleString();
  }

  function showError(message) {
    const el = document.getElementById("error");
    if (el) el.textContent = message;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function readCookie(name) {
    const parts = ("; " + document.cookie).split("; " + name + "=");
    if (parts.length === 2) return parts.pop().split(";").shift();
    return "";
  }
})();
