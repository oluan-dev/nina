# Nina — uma auxiliar de voz para o Claude Code

![O rosto da Nina com as cinco formas de boca: M, S, AH, E e O](nina/arte/prova.png)

A Nina é uma **auxiliar por voz para as suas sessões do Claude Code** no Windows.
Você trabalha com várias sessões do Claude Code abertas no VS Code, cada uma num
painel do [Canteiro](https://github.com/oluan-dev/canteiro). Você fala com a Nina
em português; ela **digita o pedido na sessão certa**, acompanha, e **avisa
falando quando a sessão termina** ou para esperando você — sem você precisar
olhar nem perguntar.

Exemplos: "Nina, manda pro painel do app rodar os testes", "Nina, o que a sessão
da API respondeu?", "Nina, o que você está esperando?". Ela também tem uma sessão
própria do Claude Code, sempre aberta, para responder e fazer coisas rápidas
(ler um arquivo, rodar um comando, pesquisar). Tudo pela sua **assinatura do
Claude** (o login do `claude` no terminal), nunca pela API paga por token.

A conversa por voz (ouvir, perceber quando você terminou de falar, ser
interrompida, tocar o áudio) é do [Pipecat](https://github.com/pipecat-ai/pipecat).
Este repositório liga o Pipecat ao cérebro (a sessão própria dela), às sessões do
Canteiro, à voz e ao microfone do celular. Ela também tem um **rosto** que mexe a
boca junto com a fala.

> [!WARNING]
> **Leia antes de rodar.**
> - **Ela age no seu computador.** O Claude Code da Nina pode rodar comandos (Bash),
>   ler e gravar arquivos e acessar a web. O único freio é uma lista de comandos
>   perigosos (`nina/perigo.mjs`): ao reconhecer um, ela pergunta "Posso fazer isso?"
>   e espera o "sim" falado. Isso **não é um sandbox**. Rode numa conta ou máquina
>   onde um comando errado não cause estrago.
> - **Ela digita nas suas sessões abertas.** Pelo Canteiro, ela escreve o pedido
>   no terminal de uma sessão do Claude Code sua e aperta ENTER. Essa sessão roda
>   com as permissões que **você** deu a ela, não com o freio da Nina. As regras
>   dela mandam repetir o pedido em voz alta e esperar o seu "sim" antes de enviar,
>   mas isso é regra de prompt, não trava no código.
> - **O que você fala sai da máquina.** O áudio é transcrito localmente (Whisper),
>   mas a resposta falada usa o edge-tts, que envia o texto aos servidores da
>   Microsoft. E o pedido em si vai para o Claude, da Anthropic.

---

## Sumário

1. [O que dá para pedir](#o-que-dá-para-pedir)
2. [Como funciona por dentro](#como-funciona-por-dentro)
3. [Pré-requisitos](#pré-requisitos)
4. [Instalação passo a passo](#instalação-passo-a-passo)
5. [Rodar](#rodar)
6. [Configuração, campo a campo](#configuração-campo-a-campo)
7. [O rosto](#o-rosto)
8. [Segurança e privacidade](#segurança-e-privacidade)
9. [Problemas comuns](#problemas-comuns)
10. [Limitações](#limitações)
11. [Testes](#testes) · [Licença e créditos](#licença-e-créditos)

---

## O que dá para pedir

Ela só atende quando a fala **começa com o nome dela** ("Nina, …"). Depois que ela
responde, você tem **20 segundos** para continuar o assunto sem repetir o nome.

### Trabalhar nas suas sessões do Canteiro

Cada painel do Canteiro é uma sessão do Claude Code com um nome (o que aparece na
aba) e uma pasta. Você se refere a ele pelo nome, pela pasta ou pelo id.

| Você fala | O que acontece |
|---|---|
| "Nina, quais sessões estão abertas?" | Ela lista os painéis abertos no Canteiro (nome e pasta) e diz o estado de cada um: "respondeu e parou", "esperando você" ou "sem sinal ainda" |
| "Nina, manda pro painel do app rodar os testes" | Ela repete o que vai mandar e para qual painel, e espera o seu "sim". Com o sim, a extensão **digita** "Pedido por voz: rodar os testes" no terminal daquela sessão e aperta ENTER — você vê o texto chegar. Ela só diz "mandei" se a extensão confirmar |
| *(a sessão termina)* | Sem você perguntar, ela fala: "aquilo do app voltou: …", em uma ou duas frases. Se a sessão parar pedindo permissão, ela avisa que está esperando um clique seu |
| "Nina, o que a sessão da API respondeu?" | Ela lê as últimas falas daquela conversa e resume |
| "Nina, o que você está fazendo?" | Ela responde pela lista do que mandou e ainda espera ("mandei pro app há 3 minutos, ainda não voltou") |
| "Nina, manda pro financeiro…" e há dois painéis com esse nome | Ela pergunta qual dos dois, em vez de chutar |
| O painel existe, mas a aba está fechada no VS Code | Ela diz o nome do painel e pede para você abrir a aba; não manda para um parecido |

Pendência sem resposta há mais de 1 hora é esquecida. Um resultado não contado fica
guardado por até 2 horas e entra na próxima conversa.

### Pedidos para a sessão própria dela

| Você fala | O que acontece |
|---|---|
| "Nina, o que tem nessa pasta?" | A sessão usa `Glob`/`Read` e ela resume em voz. Caminhos e código não são falados: ela diz "te mandei na tela" e o texto aparece na legenda |
| "Nina, roda os testes do projeto" | A sessão roda o comando pelo `Bash` e ela conta se passou ou o que quebrou |
| "Nina, cria um arquivo de notas com o que eu disser" | A sessão escreve o arquivo (sem perguntar, se for dentro desta pasta ou de uma `pastas_extras`) |
| "Nina, apaga a pasta de rascunhos" | Comando destrutivo: ela explica o que vai fazer e pergunta **"Posso fazer isso?"**. Só faz se você responder "sim", "pode", "manda", "pode fazer"… Silêncio por 2 minutos vale como **não** |
| "Nina, pesquisa como configurar tal coisa" | A sessão usa `WebSearch`/`WebFetch` e ela resume |

Ferramentas que a sessão tem: `Read`, `Write`, `Edit`, `Bash`, `Grep`, `Glob`,
`WebSearch`, `WebFetch`. Modelo padrão: `sonnet`, com esforço baixo (para responder
rápido). A sessão é **retomada no dia seguinte**: ela lembra do que foi dito.

### Comandos de conversa (decididos na hora, sem passar pelo Claude)

| Você fala | O que acontece |
|---|---|
| "Nina." (só o nome, e pausa) | Ela responde "Oi?" depois de 1,5 s, se você não continuar |
| "Pera, Nina" / "Espera, Nina" / "Nina, para de ouvir" | Ela responde "Tá." e **para de ouvir** até você dizer "voltei" |
| "Voltei" / "Volta, Nina" / "Pode ouvir, Nina" | Ela responde "Voltei." e volta a ouvir |
| "Para, Nina" / "Chega" / "Já entendi" | Ela para de falar e **continua ouvindo** |
| "Tchau, Nina" / "Desliga" | "Falou, tô por aqui." — a partir daí só atende pelo nome de novo |
| **Ctrl+Alt+N** (teclado, em qualquer janela) | Liga e desliga o ouvido dela, igual a "pera" / "voltei" |

### O que ela faz sozinha para a conversa parecer de gente

- **Aceno:** um "hum." baixinho no instante em que você termina de falar, antes de a
  resposta existir.
- **Frases de espera:** se o Claude demora mais de 2,5 s, ela diz "Tô conferindo",
  "Deixa eu olhar"…; passou de 14 s, "Isso vai demorar um pouco, eu te aviso quando
  terminar". (Só se você gravar essas frases, ver [passo 6](#instalação-passo-a-passo).)
- **Frase pela metade:** se a fala termina aberta ("manda isso pro…", "preciso que
  você…"), ela espera até 3 s pela continuação antes de responder.
- **Você terminou?** O Claude também decide: toda resposta começa com `●` (responder),
  `◐` (você parou no meio, esperar calada) ou `○` (você pediu tempo). Só `●` vira voz.
- **Interrompida:** se você falar por cima (com fone), ela cala e a sessão fica
  sabendo **o que você chegou a ouvir**, não o que ela ia dizer.
- **Eco do Whisper:** a mesma fala repetida em 6 s, ou uma palavra repetida 4 vezes
  seguidas ("suja, suja, suja, suja"), é ignorada.

---

## Como funciona por dentro

```
 você fala
    │
    ▼
 microfone ──────────────── celular no cabo (scrcpy, cano nomeado do Windows)
    │                       ou o microfone padrão do Windows
    ▼
 Silero VAD ─► Whisper large-v3-turbo (local, GPU) ─► smart-turn v3 ("terminou?")
    │                                     [Pipecat]
    ▼
 conversa/cerebro.py  ── é comigo? é comando? ("pera", "tchau", "sim")
    │   │
    │   ├─ diretrizes curtas desta fala (nina/diretrizes.py)
    │   └─ o que ela mandou e espera + painéis abertos (nina/sessoes.py)
    ▼
 node nina/cerebro.mjs ── 1 sessão do Claude Code sempre viva (Claude Agent SDK)
    │   │                  JSON por linha: {"pergunta"} → {"pedaco"}… {"fim"}
    │   └─ antes de cada ferramenta: é perigoso? ─► {"confirmar"} ─► "Posso fazer isso?"
    ▼
 resposta em pedaços ─► voz edge-tts (em fluxo, via ffmpeg) ─► caixa de som
                              │                                    │
                              └─ instante de cada palavra          └─ nina/boca.py mede o som tocado
                                 (nina/visema.py)                      ─► diario/boca.json ─► rosto

 sessões do Canteiro (VS Code):
   cérebro roda "python -m nina.sessoes --mandar <painel> <texto>"
     ─► estado/_entrada.json ─► Canteiro digita no terminal da sessão ─► _entrada.ack.json ("MANDEI")
   a sessão para ─► relator do Canteiro grava <painel>.evento.json
     ─► nina.sessoes.vigiar (a cada 5 s) lê a resposta no .jsonl da conversa ─► ela conta em voz
```

| Peça | Arquivo | O que faz |
|---|---|---|
| Laço | `conversa/__main__.py` | Escolhe o microfone, monta o pipeline do Pipecat, sobe legenda, atalho e rosto |
| Ponte | `conversa/cerebro.py` | Decide se a fala é com ela, trata os comandos, manda o resto ao cérebro, fala a resposta frase a frase |
| Cérebro | `nina/cerebro.mjs` | A sessão do Claude Code: nascer custa ~8 s (por isso nasce uma vez só); cada resposta começa em ~1,5 a 2 s |
| Freio | `nina/cerebro.mjs`, `nina/perigo.mjs` | Lista de comandos perigosos, escrita fora das pastas liberadas e scripts de outros projetos pedem o "sim" |
| Regras faladas | `conversa/regras.py` | Nome dela e as variações que o Whisper escreve ("Mina", "Menina"), comandos, "sim", frase aberta |
| Diretrizes | `nina/diretrizes.py` | Regras "quando X, faça Y" que entram no pedido só quando a fala pede (ideia do [Parlant](https://github.com/emcie-co/parlant)) |
| Voz | `conversa/voz.py` | edge-tts em fluxo: o áudio começa a tocar antes de a frase terminar de ser gerada |
| Microfone do celular | `conversa/celular.py`, `nina/microfone_celular.py` | Áudio do celular pelo scrcpy, em pedaços de ~20 ms; se o cabo soltar, espera ele voltar |
| Fone sob demanda | `conversa/fone.py` | Abre o microfone do Windows só no Ctrl+Alt+N (fone Bluetooth com microfone aberto piora o som do PC) |
| Legenda | `nina/legenda.py` | Faixa na tela com o que ela ouviu ("Você") e o que respondeu ("Nina") |
| Atalho | `nina/atalho.py` | Ctrl+Alt+N |
| Sessões | `nina/sessoes.py` | Lista, acha, digita e lê as sessões do Canteiro; anota o que mandou e avisa quando a sessão responde. A pasta da extensão é `%APPDATA%\Code\User\globalStorage\oluan-dev.canteiro` |
| Rosto | `nina/visema.py`, `nina/boca.py`, `nina/rosto_flutuante.py`, `nina/rosto_web.py`, `nina/rosto.html` | Ver [O rosto](#o-rosto) |

Por que um processo vivo e não `claude -p` a cada fala: medido, abrir um processo
novo do Claude custa ~7,7 s até a primeira palavra; com o processo sempre aberto,
~1,7 a 2,5 s.

---

## Pré-requisitos

Versões com que a Nina foi testada. Outras próximas devem funcionar, mas não foram testadas.

| O quê | Versão testada | Para quê |
|---|---|---|
| Windows | 11 (usa API do Windows: legenda, atalho, cano nomeado, janela do rosto) | — |
| Python | 3.11.9 | o laço de voz |
| Node.js | 24 (o Agent SDK pede 18 ou mais) | o cérebro |
| Claude Code | logado com uma assinatura do Claude | a sessão que trabalha |
| ffmpeg | qualquer recente, no PATH | converter a voz |
| GPU NVIDIA + CUDA 12 | testado com torch 2.11 (cu128) | Whisper rápido (~0,2 s). Sem GPU funciona em CPU, mais lento |
| Internet | — | voz (edge-tts) e o Claude |
| Celular Android (opcional) | adb 1.0.41, scrcpy 5.0.1 | microfone perto da boca |
| VS Code + [Canteiro](https://github.com/oluan-dev/canteiro) | a extensão aberta, com as sessões em painéis | a Nina ver e digitar nas sessões |
| Ollama (opcional) | com `bge-m3` | diretrizes casarem pelo sentido; sem ele, casam por palavra |

Pacotes Python (em `requirements.txt`): Pipecat no commit `c38f3184` com
`silero`, `whisper` e `local`; `edge-tts` 7.3; `loguru`. O Pipecat traz junto
numpy, Pillow, onnxruntime, o Silero VAD e o modelo smart-turn v3.
Pacote Node: `@anthropic-ai/claude-agent-sdk` 0.3.296.

---

## Instalação passo a passo

Todos os comandos rodam no PowerShell, dentro da pasta do projeto.

**1. Baixe o projeto.**
```powershell
git clone <url-deste-repositório> nina
cd nina
```
*Deu certo se:* `dir` mostra `conversa`, `nina`, `README.md`.

**2. Confira o Claude Code logado.** Instale o [Claude Code](https://docs.claude.com/en/docs/claude-code)
e entre com a sua conta (rode `claude` uma vez e faça o login).
```powershell
claude --version
```
*Deu certo se:* mostra a versão, e `claude` abre sem pedir login. A Nina **apaga toda
variável `ANTHROPIC_*`** antes de subir, então ela sempre usa esse login da assinatura.

**3. Crie o ambiente Python e instale o Pipecat.**
```powershell
py -3.11 -m venv venv-pipecat
venv-pipecat\Scripts\python.exe -m pip install -r requirements.txt
```
*Deu certo se:* `venv-pipecat\Scripts\python.exe -c "import pipecat, edge_tts; print('ok')"` imprime `ok`.

**4. (Com GPU NVIDIA) Instale o torch com CUDA no mesmo ambiente.** O Whisper
(ctranslate2) precisa das DLLs do CUDA; `conversa/__init__.py` põe a pasta
`torch\lib` deste ambiente no PATH sozinho.
```powershell
venv-pipecat\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cu128
```
*Deu certo se:* `venv-pipecat\Scripts\python.exe -c "import torch; print(torch.cuda.is_available())"` imprime `True`.
Sem GPU, pule este passo e use `"whisper_device": "cpu"` e `"whisper_compute": "int8"` no passo 7.

**5. Instale o cérebro (Node).**
```powershell
npm install
```
*Deu certo se:* existe a pasta `node_modules\@anthropic-ai\claude-agent-sdk`.

**6. Grave as frases de espera (opcional, recomendado).** Precisa de internet e ffmpeg.
```powershell
venv-pipecat\Scripts\python.exe gerar_bordoes.py
```
*Deu certo se:* imprime `hum: ok (… KB)` e as outras, e a pasta `bordoes\` tem 13 arquivos `.wav`.
Sem elas a Nina funciona, mas fica calada enquanto pensa e não faz o "hum." de aceno.

**7. Crie a sua configuração.**
```powershell
copy config.example.json config.json
```
Edite pelo menos `pastas_extras` (onde ela pode trabalhar) e `nomes` (ver
[Configuração](#configuração-campo-a-campo)).
*Deu certo se:* `venv-pipecat\Scripts\python.exe -m nina.config` lista os campos, com `(mudado)` nos que você alterou.

**8. Instale o Canteiro no VS Code.** Siga o README do
[Canteiro](https://github.com/oluan-dev/canteiro) e abra pelo menos uma sessão do
Claude Code num painel.
*Deu certo se:* com o VS Code aberto, `venv-pipecat\Scripts\python.exe -m nina.sessoes`
lista os painéis no formato `[id] nome (pasta) — estado`. Se responder "Nenhuma
sessão aberta." com painéis abertos, confira `canteiro_extensao` no `config.json`.

**9. (Opcional) Celular como microfone.** Ative a depuração USB no Android, instale
o `adb` (Android Platform Tools) e o [scrcpy](https://github.com/Genymobile/scrcpy),
e deixe os dois no PATH — ou aponte as variáveis `NINA_ADB` e `NINA_SCRCPY` para os `.exe`.
*Deu certo se:* `adb devices` lista o aparelho como `device`.

**10. Primeira conversa.** Clique duas vezes em `conversa.cmd`.
*Deu certo se:* a janela mostra `Nina (Pipecat) ouvindo. Ctrl+C encerra.`, o rosto
aparece no canto inferior esquerdo da tela, e "Nina, tá me ouvindo?" recebe resposta
falada. Na primeira vez o Whisper baixa o modelo (~1,6 GB) antes de ouvir.

---

## Rodar

```powershell
conversa.cmd                                               # o jeito normal; religa sozinha se cair
venv-pipecat\Scripts\python.exe -m conversa                # celular no cabo; sem ele, o mic do Windows
venv-pipecat\Scripts\python.exe -m conversa --fone         # força o microfone do Windows
venv-pipecat\Scripts\python.exe -m conversa --fone --sob-demanda   # mic só abre no Ctrl+Alt+N
venv-pipecat\Scripts\python.exe -m conversa --deixar-cortar        # deixa interromper mesmo no celular
venv-pipecat\Scripts\python.exe -m conversa --fone --sem-cortar    # não deixa interromper no fone
```

- **Interromper:** ligado por padrão com o microfone do Windows (fone de ouvido) e
  desligado com o celular, porque a caixa de som vaza no celular e ela se cortaria sozinha.
- **Uma Nina por vez:** a trava `nina.lock` impede duas de disputarem microfone e caixa.
- **Subir com o Windows:** `nina-sempre.ps1` sobe e religa a Nina se ela cair; crie uma
  tarefa agendada para ele (instruções no topo do arquivo). O log vai para `diario\sessao.log`.
- **Onde ficam os registros:** `diario\conversa.log` (técnico), `diario\conversas.log`
  (o que você falou e o que ela respondeu), `diario\ferramentas.log` (cada ferramenta
  que a sessão usou). Tudo só na sua máquina.

---

## Configuração, campo a campo

`config.json` na raiz (cópia de `config.example.json`). Campo ausente usa o valor de fábrica.

| Campo | Padrão | O que muda |
|---|---|---|
| `whisper_modelo` | `"large-v3-turbo"` | Modelo do Whisper. Menores (`"small"`, `"medium"`) são mais leves e erram mais |
| `whisper_device` | `"cuda"` | `"cuda"` (GPU NVIDIA) ou `"cpu"` |
| `whisper_compute` | `"float16"` | Precisão. Na CPU use `"int8"` |
| `nomes` | `"Nina, Claude, Whisper, Pipecat."` | Palavras que o Whisper deve acertar (nomes de projetos, pessoas, ferramentas), numa frase separada por vírgulas. Vão como *hotwords* |
| `voz` | `"pt-BR-FranciscaNeural"` | Voz do edge-tts. `venv-pipecat\Scripts\edge-tts.exe --list-voices` lista todas |
| `voz_velocidade` | `"+18%"` | Velocidade da fala, ex. `"+0%"`, `"+25%"` |
| `legenda` | `"balao"` | `"balao"` (com o nome de quem falou) ou `"filme"` (letra grande sobre faixa translúcida) |
| `legenda_tamanho` | `20` | Tamanho da letra no estilo `"filme"` |
| `legenda_altura` | `140` | Distância da legenda até o pé da tela, em pixels |
| `cerebro_modelo` | `"sonnet"` | Modelo da sessão do Claude Code |
| `canteiro_extensao` | `"oluan-dev.canteiro"` | Id da extensão Canteiro no VS Code: a Nina procura a pasta `%APPDATA%\Code\User\globalStorage\<id>`. Mude só se instalou o Canteiro com outro publisher |
| `pastas_extras` | `[]` | Pastas (caminho completo) onde a sessão pode ler e **escrever sem perguntar**, além da pasta da Nina e da pasta temporária. É aqui que você coloca os projetos em que ela vai trabalhar |

Outros ajustes:

- **Variáveis de ambiente:** `NINA_ADB`, `NINA_SCRCPY` (caminho dos executáveis),
  `NINA_CUDA_LIB` (pasta das DLLs do CUDA, se não for o `torch\lib` do ambiente).
- **`memoria/usuario.md`** (você cria): texto livre com preferências suas ("prefiro
  resposta curta", "meus projetos ficam em tal pasta"). Vai junto em toda conversa.
- **Mudou as regras dela** (o texto `REGRAS` em `nina/cerebro.mjs`)? A sessão antiga
  é descartada e começa uma nova, para ela não seguir as regras velhas.
- **Smart-turn ajustado ao português (opcional):** se existir `modelos\smart-turn-pt.onnx`,
  ele substitui o modelo original do Pipecat.

---

## O rosto

O rosto aparece em dois lugares ao mesmo tempo, os dois com a boca mexendo junto da voz:

- **flutuando no canto inferior esquerdo da tela** (`nina/rosto_flutuante.py`):
  arraste para mover (a posição fica guardada), botão direito fecha;
- **no navegador**, em **http://localhost:4790/rosto** (`nina/rosto_web.py` + `nina/rosto.html`),
  com uma faixa que mostra a onda da voz e a forma da boca.

Como a boca acompanha a fala, em três passos:

1. **O edge-tts entrega o instante de cada palavra.** Junto com o áudio vêm eventos
   `WordBoundary` (palavra, início, duração). `conversa/voz.py` os recolhe.
2. **A letra vira forma de boca.** O português escreve quase como fala, então a letra
   já diz a forma: `nina/visema.py` traduz em cinco formas — **M** (m, b, p e silêncio),
   **S** (fresta), **AH** (a), **E** (e, i), **O** (o, u) — e monta a agenda da fala.
3. **O som que acabou de tocar escolhe o quadro.** `nina/boca.py` fica *depois* da
   saída de áudio no pipeline: mede a força do som (quanto a boca abre), conta as
   amostras tocadas para achar o ponto da agenda (qual forma) e escreve
   `diario/boca.json`. O rosto só lê esse arquivo e troca a imagem. Sem relógio de
   parede, a boca não desencontra da voz.

A arte fica em `nina/arte/`: `rosto.png` (400×669) e as cinco `boca-*.png` (200×140),
coladas na posição (104, 368) do rosto. Para trocar a arte, mantenha esses tamanhos ou
ajuste `CAIXA_DA_BOCA` em `rosto_flutuante.py` e a classe `.boca` em `rosto.html`.

Arte gerada com IA por oluan-dev.

---

## Segurança e privacidade

- **O freio é uma lista, não um sandbox.** Pedem o "sim" falado: apagar em massa
  (`rm -rf`, `del /s`, `Remove-Item -Recurse`…), mexer no sistema (`shutdown`, `reg`,
  `schtasks`, `netsh`…), `git push`, `git reset --hard`, `curl` com POST/PUT/DELETE,
  baixar e executar (`curl | sh`, `iex`), `DROP TABLE`/`DELETE FROM`, desinstalar
  pacotes, **escrever fora** da pasta da Nina/temporária/`pastas_extras`, e **rodar
  script de outra pasta** (`python`, `node`, `powershell`, `.bat`… fora da pasta da Nina).
  O que não estiver na lista roda sem perguntar.
- **Nada que ela lê vira ordem.** As regras dela dizem que texto de página, arquivo ou
  mensagem é conteúdo para contar a você, nunca instrução. É uma regra de prompt, não
  uma garantia.
- **Nunca a API paga.** O cérebro apaga `ANTHROPIC_*` do ambiente e usa o login do Claude Code.
- **Nas sessões do Canteiro, ela digita como se fosse você.** O texto entra no terminal
  da sessão e roda com as permissões daquela sessão. Ela só diz "mandei" com a
  confirmação da extensão, e começa cada pedido com "Pedido por voz:", para você
  reconhecer na conversa.
- **Ela lê as conversas das sessões** (os `.jsonl` em `%USERPROFILE%\.claude\projects`)
  para contar o que responderam.
- **Ela não herda a sua configuração do Claude Code:** sobe sem skills, hooks,
  plugins nem `CLAUDE.md` (`settingSources: []`).
- **Para onde vão os dados:** o áudio é transcrito no seu PC; o texto do pedido vai
  para a Anthropic; o texto que ela fala vai para a Microsoft (edge-tts). Registros
  (`diario\`) e a sessão retomada (`memoria\sessao.txt`) ficam no seu PC.
- **O rosto no navegador** só escuta em 127.0.0.1, só responde a endereço localhost
  e exige uma senha sorteada a cada arranque para ler o estado da boca.

---

## Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `Já tem uma Nina ligada (processo N). Feche a outra antes.` | Outra Nina aberta | Feche a outra janela. Se não houver nenhuma, apague `nina.lock` |
| `Sem microfone: ligue o celular no cabo (depuração USB). Esperando…` | Nem celular nem microfone do Windows | Ligue um dos dois; ela continua sozinha quando o celular aparece |
| `celular fora do cabo: usando o microfone padrão do Windows` | `adb devices` não achou o aparelho | Confira cabo, depuração USB e `adb` no PATH (ou `NINA_ADB`) |
| `o microfone do celular não respondeu (cabo e depuração USB?)` | scrcpy não subiu | Confira `scrcpy` no PATH (ou `NINA_SCRCPY`) e rode `scrcpy --no-video --audio-source=mic` à mão para ver o erro |
| `microfone parou de mandar som há 10 s — religando a Nina` | O microfone dormiu ou o Bluetooth caiu | Pelo `conversa.cmd` ela religa sozinha em 5 s |
| Erro de DLL do CUDA (cublas/cudnn) ao carregar o Whisper | Faltam as DLLs do CUDA no PATH | Faça o passo 4, ou aponte `NINA_CUDA_LIB`, ou use `"whisper_device": "cpu"` |
| Ela ouve mas não responde | A fala não começou com "Nina" e passaram mais de 20 s da última troca; ou ela está "surda" | Comece com "Nina, …"; diga "voltei" ou aperte Ctrl+Alt+N. `diario\conversas.log` mostra `(não era comigo)` ou `(pediu para eu não ouvir — ignorei)` |
| Ela demora para falar e fica em silêncio | Sem frases de espera gravadas | Faça o passo 6 |
| Sem voz, e erro `voz falhou` no log | Sem internet ou sem `ffmpeg` no PATH | Confira os dois |
| Ela entende errado um nome | O Whisper não conhece a palavra | Ponha a palavra em `nomes` no `config.json` |
| Ela pergunta "Posso fazer isso?" para escrever no seu projeto | A pasta não está liberada | Ponha a pasta em `pastas_extras` |
| `http://localhost:4790/rosto` não abre | Outro programa usa a porta 4790 (o servidor do rosto não sobe e a Nina segue sem ele) | Libere a porta ou use só o rosto flutuante |
| "o Canteiro não está rodando (a pasta de estado não existe)" | Canteiro não instalado, ou `canteiro_extensao` errado | Instale o Canteiro; confira o id da extensão no `config.json` |
| "o Canteiro não respondeu: o VS Code está aberto?" | VS Code fechado | Abra o VS Code com os painéis |
| Ela diz "ABA FECHADA" | O painel existe, mas a aba não está aberta | Abra a aba no VS Code e peça de novo |
| Ela não avisa quando a sessão termina | O vigia só acompanha o que **ela** mandou, por até 1 hora | Peça "Nina, o que a sessão X respondeu?" |
| Diretrizes "pelo sentido" não funcionam | Ollama fora do ar ou sem `bge-m3` | Opcional: `ollama pull bge-m3` e deixe o Ollama aberto |

---

## Limitações

- **Só Windows.** Legenda, atalho, cano nomeado, janela do rosto e o encerramento do
  cérebro (`taskkill`) usam a API do Windows.
- **Só português (pt-BR).** Nome, comandos, "sim" e frase aberta são listas em português.
- **Sessões só pelo Canteiro e só no VS Code** (a pasta `Code\User\globalStorage`).
  Sessões abertas em outro terminal não aparecem; as de fundo (`claude --bg`) recebem o
  pedido sem confirmação.
- **Precisa de assinatura do Claude** e do Claude Code logado; o uso conta no seu limite.
- **Precisa de internet** para a voz e para o Claude. Só a transcrição é local.
- **O freio é por lista**, não um isolamento: ver [Segurança](#segurança-e-privacidade).
- **Tempo de resposta**, medido numa GPU NVIDIA recente: ~0,2 s de Whisper + 1,5 a 2 s
  até o Claude começar + ~1 s até a voz sair. Na CPU, o Whisper é bem mais lento.
- **Com o microfone do celular ela não pode ser interrompida** por padrão (a caixa de
  som vaza no microfone). Com fone de ouvido, pode.
- O nome de ativação "Nina" é fixo no código (`conversa/regras.py`).

---

## Testes

```powershell
venv-pipecat\Scripts\python.exe testes\teste_conversa_regras.py   # nome, comandos, sim, frase aberta
venv-pipecat\Scripts\python.exe testes\teste_diretrizes.py        # diretrizes e "disse que fez sem ferramenta"
node testes\teste_perigo.mjs                                      # script de outra pasta pede o "sim"
venv-pipecat\Scripts\python.exe testes\teste_o_que_espero.py      # sessões: pendências e MANDEI só com ack
venv-pipecat\Scripts\python.exe -m nina.visema                    # letra → forma de boca
venv-pipecat\Scripts\python.exe -m nina.boca                      # som → abertura da boca
```

---

## Licença e créditos

MIT — veja `LICENSE`. Arte do rosto gerada com IA por oluan-dev.
O [Pipecat](https://github.com/pipecat-ai/pipecat) é BSD-2-Clause. As regras de estilo
de fala vêm do [humanizer](https://github.com/blader/humanizer) (MIT); a ideia das
diretrizes por fala, do [Parlant](https://github.com/emcie-co/parlant).
