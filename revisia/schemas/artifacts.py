"""Contratos de los artefactos de una corrida (Ola 1 · PR-0).

Un solo módulo con los modelos y constantes que comparten la pista del
pipeline (PR-A a PR-D) y la del auditor (PR-E): ambas importan de aquí en vez
de duplicar nombres de fichero, etapas o campos. La auditoría 2026-09-03 (C3,
A11) mostró que un auditor que "sabe" los artefactos por su cuenta deja de
detectar incoherencias en cuanto el pipeline cambia; con un contrato único,
productor y verificador no se pueden contradecir en silencio.

La especificación completa (qué fichero existe cuándo y qué relaciones deben
cumplirse entre ellos) está en
``docs/superpowers/specs/2026-10-04-ola-1-remediacion-design.md`` §4.

Convenciones (spec §4.1): horas ISO-8601 UTC con zona (``utc_now_iso``), rutas
relativas con ``/``, ``schema_version`` en todo JSON nuevo. Ningún
``record_id`` se usa como nombre de fichero (los DOI llevan ``/``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from revisia.provenance.runmeta import RunMeta, utc_now_iso

# Versión del esquema de todos los artefactos JSON nuevos de la Ola 1. Sube
# solo con un cambio incompatible de alguno de estos modelos.
ARTIFACT_SCHEMA_VERSION: int = 1

# Estados de una corrida en ``run.json`` (spec §4.3). ``paused`` sigue saliendo
# con rc 0; ``interrupted`` es un error a mitad de corrida que se reanuda (D14).
RunStatus = Literal["running", "paused", "rejected", "completed", "interrupted"]

# Etapas que llaman a un LLM y, por tanto, etiquetan cada ``LLMCall``.
LLMStage = Literal[
    "screening_ta",
    "screening_ft",
    "extraccion",
    "extraccion_2",
    "rob",
    "sintesis",
    "verificacion",
]

# Etapas con diario por registro (D3): las de LLM más la recuperación de texto
# completo, que no llama a ningún LLM pero sí a la red.
JournalStage = Literal[
    "screening_ta",
    "fulltext_retrieval",
    "screening_ft",
    "extraccion",
    "extraccion_2",
    "rob",
    "sintesis",
    "verificacion",
]

# Motivo por el que no se recuperó un texto completo (auditoría 2026-09-03,
# M11: hasta la Ola 1 el fallo no se guardaba). ``no_disponible`` es el motivo
# genérico cuando quien recupera no da uno (p. ej. un ``fetch_fn`` inyectado).
FulltextReason = Literal["sin_url_oa", "sin_httpx", "error_http", "texto_vacio", "no_disponible"]

# Motivos de fallo que NO se escriben en el diario de la recuperación: un error de red
# (``error_http``) o la falta de ``httpx`` (``sin_httpx``) no es una respuesta definitiva sobre
# el informe, así que congelarla haría que reanudar nunca lo reintentara y que "informes
# no recuperados" contara fallos que ya se habrían resuelto (auditoría 2026-09-03, A9:
# un fallo transitorio se resuelve reanudando). Se usan en esta invocación y en
# ``retrieval.json`` y se piden otra vez al reanudar. Los motivos permanentes
# (``sin_url_oa``, ``texto_vacio``, ``no_disponible``) y los éxitos sí se escriben. Lo comparten
# el pipeline (qué no se escribe en el diario) y el gate de texto completo (qué avisa de que
# se reintentará al reanudar).
TRANSIENT_FULLTEXT_REASONS: frozenset[FulltextReason] = frozenset({"error_http", "sin_httpx"})

# Ruta (relativa al directorio de la corrida) del diario de cada etapa (§4.2).
JOURNAL_PATHS: dict[str, str] = {
    "screening_ta": "03_screening/journal.jsonl",
    "fulltext_retrieval": "04_fulltext/retrieval.jsonl",
    "screening_ft": "04_fulltext/journal.jsonl",
    "extraccion": "05_extraction/journal.jsonl",
    "extraccion_2": "05_extraction/journal_2.jsonl",
    "rob": "07_rob/journal.jsonl",
    "sintesis": "06_synthesis/journal.jsonl",
    "verificacion": "06_synthesis/verification.jsonl",
}

# Etapas con checkpoint humano, en el orden canónico de ``config.STAGES``. Los
# ficheros del gate viven en ``<run_dir>/<gate>/`` (review_request.yml,
# decision.template.yml, decision.yml).
GATED_STAGES: tuple[str, ...] = ("screening_ta", "screening_ft", "extraccion", "rob", "reporte")

SearchEntryKind = Literal["database", "manual_import", "injected"]
SearchEntryStatus = Literal["ok", "failed", "manual_only", "unknown"]
QueryOrigin = Literal["file", "question_fallback"]
ReasonSource = Literal["human", "ai"]
GateAction = Literal["approve", "reject", "auto-proceed"]


class RunInterruption(BaseModel):
    """Una interrupción registrada en ``run.json`` (error redactado)."""

    utc: str
    stage: str | None = None
    error: str


class RunInfo(BaseModel):
    """``run.json``: identidad, parámetros, huellas, historia y estado de la corrida.

    Es lo primero que se escribe (spec §4.2). ``mailto_set`` registra si hubo
    correo, nunca el correo. ``protocol_sha256`` va sobre ``00_protocol/``
    (texto con CRLF convertido a LF) y ``prompt_sha256`` sobre
    ``revisia/prompts/`` con claves ``"<agente>/v1.md"``.
    """

    schema_version: int = ARTIFACT_SCHEMA_VERSION
    slug: str
    timestamp: str
    started_utc: str
    engine_version: str
    python_version: str
    max_results: int
    mailto_set: bool
    protocol_sha256: dict[str, str] = Field(default_factory=dict)
    prompt_sha256: dict[str, str] = Field(default_factory=dict)
    resumes: list[str] = Field(default_factory=list)
    interruptions: list[RunInterruption] = Field(default_factory=list)
    status: RunStatus = "running"
    stage: str | None = None
    updated_utc: str = Field(default_factory=utc_now_iso)


class LLMCall(RunMeta):
    """Una línea de ``llm_calls.jsonl``: el ``RunMeta`` más su contexto.

    Append-only, en orden de finalización de la llamada. Una caída puede dejar
    llamadas huérfanas (reales, sin decisión en el diario): son válidas.
    ``record_id`` vale ``"sintesis"``/``"verificacion"`` en las etapas globales
    y ``role`` es ``"member:<i>"`` en el ensemble de T/A.
    """

    stage: LLMStage
    record_id: str | None = None
    role: str | None = None

    @classmethod
    def from_meta(
        cls,
        meta: RunMeta,
        *,
        stage: LLMStage,
        record_id: str | None = None,
        role: str | None = None,
    ) -> LLMCall:
        """Etiqueta un ``RunMeta`` con su etapa, registro y rol."""
        data = meta.model_dump()
        data.update(stage=stage, record_id=record_id, role=role)
        return cls.model_validate(data)


class JournalEntry(BaseModel):
    """Una línea del diario de una etapa (D3).

    La clave es ``(record_id, input_sha256)``. Una entrada cuyo
    ``input_sha256`` ya no corresponde a las entradas vigentes queda obsoleta,
    pero sigue siendo válida. ``output`` es el resultado serializado de la etapa
    (``ScreeningDecision`` sin campos humanos, ``RetrievalOutcome``,
    ``ExtractionRecord``, ``RoBAssessment``, ``{"narrative": ...}`` o
    ``VerificationReport``).
    """

    schema_version: int = ARTIFACT_SCHEMA_VERSION
    stage: JournalStage
    record_id: str
    input_sha256: str
    output: dict
    metas: list[LLMCall] = Field(default_factory=list)
    timestamp_utc: str = Field(default_factory=utc_now_iso)


class SearchLogEntry(BaseModel):
    """Una entrada de ``01_search/log.json``: una base, un fichero importado o
    la búsqueda inyectada (PRISMA-S 1/8/13; auditoría 2026-09-03, M12)."""

    database: str
    db_key: str
    kind: SearchEntryKind
    declared: bool
    backend: str | None = None
    status: SearchEntryStatus
    source_db: list[str] = Field(default_factory=list)
    query: str | None = None
    query_origin: QueryOrigin | None = None
    query_file: str | None = None
    query_sha256: str | None = None
    max_results: int | None = None
    started_utc: str | None = None
    finished_utc: str | None = None
    n_returned: int = 0
    error: str | None = None
    file_sha256: str | None = None


class SearchLog(BaseModel):
    """``01_search/log.json``: su existencia marca la búsqueda como completa."""

    schema_version: int = ARTIFACT_SCHEMA_VERSION
    started_utc: str
    finished_utc: str
    max_results: int
    mailto_set: bool
    entries: list[SearchLogEntry] = Field(default_factory=list)


class DedupDuplicate(BaseModel):
    """Un registro descartado por duplicado y el que se conservó en su lugar."""

    record_id: str
    source_db: str
    kept_record_id: str
    key: str


class DedupRename(BaseModel):
    """Un ``record_id`` repetido entre los conservados, renombrado (``<id>#2``)."""

    from_id: str
    to_id: str


class DedupReport(BaseModel):
    """``02_dedup/dedup.json``: trazabilidad completa de la deduplicación."""

    schema_version: int = ARTIFACT_SCHEMA_VERSION
    n_in: int
    n_out: int
    duplicates: list[DedupDuplicate] = Field(default_factory=list)
    renamed: list[DedupRename] = Field(default_factory=list)


class RetrievalOutcome(BaseModel):
    """Resultado de recuperar el texto completo de un registro (D2, M11).

    ``reason`` es nulo si y solo si ``available``: un fallo sin motivo, o un
    éxito con motivo, no es un resultado válido.
    """

    available: bool
    source_url: str | None = None
    reason: FulltextReason | None = None
    detail: str | None = None
    n_chars: int = 0
    text_sha256: str | None = None
    text_file: str | None = None

    @model_validator(mode="after")
    def _motivo_solo_si_falla(self) -> RetrievalOutcome:
        if self.available and self.reason is not None:
            raise ValueError("un texto completo recuperado no lleva motivo de fallo")
        if not self.available and self.reason is None:
            raise ValueError("un texto completo no recuperado necesita un motivo")
        return self


class ExcludedReport(BaseModel):
    """Un informe excluido en elegibilidad, con su razón (PRISMA 2020, 16b)."""

    record_id: str
    title: str
    year: int | None = None
    doi: str | None = None
    reason: str
    reason_source: ReasonSource


class GateSummary(BaseModel):
    """Decisión efectiva de un gate, reducida del ledger por ``summarize_gates``.

    La decisión efectiva de una etapa es su **última** entrada ``approve``,
    ``reject`` o ``auto-proceed`` (D14: se puede reanudar tras un rechazo y
    todas quedan registradas). Lo usan el pipeline (checklist trAIce y
    ``metodologia.md``, M13) y el auditor, para que no se contradigan (D12).

    Attributes:
        stage: etapa del gate.
        action: ``approve`` | ``reject`` | ``auto-proceed``.
        actor: quién decidió (``human:<n>``, ``auto-approve (demo)``,
            ``agent:<etapa>``).
        autonomy: autonomía con la que se aplicó el gate.
        request_sha256: hash de la solicitud a la que responde (``None`` en
            entradas anteriores a la Ola 1).
        decision_sha256: hash de la ``decision.yml`` aplicada (``None`` en
            ``auto-proceed`` y en entradas anteriores a la Ola 1).
        n_labels: entradas ``label`` de esa etapa con el mismo
            ``decision_sha256`` (contadas en el ledger, no tomadas del
            ``detail``: así el auditor puede contrastarlas).
        n_flag_reviews: ídem con ``flag_review`` (citas adjudicadas, D8).
        forced_human: el gate exigió humano por ``hallucination_flagged`` (M5).
        timestamp_utc: hora de la entrada efectiva.
    """

    stage: str
    action: GateAction
    actor: str
    autonomy: str
    request_sha256: str | None = None
    decision_sha256: str | None = None
    n_labels: int = 0
    n_flag_reviews: int = 0
    forced_human: bool = False
    timestamp_utc: str
