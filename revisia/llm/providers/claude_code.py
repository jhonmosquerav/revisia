"""Driver de referencia: subagentes/sesión de Claude Code (Hito H5).

Es el **proveedor por defecto del autor** y una implementación más del contrato
:class:`revisia.llm.base.LLMProvider`. Habla con Claude Code en **modo
headless** (``claude -p --output-format json``), de modo que el razonamiento
consume la suscripción de Claude Code (Max), no la API de Anthropic con key:
cero costo marginal por token. El prompt viaja por *stdin* y la salida se lee
como un único objeto JSON.

Sigue siendo un proveedor más: el registro solo importa este módulo si la
config pide ``provider: claude_code``; por eso el núcleo arranca sin Claude
Code instalado y el repo conserva su capa provider-agnostic (Gemini / OpenAI /
Anthropic / local / ``fake``).

Honestidad de procedencia: el CLI headless no expone ``seed`` ni
``temperature`` estables, así que ``RunMeta.deterministic`` es ``False`` y la
reproducibilidad queda "a nivel decisión" (ledger), no a nivel token.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import replace
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from revisia.llm.base import LLMRequest, LLMResponse
from revisia.provenance.runmeta import RunMeta, sha256_text

SchemaT = TypeVar("SchemaT", bound=BaseModel)

# Tiempo máximo por llamada al CLI (segundos). El screening masivo de una SR
# puede tardar; un tope evita colgar el pipeline si el CLI no responde.
_DEFAULT_TIMEOUT = 600
# Reintentos de structured() ante JSON inválido (el CLI no fuerza tool-use).
_DEFAULT_RETRIES = 2
# Variable que el CLI lee para autenticar con la suscripción (Max/Pro) en modo
# headless. Se acuña una vez con `claude setup-token`. Es la forma soportada de
# "operar con la cuenta de Claude Code" sin sesión interactiva ni API key.
_OAUTH_TOKEN_VAR = "CLAUDE_CODE_OAUTH_TOKEN"
# Overrides de endpoint que, si vienen heredados (p. ej. una sesión de desarrollo
# que apunta a un base-url distinto), pueden hacer que un token de producción se
# envíe al lugar equivocado y devuelva 401. Se limpian solo si el usuario lo pide.
_ENDPOINT_OVERRIDE_VARS = ("ANTHROPIC_BASE_URL", "USE_STAGING_OAUTH", "USE_LOCAL_OAUTH")
# Flag (env) para limpiar esos overrides en el subproceso cuando hay token propio.
_CLEAN_ENV_FLAG = "REVISIA_CLAUDE_CODE_CLEAN_ENV"


class ClaudeCodeProvider:
    """Proveedor LLM respaldado por Claude Code en modo headless (``claude -p``)."""

    name = "claude_code"

    def __init__(
        self,
        model: str,
        *,
        cli: str = "claude",
        timeout: int = _DEFAULT_TIMEOUT,
        max_retries: int = _DEFAULT_RETRIES,
        clean_env: bool | None = None,
    ) -> None:
        self.model = model
        self.cli = cli
        self.timeout = timeout
        self.max_retries = max_retries
        # Si no se especifica, se toma del flag de entorno (opt-in).
        if clean_env is None:
            clean_env = os.environ.get(_CLEAN_ENV_FLAG, "").lower() in ("1", "true", "yes")
        self.clean_env = clean_env

    # ── infraestructura ────────────────────────────────────────────────
    def _subprocess_env(self) -> dict[str, str]:
        """Entorno para el subproceso ``claude``.

        Hereda el entorno del proceso (donde vive ``CLAUDE_CODE_OAUTH_TOKEN`` si
        el usuario acuñó un token con ``claude setup-token``, que el CLI usa para
        autenticar con la suscripción Max/Pro). Si ``clean_env`` está activo y hay
        token propio, elimina overrides de endpoint heredados para no enviar el
        token a un base-url ajeno.
        """
        env = dict(os.environ)
        if self.clean_env and env.get(_OAUTH_TOKEN_VAR):
            for var in _ENDPOINT_OVERRIDE_VARS:
                env.pop(var, None)
        return env

    def _resolve_cli(self) -> str:
        """Resuelve el ejecutable del CLI respetando PATHEXT.

        En Windows ``claude`` se instala como shim ``claude.CMD``; ``CreateProcess``
        no resuelve la extensión a partir del nombre pelado, así que
        ``subprocess.run(["claude", ...])`` lanza ``FileNotFoundError``. ``shutil.which``
        devuelve la ruta completa con extensión (``.CMD`` en Windows, sin extensión en
        POSIX), que subprocess sí ejecuta. Si no se encuentra, se devuelve el nombre
        original para que ``_invoke`` emita el ``RuntimeError`` accionable de siempre.
        """
        return shutil.which(self.cli) or self.cli

    def _command(self, req: LLMRequest) -> list[str]:
        cmd = [
            self._resolve_cli(),
            "-p",
            "--output-format",
            "json",
            "--model",
            self.model,
            "--no-session-persistence",  # no guarda la sesión en disco
            "--allowedTools",
            "",  # razonamiento puro: sin herramientas (ni prompts de permiso)
        ]
        if req.system:
            cmd += ["--append-system-prompt", req.system]
        return cmd

    def _invoke(self, req: LLMRequest) -> tuple[str, dict]:
        """Corre ``claude -p`` con el prompt por stdin y devuelve (texto, usage).

        Raises:
            RuntimeError: si el CLI no está instalado, falla, agota el timeout
                o devuelve un error de API. Siempre con mensaje accionable.
        """
        try:
            proc = subprocess.run(
                self._command(req),
                input=req.prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout,
                env=self._subprocess_env(),
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"No se encontró el CLI {self.cli!r}. El proveedor 'claude_code' "
                "requiere Claude Code instalado y con sesión iniciada (Max). "
                "Instálalo o cambia el proveedor en protocol.yml."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Claude Code no respondió en {self.timeout}s. Sube el timeout o "
                "revisa la conectividad."
            ) from exc

        if proc.returncode != 0:
            output = (proc.stderr or proc.stdout or "").strip()
            self._raise_if_auth_error(output)
            raise RuntimeError(f"Claude Code salió con código {proc.returncode}: {output[:500]}")

        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Salida de Claude Code no es JSON válido: {proc.stdout[:300]!r}"
            ) from exc

        if data.get("is_error"):
            result = str(data.get("result", ""))
            self._raise_if_auth_error(result)
            raise RuntimeError(f"Claude Code devolvió un error: {result}")

        return data.get("result", ""), data.get("usage") or {}

    @staticmethod
    def _raise_if_auth_error(output: str) -> None:
        """Convierte un fallo de autenticación headless en un error accionable.

        ``claude -p`` headless no puede heredar la auth del host: si el token en
        disco está vencido/sin refresh (o se corre dentro de otra sesión de
        Claude Code que refresca el token en memoria), la API devuelve 401. El
        mensaje genérico no orienta; este lo hace explícito y propone remedios.
        """
        low = output.lower()
        if "401" in output or "authenticat" in low or "invalid authentication" in low:
            raise RuntimeError(
                "Claude Code no pudo autenticar en modo headless (401). El driver "
                "'claude_code' necesita una sesión Max delegable a un subproceso: "
                "genera un token headless con `claude setup-token` (expórtalo como "
                "CLAUDE_CODE_OAUTH_TOKEN), o usa otro proveedor (gemini/openai/"
                "anthropic) en protocol.yml. Si conduces revisia dentro de una "
                "sesión de agente, usa el proveedor 'agent' (sin auth headless)."
            )

    def _meta(self, req: LLMRequest, text: str, usage: dict) -> RunMeta:
        return RunMeta(
            provider=self.name,
            model=self.model,
            model_version=None,  # el CLI no reporta la versión exacta del modelo
            seed=req.seed,
            temperature=req.temperature,
            top_p=req.top_p,
            prompt_sha256=sha256_text(f"{req.system or ''}\n{req.prompt}"),
            response_sha256=sha256_text(text),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            deterministic=False,  # headless no garantiza seed/temperature estables
        )

    @staticmethod
    def _extract_json(text: str) -> str:
        """Aísla el objeto JSON de una respuesta que puede traer texto/fences."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            # quita ```json ... ``` o ``` ... ```
            cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned
            if cleaned.endswith("```"):
                cleaned = cleaned[: -len("```")]
            cleaned = cleaned.strip()
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return cleaned[start : end + 1]
        return cleaned

    # ── contrato LLMProvider ───────────────────────────────────────────
    def complete(self, req: LLMRequest) -> LLMResponse:
        text, usage = self._invoke(req)
        return LLMResponse(text=text, meta=self._meta(req, text, usage))

    def structured(self, req: LLMRequest, schema: type[SchemaT]) -> tuple[SchemaT, RunMeta]:
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        instruction = (
            "\n\nResponde ÚNICAMENTE con un objeto JSON válido que cumpla este "
            "JSON Schema. Sin texto adicional, sin explicación, sin markdown ni "
            f"```:\n{schema_json}"
        )
        last_error = ""
        for _ in range(self.max_retries + 1):
            prompt = req.prompt + instruction
            if last_error:
                prompt += (
                    f"\n\nTu respuesta anterior no validó ({last_error}). "
                    "Corrige y devuelve solo JSON."
                )
            text, usage = self._invoke(replace(req, prompt=prompt))
            try:
                obj = schema.model_validate_json(self._extract_json(text))
            except (ValidationError, ValueError) as exc:
                last_error = str(exc)[:200]
                continue
            return obj, self._meta(req, obj.model_dump_json(), usage)
        raise RuntimeError(
            f"Claude Code no produjo JSON válido para {schema.__name__} tras "
            f"{self.max_retries + 1} intentos. Último error: {last_error}"
        )
