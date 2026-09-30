// app/static/torneio.js
let tournamentId = null;

const $ = id => document.getElementById(id);

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.style.display = "block";
  clearTimeout(window._toast);
  window._toast = setTimeout(() => t.style.display = "none", 2200);
}

async function api(url, options = {}) {
  const r = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Erro");
  return data;
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// Lowercase + strip accents, so "cecilia" finds "Cecília" — useful with ~60
// names on the pre-list and phone keyboards that don't default to accents.
function normalize(s) {
  return String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

async function loadActiveTournament() {
  const t = await api("/api/tournaments/active");
  if (t) {
    tournamentId = t.id;
    $("tournamentName").textContent = `${t.name} (${t.start_date} a ${t.end_date})`;
    $("newTournament").classList.add("hidden");
    $("tournamentPanel").classList.remove("hidden");
    $("formTeamsSection").classList.remove("hidden");
    $("matchesSection").classList.remove("hidden");
    await loadState();
    await loadPlayerPool();
    await loadMatches();
  } else {
    tournamentId = null;
    $("tournamentName").textContent = "Nenhum torneio ativo";
    $("newTournament").classList.remove("hidden");
    $("tournamentPanel").classList.add("hidden");
    $("formTeamsSection").classList.add("hidden");
    $("matchesSection").classList.add("hidden");
  }
}

async function loadState() {
  const state = await api(`/api/tournaments/${tournamentId}`);
  $("teams").innerHTML = state.teams.map(renderTeam).join("");

  const anyOccupied = state.teams.some(team => team.players.length > 0);
  $("formTeamsBtn").disabled = anyOccupied;
  $("formTeamsBtn").title = anyOccupied
    ? "Remova os jogadores dos times antes de sortear de novo"
    : "";

  populateTeamSelect($("matchTeamA"), state.teams);
  populateTeamSelect($("matchTeamB"), state.teams);
}

function renderTeam(team) {
  const titulares = team.players.filter(p => p.role === "titular").length;
  return `
    <div class="panel" data-team-id="${team.id}">
      <h3>Time ${esc(team.code)} <span class="muted">(${team.players.length} jogador(es), ${titulares} titulares)</span></h3>
      <div class="player-grid">
        ${team.players.map(p => renderPlayer(team.id, p)).join("")}
      </div>
      <form class="inline add-player-form" data-team-id="${team.id}">
        <input placeholder="Nome do jogador" class="player-search" required>
        <button class="primary">Adicionar</button>
      </form>
    </div>
  `;
}

function renderPlayer(teamId, p) {
  return `
    <div class="player">
      <div class="info">
        <div class="name">${esc(p.name)} ${p.is_captain ? '<span class="badge wait">Capitão</span>' : ""}</div>
        <div class="muted">${p.role === "titular" ? "Titular" : "Reserva"}</div>
      </div>
      <div class="actions">
        <button data-action="toggle-role" data-team-id="${teamId}" data-player-id="${p.id}">
          ${p.role === "titular" ? "Reserva" : "Titular"}
        </button>
        <button data-action="toggle-captain" data-team-id="${teamId}" data-player-id="${p.id}">
          ${p.is_captain ? "Remover capitão" : "Capitão"}
        </button>
        <button class="danger" data-action="remove" data-team-id="${teamId}" data-player-id="${p.id}">Remover</button>
      </div>
    </div>
  `;
}

$("tournamentForm").addEventListener("submit", async e => {
  e.preventDefault();
  try {
    await api("/api/tournaments", {
      method: "POST",
      body: JSON.stringify({
        name: $("tournamentNameInput").value,
        start_date: $("tournamentStart").value,
        end_date: $("tournamentEnd").value,
      }),
    });
    await loadActiveTournament();
  } catch (err) {
    toast(err.message);
  }
});

$("teamForm").addEventListener("submit", async e => {
  e.preventDefault();
  try {
    await api(`/api/tournaments/${tournamentId}/teams`, {
      method: "POST",
      body: JSON.stringify({ code: $("teamCode").value }),
    });
    $("teamCode").value = "";
    await loadState();
  } catch (err) {
    toast(err.message);
  }
});

$("teams").addEventListener("submit", async e => {
  if (!e.target.classList.contains("add-player-form")) return;
  e.preventDefault();
  const teamId = e.target.dataset.teamId;
  const input = e.target.querySelector(".player-search");
  const name = input.value.trim();
  if (!name) return;

  try {
    const players = await api("/api/players");
    const matches = players.filter(p => normalize(p.name).includes(normalize(name)));
    if (matches.length === 0) {
      toast("Jogador não encontrado — cadastre primeiro na pelada");
      return;
    }
    if (matches.length > 1) {
      toast("Mais de um jogador encontrado — digite mais do nome");
      return;
    }
    const match = matches[0];

    await api(`/api/teams/${teamId}/players`, {
      method: "POST",
      body: JSON.stringify({ player_id: match.id }),
    });
    await loadState();
  } catch (err) {
    toast(err.message);
  }
});

$("teams").addEventListener("click", async e => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;
  const { action, teamId, playerId } = btn.dataset;

  try {
    if (action === "remove") {
      await api(`/api/teams/${teamId}/players/${playerId}`, { method: "DELETE" });
    } else if (action === "toggle-role") {
      const newRole = btn.textContent.trim() === "Reserva" ? "reserva" : "titular";
      await api(`/api/teams/${teamId}/players/${playerId}`, {
        method: "PATCH",
        body: JSON.stringify({ role: newRole }),
      });
    } else if (action === "toggle-captain") {
      const makeCaptain = btn.textContent.trim() === "Capitão";
      await api(`/api/teams/${teamId}/players/${playerId}`, {
        method: "PATCH",
        body: JSON.stringify({ is_captain: makeCaptain }),
      });
    }
    await loadState();
  } catch (err) {
    toast(err.message);
  }
});

let selectedPoolIds = new Set();
let allPlayers = [];

async function loadPlayerPool() {
  allPlayers = await api("/api/players");
  renderPlayerPool();
}

function filteredPoolPlayers() {
  const search = normalize($("playerPoolSearch").value.trim());
  return allPlayers.filter(p => normalize(p.name).includes(search));
}

function renderPlayerPool() {
  $("playerPool").innerHTML = filteredPoolPlayers().map(p => `
    <label class="player">
      <div class="info">
        <div class="name">${esc(p.name)}</div>
        <div class="muted">${p.gender} · score ${p.score}</div>
      </div>
      <input type="checkbox" data-player-id="${p.id}" ${selectedPoolIds.has(p.id) ? "checked" : ""}>
    </label>
  `).join("");
  $("poolCount").textContent = `${selectedPoolIds.size} selecionado(s)`;
}

$("playerPoolSearch").addEventListener("input", renderPlayerPool);

$("playerPool").addEventListener("change", e => {
  const checkbox = e.target.closest("input[type=checkbox]");
  if (!checkbox) return;
  const id = Number(checkbox.dataset.playerId);
  if (checkbox.checked) selectedPoolIds.add(id);
  else selectedPoolIds.delete(id);
  $("poolCount").textContent = `${selectedPoolIds.size} selecionado(s)`;
});

$("selectAllPlayers").addEventListener("change", e => {
  const ids = filteredPoolPlayers().map(p => p.id);
  if (e.target.checked) {
    ids.forEach(id => selectedPoolIds.add(id));
  } else {
    ids.forEach(id => selectedPoolIds.delete(id));
  }
  renderPlayerPool();
});

$("formTeamsBtn").addEventListener("click", async () => {
  $("formTeamsBtn").disabled = true;
  if (selectedPoolIds.size === 0) {
    toast("Selecione pelo menos um jogador");
    $("formTeamsBtn").disabled = false;
    return;
  }
  try {
    await api(`/api/tournaments/${tournamentId}/form-teams`, {
      method: "POST",
      body: JSON.stringify({ player_ids: Array.from(selectedPoolIds) }),
    });
    selectedPoolIds.clear();
    renderPlayerPool();
    await loadState();
  } catch (err) {
    toast(err.message);
    await loadState();
  }
});

function populateTeamSelect(select, teams) {
  const previous = select.value;
  select.innerHTML = teams.map(t => `<option value="${t.id}">${esc(t.code)}</option>`).join("");
  if (teams.some(t => String(t.id) === previous)) select.value = previous;
}

async function loadMatches() {
  const matches = await api(`/api/tournaments/${tournamentId}/matches`);
  renderMatches(matches);
}

function renderMatches(matches) {
  const next = matches.find(m => m.status !== "encerrado");
  $("matches").innerHTML = matches.map(m => renderMatch(m, next && m.id === next.id)).join("");
}

function renderMatch(m, isNext) {
  const when = new Date(m.scheduled_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
  return `
    <div class="player ${isNext ? "status-arrived" : ""}" data-match-id="${m.id}">
      <div class="info">
        <div class="name">
          ${esc(m.team_a_code)} × ${esc(m.team_b_code)}
          ${m.is_final ? '<span class="badge wait">Final</span>' : ""}
        </div>
        <div class="muted">${when}${m.court ? " · " + esc(m.court) : ""} · ${m.status}</div>
      </div>
      <div class="actions">
        ${m.status === "agendado" ? `<button data-action="start" data-match-id="${m.id}">Iniciar</button>` : ""}
        ${m.status === "em_andamento" ? `<button data-action="finish" data-match-id="${m.id}">Encerrar</button>` : ""}
        <button class="danger" data-action="remove-match" data-match-id="${m.id}">Remover</button>
      </div>
    </div>
  `;
}

$("matchForm").addEventListener("submit", async e => {
  e.preventDefault();
  try {
    await api(`/api/tournaments/${tournamentId}/matches`, {
      method: "POST",
      body: JSON.stringify({
        team_a_id: Number($("matchTeamA").value),
        team_b_id: Number($("matchTeamB").value),
        scheduled_at: $("matchScheduledAt").value,
        court: $("matchCourt").value || null,
        is_final: $("matchIsFinal").checked,
      }),
    });
    $("matchScheduledAt").value = "";
    $("matchCourt").value = "";
    $("matchIsFinal").checked = false;
    await loadMatches();
  } catch (err) {
    toast(err.message);
  }
});

$("matches").addEventListener("click", async e => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;
  const { action, matchId } = btn.dataset;

  try {
    if (action === "start") {
      await api(`/api/tournaments/${tournamentId}/matches/${matchId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "em_andamento" }),
      });
    } else if (action === "finish") {
      await api(`/api/tournaments/${tournamentId}/matches/${matchId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "encerrado" }),
      });
    } else if (action === "remove-match") {
      await api(`/api/tournaments/${tournamentId}/matches/${matchId}`, { method: "DELETE" });
    }
    await loadMatches();
  } catch (err) {
    toast(err.message);
  }
});

loadActiveTournament().catch(err => toast(err.message));
