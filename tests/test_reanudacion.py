"""Reanudación de corridas: estado en run.json, interrupciones y entrypoints (Ola 1,
D3 y D14; auditoría 2026-09-03, A9; spec 2026-10-04 §7)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fakes import ScriptedProvider, fetch_disponible, fetch_no_disponible
from hitl_helpers import correr_hasta

from revisia.agent_driver import run_review_with_agent
from revisia.agents.fulltext import FullText
from revisia.config import load_protocol
from revisia.llm.base import LLMRequest
from revisia.llm.preflight import PreflightError
from revisia.orchestration import pipeline as pipeline_mod
from revisia.orchestration.flow import resume_review
from revisia.orchestration.hitl import DecisionFileError
from revisia.orchestration.journal import JournalError
from revisia.orchestration.pipeline import run_pipeline
from revisia.orchestration.run_context import RunContext, RunInterrupted
from revisia.orchestration.snapshot import read_run_info
from revisia.provenance.runmeta import sha256_text
from revisia.schemas.artifacts import JournalEntry
from revisia.schemas.records import SearchRecord

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "demo-mini-review"


def _busqueda(query: str, n: int) -> list[SearchRecord]:
    return [
        SearchRecord(
            record_id="rec-1",
            title="LLM screening for systematic reviews",
            abstract="We evaluate LLM screening.",
            source_db="OpenAlex",
        ),
        SearchRecord(
            record_id="rec-2",
            title="Active learning with ASReview",
            abstract="Active learning reduces workload.",
            source_db="OpenAlex",
        ),
    ][:n]


def test_resume_toma_el_slug_de_run_json(tmp_path: Path) -> None:
    protocol = load_protocol(EXAMPLE)  # el demo no declara `slug`
    ctx = RunContext(protocol.slug, tmp_path, "T")
    assert run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda).status == "paused"

    result = resume_review(ctx.run_dir)

    assert (result.status, result.stage, result.run_dir) == ("paused", "screening_ta", ctx.run_dir)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["demo-mini-review-T"]
    info = read_run_info(ctx.run_dir)
    assert info.slug == "demo-mini-review"
    assert len(info.resumes) == 1


def test_estado_de_la_corrida_en_run_json(tmp_path: Path) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)
    info = read_run_info(ctx.run_dir)
    assert (info.status, info.stage) == ("paused", "screening_ta")

    run_pipeline(
        protocol, EXAMPLE, ctx, auto_approve=True, search_fn=_busqueda, fetch_fn=fetch_disponible
    )
    info = read_run_info(ctx.run_dir)
    assert (info.status, info.stage) == ("completed", None)


def test_interrupcion_queda_en_run_json_y_se_relanza(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proveedor = ScriptedProvider(fail_at=1)
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: proveedor)
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")

    with pytest.raises(RunInterrupted) as exc:
        run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)

    assert exc.value.stage == "screening_ta"
    assert isinstance(exc.value.__cause__, RuntimeError)
    assert f"revisia run --resume {ctx.run_dir}" in str(exc.value)
    info = read_run_info(ctx.run_dir)
    assert (info.status, info.stage) == ("interrupted", "screening_ta")
    (interrupcion,) = info.interruptions
    assert interrupcion.stage == "screening_ta"
    assert interrupcion.error == "RuntimeError: 429 Too Many Requests"


def test_preflight_al_empezar_no_crea_nada(tmp_path: Path) -> None:
    protocol = load_protocol(EXAMPLE)
    sin_proveedor = protocol.model_copy(update={"llm": {}, "ensemble_llm": {}})
    ctx = RunContext(protocol.slug, tmp_path, "T")
    with pytest.raises(PreflightError, match="screening_ft"):
        run_pipeline(sin_proveedor, EXAMPLE, ctx, search_fn=_busqueda)
    assert list(ctx.run_dir.iterdir()) == []  # ni run.json ni instantánea


def test_agent_driver_reanuda_con_run_dir(tmp_path: Path) -> None:
    def callback(req, schema):  # el demo usa `fake`: el callback no se llega a usar
        raise AssertionError("no debería llamarse")

    pausa = run_review_with_agent(
        EXAMPLE,
        callback,
        timestamp="T",
        runs_root=tmp_path,
        auto_approve=False,
        search_fn=_busqueda,
    )
    assert pausa.status == "paused"
    completa = run_review_with_agent(
        None, callback, run_dir=pausa.run_dir, auto_approve=True, fetch_fn=fetch_disponible
    )
    assert (completa.status, completa.run_dir) == ("completed", pausa.run_dir)


def _diario(ctx: RunContext, relpath: str) -> list[JournalEntry]:
    path = ctx.run_dir / relpath
    if not path.exists():
        return []
    return [JournalEntry.model_validate_json(x) for x in path.read_text("utf-8").splitlines()]


def test_429_a_mitad_del_cribado_conserva_diario_y_reanuda(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A9: un 429 en cualquier registro perdía la etapa entera. Dos miembros por
    # registro: la llamada 3 es la del primer miembro sobre rec-2.
    proveedor = ScriptedProvider(fail_at=3)
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: proveedor)
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")

    with pytest.raises(RunInterrupted):
        run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)
    assert [e.record_id for e in _diario(ctx, "03_screening/journal.jsonl")] == ["rec-1"]
    assert len(ctx.llm_calls_path.read_text("utf-8").splitlines()) == 2

    result = resume_review(ctx.run_dir)

    assert (result.status, result.stage) == ("paused", "screening_ta")
    # Cada registro se cribó una vez: rec-1 sale del diario; rec-2, al reanudar.
    assert sum("LLM screening" in p for p in proveedor.prompts) == 2
    assert sum("Active learning" in p for p in proveedor.prompts) == 3  # 1 fallida + 2
    entradas = _diario(ctx, "03_screening/journal.jsonl")
    assert [e.record_id for e in entradas] == ["rec-1", "rec-2"]
    assert [len(e.metas) for e in entradas] == [2, 2]
    assert len(ctx.llm_calls_path.read_text("utf-8").splitlines()) == 4
    info = read_run_info(ctx.run_dir)
    assert (info.status, len(info.interruptions), len(info.resumes)) == ("paused", 1, 1)


# ── Clasificación de excepciones y contabilidad de run.json (revisión de B8) ──


class _ProveedorQueFalla(ScriptedProvider):
    """Proveedor cuya primera llamada lanza ``exc`` (cualquier excepción, también Ctrl+C)."""

    def __init__(self, exc: BaseException) -> None:
        super().__init__()
        self._exc = exc

    def _llamar(self, req: LLMRequest) -> None:
        super()._llamar(req)
        raise self._exc


def _correr_con_fallo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exc: BaseException):
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: _ProveedorQueFalla(exc))
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    return ctx, lambda: run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)


def _run_json_bloqueado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simula run.json bloqueado (p. ej. por un antivirus en Windows) tras la instantánea."""

    def _bloqueado(*_args, **_kwargs):
        raise PermissionError("run.json bloqueado")

    monkeypatch.setattr(pipeline_mod, "write_run_info", _bloqueado)


