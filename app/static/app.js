let sessionId = null;
let socket = null;
let state = null;

const $ = id => document.getElementById(id);

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.style.display = "block";
  clearTimeout(window._toast);
  window._toast = setTimeout(() => t.style.display = "none", 2200);
}

async function api(url, options={}) {
  const r = await fetch(url, {
    headers: {"Content-Type":"application/json"},
    ...options
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Erro");
  return data;
}

async function loadPlayers() {
  const ps = await api("/api/players");
  $("masterPlayers").innerHTML = ps.map(p => `
    <div class="player">
      <div class="info">
        <div class="name">${esc(p.name)}</div>
        <div class="muted">${p.score} pts · ${p.gender}</div>
      </div>
    </div>
  `).join("");
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));
}

async function loadActive() {
  const s = await api("/api/sessions/active");
  if (s) {
    sessionId = s.id;
    $("sessionName").textContent = s.name;
    $("sessionPanel").classList.remove("hidden");
    $("setup").classList.add("hidden");
    connectWS();
    await refresh();
  }
}

function connectWS() {
  if (socket) socket.close();
  const proto = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${proto}://${location.host}/ws/${sessionId}`);
  socket.onmessage = e => refresh();
}

async function refresh() {
  if (!sessionId) return;
  state = await api(`/api/sessions/${sessionId}`);
  renderAttendance();
  renderMatch();
}

function renderAttendance() {
  const ps = state.players;
  const arrived = ps.filter(p => p.status === "arrived").length;
  const active = ps.filter(p => ["arrived"].includes(p.status)).length;
  $("counts").textContent = `${arrived} presentes · ${state.match_count} partidas registradas`;

  $("attendance").innerHTML = ps.map(p => {
    let action = "";
    if (p.status === "expected") {
      action = `<button onclick="setAttendance(${p.id},'arrived')" class="primary">Chegou</button>`;
    } else if (p.status === "arrived") {
      action = `<button onclick="setAttendance(${p.id},'left')">Foi embora</button>`;
    } else if (p.status === "absent") {
      action = `<button onclick="setAttendance(${p.id},'arrived')">Chegou afinal</button>`;
    } else {
      action = `<button onclick="setAttendance(${p.id},'arrived')">Voltou</button>`;
    }
    return `
      <div class="player status-${p.status}">
        <div class="info">
          <div class="name">${esc(p.name)}
            <span class="badge">${p.gender}</span>
            ${p.outside_streak >= 1 ? `<span class="badge wait">espera ${p.outside_streak}</span>` : ''}
          </div>
          <div class="muted">
            ${statusText(p.status)}
            · ${p.matches} partidas
          </div>
        </div>
        ${action}
      </div>`;
  }).join("");
}

function statusText(s) {
  return ({
    expected:"Pré-lista",
    arrived:"Presente",
    absent:"Faltou",
    left:"Foi embora"
  })[s] || s;
}

async function setAttendance(id, status) {
  try {
    await api(`/api/sessions/${sessionId}/attendance/${id}`, {
      method:"PATCH", body:JSON.stringify({status})
    });
    await refresh();
  } catch(e) { toast(e.message); }
}

function renderMatch() {
  const m = state.current_match;
  if (!m) {
    $("matchPanel").classList.add("hidden");
    return;
  }
  $("matchPanel").classList.remove("hidden");
  $("matchTitle").textContent = `Partida ${m.number}`;
  const a = m.teams.A, b = m.teams.B;
  const sa = a.reduce((x,p)=>x+p.score,0);
  const sb = b.reduce((x,p)=>x+p.score,0);
  $("balance").textContent = `Time A: ${sa.toFixed(0)} · Time B: ${sb.toFixed(0)} · diferença: ${Math.abs(sa-sb).toFixed(0)}`;

  $("teams").innerHTML = ["A","B"].map(team => {
    const arr = m.teams[team];
    const total = arr.reduce((x,p)=>x+p.score,0);
    return `
      <div class="team">
        <h3>Time ${team}</h3>
        ${arr.map(p => `
          <div class="member">
            <span>${esc(p.name)} ${p.role === "substitute" ? '<span class="badge">sub</span>' : ''}</span>
            ${m.status === "running" && !p.exited ?
              `<button onclick="playerExit(${m.id},${p.id})">Saiu</button>` : ''}
          </div>`).join("")}
        <div class="total">Total: ${total.toFixed(0)}</div>
      </div>`;
  }).join("");

  $("startMatch").classList.toggle("hidden", m.status !== "proposed");
  $("finishMatch").classList.toggle("hidden", m.status !== "running");
  $("substitution").classList.add("hidden");
}

