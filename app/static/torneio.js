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

// "2026-11-28" -> "28/11/2026" — the API's plain YYYY-MM-DD, formatted for pt-BR.
function fmtDate(s) {
  const [y, m, d] = s.split("-");
  return `${d}/${m}/${y}`;
}

async function loadActiveTournament() {
  const t = await api("/api/tournaments/active");
  if (t) {
    tournamentId = t.id;
    $("tournamentName").textContent = `${t.name} (${fmtDate(t.start_date)} a ${fmtDate(t.end_date)})`;
    $("newTournament").classList.add("hidden");
    $("tournamentPanel").classList.remove("hidden");
    $("matchesSection").classList.remove("hidden");
    $("standingsSection").classList.remove("hidden");
    await loadState();
    await loadMatches();
    await loadStandings();
    await loadPodium();
  } else {
    tournamentId = null;
    $("tournamentName").textContent = "Nenhum torneio ativo";
    $("newTournament").classList.remove("hidden");
    $("tournamentPanel").classList.add("hidden");
    $("matchesSection").classList.add("hidden");
    $("standingsSection").classList.add("hidden");
  }
}

async function loadState() {
  const state = await api(`/api/tournaments/${tournamentId}`);
  $("teams").innerHTML = state.teams.map(renderTeam).join("");

  populateTeamSelect($("matchTeamA"), state.teams);
  populateTeamSelect($("matchTeamB"), state.teams);
}