def test_run_json_bloqueado_no_tapa_el_error_del_proveedor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # I1: la contabilidad de run.json corre dentro del `except`; si falla, el 429
    # salía como PermissionError y el CLI (rc 3) no lo reconocía.
    _, correr = _correr_con_fallo(tmp_path, monkeypatch, RuntimeError("429 Too Many Requests"))
    _run_json_bloqueado(monkeypatch)

    with pytest.raises(RunInterrupted) as exc:
        correr()

    assert isinstance(exc.value.__cause__, RuntimeError)
    assert exc.value.error == "RuntimeError: 429 Too Many Requests"
    assert exc.value.stage == "screening_ta"


def test_run_json_bloqueado_no_tapa_el_ctrl_c(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, correr = _correr_con_fallo(tmp_path, monkeypatch, KeyboardInterrupt())
    _run_json_bloqueado(monkeypatch)

    with pytest.raises(KeyboardInterrupt):
        correr()


def test_ctrl_c_queda_registrado_y_se_relanza_tal_cual(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, correr = _correr_con_fallo(tmp_path, monkeypatch, KeyboardInterrupt())

    with pytest.raises(KeyboardInterrupt):
        correr()

    info = read_run_info(ctx.run_dir)
    assert (info.status, info.stage) == ("interrupted", "screening_ta")
    (interrupcion,) = info.interruptions
    assert (interrupcion.stage, interrupcion.error) == ("screening_ta", "KeyboardInterrupt")


def test_el_error_interrumpido_no_deja_secretos_en_run_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = RuntimeError("fallo https://api.example/v1?q=x&api_key=SECRETO&token=OTRO")
    ctx, correr = _correr_con_fallo(tmp_path, monkeypatch, error)

    with pytest.raises(RunInterrupted) as exc:
        correr()

    crudo = (ctx.run_dir / "run.json").read_text(encoding="utf-8")
    assert "SECRETO" not in crudo and "OTRO" not in crudo
    assert "SECRETO" not in str(exc.value) and "OTRO" not in str(exc.value)
    assert "api_key=<redacted>" in read_run_info(ctx.run_dir).interruptions[0].error


def test_el_error_interrumpido_se_recorta_a_mil_caracteres(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, correr = _correr_con_fallo(tmp_path, monkeypatch, RuntimeError("x" * 5000))

    with pytest.raises(RunInterrupted) as exc:
        correr()

    (interrupcion,) = read_run_info(ctx.run_dir).interruptions
    assert interrupcion.error.startswith("RuntimeError: xxx")
    assert len(interrupcion.error) == 1000
    assert exc.value.error == interrupcion.error


def test_decision_malformada_al_reanudar_conserva_la_pausa(tmp_path: Path) -> None:
    # I2: `ensure_snapshot` deja `running`; un decision.yml mal escrito (error de
    # configuración) no debe dejar run.json en `running`/None ni perder la pausa.
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    assert run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda).status == "paused"
    (ctx.run_dir / "screening_ta" / "decision.yml").write_text("approved: [\n", encoding="utf-8")

    with pytest.raises(DecisionFileError):
        resume_review(ctx.run_dir)

    info = read_run_info(ctx.run_dir)
    assert (info.status, info.stage) == ("paused", "screening_ta")
    assert info.interruptions == []  # no fue una caída: el usuario corrige el fichero


def test_decision_malformada_en_corrida_nueva_queda_interrumpida_sin_caida(
    tmp_path: Path,
) -> None:
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    (ctx.run_dir / "screening_ta").mkdir()
    (ctx.run_dir / "screening_ta" / "decision.yml").write_text("approved: [\n", encoding="utf-8")

    with pytest.raises(DecisionFileError):
        run_pipeline(protocol, EXAMPLE, ctx, search_fn=_busqueda)

    info = read_run_info(ctx.run_dir)
    assert (info.status, info.stage) == ("interrupted", "screening_ta")
    assert info.interruptions == []


def test_recuperacion_en_diario_y_texto_en_cache(tmp_path: Path) -> None:
    descargas: list[str] = []

    def fetch(record: SearchRecord):
        descargas.append(record.record_id)
        return fetch_disponible(record)

    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    pausa = correr_hasta(
        protocol, EXAMPLE, ctx, search_fn=_busqueda, fetch_fn=fetch, parar_en="screening_ft"
    )
    assert (pausa.status, pausa.stage) == ("paused", "screening_ft")
    assert descargas == ["rec-1", "rec-2"]

    # Reanudar no vuelve a descargar: el resultado sale del diario y el texto, de la caché.
    otra = run_pipeline(protocol, EXAMPLE, RunContext.open(ctx.run_dir), fetch_fn=fetch)
    assert (otra.status, otra.stage) == ("paused", "screening_ft")
    assert descargas == ["rec-1", "rec-2"]
    cache = ctx.run_dir / "04_fulltext" / "texts" / f"{sha256_text('rec-1')[:16]}.txt"
    assert "LLM screening for systematic reviews" in cache.read_text(encoding="utf-8")
    entradas = _diario(ctx, "04_fulltext/retrieval.jsonl")
    assert [(e.record_id, e.metas) for e in entradas] == [("rec-1", []), ("rec-2", [])]
    # Contrato vigente (revisión de B12): la etapa del diario y la ruta de la caché en
    # retrieval.json.
    assert {e.stage for e in entradas} == {"fulltext_retrieval"}
    retrieval = json.loads((ctx.run_dir / "04_fulltext" / "retrieval.json").read_text("utf-8"))
    assert retrieval[0]["text_file"] == f"04_fulltext/texts/{sha256_text('rec-1')[:16]}.txt"

    # Un texto en caché alterado no se usa en silencio.
    cache.write_text("otro texto", encoding="utf-8")
    with pytest.raises(JournalError, match="caché"):
        run_pipeline(protocol, EXAMPLE, RunContext.open(ctx.run_dir), fetch_fn=fetch)


# ── Recuperación: caché ilegible, fallos transitorios y escritura duradera (revisión de B12) ──


def _pausar_en_ft(tmp_path: Path, fetch) -> tuple:
    """Corre hasta el gate de ``screening_ft`` (el texto completo ya está recuperado)."""
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    pausa = correr_hasta(
        protocol, EXAMPLE, ctx, search_fn=_busqueda, fetch_fn=fetch, parar_en="screening_ft"
    )
    assert (pausa.status, pausa.stage) == ("paused", "screening_ft")
    return protocol, ctx


def _alterar_diario_de_recuperacion(ctx: RunContext, **campos: object) -> None:
    """Cambia campos de la salida de la primera entrada (rec-1) de retrieval.jsonl."""
    ruta = ctx.run_dir / "04_fulltext" / "retrieval.jsonl"
    lineas = ruta.read_text("utf-8").splitlines()
    entrada = json.loads(lineas[0])
    entrada["output"].update(campos)
    lineas[0] = json.dumps(entrada, ensure_ascii=False)
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8", newline="\n")


def _cache_de(ctx: RunContext, record_id: str) -> Path:
    return ctx.run_dir / "04_fulltext" / "texts" / f"{sha256_text(record_id)[:16]}.txt"


@pytest.mark.parametrize(
    ("dano", "mensaje"),
    [
        pytest.param(
            lambda ctx: _cache_de(ctx, "rec-1").unlink(), "falta o es ilegible", id="ausente"
        ),
        pytest.param(
            lambda ctx: _cache_de(ctx, "rec-1").write_bytes(b"\xff\xfe no es UTF-8"),
            "falta o es ilegible",
            id="no_utf8",
        ),
        pytest.param(
            lambda ctx: _alterar_diario_de_recuperacion(ctx, text_file=None),
            "mal formada",
            id="entrada_sin_text_file",
        ),
        pytest.param(
            lambda ctx: _alterar_diario_de_recuperacion(ctx, text_sha256=None),
            "mal formada",
            id="entrada_sin_text_sha256",
        ),
    ],
)
def test_cache_ilegible_es_error_del_diario_y_no_una_caida(
    tmp_path: Path, dano, mensaje: str
) -> None:
    # Un texto en caché ausente (alguien comparte la carpeta sin 04_fulltext/texts/),
    # no UTF-8, o una entrada disponible sin ruta ni hash, salían como RunInterrupted
    # (rc 3): cada reanudación fallaba igual, un bucle sin salida. Es un error del
    # diario (rc 2): no cuenta como caída y deja la pausa tal como estaba.
    protocol, ctx = _pausar_en_ft(tmp_path, fetch_disponible)
    dano(ctx)

    with pytest.raises(JournalError, match=mensaje):
        run_pipeline(protocol, EXAMPLE, RunContext.open(ctx.run_dir), fetch_fn=fetch_disponible)

    info = read_run_info(ctx.run_dir)
    assert (info.status, info.stage) == ("paused", "screening_ft")
    assert info.interruptions == []


@pytest.mark.parametrize("motivo", ["error_http", "sin_httpx"])
def test_fallo_transitorio_de_recuperacion_no_se_congela_y_se_reintenta(
    tmp_path: Path, motivo: str
) -> None:
    # Decisión del controlador (§14 del spec): un error de red no es una respuesta
    # definitiva; se usa en esta invocación y se reintenta al reanudar (A9).
    llamadas: dict[str, int] = {}

    def fetch(record: SearchRecord) -> FullText:
        llamadas[record.record_id] = llamadas.get(record.record_id, 0) + 1
        if record.record_id == "rec-1" and llamadas["rec-1"] == 1:
            return FullText(text="", available=False, reason=motivo, detail="sin red")
        return fetch_disponible(record)

    protocol, ctx = _pausar_en_ft(tmp_path, fetch)
    # Esta invocación lo cuenta como no recuperado, con su motivo, pero no lo congela.
    retrieval = json.loads((ctx.run_dir / "04_fulltext" / "retrieval.json").read_text("utf-8"))
    assert [(r["record_id"], r["available"], r["reason"]) for r in retrieval] == [
        ("rec-1", False, motivo),
        ("rec-2", True, None),
    ]
    assert [e.record_id for e in _diario(ctx, "04_fulltext/retrieval.jsonl")] == ["rec-2"]

    run_pipeline(protocol, EXAMPLE, RunContext.open(ctx.run_dir), fetch_fn=fetch)

    assert llamadas == {"rec-1": 2, "rec-2": 1}  # al reanudar solo se reintenta el que falló
    entradas = _diario(ctx, "04_fulltext/retrieval.jsonl")
    assert [(e.record_id, e.output["available"]) for e in entradas] == [
        ("rec-2", True),
        ("rec-1", True),
    ]  # una sola entrada por registro: la del éxito
    retrieval = json.loads((ctx.run_dir / "04_fulltext" / "retrieval.json").read_text("utf-8"))
    assert [(r["record_id"], r["available"]) for r in retrieval] == [
        ("rec-1", True),
        ("rec-2", True),
    ]
    decisiones = json.loads((ctx.run_dir / "04_fulltext" / "decisions.json").read_text("utf-8"))
    assert [d["fulltext_status"] for d in decisiones] == ["retrieved", "retrieved"]


def _sin_texto(motivo: str):
    def fetch(record: SearchRecord) -> FullText:
        if record.record_id == "rec-1":
            return FullText(text="", available=False, reason=motivo)
        return fetch_disponible(record)

    return fetch


@pytest.mark.parametrize(
    ("fetch_sin_texto", "motivo"),
    [
        pytest.param(fetch_no_disponible(["rec-1"]), "no_disponible", id="no_disponible"),
        pytest.param(_sin_texto("sin_url_oa"), "sin_url_oa", id="sin_url_oa"),
        pytest.param(_sin_texto("texto_vacio"), "texto_vacio", id="texto_vacio"),
    ],
)
def test_no_recuperado_permanente_va_al_diario_y_no_se_vuelve_a_pedir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fetch_sin_texto, motivo: str
) -> None:
    proveedor = ScriptedProvider()
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: proveedor)
    descargas: list[str] = []

    def fetch(record: SearchRecord) -> FullText:
        descargas.append(record.record_id)
        return fetch_sin_texto(record)

    protocol, ctx = _pausar_en_ft(tmp_path, fetch)
    run_pipeline(protocol, EXAMPLE, RunContext.open(ctx.run_dir), fetch_fn=fetch)

    assert descargas == ["rec-1", "rec-2"]  # al reanudar no se pidió nada otra vez
    entradas = _diario(ctx, "04_fulltext/retrieval.jsonl")
    assert [(e.record_id, e.output["available"], e.output["reason"]) for e in entradas] == [
        ("rec-1", False, motivo),
        ("rec-2", True, None),
    ]
    assert {e.stage for e in entradas} == {"fulltext_retrieval"}
    assert [e.metas for e in entradas] == [[], []]
    retrieval = json.loads((ctx.run_dir / "04_fulltext" / "retrieval.json").read_text("utf-8"))
    assert [(r["record_id"], r["text_file"] is None) for r in retrieval] == [
        ("rec-1", True),
        ("rec-2", False),
    ]
    # El informe no recuperado nunca llega a la IA de texto completo (PRISMA estricto, D2).
    prompts_ft = [p for p in proveedor.prompts if "Texto completo de prueba" in p]
    assert prompts_ft  # rec-2 sí se criba (en la corrida y al reanudar)
    assert all("Active learning" in p and "LLM screening" not in p for p in prompts_ft)


