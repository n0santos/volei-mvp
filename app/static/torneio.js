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

async function loadActiveTournament() {
  const t = await api("/api/tournaments/active");
  if (t) {
    tournamentId = t.id;
    $("tournamentName").textContent = `${t.name} (${t.start_date} a ${t.end_date})`;
    $("newTournament").classList.add("hidden");
    $("tournamentPanel").classList.remove("hidden");
    await loadState();
  } else {
    tournamentId = null;
    $("tournamentName").textContent = "Nenhum torneio ativo";
    $("newTournament").classList.remove("hidden");
    $("tournamentPanel").classList.add("hidden");
  }
}

async function loadState() {
  const state = await api(`/api/tournaments/${tournamentId}`);
  $("teams").innerHTML = state.teams.map(renderTeam).join("");
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
  await api("/api/tournaments", {
    method: "POST",
    body: JSON.stringify({
      name: $("tournamentNameInput").value,
      start_date: $("tournamentStart").value,
      end_date: $("tournamentEnd").value,
    }),
  });
  await loadActiveTournament();
});

$("teamForm").addEventListener("submit", async e => {
  e.preventDefault();
  await api(`/api/tournaments/${tournamentId}/teams`, {
    method: "POST",
    body: JSON.stringify({ code: $("teamCode").value }),
  });
  $("teamCode").value = "";
  await loadState();
});

$("teams").addEventListener("submit", async e => {
  if (!e.target.classList.contains("add-player-form")) return;
  e.preventDefault();
  const teamId = e.target.dataset.teamId;
  const input = e.target.querySelector(".player-search");
  const name = input.value.trim();
  if (!name) return;

  const players = await api("/api/players");
  const match = players.find(p => p.name.toLowerCase() === name.toLowerCase());
  if (!match) {
    toast("Jogador não encontrado — cadastre primeiro na pelada");
    return;
  }

  try {
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

loadActiveTournament();
