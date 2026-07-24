/* --------------------------------------------------------------------------
   NeuroNudge frontend logic.
   Uses relative /api paths so the same code works in `vercel dev` and prod.
   Stores the JWT in localStorage under 'nn_token'.
   -------------------------------------------------------------------------- */

const API = "https://neuronudge-qpok.onrender.com"; // same origin — /api/* routes to the serverless function

// ---------- Token helpers ----------
const getToken   = () => localStorage.getItem("nn_token");
const setToken   = (t) => localStorage.setItem("nn_token", t);
const clearToken = () => localStorage.removeItem("nn_token");

// ---------- Generic fetch wrapper ----------
async function api(path, { method = "GET", body, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && getToken()) headers["Authorization"] = `Bearer ${getToken()}`;

  const res = await fetch(`${API}/api${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  const text = await res.text();
  const data = text ? JSON.parse(text) : {};
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

// ---------- Toast ----------
function toast(msg, isError = false) {
  const el = document.createElement("div");
  el.className = `toast${isError ? " error" : ""}`;
  el.textContent = msg;
  document.body.appendChild(el);
  requestAnimationFrame(() => el.classList.add("show"));
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 250);
  }, 2600);
}

// ---------- Route guard ----------
function requireAuth() {
  if (!getToken()) {
    window.location.href = "/login";
    return false;
  }
  return true;
}

// ---------- Signup ----------
function initSignup() {
  const form = document.getElementById("signup-form");
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email    = form.email.value.trim();
    const password = form.password.value;
    try {
      const data = await api("/signup", {
        method: "POST", auth: false, body: { email, password },
      });
      setToken(data.access_token);
      toast("Welcome to NeuroNudge!");
      setTimeout(() => (window.location.href = "/dashboard"), 500);
    } catch (err) { toast(err.message, true); }
  });
}

// ---------- Login ----------
function initLogin() {
  const form = document.getElementById("login-form");
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email    = form.email.value.trim();
    const password = form.password.value;
    try {
      const data = await api("/login", {
        method: "POST", auth: false, body: { email, password },
      });
      setToken(data.access_token);
      toast(`Welcome back, ${data.email}`);
      setTimeout(() => (window.location.href = "/dashboard"), 400);
    } catch (err) { toast(err.message, true); }
  });
}

// ---------- Dashboard ----------
function initDashboard() {
  if (!requireAuth()) return;

  const logoutBtn = document.getElementById("logout-btn");
  logoutBtn?.addEventListener("click", () => {
    clearToken();
    window.location.href = "/";
  });

  const form = document.getElementById("log-form");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      sleep_hours:       parseFloat(form.sleep_hours.value),
      stress_level:      parseInt(form.stress_level.value, 10),
      screen_time_hours: parseFloat(form.screen_time_hours.value),
      activity_minutes:  parseInt(form.activity_minutes.value, 10),
    };
    try {
      // 1. Persist the entry
      await api("/logs", { method: "POST", body: payload });
      // 2. Get an ML prediction + nudges for this entry
      const pred = await api("/predict", { method: "POST", body: payload });
      renderPrediction(pred);
      // 3. Refresh log history
      await loadLogs();
      toast("Entry logged");
      form.reset();
    } catch (err) { toast(err.message, true); }
  });

  loadUser();
  loadLogs();
}

async function loadUser() {
  try {
    const me = await api("/me");
    const el = document.getElementById("user-email");
    if (el) el.textContent = me.email;
  } catch { clearToken(); window.location.href = "/login"; }
}

async function loadLogs() {
  const tbody = document.getElementById("log-history");
  if (!tbody) return;
  try {
    const logs = await api("/logs");
    if (!logs.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="muted center">No entries yet — add your first log above.</td></tr>`;
      return;
    }
    tbody.innerHTML = logs.map((l) => `
      <tr>
        <td>${new Date(l.created_at).toLocaleString()}</td>
        <td>${l.sleep_hours} h</td>
        <td>${l.stress_level}/10</td>
        <td>${l.screen_time_hours} h</td>
        <td>${l.activity_minutes} min</td>
      </tr>
    `).join("");
  } catch (err) { toast(err.message, true); }
}

function renderPrediction(pred) {
  const box = document.getElementById("prediction-box");
  const pillClass = `risk-${pred.risk_level}`;
  const pct = Math.round(pred.risk_probability * 100);
  box.innerHTML = `
    <div>
      <span class="risk-pill ${pillClass}">${pred.risk_level} risk</span>
      <span class="muted" style="margin-left:10px">${pct}% probability of a dip in the next 48h</span>
    </div>
    <ul class="nudge-list">
      ${pred.nudges.map((n) => `<li>${n}</li>`).join("")}
    </ul>
  `;
}

// ---------- Boot ----------
document.addEventListener("DOMContentLoaded", () => {
  initSignup();
  initLogin();
  initDashboard();
});
