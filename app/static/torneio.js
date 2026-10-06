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

const TABS = ["jogos", "classificacao", "equipes"];

// The tournament runs on known days, so a manual game is placed by day + time
// instead of a free date field.
let tournamentDays = [];

function daysBetween(start, end) {
  const days = [];
  const day = new Date(`${start}T12:00:00`);
  const last = new Date(`${end}T12:00:00`);
  for (; day <= last; day.setDate(day.getDate() + 1)) days.push(day.toLocaleDateString("sv-SE"));
  return days;
}

function dayLabel(iso) {
  return new Date(`${iso}T12:00:00`)
    .toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "2-digit" });
}

function fillDayOptions() {
  $("matchDay").innerHTML = tournamentDays.map(d => `<option value="${d}">${dayLabel(d)}</option>`).join("");
}


// The tab lives in the URL hash (/torneio#equipes), so a reload or a shared
// link opens the same one; the panes themselves are hidden by CSS.
function selectTab(name) {
  if (!TABS.includes(name)) name = "jogos";
  document.body.dataset.tab = name;
  document.querySelectorAll("#tabs button").forEach(btn => {
    const active = btn.dataset.tab === name;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active);
  });
  if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
}

$("tabs").addEventListener("click", e => {
  const btn = e.target.closest("button[data-tab]");
  if (btn) selectTab(btn.dataset.tab);
});
window.addEventListener("hashchange", () => selectTab(location.hash.slice(1)));
selectTab(location.hash.slice(1));

async function loadActiveTournament() {
  const t = await api("/api/tournaments/active");
  if (t) {
    tournamentId = t.id;
    tournamentDays = daysBetween(t.start_date, t.end_date);
    fillDayOptions();
    $("tournamentName").textContent = `${t.name} (${fmtDate(t.start_date)} a ${fmtDate(t.end_date)})`;
    $("newTournament").classList.add("hidden");
    $("tabs").classList.remove("hidden");
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
    $("tabs").classList.add("hidden");
    $("tournamentPanel").classList.add("hidden");
    $("matchesSection").classList.add("hidden");
    $("standingsSection").classList.add("hidden");
  }
}

async function loadState() {
  const state = await api(`/api/tournaments/${tournamentId}`);
  lastTeams = state.teams;
  renderTeams(state.teams);

  populateTeamSelect($("matchTeamA"), state.teams);
  populateTeamSelect($("matchTeamB"), state.teams);
  // Open with two different teams instead of the same one on both sides
  if (state.teams.length > 1 && $("matchTeamA").value === $("matchTeamB").value) {
    $("matchTeamB").value = String(state.teams.find(t => String(t.id) !== $("matchTeamA").value).id);
  }
}

function renderTeams(teams) {
  const athletes = teams.reduce((sum, t) => sum + t.players.length, 0);
  $("teamsSummary").textContent = `${teams.length} equipes, ${athletes} atletas`;

  // Group A, group B, then teams still without a group
  const groups = [...new Set(teams.map(t => t.group_name))].sort((a, b) => (a === null) - (b === null) || String(a).localeCompare(b));
  $("teams").innerHTML = groups.map(g => {
    const inGroup = teams.filter(t => t.group_name === g);
    return `
      <section class="team-group">
        <h3 class="group-title">${g ? `Grupo ${esc(g)}` : "Sem grupo"}
          <span class="muted">${inGroup.length} ${inGroup.length === 1 ? "equipe" : "equipes"}</span>
        </h3>
        <div class="team-grid">${inGroup.map(renderTeam).join("")}</div>
      </section>
    `;
  }).join("");
}

function renderTeam(team) {
  // Captain first, then starters, then reserves
  const rank = p => (p.is_captain ? 0 : p.role === "titular" ? 1 : 2);
  const players = [...team.players].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
  const full = team.players.length >= team.max_players;
  const hasCaptain = team.players.some(p => p.is_captain);

  return `
    <article class="team-card" data-team-id="${team.id}">
      <div class="tc-head">
        <div>
          <h4 class="tc-name">${esc(team.code)}</h4>
          <div class="tc-count${full ? " full" : ""}">${team.players.length} de ${team.max_players} atletas</div>
        </div>
        <details class="more">
          <summary class="btn sm" aria-label="Ajustes da equipe">Ajustes</summary>
          <div class="more-menu">
            <label class="tournament-label">Grupo
              <select class="group-select" data-team-id="${team.id}">
                <option value="">Sem grupo</option>
                ${["A", "B"].map(g => `<option value="${g}"${team.group_name === g ? " selected" : ""}>Grupo ${g}</option>`).join("")}
              </select>
            </label>
            <label class="tournament-label">Limite de atletas
              <select class="max-players-select" data-team-id="${team.id}">
                ${[7, 8].map(n => `<option value="${n}"${team.max_players === n ? " selected" : ""}>${n}</option>`).join("")}
              </select>
            </label>
          </div>
        </details>
      </div>
      ${players.length && !hasCaptain ? '<div class="tc-warn">Sem capitão definido</div>' : ""}
      <ul class="tp-list">
        ${players.map(p => renderPlayer(team.id, p)).join("") || '<li class="tp-empty">Nenhum atleta ainda.</li>'}
      </ul>
      <form class="inline add-player-form" data-team-id="${team.id}">
        <input placeholder="Nome do atleta" class="player-search" required>
        <button class="primary">Adicionar</button>
      </form>
    </article>
  `;
}

