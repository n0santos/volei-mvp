const matchId = Number(location.pathname.split("/").filter(Boolean).pop());
let tournamentId = null;
let currentMatch = null;

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

async function findMatch() {
  const t = await api("/api/tournaments/active");
  if (!t) throw new Error("Nenhum torneio ativo");
  tournamentId = t.id;
  const matches = await api(`/api/tournaments/${tournamentId}/matches`);
  const m = matches.find(x => x.id === matchId);
  if (!m) throw new Error("Jogo não encontrado");
  return m;
}

function renderBoard(match, board) {
  $("matchTitle").textContent = `${esc(match.team_a_code)} × ${esc(match.team_b_code)}`;
  $("teamALabel").textContent = match.team_a_code;
  $("teamBLabel").textContent = match.team_b_code;

  $("setsHistory").innerHTML = board.sets
    .filter(s => s.closed)
    .map(s => `<span class="badge">Set ${s.set_number}: ${s.points_a}×${s.points_b}</span>`)
    .join("");

  if (board.result) {
    $("scoreA").textContent = "-";
    $("scoreB").textContent = "-";
    $("currentSetLabel").textContent = "";
    $("closeSetBtn").classList.add("hidden");
    document.querySelectorAll(".score-btn").forEach(b => b.classList.add("hidden"));
    $("resultBanner").classList.remove("hidden");
    $("resultBanner").textContent =
      `Vencedor: ${board.result.winner === "A" ? match.team_a_code : match.team_b_code} (${board.result.sets_a}×${board.result.sets_b})`;
    return;
  }

  $("resultBanner").classList.add("hidden");
  document.querySelectorAll(".score-btn").forEach(b => b.classList.remove("hidden"));
  $("closeSetBtn").classList.remove("hidden");

  const cur = board.current_set;
  $("currentSetLabel").textContent = cur ? `Set ${cur.set_number} (alvo ${cur.target})` : "";
  $("scoreA").textContent = cur ? cur.points_a : 0;
  $("scoreB").textContent = cur ? cur.points_b : 0;
  $("closeSetBtn").disabled = !cur || !cur.is_over;
}

async function refresh() {
  const board = await api(`/api/tournaments/${tournamentId}/matches/${matchId}/scoreboard`);
  renderBoard(currentMatch, board);
}

document.addEventListener("click", async e => {
  const scoreBtn = e.target.closest(".score-btn");
  if (scoreBtn) {
    try {
      await api(`/api/tournaments/${tournamentId}/matches/${matchId}/scoreboard/point`, {
        method: "POST",
        body: JSON.stringify({ team: scoreBtn.dataset.team, delta: Number(scoreBtn.dataset.delta) }),
      });
      await refresh();
    } catch (err) {
      toast(err.message);
    }
    return;
  }

  if (e.target.id === "closeSetBtn") {
    try {
      await api(`/api/tournaments/${tournamentId}/matches/${matchId}/scoreboard/close-set`, { method: "POST" });
      await refresh();
    } catch (err) {
      toast(err.message);
    }
  }
});

(async () => {
  try {
    currentMatch = await findMatch();
    await refresh();
    setInterval(() => refresh().catch(err => toast(err.message)), 4000);
  } catch (err) {
    toast(err.message);
  }
})();
