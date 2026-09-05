# Vôlei MVP

Gerenciador local de sessões de vôlei para celular/computador, com:

- pré-lista da noite;
- check-in por ordem de chegada;
- jogadores fora da lista;
- faltas e saída antecipada;
- seleção justa dos próximos jogadores;
- times equilibrados por score;
- preferência por distribuição de homens/mulheres;
- substituições durante a partida;
- sincronização em tempo real via WebSocket;
- histórico da sessão;
- modo simples para outra pessoa administrar.

## Requisitos

Python 3.11+.

## Rodar no Mac

```bash
cd volei-mvp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

No mesmo Mac:

```text
http://127.0.0.1:8000
```

Para abrir em celulares na mesma rede Wi-Fi, descubra o IP do Mac:

```bash
ipconfig getifaddr en0
```

ou, se estiver no Wi-Fi via outra interface:

```bash
ifconfig | grep "inet "
```

Depois abra no celular:

```text
http://IP_DO_MAC:8000
```

Exemplo:

```text
http://192.168.1.42:8000
```

Se o macOS pedir permissão para conexões de entrada, permita para Python.

## Fluxo do MVP

1. Cadastre os jogadores permanentes e seus scores.
2. Crie uma sessão.
3. Selecione quem confirmou na pré-lista.
4. Durante a chegada, marque `Chegou`.
5. Quando quiser, clique em `Gerar próxima partida`.
6. O sistema escolhe os jogadores e monta os times.
7. Clique em `Iniciar partida`.
8. Se alguém sair, use `Saiu` e escolha a substituição sugerida.
9. Ao terminar, clique em `Encerrar partida`.
10. Repita.

## Filosofia do algoritmo

O sistema separa:

- **skill score**: capacidade estimada do jogador;
- **fairness**: histórico da sessão.

O score não determina quem tem direito de jogar. Ele é usado principalmente para equilibrar os times.

A seleção considera:

- espera acumulada;
- partidas consecutivas fora;
- partidas consecutivas jogadas;
- total de tempo jogado;
- tempo desde a última participação.

A divisão dos times considera:

- soma dos scores;
- diferença de distribuição de scores;
- distribuição de homens/mulheres.

## Limitações deliberadas do MVP

- Não integra automaticamente com WhatsApp.
- Não exige registro do minuto exato: timestamps são automáticos.
- Não tenta registrar pontos/rallies.
- Não tem autenticação.
- Não é projetado para ficar exposto diretamente à Internet.

A ideia é validar o fluxo real no vôlei antes de adicionar complexidade.