function renderTeam(team) {
  const titulares = team.players.filter(p => p.role === "titular").length;
  return `
    <div class="panel" data-team-id="${team.id}">
      <h3>Time ${esc(team.code)} <span class="muted">(${team.players.length}/${team.max_players} atletas, ${titulares} titulares)</span></h3>
      <label class="muted">Grupo
        <select class="group-select" data-team-id="${team.id}">
          <option value="">—</option>
          ${["A", "B"].map(g => `<option value="${g}"${team.group_name === g ? " selected" : ""}>${g}</option>`).join("")}
        </select>
      </label>
      <label class="muted">Limite de atletas
        <select class="max-players-select" data-team-id="${team.id}">
          ${[7, 8].map(n => `<option value="${n}"${team.max_players === n ? " selected" : ""}>${n}</option>`).join("")}
        </select>
      </label>
      <div class="roster-list">
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

$("teams").addEventListener("change", async e => {
  const isGroup = e.target.classList.contains("group-select");
  const isMax = e.target.classList.contains("max-players-select");
  if (!isGroup && !isMax) return;
  try {
    await api(`/api/teams/${e.target.dataset.teamId}`, {
      method: "PATCH",
      body: JSON.stringify(isGroup ? { group_name: e.target.value || null } : { max_players: Number(e.target.value) }),
    });
  } catch (err) {
    toast(err.message);
  }
  // Reload either way so a refused change snaps back to the stored value.
  await loadState();
  await loadStandings();
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

function populateTeamSelect(select, teams) {
  const previous = select.value;
  select.innerHTML = teams.map(t => `<option value="${t.id}">${esc(t.code)}</option>`).join("");
  if (teams.some(t => String(t.id) === previous)) select.value = previous;
}

const STAGE_LABELS = {
  semifinal_1: "Semifinal 1",
  semifinal_2: "Semifinal 2",
  terceiro_lugar: "3º lugar",
  final: "Final",
};

let lastMatches = [];
let lastStandings = [];

async function loadMatches() {
  const matches = await api(`/api/tournaments/${tournamentId}/matches`);
  lastMatches = matches;
  renderMatches(matches);
  updateKnockoutForms();
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
          ${STAGE_LABELS[m.stage] ? `<span class="badge wait">${STAGE_LABELS[m.stage]}</span>` : ""}
          ${m.walkover ? '<span class="badge">W.O.</span>' : ""}
        </div>
        <div class="muted">${when}${m.court ? " · " + esc(m.court) : ""} · ${m.status}</div>
      </div>
      <div class="actions">
        <a href="/torneio/partidas/${m.id}"><button>Placar</button></a>
        ${m.status !== "encerrado" ? `
          <select data-action="walkover" data-match-id="${m.id}" title="Registrar W.O.">
            <option value="">W.O.…</option>
            <option value="b">${esc(m.team_a_code)} ausente (${esc(m.team_b_code)} vence)</option>
            <option value="a">${esc(m.team_b_code)} ausente (${esc(m.team_a_code)} vence)</option>
          </select>` : ""}
        ${m.walkover ? `<button data-action="undo-walkover" data-match-id="${m.id}">Desfazer W.O.</button>` : ""}
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
        stage: $("matchStage").value,
      }),
    });
    $("matchScheduledAt").value = "";
    $("matchCourt").value = "";
    $("matchStage").value = "grupos";
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
    } else if (action === "undo-walkover") {
      await api(`/api/tournaments/${tournamentId}/matches/${matchId}/walkover`, { method: "DELETE" });
    }
    await loadMatches();
    await loadStandings();
  } catch (err) {
    toast(err.message);
  }
});

$("matches").addEventListener("change", async e => {
  const select = e.target.closest("select[data-action='walkover']");
  if (!select || !select.value) return;
  const present = select.value;
  const label = select.options[select.selectedIndex].text;
  if (!confirm(`Registrar W.O.: ${label}? O jogo termina 2×0 (15×0 e 15×0).`)) {
    select.value = "";
    return;
  }
  try {
    await api(`/api/tournaments/${tournamentId}/matches/${select.dataset.matchId}/walkover`, {
      method: "POST",
      body: JSON.stringify({ present }),
    });
    await loadMatches();
    await loadStandings();
    await loadPodium();
  } catch (err) {
    select.value = "";
    toast(err.message);
  }
});

async function loadStandings() {
  lastStandings = await api(`/api/tournaments/${tournamentId}/standings`);
  renderStandings(lastStandings);
  updateKnockoutForms();
}

function updateKnockoutForms() {
  const byStage = stage => lastMatches.find(m => m.stage === stage);
  const bothGroupsDone = ["A", "B"].every(name => lastStandings.some(g => g.group === name && g.complete));
  const semis = [byStage("semifinal_1"), byStage("semifinal_2")];

  $("generateSemisForm").classList.toggle("hidden", !(bothGroupsDone && !semis[0] && !semis[1]));
  $("generateFinalsForm").classList.toggle("hidden", !(
    semis.every(m => m && m.status === "encerrado") && !byStage("final") && !byStage("terceiro_lugar")
  ));
}

async function loadPodium() {
  const podium = await api(`/api/tournaments/${tournamentId}/podium`);
  const places = [
    ["🥇 Campeã", podium.champion],
    ["🥈 Vice-campeã", podium.runner_up],
    ["🥉 Terceira colocada", podium.third_place],
  ].filter(([, team]) => team);
  $("podiumSection").classList.toggle("hidden", places.length === 0);
  $("podiumBody").innerHTML = places.map(([label, team]) => `
    <div class="player"><div class="info"><div class="name">${label}: ${esc(team)}</div></div></div>
  `).join("");
}

$("generateSemisForm").addEventListener("submit", async e => {
  e.preventDefault();
  const btn = e.target.querySelector("button");
  btn.disabled = true;
  try {
    await api(`/api/tournaments/${tournamentId}/generate-semifinals`, {
      method: "POST",
      body: JSON.stringify({
        semifinal_1_at: $("semi1At").value,
        semifinal_2_at: $("semi2At").value,
        court: $("semisCourt").value || null,
      }),
    });
    e.target.reset();
    await loadMatches();
  } catch (err) {
    toast(err.message);
  } finally {
    btn.disabled = false;
  }
});

$("generateFinalsForm").addEventListener("submit", async e => {
  e.preventDefault();
  const btn = e.target.querySelector("button");
  btn.disabled = true;
  try {
    await api(`/api/tournaments/${tournamentId}/generate-finals`, {
      method: "POST",
      body: JSON.stringify({
        third_place_at: $("thirdAt").value,
        final_at: $("finalAt").value,
        court: $("finalsCourt").value || null,
      }),
    });
    e.target.reset();
    await loadMatches();
  } catch (err) {
    toast(err.message);
  } finally {
    btn.disabled = false;
  }
});

function renderStandings(groups) {
  $("standingsBody").innerHTML = groups.map(g => `
    <h3>${g.group ? `Grupo ${esc(g.group)}` : "Sem grupo"}
      ${g.group && !g.complete ? '<span class="muted">(jogos pendentes)</span>' : ""}
    </h3>
    ${g.rows.map((row, i) => `
      <div class="player">
        <div class="info">
          <div class="name">
            ${i + 1}º ${esc(row.team)}
            ${row.qualified ? '<span class="badge qualified">classificada</span>' : ""}
            ${row.tied ? '<span class="badge wait">empate</span>' : ""}
            <span class="badge">${row.tournament_points} pts</span>
          </div>
          <div class="muted">V: ${row.wins} · Saldo sets: ${row.sets_balance} · Saldo pontos: ${row.points_balance}</div>
        </div>
      </div>
    `).join("")}
  `).join("");
}

setInterval(() => {
  if (!tournamentId) return;
  // Both are polled together: a spectator tab that never performs a match
  // action would otherwise never refresh lastMatches, leaving the "Gerar
  // final" visibility check stuck on stale data indefinitely.
  loadMatches().catch(err => toast(err.message));
  loadStandings().catch(err => toast(err.message));
  loadPodium().catch(err => toast(err.message));
}, 8000);

loadActiveTournament().catch(err => toast(err.message));
