# Vôlei MVP

Gerenciador de noites de vôlei para um grupo fixo: check-in por ordem de chegada, rodízio justo de quem joga, times equilibrados e substituições, sincronizado em tempo real entre celulares.

Feito para um grupo real que joga 6x6 com 15–25 pessoas por noite, onde quem fica de fora precisa conseguir entender por que ficou.

## Antes de usar: a lista de jogadores

O app **não funciona sem um cadastro prévio**. Para cada pessoa do grupo você precisa de:

| Campo | O que é |
|---|---|
| **Nome** | Único. Se houver dois nomes iguais, diferencie (ex.: `Silvana (2)`). |
| **Gênero** | `M` ou `F` — usado para distribuir homens e mulheres entre os times. |
| **Score** | Nível de jogo, numa escala de ~40 (iniciante) a ~95 (muito forte). |

Sobre o score:

- Ele **só serve para equilibrar os times**. Nunca decide quem joga — isso é só pelo rodízio.
- Compare homens com homens e mulheres com mulheres. Internamente os homens recebem +10 na hora de montar os times (`MALE_ADJUSTMENT` em `app/services/teams.py`), calibrado a partir de "um homem 80 joga como uma mulher 90". Ajuste para o seu grupo.
- Não precisa ser preciso. Chute (70 para intermediário) e corrija depois de ver a pessoa jogar.

Dá para cadastrar pela tela (**⚙ Jogadores**) ou pela API:

```bash
curl -X POST http://localhost:8000/api/players \
  -H 'Content-Type: application/json' \
  -d '{"name": "Ana", "score": 70, "gender": "F"}'
```

## Rodar

Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Abra `http://127.0.0.1:8000`. Para usar nos celulares na mesma rede Wi-Fi, abra `http://IP_DO_COMPUTADOR:8000` (no Mac: `ipconfig getifaddr en0`).

Ou com Docker (o banco fica em `./data/volei.db`):

```bash
docker compose up -d --build
```

Testes: `pytest`.

## Uma noite de jogo

1. **Crie a sessão do dia** com quem confirmou presença (o botão na tela fica desabilitado para ninguém resetar a noite sem querer):

   ```bash
   curl -X POST http://localhost:8000/api/sessions \
     -H 'Content-Type: application/json' \
     -d '{"name": "Vôlei 14/09", "player_ids": [1, 2, 3]}'
   ```

   Sem `player_ids`, todos os jogadores cadastrados entram na pré-lista.
2. Conforme as pessoas chegam, marque **Chegou** — a ordem de chegada importa na primeira partida.
3. **Gerar próxima partida** → o app escolhe 12 pessoas e monta os times, mostrando o motivo de cada escolha.
4. **Iniciar**. Se alguém se machucar ou for embora no meio, toque em **Saiu** e escolha o substituto sugerido.
5. Ao terminar, toque em **Time A venceu** ou **Time B venceu** e repita.

As vitórias alimentam o **ranking do dia**, ordenado por vitórias ÷ partidas jogadas (quem ficou mais tempo não lidera só por ter jogado mais). Entrar como substituto não conta.

Quem chega sem estar na lista entra por **+ Pessoa fora da lista**.

## Regras do rodízio

Combinadas com o grupo:

1. **Ninguém joga 3 partidas seguidas.** Quem jogou 2 fica de fora da próxima. (Abaixo de 18 presentes isso não cabe no 6x6; aí o app libera o mínimo de gente necessário.)
2. **Quem esperou entra.** Na prática, ninguém espera mais de uma partida seguida enquanto houver até ~24 presentes.
3. **As vagas que sobram** vão para quem jogou a menor *fração* das partidas em que estava presente — proporcional, para não favorecer nem punir quem chegou tarde. Empates são sorteados.
4. **Sempre 6x6.**
5. **Entrar como substituto é emergência:** não conta como partida jogada nem prende a pessoa na regra das seguidas.

Os critérios são baseados em contagem de partidas, não em minutos jogados — depender de alguém apertar iniciar/encerrar na hora certa se mostrou frágil.

O raciocínio e as simulações que validaram essas regras estão em [SIMULATION.md](SIMULATION.md).

## Limitações deliberadas

- **Sem autenticação.** Qualquer um com o link controla a sessão. Rode na rede local ou deixe no ar só durante o jogo.
- Não integra com WhatsApp: a lista de confirmados é cadastrada à mão.
- Registra só quem venceu cada partida, não o placar.
- Uma sessão ativa por vez, banco SQLite local.

## Licença

MIT — veja [LICENSE](LICENSE).
