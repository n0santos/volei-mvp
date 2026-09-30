# Formação Balanceada de Times — design

Sub-projeto 3 do "Modo Torneio". Sub-projetos anteriores já em `main`: o motor
de regras (`app/services/tournament_engine.py`) e o cadastro do torneio
(`Tournament`/`Team`/`TeamPlayer`, rotas em `app/tournament.py`, página
`/torneio`). Este documento cobre o sorteio balanceado que preenche os times
já cadastrados a partir de um pool de jogadores.

## Contexto

`app/services/teams.py` já resolve um problema parecido pra pelada casual:
divide 12 jogadores em 2 times por força bruta sobre todas as bipartições,
minimizando `|score(A) - score(B)|` mais uma penalidade de desequilíbrio de
gênero, com um ajuste de calibração (`MALE_ADJUSTMENT`) porque score de
homem e de mulher não estão na mesma escala. Força bruta não escala pra 5
times com ~40 jogadores (não é mais uma bipartição, é uma partição em N
partes) — precisa de outro algoritmo, mas a mesma lógica de score efetivo e
penalidade de gênero deve ser reaproveitada, não duplicada.

## Decisões tomadas com o usuário nesta sessão

1. **Algoritmo:** hill-climbing simples — snake draft inicial (distribui em
   zigue-zague por score, do mais forte ao mais fraco) seguido de troca de
   pares de jogadores entre times enquanto isso reduzir o custo. Sem
   simulated annealing.
2. **Sem restrição de juntar/separar jogadores específicos** neste
   sub-projeto — o cadastro já permite editar manualmente depois do sorteio,
   cobrindo o caso raro sem precisar de UI própria pra isso.
3. **Sem sorteio.** O algoritmo é determinístico (ao contrário de
   `teams.py`, que sorteia entre divisões quase-empatadas de propósito para
   variar entre peladas). Aqui não há motivo pra variar — é um sorteio único
   pra um torneio único — e determinismo simplifica os testes (evita a
   instabilidade que `tests/test_teams.py::test_balanced_scores` tem hoje).
4. **Local na UI:** um botão "Sortear times" dentro da página `/torneio`
   que já existe — sem página nova.
5. **Uma proposta só,** não três pra comparar. Se não gostar do resultado,
   edita manualmente via as rotas de elenco que já existem.

## Algoritmo

Novo arquivo `app/services/team_formation.py`, mesmo estilo de `teams.py`
(funções puras, sem type hints, duck-typed — aceita qualquer objeto com
`.score`/`.gender`). Reaproveita `effective_score`/`MALE_ADJUSTMENT` de
`teams.py` por import, não duplica a calibração.

```python
from .teams import effective_score

GENDER_WEIGHT = 8
MAX_HILL_CLIMB_ITERATIONS = 500


def team_score(players):
    return sum(effective_score(p) for p in players)


def _gender_imbalance(teams):
    counts_f = [sum(1 for p in t if p.gender == "F") for t in teams]
    counts_m = [sum(1 for p in t if p.gender == "M") for t in teams]
    avg_f = sum(counts_f) / len(teams)
    avg_m = sum(counts_m) / len(teams)
    return (
        sum(abs(c - avg_f) for c in counts_f) * GENDER_WEIGHT
        + sum(abs(c - avg_m) for c in counts_m) * GENDER_WEIGHT
    )


def _cost(teams):
    scores = [team_score(t) for t in teams]
    return (max(scores) - min(scores)) + _gender_imbalance(teams)


def _snake_draft(players, num_teams):
    ordered = sorted(players, key=effective_score, reverse=True)
    teams = [[] for _ in range(num_teams)]
    order = list(range(num_teams))
    i = 0
    for p in ordered:
        teams[order[i]].append(p)
        i += 1
        if i == len(order):
            order.reverse()
            i = 0
    return teams


def _hill_climb(teams):
    teams = [list(t) for t in teams]
    best_cost = _cost(teams)
    improved = True
    iterations = 0
    while improved and iterations < MAX_HILL_CLIMB_ITERATIONS:
        improved = False
        iterations += 1
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                for a in range(len(teams[i])):
                    for b in range(len(teams[j])):
                        teams[i][a], teams[j][b] = teams[j][b], teams[i][a]
                        cost = _cost(teams)
                        if cost < best_cost:
                            best_cost = cost
                            improved = True
                        else:
                            teams[i][a], teams[j][b] = teams[j][b], teams[i][a]
    return teams


def form_teams(players, num_teams):
    if num_teams < 2:
        raise ValueError("form_teams precisa de pelo menos 2 times")
    if len(players) < num_teams:
        raise ValueError("menos jogadores do que times")
    return _hill_climb(_snake_draft(players, num_teams))
```

