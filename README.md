# open-m711pro

Driver/utilitário **aberto** para o mouse **Redragon M711 Pro** (chip Compx,
receptor 2.4G) no **Linux** — sem depender do software oficial do Windows.

Controla a iluminação do mouse por uma **interface gráfica** (paleta de cores
estilo editor de imagem) ou pela **linha de comando** — funcionando tanto no
modo **2.4G (dongle)** quanto por **cabo**. Todo o protocolo foi obtido por
engenharia reversa e está documentado em [`docs/PROTOCOL.md`](docs/PROTOCOL.md).

> ⚠️ Projeto experimental, feito por engenharia reversa. Use por sua conta e
> risco. Não é afiliado à Redragon.

## Estado atual

| Função | Status |
|--------|--------|
| Cor do LED (qualquer cor) | ✅ funcionando |
| Ligar / desligar o LED | ✅ funcionando |
| Funciona no dongle 2.4G **e** no cabo | ✅ testado |
| Interface gráfica (paleta + seletor HSV) | ✅ funcionando |
| Brilho / efeitos | ⬜ a mapear |
| DPI / polling / botões / macros | ⬜ a mapear |

## Requisitos

- **Python 3** (a aplicação em si **não tem dependências externas** — usa
  `hidraw` direto e `tkinter`, ambos da stdlib)
- Mouse ligado (dongle 2.4G) ou conectado por cabo
- Acesso ao dispositivo HID (regra udev abaixo)

### Regra udev (acesso sem root)

Crie `/etc/udev/rules.d/99-redragon-m711.rules`:

```
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="25a7", MODE="0666"
```

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw
# reconecte o dongle / cabo
```

## Uso

**Interface gráfica** (sem argumentos):

```bash
python3 main.py
```

Clique numa cor da paleta, use **"Cor personalizada…"** para o seletor HSV
completo, ou **"Desligar LED"**. A cor é aplicada ao vivo.

**Linha de comando:**

```bash
python3 main.py FF0000        # vermelho (hex)
python3 main.py 0 255 0       # verde (R G B)
python3 main.py azul          # cor por nome
python3 main.py off           # desliga o LED

python3 main.py dpi           # mostra os 5 estágios lidos do mouse
python3 main.py dpi 1600      # um DPI só: aplica aos 5 estágios
python3 main.py dpi 3 4000    # muda só o estágio 3
python3 main.py dpi-effect on # LED indicador de nível de DPI (on/off)
```

> O mouse guarda o DPI em passos de ~83, então o valor exibido é o que ele
> realmente tem: pedir 1600 resulta em 1583. Preferimos mostrar a verdade a
> arredondar por conta própria.

## Estrutura do projeto

```
open-m711pro/
├── main.py               # ponto de entrada (GUI sem args, CLI com args)
├── m711pro/              # o pacote
│   ├── core/
│   │   ├── protocol.py   # construção de pacotes + checksums (lógica pura)
│   │   └── device.py     # comunicação hidraw (I/O)
│   ├── colors.py         # cores nomeadas + paleta da GUI
│   ├── cli.py            # interface de linha de comando
│   └── gui.py            # interface gráfica (tkinter)
├── tests/                # byte-match contra as capturas (pytest)
├── docs/PROTOCOL.md      # a engenharia reversa
└── .claude/skills/       # fluxo de trabalho (Claude Code)
```

## Como funciona

Cada comando é um **HID Feature Report de 17 bytes** enviado à interface de
configuração do mouse. A estrutura do pacote, os registradores e os dois níveis
de checksum estão em [`docs/PROTOCOL.md`](docs/PROTOCOL.md).

## Desenvolvimento

Convenções (commits, branches, PRs, testes) no [**CLAUDE.md**](CLAUDE.md).
Rodar os testes:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

## Roadmap

1. ✅ Cor e liga/desliga do LED (GUI + CLI, dongle e cabo)
2. Brilho e efeitos do LED (bytes `96 FF` do registrador `0xA0`)
3. DPI e polling rate
4. Remapeamento de botões e macros
5. Empacotar (`.desktop` / PyInstaller) e portar a GUI pra outros sistemas

## Licença

GPL v3 (a confirmar).