def test_la_cache_se_escribe_en_un_temporal_se_fuerza_a_disco_y_se_renombra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Sin esto, tras un corte de luz el diario (que sí hace fsync) puede sobrevivir y
    # el texto no: la reanudación declararía la corrida no fiable.
    eventos: list[tuple] = []
    fsync_real, replace_real = os.fsync, os.replace

    def fsync(fd: int) -> None:
        eventos.append(("fsync", os.fstat(fd).st_size))
        fsync_real(fd)

    def replace(src, dst) -> None:
        origen, destino = Path(src), Path(dst)
        eventos.append(("replace", origen, destino, origen.read_bytes()))
        replace_real(src, dst)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)

    _, ctx = _pausar_en_ft(tmp_path, fetch_disponible)

    reemplazos = [i for i, e in enumerate(eventos) if e[0] == "replace" and "texts" in e[2].parts]
    assert len(reemplazos) == 2  # rec-1 y rec-2
    for i in reemplazos:
        _, origen, destino, contenido = eventos[i]
        assert origen != destino and origen.parent == destino.parent
        assert eventos[i - 1] == ("fsync", len(contenido))  # fsync del temporal justo antes
        assert destino.read_bytes() == contenido
    assert list((ctx.run_dir / "04_fulltext" / "texts").glob("*.tmp")) == []


