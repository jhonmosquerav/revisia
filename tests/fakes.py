"""Dobles de prueba compartidos por las pistas de la Ola 1 (spec 2026-10-04 §4.5).

``FakeProvider`` vota siempre ``include`` (el primer valor del ``Literal``,
``fake.py:30``): con él no hay exclusiones, ni gold de dos clases, ni
``unclear`` (hallazgo 5 de la exploración de la Ola 1). ``ScriptedProvider``
etiqueta según palabras clave del prompt, puede simular un 429 en la llamada
``k`` y cuenta las llamadas, para que los tests de reanudación (A9) puedan
afirmar que nada se llama dos veces.

Ola 2 (spec 2026-10-18 §4.4): ``fail_at`` lanza ``TransientCallError`` y
``fail_deterministic_at`` lanza ``DeterministicCallError`` (D9); ``judge``
guioniza el veredicto de grounding por palabra clave de la afirmación;
``extraccion`` fija el valor de cada campo del formulario; ``rob`` fija el
juicio por dominio (y el global con ``"overall"``).

Los ``fetch_fn`` de prueba sustituyen la recuperación de texto completo, que
en la Ola 1 sigue PRISMA estricto (D2): sin ellos, ningún registro de prueba
tiene texto en abierto y nada llega a extracción.

Uso desde un test (``tests/`` está en ``sys.path`` porque no es un paquete)::

    from fakes import ScriptedProvider, fetch_disponible

    proveedor = ScriptedProvider()
    monkeypatch.setattr(pipeline, "build_provider", lambda cfg: proveedor)
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import TypeVar, get_args

import yaml
from pydantic import BaseModel

from revisia.agents.extraccion import _ExtractionOut
from revisia.agents.fulltext import FullText
from revisia.agents.rob import _RoBOut
from revisia.llm.base import DeterministicCallError, LLMRequest, LLMResponse, TransientCallError
from revisia.llm.providers.fake import _fabricate_model
from revisia.provenance.runmeta import RunMeta, sha256_text
from revisia.rag.grounding import GroundingVerdict
from revisia.schemas.records import SearchRecord
from revisia.schemas.screening import ScreeningLabel

SchemaT = TypeVar("SchemaT", bound=BaseModel)

# Palabra clave (sin distinguir mayúsculas) → etiqueta. Gana la primera que
# aparezca en el prompt, en este orden; sin coincidencia, ``include``.
PALABRAS_POR_DEFECTO: dict[str, ScreeningLabel] = {
    "irrelevante": "exclude",
    "dudoso": "unclear",
}

_ETIQUETAS = frozenset({"include", "exclude", "unclear"})


class ScriptedProvider:
    """Proveedor con guion: etiqueta por palabra clave, cuenta llamadas y falla a pedido.

    Conserva ``provider="fake"`` y ``deterministic=True`` en cada ``RunMeta``,
    como ``FakeProvider``: el auditor exime de sus heurísticas temporales solo
    a ese proveedor (spec §9.3, ``timing``).

    Attributes:
        model: modelo que declara en ``RunMeta.model``.
        fail_at: número de llamada (1, 2, …) que lanza
            ``TransientCallError("429 Too Many Requests")`` (subclase de
            ``RuntimeError``) en vez de responder; las demás responden con
            normalidad. ``None`` = nunca falla; un valor menor que 1 es un error
            (``ValueError``).
        fail_deterministic_at: número de llamada (desde 1) que lanza
            ``DeterministicCallError`` (400, contexto excedido, ``attempts=1``).
            Puede convivir con ``fail_at`` en llamadas distintas; si coinciden,
            gana el determinista.
        judge: palabra clave → ``grounded`` para ``GroundingVerdict``. Se busca
            (sin distinguir mayúsculas) en la afirmación del prompt; gana la
            primera del dict que aparezca; sin coincidencia, ``grounded=False``
            (fail-closed). ``None`` = veredicto fabricado (``grounded=True``).
        extraccion: clave del formulario → valor (``None`` = no encontrado), en
            el orden del dict. ``None`` = salida fabricada.
        rob: dominio → juicio, más ``"overall"`` para el global (por defecto
            ``unclear``). Indexado por nombre de dominio: forma interina que E1.6
            cambiará a id (§19 fila 10). ``None`` = salida fabricada.
        calls: llamadas recibidas (``complete`` + ``structured``), incluida la
            que falla.
        prompts: prompt de cada llamada, en orden (para afirmar qué se cribó).
        sintesis: texto que devuelve ``complete`` (la síntesis narrativa); por
            defecto, uno sin citas. Con citas ``[id]`` el verificador tiene algo
            que comprobar (y con un id que no está en el corpus, marca).
    """

    name = "fake"

    def __init__(
        self,
        model: str = "fake-guion",
        *,
        fail_at: int | None = None,
        fail_deterministic_at: int | None = None,
        judge: Mapping[str, bool] | None = None,
        extraccion: Mapping[str, str | None] | None = None,
        rob: Mapping[str, str] | None = None,
        palabras: Mapping[str, ScreeningLabel] | None = None,
        criterio_exclusion: str = "fuera de alcance",
        sintesis: str | None = None,
    ) -> None:
        # Las llamadas se cuentan desde 1: con `fail_at=0` (o negativo) el 429 nunca
        # se dispararía y el test pasaría sin haber probado la reanudación.
        if fail_at is not None and fail_at < 1:
            raise ValueError(f"fail_at cuenta llamadas desde 1; recibido {fail_at}")
        if fail_deterministic_at is not None and fail_deterministic_at < 1:
            raise ValueError(
                f"fail_deterministic_at cuenta llamadas desde 1; recibido {fail_deterministic_at}"
            )
        self.model = model
        self.fail_deterministic_at = fail_deterministic_at
        self.judge = None if judge is None else dict(judge)
        self.extraccion = None if extraccion is None else dict(extraccion)
        self.rob = None if rob is None else dict(rob)
        self.sintesis = sintesis
        self.fail_at = fail_at
        self.palabras: dict[str, ScreeningLabel] = dict(
            PALABRAS_POR_DEFECTO if palabras is None else palabras
        )
        self.criterio_exclusion = criterio_exclusion
        self.calls = 0
        self.prompts: list[str] = []

    def label_for(self, prompt: str) -> ScreeningLabel:
        """Etiqueta que el guion asigna a ``prompt``."""
        texto = prompt.lower()
        for palabra, etiqueta in self.palabras.items():
            if palabra.lower() in texto:
                return etiqueta
        return "include"

    def _llamar(self, req: LLMRequest) -> None:
        self.calls += 1
        self.prompts.append(req.prompt)
        if self.fail_deterministic_at is not None and self.calls == self.fail_deterministic_at:
            raise DeterministicCallError(
                "400 Bad Request: el contexto excede el límite del modelo", attempts=1
            )
        if self.fail_at is not None and self.calls == self.fail_at:
            raise TransientCallError("429 Too Many Requests")

    def _meta(self, req: LLMRequest, text: str) -> RunMeta:
        return RunMeta(
            provider=self.name,
            model=self.model,
            seed=req.seed,
            temperature=req.temperature,
            top_p=req.top_p,
            prompt_sha256=sha256_text(f"{req.system or ''}\n{req.prompt}"),
            response_sha256=sha256_text(text),
            deterministic=True,
        )

    def complete(self, req: LLMRequest) -> LLMResponse:
        self._llamar(req)
        # Por defecto sin tokens "[...]": el verificador no debe confundirlos con citas.
        text = self.sintesis or "Síntesis de prueba (proveedor con guion · sin contenido real)."
        return LLMResponse(text=text, meta=self._meta(req, text))

    def _veredicto(self, prompt: str) -> dict:
        """Veredicto de grounding guionizado por palabra clave (fail-closed)."""
        assert self.judge is not None
        inicio = prompt.find("AFIRMACIÓN:")
        fin = prompt.find("TEXTO FUENTE CITADO:")
        if inicio != -1 and fin > inicio:
            afirmacion = prompt[inicio + len("AFIRMACIÓN:") : fin]
            fuente = prompt[fin + len("TEXTO FUENTE CITADO:") :]
        else:
            afirmacion, fuente = prompt, prompt
        texto = afirmacion.lower()
        for palabra, grounded in self.judge.items():
            if palabra.lower() in texto:
                cita = None
                if grounded:
                    cita = fuente.strip().split("\n\n")[0].split(". ")[0].strip() or None
                return {"grounded": grounded, "support_quote": cita, "reason": f"guion: {palabra}"}
        return {"grounded": False, "support_quote": None, "reason": "guion: sin palabra clave"}

    def structured(self, req: LLMRequest, schema: type[SchemaT]) -> tuple[SchemaT, RunMeta]:
        self._llamar(req)
        if schema is GroundingVerdict and self.judge is not None:
            obj = schema.model_validate(self._veredicto(req.prompt))
            return obj, self._meta(req, obj.model_dump_json())
        if schema is _ExtractionOut and self.extraccion is not None:
            campos = [
                {"key": k, "value": v, "source_quote": v, "found": v is not None, "confidence": 0.9}
                for k, v in self.extraccion.items()
            ]
            obj = schema.model_validate({"fields": campos})
            return obj, self._meta(req, obj.model_dump_json())
        if schema is _RoBOut and self.rob is not None:
            dominios = [
                {"domain": d, "judgment": j, "rationale": f"guion: {j}", "support_quote": None}
                for d, j in self.rob.items()
                if d != "overall"
            ]
            obj = schema.model_validate(
                {"domains": dominios, "overall": self.rob.get("overall", "unclear")}
            )
            return obj, self._meta(req, obj.model_dump_json())
        data = _fabricate_model(schema).model_dump()
        fields = schema.model_fields
        if "label" in fields and set(get_args(fields["label"].annotation)) >= _ETIQUETAS:
            label = self.label_for(req.prompt)
            data["label"] = label
            if "confidence" in fields:
                data["confidence"] = 0.9
            if "rationale" in fields:
                data["rationale"] = f"guion: {label}"
            if "criteria_violated" in fields:
                data["criteria_violated"] = [self.criterio_exclusion] if label == "exclude" else []
        obj = schema.model_validate(data)
        return obj, self._meta(req, obj.model_dump_json())


def fetch_disponible(record: SearchRecord) -> FullText:
    """``fetch_fn`` de prueba: todo registro tiene texto completo en abierto."""
    text = f"Texto completo de prueba de «{record.title}». {record.abstract or ''}".strip()
    return FullText(
        text=text,
        available=True,
        source_url=f"https://example.org/texto/{sha256_text(record.record_id)[:16]}",
    )


def fetch_no_disponible(ids: Iterable[str]) -> Callable[[SearchRecord], FullText]:
    """``fetch_fn`` de prueba: los ``ids`` dados no se recuperan; el resto sí.

    El ``FullText`` de un no recuperado lleva el abstract en ``text`` y
    ``available=False``, como el fallback real de
    :func:`revisia.agents.fulltext.fetch_fulltext`.
    """
    if isinstance(ids, str):
        # `frozenset("10.1/b")` troceaba el id en caracteres y el registro salía disponible.
        raise TypeError(f"ids debe ser una colección de ids (p. ej. ['{ids}']), no un str")
    sin_texto = frozenset(ids)

    def _fetch(record: SearchRecord) -> FullText:
        if record.record_id in sin_texto:
            return FullText(text=record.abstract or "", available=False)
        return fetch_disponible(record)

    return _fetch


def fetch_disponible_largo(n_chars: int) -> Callable[[SearchRecord], FullText]:
    """``fetch_fn`` de prueba: texto completo de **exactamente** ``n_chars`` caracteres.

    Párrafos numerados unidos con ``"\n\n"`` y cortados a ``n_chars``. Sirve a los
    tests de recorte (D20) y de ventana por párrafos (D15).
    """
    if n_chars < 1:
        raise ValueError(f"n_chars debe ser >= 1; recibido {n_chars}")

    def _fetch(record: SearchRecord) -> FullText:
        partes: list[str] = []
        total = 0
        k = 1
        while total < n_chars:
            parrafo = (
                f"Párrafo {k} del texto completo de prueba de «{record.title}»: "
                f"{k * 7} participantes."
            )
            partes.append(parrafo)
            total += len(parrafo) + (2 if partes[:-1] else 0)  # separador solo entre párrafos
            k += 1
        return FullText(
            text="\n\n".join(partes)[:n_chars],
            available=True,
            source_url=f"https://example.org/texto/{sha256_text(record.record_id)[:16]}",
        )

    return _fetch


_RIS_OFFLINE = """TY  - JOUR
TI  - LLM screening for systematic reviews
AU  - Prueba, Ana
PY  - 2021
AB  - Estudio de prueba sobre cribado asistido por modelos de lenguaje.
ER  -

