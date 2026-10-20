"""Sonda del CLI `claude`: registra qué ofrece de verdad la versión instalada (D11; spec §4.4).

Por qué una sonda y no una suposición: PR-A fija `MIN_CLI_VERSION` y el contrato de
`--json-schema` (dónde llega el objeto validado, cómo se comporta `--max-turns`). Eso depende de
la versión instalada en la máquina del arquitecto (el shim de npm no anuncia lo mismo que el CLI
completo), y una sesión anidada de Claude Code no puede hacer la llamada real (401). Así que el
arquitecto la ejecuta desde un terminal con sesión válida y commitea el informe redactado.

Uso (stdlib pura; compatible con Python 3.11; no importa `revisia`)::

    python scripts/sonda_claude_cli.py [--cli claude] [--model sonnet] \\
        [--out docs/superpowers/sondas/<YYYY-MM-DD>-claude-cli.md] [--timeout 120]

Siempre termina con código 0 y escribe el informe: los fallos (CLI ausente, tiempo agotado, JSON
inválido, sin `--safe-mode`) quedan documentados dentro del informe. Sin `--bare`: rompe la
autenticación por suscripción (§2).
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SCHEMA: dict = {
    "type": "object",
    "properties": {"respuesta": {"type": "string"}, "numero": {"type": "integer"}},
    "required": ["respuesta", "numero"],
    "additionalProperties": False,
}
PROMPT = "Responde exactamente con respuesta='hola' y numero=7."
FLAGS = (
    "--safe-mode",
    "--tools",
    "--json-schema",
    "--max-turns",
    "--max-budget-usd",
    "--bare",
    "--strict-mcp-config",
    "--no-session-persistence",
)
SECRET_ENV = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
_TIPOS = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "object": dict}


def detect_flags(help_text: str) -> dict[str, bool]:
    """Una bandera está anunciada si aparece como palabra completa en el `--help`."""
    return {
        f: re.search(rf"(?<![\w-]){re.escape(f)}(?![\w-])", help_text) is not None for f in FLAGS
    }


def parse_version(text: str) -> str | None:
    m = re.search(r"\d+\.\d+\.\d+", text)
    return m.group(0) if m else None


def _tipo_ok(valor: object, tipo: str | None) -> bool:
    if tipo is None:
        return True
    if tipo in ("integer", "number") and isinstance(valor, bool):
        return False
    esperado = _TIPOS.get(tipo)
    return True if esperado is None else isinstance(valor, esperado)


def locate_structured(data: object, schema: dict) -> dict:
    """Busca el objeto validado en `result` y luego en el resto de claves de primer nivel."""
    if not isinstance(data, dict):
        return {"where": None, "valid": False}
    required = list(schema.get("required", []))
    props = schema.get("properties", {})

    def _candidato(valor: object) -> dict | None:
        if isinstance(valor, str):
            try:
                valor = json.loads(valor)
            except ValueError:
                return None
        if isinstance(valor, dict) and all(k in valor for k in required):
            return valor
        return None

    claves = (["result"] if "result" in data else []) + [k for k in data if k != "result"]
    for clave in claves:
        objeto = _candidato(data[clave])
        if objeto is not None:
            valido = all(_tipo_ok(objeto[k], props.get(k, {}).get("type")) for k in required)
            return {"where": clave, "valid": valido}
    return {"where": None, "valid": False}


def result_meta(data: object) -> dict:
    if not isinstance(data, dict):
        return {"subtype": None, "total_cost_usd": None, "is_error": None}
    return {
        "subtype": data.get("subtype"),
        "total_cost_usd": data.get("total_cost_usd"),
        "is_error": data.get("is_error"),
    }


def _home_corto(home: str) -> str | None:
    """Forma corta 8.3 de Windows del home (el nombre de usuario recortado a `XXXXXX~1`)."""
    if sys.platform != "win32":
        return None
    import ctypes

    buf = ctypes.create_unicode_buffer(1024)
    n = ctypes.windll.kernel32.GetShortPathNameW(home, buf, 1024)  # type: ignore[attr-defined]
    return buf.value if 0 < n < 1024 else None


def _identidad_local() -> tuple[set[str], set[str]]:
    """Rutas del home (largas y cortas) y nombre de usuario; nunca lanza (rc 0 siempre)."""
    homes: set[str] = set()
    try:
        home = os.path.expanduser("~")
        if home and home != "~":
            homes.add(home)
            corto = _home_corto(home)
            if corto:
                homes.add(corto)
    except Exception:  # noqa: BLE001
        pass
    variantes: set[str] = set()
    for h in homes:
        variantes |= {h, h.replace("\\", "/"), h.replace("\\", "\\\\")}
    usuarios: set[str] = set()
    try:
        usuario = getpass.getuser()
        if len(usuario) >= 3:
            usuarios.add(usuario)
    except Exception:  # noqa: BLE001
        pass
    return variantes, usuarios


def redact(text: str, secrets: Iterable[str | None]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "<redacted>")
    text = re.sub(r"sk-[A-Za-z0-9_-]{16,}", "<redacted>", text)
    text = re.sub(r"Bearer \S+", "Bearer <redacted>", text)
    # El informe se commitea en un repo público: fuera la ruta del usuario, su nombre y su correo.
    variantes, usuarios = _identidad_local()
    for h in sorted(variantes, key=len, reverse=True):
        if h and h not in ("~", "/"):
            text = text.replace(h, "~")
    for u in usuarios:
        text = text.replace(u, "<usuario>")
    return re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "<correo>", text)


def _fmt_cmd(command: list[str]) -> str:
    partes = []
    # Se muestra el nombre base del ejecutable: la ruta resuelta lleva el usuario del equipo.
    for i, a in enumerate(command):
        if i == 0:
            a = re.split(r"[\\/]", a)[-1]
        if len(a) > 300:
            a = "<schema>"
        partes.append(f'"{a}"' if (a == "" or " " in a) else a)
    return " ".join(partes)


def _parse(stdout: str) -> object:
    try:
        return json.loads(stdout)
    except ValueError:
        return None


def _fence(texto: str, lang: str = "text") -> str:
    return f"```{lang}\n{texto.rstrip()}\n```"


def _donde(data: object, located: dict, meta: dict) -> list[str]:
    claves = ", ".join(data) if isinstance(data, dict) and data else "ninguna"
    coste = meta["total_cost_usd"] if meta["total_cost_usd"] is not None else "ninguno"
    return [
        f"- clave: `{located['where']}`" if located["where"] else "- clave: ninguna",
        f"- válido: {'sí' if located['valid'] else 'no'}",
        f"- claves de primer nivel: {claves}",
        f"- subtype: `{meta['subtype']}`" if meta["subtype"] else "- subtype: ninguno",
        f"- total_cost_usd: {coste}",
    ]


def _bloque_llamada(llamada: dict, nivel: str) -> list[str]:
    stdout = llamada["stdout"]
    data = _parse(stdout)
    return [
        f"{nivel} Comando",
        _fence(_fmt_cmd(llamada["command"])),
        f"{nivel} Código de salida",
        str(llamada["returncode"]),
        f"{nivel} stdout crudo",
        _fence(stdout, "json" if data is not None else "text"),
        f"{nivel} stderr",
        _fence(llamada["stderr"]),
    ]


def render_report(
    *,
    cli: str,
    version: str | None,
    flags: dict[str, bool],
    help_text: str,
    command: list[str],
    returncode: int | None,
    stdout: str,
    stderr: str,
    located: dict,
    meta: dict,
    second: dict | None,
    date: str,
) -> str:
    primera = {"command": command, "returncode": returncode, "stdout": stdout, "stderr": stderr}
    out = [f"# Sonda del CLI `{cli}` ({date})", "", "## Versión", version or "desconocida", ""]
    out += ["## Flags anunciados", "| flag | anunciado |", "|---|---|"]
    out += [f"| `{f}` | {'sí' if ok else 'no'} |" for f, ok in flags.items()]
    out += ["", "## --help crudo", _fence(help_text), ""]
    out += _bloque_llamada(primera, "##")
    out += ["", "## Dónde viene el objeto validado", *_donde(_parse(stdout), located, meta), ""]
    out += ["## Segunda llamada: --max-turns 1"]
    if second is None:
        out += ["no se lanzó: el CLI no anuncia --max-turns"]
    else:
        out += _bloque_llamada(second, "###")
        out += [""]
        out += _donde(_parse(second["stdout"]), second["located"], second["meta"])
    out += ["", "## Para PR-A"]
    if flags["--safe-mode"] and flags["--tools"] and flags["--json-schema"]:
        out += [f"MIN_CLI_VERSION candidata: {version or 'desconocida'}"]
    else:
        out += [
            "esta versión no sirve: actualiza el CLI (npm i -g @anthropic-ai/claude-code@latest)"
        ]
    if second is None:
        out += ["MAX_TURNS con --json-schema: no anunciado"]
    elif second["returncode"] == 0 and second["located"]["valid"]:
        out += ["MAX_TURNS con --json-schema: compatible"]
    else:
        out += [f"MAX_TURNS con --json-schema: incompatible (subtype {second['meta']['subtype']})"]
    return "\n".join(out) + "\n"


def _run(command: list[str], *, timeout: int, cwd: str | None, stdin: str | None) -> dict:
    """Ejecuta sin lanzar: cualquier fallo del proceso queda como texto en `stderr`."""
    try:
        proc = subprocess.run(
            command,
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=cwd,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        # `TimeoutExpired` repite el comando completo (con la ruta del usuario): no se copia.
        detalle = (
            f"tiempo agotado tras {timeout} s"
            if isinstance(exc, subprocess.TimeoutExpired)
            else str(exc)
        )
        return {
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {detalle}",
        }
    return {
        "command": command,
        "returncode": proc.returncode,
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
    }


def _llamada_p(cli: str, model: str, extra: list[str], timeout: int, cwd: str) -> dict:
    command = [
        cli,
        "-p",
        "--output-format",
        "json",
        "--model",
        model,
        "--no-session-persistence",
        "--tools",
        "",
        "--strict-mcp-config",
        "--json-schema",
        json.dumps(SCHEMA),
        *extra,
    ]
    r = _run(command, timeout=timeout, cwd=cwd, stdin=PROMPT)
    data = _parse(r["stdout"])
    r["located"] = locate_structured(data, SCHEMA)
    r["meta"] = result_meta(data)
    return r


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sonda del CLI claude (D11).")
    ap.add_argument("--cli", default="claude")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--out", default=None)
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args(argv)

    fecha = datetime.now(UTC).date().isoformat()
    out = (
        Path(args.out)
        if args.out
        else REPO_ROOT / "docs" / "superpowers" / "sondas" / f"{fecha}-claude-cli.md"
    )
    cli = shutil.which(args.cli) or args.cli
    version_run = _run([cli, "--version"], timeout=args.timeout, cwd=None, stdin=None)
    help_run = _run([cli, "--help"], timeout=args.timeout, cwd=None, stdin=None)
    help_text = help_run["stdout"] or help_run["stderr"]
    flags = detect_flags(help_text)
    version = parse_version(version_run["stdout"] or version_run["stderr"])

    extra = ["--safe-mode"] if flags["--safe-mode"] else []
    with tempfile.TemporaryDirectory() as cwd:
        primera = _llamada_p(cli, args.model, extra, args.timeout, cwd)
        second = None
        if flags["--max-turns"]:
            second = _llamada_p(cli, args.model, [*extra, "--max-turns", "1"], args.timeout, cwd)

    informe = render_report(
        cli=args.cli,
        version=version,
        flags=flags,
        help_text=help_text,
        command=primera["command"],
        returncode=primera["returncode"],
        stdout=primera["stdout"],
        stderr=primera["stderr"],
        located=primera["located"],
        meta=primera["meta"],
        second=second,
        date=fecha,
    )
    informe = informe.replace(cli, re.split(r"[\\/]", cli)[-1])
    informe = redact(informe, [os.environ.get(v, "") for v in SECRET_ENV])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(informe, encoding="utf-8", newline="\n")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