function renderPlayer(teamId, p) {
  const captainLabel = p.gender === "F" ? "Capitã" : "Capitão";
  const attrs = `data-team-id="${teamId}" data-player-id="${p.id}"`;
  return `
    <li class="tp">
      <span class="tp-name">${esc(p.name)}</span>
      ${p.is_captain ? `<span class="chip captain">${captainLabel}</span>` : ""}
      ${p.role === "reserva" ? '<span class="chip">Reserva</span>' : ""}
      <details class="more">
        <summary class="btn sm" aria-label="Ações de ${esc(p.name)}">Mais</summary>
        <div class="more-menu">
          <button data-action="set-captain" data-captain="${p.is_captain ? "0" : "1"}" ${attrs}>${p.is_captain ? `Remover ${captainLabel.toLowerCase()}` : `Tornar ${captainLabel.toLowerCase()}`}</button>
          <button data-action="set-role" data-role="${p.role === "titular" ? "reserva" : "titular"}" ${attrs}>${p.role === "titular" ? "Marcar como reserva" : "Marcar como titular"}</button>
          <button class="danger" data-action="remove" data-name="${esc(p.name)}" ${attrs}>Remover da equipe</button>
        </div>
      </details>
    </li>
  `;
}

function setTeamFormOpen(open) {
  $("teamForm").classList.toggle("hidden", !open);
  $("addTeamToggle").textContent = open ? "Fechar" : "+ Equipe";
  $("addTeamToggle").setAttribute("aria-expanded", open);
}