TY  - JOUR
TI  - Active learning with ASReview
AU  - Prueba, Beto
PY  - 2021
AB  - Estudio de prueba sobre aprendizaje activo para el cribado.
ER  -
"""


def protocolo_offline(dest: Path, *, provider: str = "fake", model: str = "fake-1") -> Path:
    """Copia el protocolo de demo a ``dest`` listo para correr sin red (auditoría 2026-09-03, A13).

    ``databases: [Scopus]`` es una base de importación manual: ``search_stage`` no llama a ningún
    backend y solo lee ``imported/corpus.ris`` (dos registros sin DOI, URL ni PMCID). Sin DOI ni
    ``oa_url``, ``fetch_fulltext`` no toca la red (``sin_url_oa``), así que ``run_review`` y el CLI
    completan la corrida sin dobles inyectados y con 0 incluidos. Cambia ``provider``/``model`` de
    todas las entradas de ``llm`` y ``ensemble_llm``.
    """
    raiz = Path(__file__).resolve().parent.parent
    shutil.copytree(raiz / "examples" / "demo-mini-review", dest)
    shutil.rmtree(dest / "search_strings", ignore_errors=True)
    (dest / "effects.yml").unlink(missing_ok=True)
    (dest / "imported").mkdir(exist_ok=True)
    (dest / "imported" / "corpus.ris").write_text(_RIS_OFFLINE, encoding="utf-8")
    ruta = dest / "protocol.yml"
    raw = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    raw["databases"] = ["Scopus"]
    entradas = list(raw.get("llm", {}).values())
    for miembros in raw.get("ensemble_llm", {}).values():
        entradas.extend(miembros)
    for entrada in entradas:
        entrada["provider"] = provider
        entrada["model"] = model
    ruta.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return dest


class _RespuestaJSON:
    """Respuesta mínima de ``httpx``: ``raise_for_status()`` y ``json()``."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class ClienteJSON:
    """Sustituto de ``httpx.Client`` (context manager) que sirve un payload fijo.

    Es el ``_FakeClient`` de ``test_search_multibase.py`` hecho compartible
    (auditoría 2026-09-03, M18). Guarda ``last_url`` y ``last_params``.
    """

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.last_url: str | None = None
        self.last_params: dict | None = None

    def __enter__(self) -> ClienteJSON:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def get(self, url: str, params: dict | None = None) -> _RespuestaJSON:
        self.last_url = url
        self.last_params = params
        return _RespuestaJSON(self._payload)