def _llamadas(proveedor: ScriptedProvider, marca: str) -> int:
    """Llamadas del proveedor cuyo prompt contiene ``marca`` (identifica la etapa)."""
    return sum(marca in p for p in proveedor.prompts)


def test_cribado_ft_en_diario_no_se_repite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proveedor = ScriptedProvider()
    monkeypatch.setattr(pipeline_mod, "build_provider", lambda _cfg: proveedor)
    protocol = load_protocol(EXAMPLE)
    ctx = RunContext(protocol.slug, tmp_path, "T")
    correr_hasta(
        protocol,
        EXAMPLE,
        ctx,
        search_fn=_busqueda,
        fetch_fn=fetch_disponible,
        parar_en="screening_ft",
    )
    assert _llamadas(proveedor, "TEXTO COMPLETO") == 2

    run_pipeline(protocol, EXAMPLE, RunContext.open(ctx.run_dir), fetch_fn=fetch_disponible)

    assert _llamadas(proveedor, "TEXTO COMPLETO") == 2
    entradas = _diario(ctx, "04_fulltext/journal.jsonl")
    assert [(e.record_id, len(e.metas)) for e in entradas] == [("rec-1", 1), ("rec-2", 1)]
    assert all(e.output["fulltext_status"] == "retrieved" for e in entradas)
    assert all(e.output["final_label"] is None for e in entradas)  # sin campos humanos