`form_teams(players, num_teams)` retorna uma lista de `num_teams` listas de
jogadores. Determinístico: mesma entrada (mesma ordem de `players`) sempre
produz a mesma saída — sem `random`.

## Rota

Adiciona a `app/tournament.py`: `POST /api/tournaments/{tournament_id}/form-teams`,
corpo `{"player_ids": [...]}`.

- 404 se o torneio não existe (reaproveita `get_tournament`).
- Busca os times do torneio ordenados por `code`. 400 se houver menos de 2.
- 409 **"Times já têm jogadores — remova antes de sortear de novo"** se
  qualquer time já tiver ao menos um `TeamPlayer`. Evita sortear por cima
  de uma montagem manual já feita.
- 404 se algum `player_id` não existir como `Player`.
- Chama `form_teams(players, len(teams))` e cria um `TeamPlayer` (role
  `"titular"`, `is_captain=False`) por jogador no time correspondente.
- Retorna o mesmo formato de `GET /api/tournaments/{id}` (estado completo
  atualizado) — a UI só precisa recarregar o estado, não parsear uma
  resposta nova.

## UI

Adiciona a `templates/torneio.html`/`static/torneio.js` (mesmos arquivos do
sub-projeto 2, sem nova página): uma lista de jogadores ativos com
checkbox, busca por nome (reaproveitando `normalize()`), "selecionar
todos", contador de selecionados, e um botão "Sortear times". O botão fica
desabilitado (com explicação) se qualquer time do torneio já tiver
jogador — evita a rota retornando 409 sem contexto.

## Fora de escopo

- Restrições de juntar/separar jogadores específicos.
- Três propostas comparáveis com métricas lado a lado.
- Simulated annealing ou qualquer aleatoriedade no algoritmo.
- Decidir titular/reserva automaticamente — o sorteio marca todo mundo como
  titular; o ajuste de role continua manual, via a rota que já existe
  (`PATCH /api/teams/{id}/players/{player_id}`).

## Testes

`tests/test_team_formation.py`, mesmo padrão de `test_teams.py` (helper
`p(name, score, gender)` com `SimpleNamespace`):

- `form_teams` com N times e pool múltiplo de N distribui o tamanho certo
  por time (todos com o mesmo tamanho).
- `form_teams` com pool não múltiplo de N distribui o resto de forma
  balanceada (nenhum time com mais de 1 a mais que outro).
- Determinismo: chamar duas vezes com a mesma entrada dá o mesmo resultado
  exato (mesma composição por time, mesma ordem).
- Hill-climbing efetivamente melhora um cenário construído para ficar
  desequilibrado pelo snake draft puro (grupo com clusters de score que
  fariam o zigue-zague empilhar força de um lado).
- Balanceamento de gênero: pool com mistura de M/F resulta em contagem por
  time próxima da média (diferença pequena, não necessariamente zero).
  Caso realista com uma composição parecida com ~40 jogadores / 5 times.
- `form_teams` com menos de 2 times ou menos jogadores que times levanta
  `ValueError`.
- Teste de rota: sorteio grava os `TeamPlayer` certos nos times certos
  (ordenados por `code`), todos como `titular`; 409 se algum time já tem
  jogador; 400 se o torneio tem menos de 2 times.