$("addTeamToggle").addEventListener("click", () => {
  setTeamFormOpen($("teamForm").classList.contains("hidden"));
});

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
    setTeamFormOpen(false);
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
  const url = `/api/teams/${teamId}/players/${playerId}`;

  try {
    if (action === "remove") {
      if (!confirm(`Remover ${btn.dataset.name} da equipe?`)) return;
      await api(url, { method: "DELETE" });
    } else if (action === "set-role") {
      await api(url, { method: "PATCH", body: JSON.stringify({ role: btn.dataset.role }) });
    } else if (action === "set-captain") {
      await api(url, { method: "PATCH", body: JSON.stringify({ is_captain: btn.dataset.captain === "1" }) });
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

const STATUS_LABELS = { agendado: "Agendado", em_andamento: "Em andamento", encerrado: "Encerrado" };
const STAGE_ORDER = { semifinal_1: 1, semifinal_2: 1, terceiro_lugar: 2, final: 3 };

let lastMatches = [];
let lastStandings = [];
let lastTeams = [];
let lastRendered = "";

async function loadMatches() {
  const matches = await api(`/api/tournaments/${tournamentId}/matches`);
  lastMatches = matches;
  renderMatches(matches);
  updateFinalHint();
}

function groupLabel(m) {
  const team = lastTeams.find(t => t.id === m.team_a_id);
  return team && team.group_name ? `Grupo ${team.group_name}` : "Sem grupo";
}

function renderMatches(matches) {
  // The 8s poll re-renders; skip it when nothing changed so an open "Mais"
  // menu or a half-chosen W.O. isn't wiped out from under the organizer.
  const key = JSON.stringify([matches, lastTeams.map(t => [t.id, t.group_name])]);
  if (key === lastRendered) return;
  lastRendered = key;

  const next = matches.find(m => m.status !== "encerrado");
  const groupStage = matches.filter(m => m.stage === "grupos");
  const finalStage = matches
    .filter(m => m.stage !== "grupos")
    .sort((a, b) => STAGE_ORDER[a.stage] - STAGE_ORDER[b.stage] || a.scheduled_at.localeCompare(b.scheduled_at));
  // The day only shows when it changes, so a day of games isn't a column of repeated dates.
  const fixtures = list => {
    let previousDay = null;
    return list.map(m => {
      const day = m.scheduled_at.slice(0, 10);
      const showDay = day !== previousDay;
      previousDay = day;
      return renderFixture(m, next && m.id === next.id, showDay);
    }).join("");
  };

  $("groupMatches").innerHTML = groupStage.length
    ? fixtures(groupStage)
    : '<p class="empty">Nenhum jogo cadastrado. Use “+ Jogo” para adicionar.</p>';
  $("finalMatches").innerHTML = fixtures(finalStage);

  const done = groupStage.filter(m => m.status === "encerrado").length;
  $("groupProgress").textContent = groupStage.length ? `${done} de ${groupStage.length} jogos encerrados` : "";
}

function renderFixture(m, isNext, showDay) {
  const when = new Date(m.scheduled_at);
  const time = when.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  const day = when.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" }).replace(".", "");
  const decided = m.sets_a != null && m.sets_b != null;
  const winner = decided ? (m.sets_a > m.sets_b ? "a" : "b") : null;
  const teamClass = side => (winner ? (winner === side ? "won" : "lost") : "");
  const where = m.stage === "grupos" ? groupLabel(m) : STAGE_LABELS[m.stage];
  const status = STATUS_LABELS[m.status] || m.status;

  return `
    <article class="fixture ${m.status}${isNext ? " next" : ""}" data-match-id="${m.id}">
      <div class="fx-when">
        <span class="fx-time">${time}</span>
        ${showDay ? `<span class="fx-day">${esc(day)}</span>` : ""}
      </div>
      <div class="fx-teams">
        <span class="fx-team a ${teamClass("a")}">${esc(m.team_a_code)}</span>
        <span class="fx-score">${decided ? `${m.sets_a}–${m.sets_b}` : "×"}</span>
        <span class="fx-team b ${teamClass("b")}">${esc(m.team_b_code)}</span>
      </div>
      <div class="fx-meta">
        <span class="chip">${esc(where)}</span>
        <span class="chip ${m.status === "em_andamento" ? "live" : m.status === "encerrado" ? "done" : ""}">${status}</span>
        ${isNext ? '<span class="chip next">A seguir</span>' : ""}
        ${m.walkover ? '<span class="chip">W.O.</span>' : ""}
      </div>
      <div class="fx-actions">
        <a class="btn${m.status === "em_andamento" ? " primary" : ""}" href="/torneio/partidas/${m.id}">Placar</a>
        ${m.status === "agendado" ? `<button data-action="start" data-match-id="${m.id}">Iniciar</button>` : ""}
        <details class="more">
          <summary class="btn" aria-label="Mais ações do jogo">Mais</summary>
          <div class="more-menu">
            ${m.status !== "encerrado" ? `
              <select data-action="walkover" data-match-id="${m.id}" title="Registrar W.O.">
                <option value="">Registrar W.O.…</option>
                <option value="b">${esc(m.team_a_code)} ausente (${esc(m.team_b_code)} vence)</option>
                <option value="a">${esc(m.team_b_code)} ausente (${esc(m.team_a_code)} vence)</option>
              </select>` : ""}
            ${m.status !== "encerrado" ? `<button data-action="reschedule" data-match-id="${m.id}" data-day="${m.scheduled_at.slice(0, 10)}" data-time="${time}">Alterar horário</button>` : ""}
            ${m.walkover ? `<button data-action="undo-walkover" data-match-id="${m.id}">Desfazer W.O.</button>` : ""}
            ${m.status === "em_andamento" ? `<button data-action="finish" data-match-id="${m.id}">Encerrar sem placar</button>` : ""}
            <button class="danger" data-action="remove-match" data-match-id="${m.id}">Remover jogo</button>
          </div>
        </details>
      </div>
    </article>
  `;
}

function setMatchFormOpen(open) {
  $("matchForm").classList.toggle("hidden", !open);
  $("addMatchToggle").textContent = open ? "Fechar" : "+ Jogo";
  $("addMatchToggle").setAttribute("aria-expanded", open);
}

$("addMatchToggle").addEventListener("click", () => {
  setMatchFormOpen($("matchForm").classList.contains("hidden"));
});

$("matchForm").addEventListener("submit", async e => {
  e.preventDefault();
  try {
    await api(`/api/tournaments/${tournamentId}/matches`, {
      method: "POST",
      body: JSON.stringify({
        team_a_id: Number($("matchTeamA").value),
        team_b_id: Number($("matchTeamB").value),
        scheduled_at: `${$("matchDay").value}T${$("matchTime").value}`,
        stage: $("matchStage").value,
      }),
    });
    $("matchTime").value = "";
    $("matchStage").value = "grupos";
    setMatchFormOpen(false);
    await loadMatches();
  } catch (err) {
    toast(err.message);
  }
});

$("matchesSection").addEventListener("click", async e => {
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
      if (!confirm("Remover este jogo e o placar dele?")) return;
      await api(`/api/tournaments/${tournamentId}/matches/${matchId}`, { method: "DELETE" });
    } else if (action === "reschedule") {
      const input = prompt("Novo horário (HH:MM)", btn.dataset.time);
      if (input === null) return;
      const hhmm = input.trim();
      if (!/^([01]?\d|2[0-3]):[0-5]\d$/.test(hhmm)) {
        toast("Use o formato HH:MM, por exemplo 09:30");
        return;
      }
      await api(`/api/tournaments/${tournamentId}/matches/${matchId}`, {
        method: "PATCH",
        body: JSON.stringify({ scheduled_at: `${btn.dataset.day}T${hhmm.padStart(5, "0")}` }),
      });
    } else if (action === "undo-walkover") {
      await api(`/api/tournaments/${tournamentId}/matches/${matchId}/walkover`, { method: "DELETE" });
    }
    await loadMatches();
    await loadStandings();
  } catch (err) {
    toast(err.message);
  }
});

