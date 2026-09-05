# Simulações de calibração

## 1. Primeira simulação (aproximada)

Reimplementação simplificada (gulosa, sem otimização combinatória) do algoritmo
de seleção, rodada fora do banco de dados. 500 sessões, 30 jogadores (17F/13M),
presença 70-95%, chegadas atrasadas, saída antecipada.

```json
{
  "sessoes": 500,
  "presentes_medio": 24.77,
  "partidas_medio": 12,
  "CV_medio_minutos": 0.173,
  "SD_medio_partidas_por_jogador": 1.037,
  "dif_score_media": 0.13,
  "dif_score_max_media": 0.46,
  "maior_espera_media": 1.54,
  "sessoes_com_2_ou_mais_fora": 54.4,
  "sessoes_com_3_partidas_seguidas_jogando": 11.6
}
```

O número alto de "sessões com alguém esperando 2+ partidas seguidas" (54.4%)
motivou uma simulação mais fiel, chamando o código real do app.

## 2. Bugs encontrados ao construir a simulação fiel

1. **`app/services/fairness.py` (`history`)** — um jogador que nunca era
   escolhido para nenhuma partida nunca ganhava uma entrada de histórico
   (o dicionário só era populado a partir de `MatchPlayer`), então seu
   `outside_streak` ficava travado em 0 para sempre. Isso significa que a
   regra "força quem esperou 2+ partidas" nunca disparava para alguém que
   estava sendo sistematicamente ignorado - exatamente o cenário mais grave
   de injustiça. Corrigido para computar o streak de todo mundo que chegou
   à sessão (via `Attendance`), limitando a janela às partidas que
   aconteceram enquanto a pessoa estava realmente presente (entre chegada e
   saída, quando houver).
2. **`app/services/selection.py`** — o desempate entre jogadores empatados em
   critério de justiça (mesma espera, mesmas partidas jogadas) era decidido
   por `arrival_order`: quem chegava mais cedo sempre ganhava. Na prática do
   grupo, esse empate é resolvido por sorteio ("adedonha"). Trocado por um
   sorteio aleatório novo a cada `Gerar próxima partida`, mantendo intacta a
   regra dura de forçar quem já esperou 2+ partidas seguidas.

Ambos confirmados com testes de regressão (`tests/test_fairness.py`,
`tests/test_selection.py::test_tiebreak_among_equally_fair_players_is_randomized`).

## 3. Simulação fiel (código real do app, banco SQLite real)

Mesmo cenário (30 jogadores, agora 80% mulheres / 20% homens, presença 70-95%,
chegadas atrasadas, saída antecipada), mas chamando diretamente
`select_players`, `balance_teams` e `history` de verdade contra um banco
SQLite, em vez de reimplementar o algoritmo. 80 sessões (mais lento por rodar
a otimização combinatória de verdade).

```json
{
  "sessoes": 80,
  "presentes_medio": 24.77,
  "partidas_medio": 12,
  "CV_medio_minutos": 0.157,
  "SD_medio_partidas_por_jogador": 0.968,
  "dif_score_media": 0.12,
  "dif_score_max_media": 0.46,
  "maior_espera_media": 0,
  "sessoes_com_alguem_esperando_2+": 0.0,
  "sessoes_com_alguem_jogando_3+_seguidas": 0.0
}
```

Depois dos dois consertos, ninguém esperou 2 partidas seguidas em nenhuma das
80 sessões simuladas neste cenário. O peso de espera na fórmula de prioridade
(-1000 por partida esperada) é forte o bastante para, na prática, trazer de
volta quase todo mundo que ficou de fora assim que sobra uma vaga - o problema
de 54.4% da primeira simulação era, na maior parte, um artefato da
implementação aproximada + o bug do histórico, não do algoritmo real.

Isso foi validado com um roster sintético; ainda precisa ser confrontado com
os padrões reais de presença do grupo (roster real via enquetes do WhatsApp).
