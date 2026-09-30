# Cadastro do Torneio — design

Sub-projeto 2 do "Modo Torneio" (I Torneio de Verão – Vôlei Misto – TOC,
28–29/11/2026). Sub-projeto 1 (motor de regras puras, `app/services/tournament_engine.py`)
já está em `main`. Este documento cobre o cadastro: torneio, times e
elencos — a base de dados sobre a qual os próximos sub-projetos (formação
balanceada, calendário, placar ao vivo, classificação, reservas, offline)
vão trabalhar.

## Contexto

O app hoje é todo voltado a pelada casual: `Player` (nome, `score`,
`gênero`, global) → `Session` (uma noite, só uma `active` por vez) →
`Attendance`/`Match`/`MatchPlayer`. `app/main.py` tem todas as rotas da
pelada, sem router split; `app/models.py` tem todos os modelos ORM num
arquivo só; `app/services/` tem lógica pura separada da persistência
(`fairness.py`, `selection.py`, `teams.py`, e agora `tournament_engine.py`).

O modo torneio é um módulo paralelo, reaproveitando só `Player`/`score`
(decisão já tomada no sub-projeto 1) — não tenta encaixar no `Match`/`Session`
de pelada.

## Decisões tomadas com o usuário nesta sessão

1. **Capitão:** é sempre um dos jogadores do elenco do time (não um
   contato separado). Modelado como `TeamPlayer.is_captain`.
2. **Local na UI:** página própria (`/torneio`), com template e JS
   separados do `app.js`/`index.html` da pelada — não uma aba dentro da
   SPA existente.

## Decisões de design (YAGNI, seguindo precedente já estabelecido)

- **Sem validação de tamanho de elenco ou composição de gênero.** Só
  exibe contagem (ex. "7/8, 6 titulares"). Mesma linha da decisão do
  sub-projeto 1 sobre vôlei misto: mostrar, não bloquear — o organizador
  se autorregula.
- **`Team.code` é texto livre**, não travado a exatamente 5 times
  A–E. A grade fixa de 5 equipes é regra deste torneio específico (2026),
  não uma invariante do software — o cadastro deixa o organizador criar
  quantos times quiser.
- **Sem WebSocket nesta tela.** É o organizador sozinho montando os times
  antes do fim de semana; não há necessidade de sync em tempo real entre
  celulares aqui — isso passa a importar a partir do sub-projeto de placar
  ao vivo.
- **Sem migração de coluna:** `Tournament`/`Team`/`TeamPlayer` são tabelas
  novas, não colunas novas em tabela existente — `Base.metadata.create_all()`
  já cria automaticamente em qualquer DB (novo ou existente), sem precisar
  do helper `add_missing_columns()` (que serve para adicionar coluna a
  tabela já existente, como foi o caso do extinto `Match.winner`).

## Modelo de dados

Adiciona a `app/models.py` (mesmo arquivo — o codebase não separa modelos
por subpacote, e 3 classes a mais não justificam quebrar o padrão):

```python
class Tournament(Base):
    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id"))
    code: Mapped[str] = mapped_column(String(20))


class TeamPlayer(Base):
    __tablename__ = "team_players"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    role: Mapped[str] = mapped_column(String(20), default="titular")  # titular/reserva
    is_captain: Mapped[bool] = mapped_column(Boolean, default=False)

    player: Mapped["Player"] = relationship()
```

`Tournament.active` segue o mesmo padrão de `Session.active`: criar um
torneio novo desativa os demais (só um ativo por vez). `Date` precisa de
`from sqlalchemy import Date` e `from datetime import date` — imports
novos no topo de `models.py`.

## Rotas

Novo arquivo `app/tournament.py`, um `APIRouter` do FastAPI, montado em
`app/main.py` com duas linhas (`from .tournament import router as
tournament_router` e `app.include_router(tournament_router)`) — não altera
nada mais em `main.py`.

- `POST /api/tournaments` — cria e ativa um torneio (`name`, `start_date`,
  `end_date`). Desativa qualquer torneio ativo anterior, mesmo padrão de
  `POST /api/sessions`.
- `GET /api/tournaments/active` — retorna o torneio ativo ou `null`.
- `POST /api/tournaments/{tournament_id}/teams` — cria um time (`code`)
  dentro do torneio.
- `GET /api/tournaments/{tournament_id}` — estado completo: dados do
  torneio + lista de times, cada um com seu elenco (jogador, role,
  is_captain).
- `POST /api/teams/{team_id}/players` — adiciona um jogador ao time
  (`player_id`, `role`). Busca de jogador por nome reaproveita o `Player`
  existente — a tela de cadastro não recria jogadores, só refere aos já
  cadastrados (criar jogador continua sendo `POST /api/players`,
  já existente).
- `PATCH /api/teams/{team_id}/players/{player_id}` — troca `role` e/ou
  `is_captain`. Marcar um novo capitão desmarca o anterior do mesmo time
  (só um capitão por time).
- `DELETE /api/teams/{team_id}/players/{player_id}` — remove o jogador do
  time.

## Schemas

Adiciona a `app/schemas.py` (mesmo arquivo, junto dos já existentes
`PlayerCreate`/`SessionCreate`/etc.): `TournamentCreate` (`name`,
`start_date`, `end_date`), `TeamCreate` (`code`), `TeamPlayerAdd`
(`player_id`, `role`), `TeamPlayerUpdate` (`role`, `is_captain`, ambos
opcionais).

## UI

`templates/torneio.html` + `static/torneio.js`, servidos em `GET /torneio`
(nova rota simples em `main.py`, só um `HTMLResponse` lendo o arquivo —
mesmo padrão da rota `GET /` existente).

- Cabeçalho: nome e datas do torneio ativo; se não houver torneio ativo,
  formulário pra criar um.
- Um card por time: código, contagem de elenco ("7/8, 6 titulares"),
  lista de jogadores com badge titular/reserva e estrela no capitão.
- Busca por nome pra adicionar jogador a um time — reaproveita o mesmo
  padrão de busca que a pelada acabou de ganhar na lista de presença
  (commit `4a63870`), adaptado pra este contexto.
- Ação de trocar role, trocar capitão, remover jogador do time.
- Ação de criar novo time (código).

## Fora de escopo (sub-projetos futuros)

- Sorteio balanceado automático de times (próximo sub-projeto — vai
  escrever nos mesmos `Team`/`TeamPlayer` em vez de recriar estrutura).
- Calendário de jogos, placar ao vivo, classificação, controle de
  reservas, funcionamento offline.
- Qualquer validação dura de composição (tamanho de elenco, gênero em
  quadra).
