// app/static/arbitro.js — referee login shared by /torneio and the scoreboard.
// The page starts in body.viewer (edit controls hidden by CSS); a referee
// cookie turns it into body.arbitro. The server enforces it either way.
(() => {
  const header = document.querySelector(".site-header .actions") || document.querySelector(".site-header .inner");
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "arbitro-btn";
  header.appendChild(btn);

  function apply(state) {
    document.body.classList.toggle("viewer", !state.arbitro);
    document.body.classList.toggle("arbitro", state.arbitro);
    btn.classList.toggle("hidden", !state.login_ativo);
    btn.textContent = state.arbitro ? "Sair (árbitro)" : "Entrar como árbitro";
  }

  async function post(url, body) {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || "Erro");
    return data;
  }

  btn.addEventListener("click", async () => {
    try {
      if (document.body.classList.contains("arbitro")) {
        await post("/api/arbitro/logout");
      } else {
        const senha = prompt("Senha dos árbitros");
        if (!senha) return;
        await post("/api/arbitro/login", { senha });
      }
      location.reload();
    } catch (err) {
      alert(err.message);
    }
  });

  fetch("/api/arbitro").then(r => r.json()).then(apply).catch(() => {});
})();
