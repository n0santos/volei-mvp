# Classificação — design

Sub-projeto 6 do "Modo Torneio". Fecha o ciclo do motor de regras: usa
`compute_standings` (`app/services/tournament_engine.py`, sub-projeto 1,
nunca modificado) sobre os resultados reais que o placar ao vivo
(sub-projeto 5) grava.

## Decisões tomadas com o usuário nesta sessão

1. **Sem final automática neste sub-projeto.** Cadastrar um jogo já
   funciona hoje (seção Jogos) — o organizador lê a tabela e cadastra a
   final manualmente. Gerar sozinho precisaria tratar empate em 1º/2º
   (que o regulamento resolve por sorteio manual), UI a mais pra um passo
   que já é possível.
2. **Atualiza sozinha** (polling), mesmo espírito do placar ao vivo —
   é uma tela que espectadores ficam checando entre partidas.

## Fonte dos dados

Partidas com `status="encerrado"` e `is_final=False` do torneio ativo
(a final não entra na classificação — ela decide o campeão depois que a
classificação já está fechada, não ajuda a decidê-la). Pra cada uma,
os `TournamentSetResult` fechados viram a lista de tuplas que
`compute_standings` espera, com `team_a`/`team_b` sendo os **códigos**
dos times (não os ids) — é esse valor que aparece como `"team"` na saída.

**Times sem nenhuma partida encerrada ainda aparecem na tabela, com tudo
zerado**, ao final da lista — gap que a revisão final do sub-projeto 1
já tinha identificado ("compute_standings só retorna times que
aparecem numa partida — pré-popular os outros fica pro sub-projeto de
classificação"). É aqui.

`compute_standings` em si **não é tocado** — a lógica de agregação e
desempate já está pronta e testada desde o sub-projeto 1; este
sub-projeto só alimenta ela com dados reais e cuida da UI.

## Rota

`GET /api/tournaments/{tournament_id}/standings` (em
`app/tournament_matches.py` — já é onde `TournamentMatch`/
`TournamentSetResult` vivem, e já importa funções do motor). Sem corpo de
request, sem schema novo.

## UI

Nova seção "Classificação" em `/torneio` (mesmos arquivos
`torneio.html`/`torneio.js`) — mesma categoria de "visão geral do
torneio" que Times e Jogos já são, não precisa de página própria como o
placar precisou. Lista de posições reaproveitando `.player-grid`/`.player`
(sem tabela HTML, sem CSS novo): posição, código do time, badge de
"empate" quando `tied=true`, pontos de torneio, e os números de desempate
(vitórias, saldo de sets, saldo de pontos, pontos marcados). Atualiza via
`setInterval` a cada 8s enquanto há torneio ativo.

## Fora de escopo

- Geração automática da final.
- Indicar visualmente qual critério específico decidiu cada desempate
  (dá pra inferir comparando os campos crus entre linhas vizinhas, não
  precisa estar na API).