$("matchesSection").addEventListener("change", async e => {
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
  updateFinalHint();
}

// The knockout games are created by the server when the phase before ends;
// this only explains what the empty "Fase final" is waiting for.
function updateFinalHint() {
  const started = lastMatches.some(m => m.stage !== "grupos");
  $("finalEmpty").classList.toggle("hidden", started);
  if (started) return;

  const tied = lastStandings
    .filter(g => g.group && g.complete && g.rows.filter(r => r.qualified).length < 2)
    .map(g => g.group);
  $("finalEmpty").textContent = tied.length
    ? `Empate na classificação do grupo ${tied.join(" e ")}. Faça o sorteio e cadastre as semifinais em “+ Jogo”.`
    : "As semifinais são criadas automaticamente quando os dois grupos terminarem.";
}

async function loadPodium() {
  const podium = await api(`/api/tournaments/${tournamentId}/podium`);
  const places = [
    ["1º", "Campeã", podium.champion, "gold"],
    ["2º", "Vice-campeã", podium.runner_up, "silver"],
    ["3º", "Terceira colocada", podium.third_place, "bronze"],
  ].filter(([, , team]) => team);
  $("podiumSection").classList.toggle("hidden", places.length === 0);
  $("podiumBody").innerHTML = places.map(([n, label, team, tone]) => `
    <li class="place ${tone}">
      <span class="place-n">${n}</span>
      <span class="place-team">${esc(team)}</span>
      <span class="place-label">${label}</span>
    </li>
  `).join("");
}

function fmtSigned(n) {
  return n > 0 ? `+${n}` : String(n);
}

function renderStandings(groups) {
  $("standingsBody").innerHTML = groups.map(g => {
    const n = g.rows.length;
    const totalGames = n * (n - 1) / 2;
    const playedGames = g.rows.reduce((sum, r) => sum + r.wins + r.losses, 0) / 2;
    const progress = !g.group
      ? "Defina o grupo na aba Equipes"
      : g.complete ? "Grupo encerrado" : `${playedGames} de ${totalGames} jogos`;

    return `
      <section class="panel group-table">
        <div class="stage-head">
          <h2>${g.group ? `Grupo ${esc(g.group)}` : "Sem grupo"}</h2>
          <span class="muted">${progress}</span>
        </div>
        <div class="st-row st-head">
          <span></span><span>Equipe</span>
          <span title="Jogos">J</span><span title="Vitórias">V</span>
          <span title="Saldo de sets">SS</span><span title="Saldo de pontos">SP</span>
          <span title="Pontos">Pts</span>
        </div>
        ${g.rows.map(row => `
          <div class="st-row${row.qualified ? " qualified" : ""}">
            <span class="st-pos">${playedGames > 0 ? row.rank : "–"}</span>
            <span class="st-team">
              ${esc(row.team)}
              ${row.qualified ? '<small class="note ok">Classificada</small>' : ""}
              ${row.tied ? '<small class="note tie">Empate</small>' : ""}
            </span>
            <span>${row.wins + row.losses}</span>
            <span>${row.wins}</span>
            <span>${fmtSigned(row.sets_balance)}</span>
            <span>${fmtSigned(row.points_balance)}</span>
            <strong>${row.tournament_points}</strong>
          </div>
        `).join("")}
      </section>
    `;
  }).join("");
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
