# Sondas

Una sonda es un script que registra lo que una herramienta externa ofrece de verdad en la máquina
del arquitecto, para fijar contratos con evidencia y no con suposiciones (D11).

## `sonda_claude_cli.py`

Registra la versión del CLI `claude`, qué banderas anuncia su `--help` y dónde llega el objeto
validado de `--json-schema` (con y sin `--max-turns 1`, si el CLI lo anuncia). No puede correr
dentro de una sesión anidada de Claude Code (401): se ejecuta desde un terminal con sesión válida.

```bash
npm i -g @anthropic-ai/claude-code@latest
python scripts/sonda_claude_cli.py            # escribe docs/superpowers/sondas/<fecha>-claude-cli.md
```

Opciones: `--cli`, `--model`, `--out`, `--timeout`. Siempre sale con código 0; los fallos quedan
dentro del informe.

## Qué se redacta

Tokens de entorno (`CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`),
claves `sk-...` y cabeceras `Bearer ...` se sustituyen por `<redacted>`.

## Después

El arquitecto commitea el informe. PR-A lo lee para fijar `MIN_CLI_VERSION` y el contrato de
`--json-schema`.
