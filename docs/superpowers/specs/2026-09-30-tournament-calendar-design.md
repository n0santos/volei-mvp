# Calendário de Jogos — design

Sub-projeto 4 do "Modo Torneio". Sub-projetos anteriores já em `main`: motor
de regras (`app/services/tournament_engine.py`), cadastro do torneio
(`Tournament`/`Team`/`TeamPlayer`, `app/tournament.py`, página `/torneio`)
e formação balanceada de times (`app/services/team_formation.py`). Este
documento cobre a grade de jogos: quem joga contra quem, quando, e um
status simples de andamento.

## Contexto

`app/models.py` já tem um `Match` — mas é o da pelada casual (uma partida
6x6, sem times nomeados, ligado a `Session`). O torneio precisa de outra
coisa: uma partida entre dois `Team`s cadastrados, com data/hora e status
de andamento, sem nada em comum com o `Match` da pelada além do nome. Para
não colidir os dois nomes no mesmo `app/models.py`, o novo modelo se chama
`TournamentMatch`.

## Decisões tomadas com o usuário nesta sessão

1. **Grade cadastrada manualmente**, não gerada automaticamente. A grade
   oficial deste torneio já está definida num PDF do regulamento (quem
   joga contra quem, em que horário) — gerar automaticamente arriscaria
   não bater com ela. Cadastro manual também cobre de graça a
   flexibilidade "pode antecipar/atrasar" que o regulamento já prevê
   (só editar o horário).
2. **Sem captura de resultado neste sub-projeto.** Só rastreia status
   (`agendado` → `em_andamento` → `encerrado`). Vencedor/placar é
   trabalho do sub-projeto de placar ao vivo (ainda não construído) —
   fazer isso aqui duplicaria esforço.

## Modelo de dados

Adiciona a `app/models.py`:

```python
class TournamentMatch(Base):
    __tablename__ = "tournament_matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id"))
    team_a_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    team_b_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime)
    court: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="agendado")  # agendado/em_andamento/encerrado
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
```

`is_final` só marca visualmente o jogo 1º×2º quando o organizador já sabe
quem chegou lá — continua cadastrado manualmente como qualquer outro jogo,
sem geração automática (isso depende de classificação, que depende de
resultado, que não existe ainda).

**Sem validação de "só um jogo `em_andamento` por vez"** — mesma linha de
confiar no organizador já estabelecida no resto do cadastro. **Sem
migração de coluna** — `tournament_matches` é tabela nova,
`Base.metadata.create_all()` já cuida disso.

## Rotas

Adiciona a `app/tournament.py`:

- `POST /api/tournaments/{tournament_id}/matches` — cria um jogo
  (`team_a_id`, `team_b_id`, `scheduled_at`, `court` opcional, `is_final`
  opcional). 404 se algum time não pertence a este torneio; 400 se
  `team_a_id == team_b_id`.
- `GET /api/tournaments/{tournament_id}/matches` — lista ordenada por
  `scheduled_at`, cada item já com `team_a_code`/`team_b_code` resolvidos
  (a UI não precisa cruzar com a lista de times separadamente).
- `PATCH /api/tournaments/{tournament_id}/matches/{match_id}` — edita
  qualquer campo, todos opcionais. `status` só aceita
  `agendado`/`em_andamento`/`encerrado` (400 se outro valor).
- `DELETE /api/tournaments/{tournament_id}/matches/{match_id}` — remove.

Sem rota de edição dedicada na UI para trocar horário/times depois de
criado — o organizador remove e recadastra, mesmo nível de polimento que
`Team.code` (também não editável) já tem.

## UI

Nova seção "Jogos" em `/torneio` (mesmos arquivos `templates/torneio.html`
+ `static/torneio.js`): formulário com dois `<select>` de time (populados
a partir dos times já cadastrados), data/hora, quadra opcional, checkbox
"é a final"; lista de jogos ordenada, destacando o primeiro não-encerrado
como "próximo"; botões Iniciar/Encerrar (conforme o status atual) e
Remover.

## Fora de escopo

- Geração automática de grade (rodízio).
- Captura de vencedor/placar.
- Final automática por classificação.
- Edição inline de horário/times de um jogo já criado.
