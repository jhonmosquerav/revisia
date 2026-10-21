"""Proveedores API con clientes falsos (auditoría 2026-09-03, M20): sin SDK ni red."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from revisia.llm.base import LLMProvider, LLMRequest
from revisia.llm.providers.anthropic_api import AnthropicProvider
from revisia.llm.providers.gemini import GeminiProvider
from revisia.llm.providers.local_openai import LocalOpenAIProvider
from revisia.llm.providers.openai_api import OpenAIProvider
from revisia.llm.providers.openai_compat import OpenRouterProvider, ZaiProvider
from revisia.provenance.runmeta import sha256_text


class Salida(BaseModel):
    etiqueta: str
    n: int


REQ = LLMRequest(prompt="¿Incluir?", system="Eres un cribador.", temperature=0.3, seed=42)
V1 = sha256_text("Eres un cribador.\n¿Incluir?")  # fórmula de la 0.8: system + "\n" + prompt


# ── Gemini ───────────────────────────────────────────────────────────────────


class _Gemini:
    def __init__(self) -> None:
        self.llamadas: list[dict[str, Any]] = []
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, **kw: Any) -> Any:
        self.llamadas.append(kw)
        con_schema = "response_schema" in str(kw.get("config"))
        parsed = Salida(etiqueta="include", n=1) if con_schema else None
        return SimpleNamespace(
            text='{"etiqueta": "include", "n": 1}',
            parsed=parsed,
            model_version="gemini-3.5-flash-lite-001",
            usage_metadata=SimpleNamespace(prompt_token_count=11, candidates_token_count=5),
        )


@pytest.fixture
def gemini(monkeypatch: pytest.MonkeyPatch) -> tuple[GeminiProvider, _Gemini]:
    cliente = _Gemini()
    proveedor = GeminiProvider("gemini-3.5-flash-lite")
    monkeypatch.setattr(proveedor, "_client", lambda: cliente)
    monkeypatch.setattr(
        proveedor,
        "_config",
        lambda req, **extra: {"temperature": req.temperature, "seed": req.seed, **extra},
    )
    return proveedor, cliente


def test_gemini_complete_y_structured_con_cliente_falso(gemini) -> None:
    proveedor, cliente = gemini
    assert isinstance(proveedor, LLMProvider)
    resp = proveedor.complete(REQ)
    assert resp.text.startswith("{") and resp.meta.provider == "gemini"
    assert (resp.meta.model_version, resp.meta.input_tokens, resp.meta.output_tokens) == (
        "gemini-3.5-flash-lite-001",
        11,
        5,
    )
    assert resp.meta.prompt_sha256 == V1 and resp.meta.deterministic is False
    obj, meta = proveedor.structured(REQ, Salida)
    assert obj == Salida(etiqueta="include", n=1) and meta.prompt_sha256 == V1
    assert cliente.llamadas[1]["config"]["response_schema"] is Salida
    assert (meta.seed, meta.temperature) == (42, 0.3)  # lo pedido, como la v1


@pytest.mark.xfail(strict=True, reason="PR-A (spec §5.2): lo aplicado y model_source=backend")
def test_gemini_runmeta_v2_aplicado(gemini) -> None:
    # `backend_version` no se afirma aquí: sin el SDK instalado (matriz del CI) PR-A lo deja
    # en None; PR-A lo prueba con `importlib.metadata.version` sustituido.
    proveedor, _ = gemini
    meta = proveedor.complete(REQ).meta
    assert (meta.seed_applied, meta.temperature_applied) == (42, 0.3)
    assert meta.model_source == "backend"


# ── OpenAI y compatibles ─────────────────────────────────────────────────────


class _OpenAI:
    def __init__(
        self, *, parsed: bool = True, content: str | None = '{"etiqueta": "include", "n": 1}'
    ) -> None:
        self.llamadas: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.beta = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(parse=self._parse))
        )
        self._parsed, self._content = parsed, content

    def _resp(self, message: Any) -> Any:
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            model="gpt-4o-mini-2024-07-18",
            usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3),
        )

    def _create(self, **kw: Any) -> Any:
        self.llamadas.append(kw)
        return self._resp(SimpleNamespace(content=self._content))

    def _parse(self, **kw: Any) -> Any:
        self.llamadas.append(kw)
        parsed = Salida(etiqueta="include", n=1) if self._parsed else None
        refusal = "no" if not self._parsed else None
        return self._resp(SimpleNamespace(parsed=parsed, content=self._content, refusal=refusal))


def test_openai_complete_y_structured_pasan_los_parametros(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cliente = _OpenAI()
    proveedor = OpenAIProvider("gpt-4o-mini")
    monkeypatch.setattr(proveedor, "_client", lambda: cliente)
    resp = proveedor.complete(REQ)
    assert resp.meta.model_version == "gpt-4o-mini-2024-07-18" and resp.meta.prompt_sha256 == V1
    assert (resp.meta.input_tokens, resp.meta.output_tokens) == (7, 3)
    assert cliente.llamadas[0]["seed"] == 42 and cliente.llamadas[0]["temperature"] == 0.3
    assert cliente.llamadas[0]["messages"][0] == {"role": "system", "content": "Eres un cribador."}
    obj, meta = proveedor.structured(REQ, Salida)
    assert obj.etiqueta == "include"
    assert cliente.llamadas[1]["response_format"] is Salida and meta.prompt_sha256 == V1


def test_openai_rehusar_structured_es_error_accionable(monkeypatch: pytest.MonkeyPatch) -> None:
    proveedor = OpenAIProvider("gpt-4o-mini")
    monkeypatch.setattr(proveedor, "_client", lambda: _OpenAI(parsed=False))
    with pytest.raises(RuntimeError, match="salida estructurada"):
        proveedor.structured(REQ, Salida)


def test_local_openai_inyecta_el_schema_en_el_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    cliente = _OpenAI()
    proveedor = LocalOpenAIProvider("llama")
    monkeypatch.setattr(proveedor, "_client", lambda: cliente)
    obj, meta = proveedor.structured(REQ, Salida)
    enviado = cliente.llamadas[0]["messages"][-1]["content"]
    assert obj.n == 1 and enviado.startswith("¿Incluir?") and '"etiqueta"' in enviado
    assert cliente.llamadas[0]["response_format"] == {"type": "json_object"}
    assert meta.prompt_sha256 == V1  # la 0.8 hashea el prompt ORIGINAL, no el enviado (A7)


@pytest.mark.xfail(
    strict=True, reason="PR-A (spec §5.2, A7): prompt_sha256 del texto enviado con el schema"
)
def test_local_openai_prompt_sha256_es_del_texto_enviado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cliente = _OpenAI()
    proveedor = LocalOpenAIProvider("llama")
    monkeypatch.setattr(proveedor, "_client", lambda: cliente)
    _, meta = proveedor.structured(REQ, Salida)
    enviado = cliente.llamadas[0]["messages"][-1]["content"]
    assert meta.prompt_sha256 == sha256_text(f"Eres un cribador.\n{enviado}")
    assert meta.schema_sha256 is None


@pytest.mark.parametrize(
    ("clase", "variable"),
    [(ZaiProvider, "ZAI_API_KEY"), (OpenRouterProvider, "OPENROUTER_API_KEY")],
)
def test_gateways_exigen_su_key_y_usan_su_base_url(
    monkeypatch: pytest.MonkeyPatch, clase, variable: str
) -> None:
    monkeypatch.delenv(variable, raising=False)
    with pytest.raises(RuntimeError, match=variable):
        clase("m").complete(REQ)
    monkeypatch.setenv(variable, "k")
    proveedor = clase("m")
    assert proveedor.base_url and proveedor.base_url.startswith("https://")
    cliente = _OpenAI()
    monkeypatch.setattr(proveedor, "_client", lambda: cliente)
    assert proveedor.complete(REQ).meta.provider == clase.name


# ── Anthropic ────────────────────────────────────────────────────────────────


class _Anthropic:
    def __init__(self, *, tool_use: bool = True) -> None:
        self.llamadas: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)
        self._tool_use = tool_use

    def _create(self, **kw: Any) -> Any:
        self.llamadas.append(kw)
        bloques = [SimpleNamespace(type="text", text="hola ")]
        if "tools" in kw and self._tool_use:
            bloques = [SimpleNamespace(type="tool_use", input={"etiqueta": "include", "n": 1})]
        return SimpleNamespace(
            content=bloques,
            model="claude-sonnet-5-5-20260601",
            usage=SimpleNamespace(input_tokens=9, output_tokens=2),
        )


def test_anthropic_complete_y_structured_por_tool_use(monkeypatch: pytest.MonkeyPatch) -> None:
    cliente = _Anthropic()
    proveedor = AnthropicProvider("claude-sonnet-5-5")
    monkeypatch.setattr(proveedor, "_client", lambda: cliente)
    resp = proveedor.complete(REQ)
    assert resp.text == "hola " and resp.meta.model_version == "claude-sonnet-5-5-20260601"
    assert (
        cliente.llamadas[0]["system"] == "Eres un cribador." and "seed" not in cliente.llamadas[0]
    )
    obj, meta = proveedor.structured(REQ, Salida)
    assert obj.n == 1 and cliente.llamadas[1]["tool_choice"] == {"type": "tool", "name": "Salida"}
    assert meta.prompt_sha256 == V1 and (meta.seed, meta.temperature) == (42, 0.3)


def test_anthropic_sin_tool_use_es_error_accionable(monkeypatch: pytest.MonkeyPatch) -> None:
    proveedor = AnthropicProvider("claude-sonnet-5-5")
    monkeypatch.setattr(proveedor, "_client", lambda: _Anthropic(tool_use=False))
    with pytest.raises(RuntimeError, match="tool_use"):
        proveedor.structured(REQ, Salida)


@pytest.mark.xfail(
    strict=True,
    reason="PR-A (spec §5.2, A6): seed_applied None, temperature aplicada, model_source=backend",
)
def test_anthropic_runmeta_v2_aplicado(monkeypatch: pytest.MonkeyPatch) -> None:
    proveedor = AnthropicProvider("claude-sonnet-5-5")
    monkeypatch.setattr(proveedor, "_client", lambda: _Anthropic())
    meta = proveedor.complete(REQ).meta
    assert (meta.seed_applied, meta.temperature_applied, meta.model_source) == (
        None,
        0.3,
        "backend",
    )
    _, meta_structured = proveedor.structured(REQ, Salida)
    assert meta_structured.schema_sha256  # el schema viaja como tool: su hash aparte (A7)