async function playerExit(matchId, playerId) {
  try {
    await api(`/api/matches/${matchId}/exit/${playerId}`, {method:"POST"});
    const candidates = await api(`/api/matches/${matchId}/substitutes`);
    const box = $("substitution");
    box.classList.remove("hidden");
    box.innerHTML = `
      <h3>Substituição necessária</h3>
      <p class="muted">Escolha quem entra. O sistema prioriza quem está esperando há mais tempo.</p>
      ${candidates.length ? candidates.map(p => `
        <button onclick="substitute(${matchId},${p.id})" style="display:block;width:100%;text-align:left;margin:6px 0">
          <strong>${esc(p.name)}</strong> · espera ${p.outside_streak} · ${p.minutes} min jogados
        </button>
      `).join("") : "<p>Ninguém disponível para substituir.</p>"}`;
    await refresh();
    $("substitution").classList.remove("hidden");
    // refresh() redraws and hides it; render again after candidate fetch
    $("substitution").classList.remove("hidden");
    $("substitution").innerHTML = `
      <h3>Substituição necessária</h3>
      ${candidates.length ? candidates.map(p => `
        <button onclick="substitute(${matchId},${p.id})" style="display:block;width:100%;text-align:left;margin:6px 0">
          <strong>${esc(p.name)}</strong> · espera ${p.outside_streak} partida(s)
        </button>
      `).join("") : "<p>Ninguém disponível.</p>"}`;
  } catch(e) { toast(e.message); }
}

async function substitute(matchId, playerId) {
  try {
    await api(`/api/matches/${matchId}/substitute`, {
      method:"POST", body:JSON.stringify({player_id:playerId})
    });
    $("substitution").classList.add("hidden");
    await refresh();
  } catch(e) { toast(e.message); }
}

$("togglePlayers").onclick = () => {
  $("setup").classList.toggle("hidden");
};

$("newSession").onclick = async () => {
  try {
    const name = prompt("Nome da sessão:", "Vôlei " + new Date().toLocaleDateString("pt-BR"));
    if (!name) return;
    const s = await api("/api/sessions", {
      method:"POST", body:JSON.stringify({name})
    });
    sessionId = s.id;
    $("sessionName").textContent = name;
    $("sessionPanel").classList.remove("hidden");
    $("setup").classList.add("hidden");
    connectWS();
    await refresh();
  } catch(e) { toast(e.message); }
};

$("playerForm").onsubmit = async e => {
  e.preventDefault();
  try {
    await api("/api/players", {
      method:"POST",
      body:JSON.stringify({
        name:$("playerName").value,
        score:Number($("playerScore").value),
        gender:$("playerGender").value
      })
    });
    $("playerName").value = "";
    await loadPlayers();
  } catch(e) { toast(e.message); }
};

$("addOutside").onclick = async () => {
  const name = prompt("Nome de quem apareceu fora da pré-lista:");
  if (!name) return;
  const score = Number(prompt("Score estimado:", "70") || 70);
  const gender = (prompt("Sexo (M/F/X):", "F") || "X").toUpperCase();
  try {
    const p = await api(`/api/sessions/${sessionId}/add-player`, {
      method:"POST",
      body:JSON.stringify({name,score,gender})
    });
    await setAttendance(p.id, "arrived");
  } catch(e) { toast(e.message); }
};

$("generate").onclick = async () => {
  try {
    const r = await api(`/api/sessions/${sessionId}/generate`, {method:"POST"});
    await refresh();
  } catch(e) { toast(e.message); }
};

$("startMatch").onclick = async () => {
  const m = state.current_match;
  if (!m) return;
  try {
    await api(`/api/matches/${m.id}/start`, {method:"POST"});
    await refresh();
  } catch(e) { toast(e.message); }
};

$("finishMatch").onclick = async () => {
  const m = state.current_match;
  if (!m) return;
  if (!confirm("Encerrar a partida?")) return;
  try {
    await api(`/api/matches/${m.id}/finish`, {method:"POST"});
    await refresh();
  } catch(e) { toast(e.message); }
};

$("resetMatch").onclick = async () => {
  if (!confirm("Apagar a partida proposta/em andamento e gerar novamente?")) return;
  try {
    await api(`/api/sessions/${sessionId}/reset-current`, {method:"POST"});
    await refresh();
  } catch(e) { toast(e.message); }
};

async function loadInitial() {
  try {
    await loadPlayers();
    await loadActive();
  } catch (e) {
    toast("Sem conexão com o servidor, tentando de novo...");
    setTimeout(loadInitial, 3000);
  }
}

loadInitial();
