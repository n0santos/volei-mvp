# Placar ao Vivo — design

Sub-projeto 5 do "Modo Torneio". Sub-projetos anteriores já em `main`:
motor de regras (`app/services/tournament_engine.py` — usado de verdade
pela primeira vez aqui), cadastro (`Tournament`/`Team`/`TeamPlayer`),
formação balanceada de times, e calendário de jogos (`TournamentMatch`,
CRUD em `app/tournament.py`). Este documento cobre a entrada de placar
ao vivo: pontos por set, fim de set/partida, resultado.

## Decisões tomadas com o usuário nesta sessão

1. **Entrada de placar:** botões +1/-1 por time no set atual. Sem log de
   eventos por ponto — "desfazer" é literalmente apertar -1 do time que
   errou. Placar não pode ficar negativo.
2. **Fim de set:** botão "Fechar set" que só habilita quando a regra bate
   (`is_set_over` do motor) — confirmação manual, não fecha sozinho.
3. **Local na UI:** página própria por partida, `/torneio/partidas/{id}`,
   com link "Placar" em cada jogo da seção Jogos que já existe. Botões
   grandes — primeira tela deste app que precisa de alvos de toque maiores
   que o padrão, então este sub-projeto adiciona algumas classes CSS novas
   pontuais (`.score-value`, `.score-btn`, etc.) em vez de forçar reuso do
   que já existe.
4. **Sincronização:** polling simples (a página recarrega o placar a cada
   poucos segundos), sem WebSocket.

## Refatoração: split de `app/tournament.py`

A revisão final do sub-projeto anterior (calendário de jogos) já
recomendou isso: "split it (por exemplo em `tournament_matches.py`)
quando o sub-projeto de placar ao vivo adicionar suas rotas, já que é
quando a lógica de partida mais vai crescer." É exatamente este momento.

Sub-projeto 1 (sub-projeto 1 = cadastro/formação) fica em `app/tournament.py`:
`create_tournament`, `active_tournament`, `get_tournament`, `create_team`,
`tournament_state`, `add_team_player`, `get_team_player`,
`update_team_player`, `remove_team_player`, `form_tournament_teams`.

Tudo sobre `TournamentMatch` (CRUD já existente + placar novo) migra pra
`app/tournament_matches.py`, um `APIRouter` novo, montado em `main.py` ao
lado do outro. `app/tournament_matches.py` importa `get_tournament` de
`app/tournament.py` (única dependência entre os dois arquivos). Isso é só
mover código — comportamento idêntico, sem mudança de rota nem de schema.

## Modelo de dados

Adiciona a `app/models.py`:

```python
class TournamentSetResult(Base):
    __tablename__ = "tournament_set_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("tournament_matches.id"))
    set_number: Mapped[int]
    points_a: Mapped[int] = mapped_column(Integer, default=0)
    points_b: Mapped[int] = mapped_column(Integer, default=0)
    closed: Mapped[bool] = mapped_column(Boolean, default=False)
```

No máximo uma linha com `closed=False` por partida a qualquer momento —
essa é "o set atual". O primeiro ponto de uma partida cria o set 1
automaticamente; fechar um set cria o próximo automaticamente no primeiro
ponto seguinte (não existe rota de "iniciar set" separada).

## Rotas (em `app/tournament_matches.py`)

- `GET /api/tournaments/{id}/matches/{match_id}/scoreboard` — estado
  completo: todos os sets (fechados + o atual), o alvo do set atual
  (`SET_TARGETS` do motor) e se ele já bateu a regra (`is_over`, calculado
  no servidor com `is_set_over` — a UI não reimplementa a regra do
  vôlei, só lê o booleano), e o resultado (`match_result` do motor sobre
  os sets fechados) quando a partida já está decidida.
- `POST .../scoreboard/point` — `{team: "a"|"b", delta: 1|-1}`. 400 se
  `team`/`delta` fora desses valores, se o placar ficaria negativo, ou se
  a partida já está decidida (2 sets fechados pra um lado). Cria o set
  seguinte automaticamente se não houver um aberto.
- `POST .../scoreboard/close-set` — fecha o set aberto. 400 se
  `is_set_over` ainda não for verdade. Se isso decidir a partida
  (`match_result` mostra 2 sets pra um lado), `TournamentMatch.status`
  vira `encerrado` sozinho — fecha o laço com o calendário sem passo
  manual extra.

## UI

**Nova página** `templates/partida.html` + `static/partida.js`, servida
em `GET /torneio/partidas/{match_id}` (o `match_id` vem da própria URL,
lido no JS via `location.pathname` — mesmo padrão estático das outras
páginas, sem variável de servidor injetada no HTML). Placar grande por
time, botões +1/-1 grandes, histórico dos sets já fechados, "Fechar set"
(desabilitado até `is_over`), banner de resultado quando decidido.
Recarrega via `setInterval` a cada poucos segundos.

**Na seção Jogos existente** (`torneio.js`): cada linha de jogo ganha um
link "Placar" para a nova página.

**CSS novo** (pontual, só pra esta página): classes de placar grande —
`.score-value`, `.score-btn`, `.score-row`, `.score-side`,
`.sets-history`, `.scoreboard`. Reaproveita `.panel`, `.badge`, `.muted`,
`.inline`, `button.primary`, `button.danger` já existentes por baixo.

## Fora de escopo

- Desfazer o fechamento de um set (a confirmação manual já é a proteção).
- Classificação entre partidas — fica pro próximo sub-projeto, que usa
  `match_points`/`compute_standings` do motor sobre os resultados que
  este sub-projeto grava.
- Qualquer sincronização além de polling.
