# Motor do torneio (regras puras) — design

Sub-projeto 1 de N do "Modo Torneio" (I Torneio de Verão – Vôlei Misto – TOC,
28–29/11/2026). Este documento cobre só o motor de regras; os demais
sub-projetos (cadastro, formação de times, calendário, placar ao vivo,
classificação, controle de reservas, offline) têm cada um seu próprio ciclo
spec → plano → implementação, na ordem da Parte 3 do plano original do
usuário.

## Contexto

O app hoje (`app/main.py`, `app/models.py`, `app/services/`) é todo voltado a
pelada casual: um `Player` global com `score`/`gênero`, uma `Session` ativa
por vez, um `Match` 6x6 sem sets nem placar. Não existe conceito de "torneio",
"equipe" ou "partida contra outro time". O modo torneio será um módulo
paralelo que reaproveita só `Player`/`score`, sem tentar encaixar no `Match`
de pelada (que não tem sets nem placar — `Match.winner` e o ranking do dia
foram inclusive removidos recentemente, commit `9fba8a5`).

## Decisões já tomadas (Parte 1 do plano, resolvidas com o usuário)

1. **Composição mista em quadra:** o app só exibe a contagem M/F em quadra,
   não valida nem bloqueia nada.
2. **"Participar de pelo menos 1 set" (regra 10.1):** conta entrar em quadra
   em qualquer momento do set, não precisa jogar o set inteiro.
3. **Desempate:** segue só a ordem literal do regulamento — vitórias → saldo
   de sets → saldo de pontos → pontos marcados → sorteio manual. Sem
   confronto direto (não está no texto).
4. **Formação de times:** é MVP — o app deve gerar/otimizar os 5 elencos a
   partir dos scores (não é a comissão que decide por fora).
5. **Terceiro lugar:** sem jogo — é o 3º colocado da classificação.
6. **Taxa de inscrição:** controle de pagamento fica para a lista "Depois"
   (não é MVP).

Decisões 2, 5 e 6 não exigiam pergunta (já estavam definidas no texto do
plano); 1, 3 e 4 foram confirmadas com o usuário nesta sessão.

## Escopo deste sub-projeto

Só as regras de set / partida / classificação, como funções puras — sem
calendário, sem persistência, sem UI.

## Localização

- `app/services/tournament_engine.py` — arquivo plano, seguindo a convenção
  atual de `services/` (módulos independentes, não um subpacote).
- `tests/test_tournament_engine.py`.

## API

Funções puras, sem type hints (consistente com `teams.py`/`selection.py`),
duck-typed onde aceitam objetos (funcionam tanto com dicts/`SimpleNamespace`
nos testes quanto com as futuras linhas do ORM do sub-projeto de
persistência).

```python
SET_TARGETS = {1: 18, 2: 18, 3: 15}

def is_set_over(a, b, target) -> bool:
    """max(a, b) >= target and abs(a - b) >= 2"""

def set_winner(a, b, target) -> "A" | "B" | None:
    """None se o set ainda não terminou."""

def match_result(sets) -> dict:
    """
    sets: lista de tuplas (pontos_a, pontos_b) por set já decidido.
    Retorna {"winner": "A"|"B"|None, "sets_a": int, "sets_b": int,
             "points_a": int, "points_b": int}.
    winner=None se a partida ainda não fechou 2 sets pra ninguém.
    """

def match_points(sets_a, sets_b) -> int:
    """Tabela 3/2/1/0 pra quem tem sets_a sets vencidos (2-0=3, 2-1=2,
    1-2=1, 0-2=0)."""

def compute_standings(matches) -> list[dict]:
    """
    matches: só partidas ENCERRADAS, objetos com .team_a, .team_b, .sets
    (lista de tuplas (pontos_a, pontos_b)).
    Retorna uma lista de dicts por equipe (vitórias, saldo de sets, saldo
    de pontos, pontos marcados, pontos de torneio).

    Critério principal de ordenação: pontos de torneio (a tabela 3/2/1/0
    de match_points, somada por equipe) — é o que a seção "Pontuação" do
    regulamento define como a classificação. A cadeia do regulamento
    (vitórias → saldo de sets → saldo de pontos → pontos marcados →
    sorteio) só entra como desempate SECUNDÁRIO, quando duas ou mais
    equipes empatam em pontos de torneio.

    Equipes que seguem empatadas depois de esgotar toda a cadeia (pontos
    de torneio E vitórias E saldo de sets E saldo de pontos E pontos
    marcados, tudo igual) saem marcadas com tied=True — o motor não
    sorteia, só sinaliza.
    """
```

## Fora de escopo (sub-projetos futuros)

- Montagem da grade de jogos (calendário automático) e geração da final
  1º×2º.
- UI mostrando "qual critério desempatou" — dá pra derivar comparando os
  campos crus entre posições vizinhas na camada de apresentação, não precisa
  estar no motor.
- Persistência (modelos `Tournament`/`Team`/`TeamPlayer`/`Match` de
  torneio/`SetResult`) — sub-projeto separado.

## Testes

- 17×17 não termina (`is_set_over` False); 19×17 termina (`is_set_over` True,
  `set_winner` "A").
- 14×14 no 3º set (alvo 15) não termina; segue até diferença de 2 (ex.:
  15×14 ainda não, 16×14 termina).
- `match_points`: 2×0=3, 2×1=2, 1×2=1, 0×2=0.
- `match_result` com partida incompleta (só 1 set decidido) retorna
  `winner=None`.
- `compute_standings` com empate triplo em pontos de torneio, decidido por
  saldo de sets.
- Cada critério de desempate isolado: vitórias decide; empatado em
  vitórias, saldo de sets decide; empatado nos dois, saldo de pontos
  decide; empatado nos três, pontos marcados decide.
- Um caso de empate total (todos os critérios iguais) marcado `tied=True`.

## Próximo sub-projeto na fila

Formação balanceada de times (Parte 3, item 2 do plano original): snake
draft + otimização por trocas a partir do pool de jogadores e seus scores,
com restrições de gênero e juntar/separar jogadores, 3 opções de sorteio,
travar jogador, edição manual. Confirmado como MVP nesta sessão — brainstorm
próprio, spec própria.
