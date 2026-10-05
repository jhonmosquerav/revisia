"""Checkpoint humano (HITL) reproducible y SIN servidor.

En lugar de depender del pause server de Prefect (que exigiría infraestructura
y rompería el "clónalo y córrelo"), el gate es file-based:

  * Escribe ``<stage>/review_request.yml`` con lo que el humano debe revisar y su
    ``request_sha256`` (hash canónico del contenido), y a su lado
    ``decision.template.yml``, la decisión a medio rellenar.
  * Si existe ``<stage>/decision.yml`` con el ``request_sha256`` de la solicitud
    vigente (o ``--auto-approve``), aplica la decisión y la registra en el ledger
    (validado: ``approved`` booleano estricto; un fichero inválido detiene la
    corrida con un mensaje accionable). Una decisión que responde a otra
    solicitud pausa sin aplicar nada.
  * Si no, devuelve estado ``paused``: el orquestador se detiene e indica al
    humano cómo rellenar la decisión y reanudar.

El ledger manda (Ola 1, spec 2026-10-04 §4.3): registrar es idempotente al
reanudar y, sin ``decision.yml``, la decisión ya registrada para la solicitud
vigente se reutiliza (``decision.yml`` es solo el canal de entrada). Las
decisiones quedan en el ledger → reproducibilidad "a nivel decisión".

Decisión por registro y por cita (Ola 1, PR-D; auditoría 2026-09-03, C1 y M5):
en los gates de cribado el humano etiqueta registros (``records``) según una
``RecordPolicy``; en el gate final, con citas marcadas por el verificador,
adjudica cada una (``flags``) según una ``FlagPolicy``. Cada etiqueta y cada
adjudicación quedan en el ledger, antes del ``approve`` al que pertenecen.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, field_validator

from revisia.orchestration.run_context import RunContext
from revisia.provenance.ledger import (
    AUTO_APPROVE_ACTOR,
    HUMAN_ACTOR_PREFIX,
    DecisionEntry,
    summarize_gates,
)
from revisia.provenance.runmeta import canonical_sha256
from revisia.schemas.artifacts import ARTIFACT_SCHEMA_VERSION

GateStatus = Literal["approved", "paused", "rejected"]

REQUEST_FILE = "review_request.yml"
TEMPLATE_FILE = "decision.template.yml"
DECISION_FILE = "decision.yml"
# Ids o índices que lista, como mucho, un error de decisión incompleta.
_MAX_LISTED = 20

# Claves que review_gate pone él mismo en la solicitud (``request_sha256`` solo en el
# fichero): un payload que las traiga las pisaría y cambiaría lo que se hashea.
_CLAVES_COMUNES = ("schema_version", "stage", "autonomy", "request_sha256")

# Límites del texto libre de un comentario de la plantilla (título, afirmación, nota…): se
# acota cada campo, no la línea. Así lo estructurado (propuesta, marcas, id citado, motivo
# de la marca) siempre sobrevive a un título de 200 caracteres (revisión de la Tarea 21).
_MAX_TEXTO = 120
_MAX_NOTA = 120
_MAX_PROPUESTA = 40
_MAX_ID_CITADO = 60
# Red de seguridad de la línea entera. Va por encima de la suma de los límites de arriba
# más las partes fijas (peor caso de un registro: ~370), así que no corta nada en la práctica.
_MAX_COMENTARIO = 400
# YAML (PyYAML y libyaml) solo lee como clave implícita ``clave: valor`` hasta 1024
# caracteres, contando las comillas y los escapes. Una más larga va en forma explícita.
_MAX_CLAVE_IMPLICITA = 1000

# Saltos de línea de YAML 1.1 que PyYAML, con ``allow_unicode=True``, escribe CRUDOS en
# estilo plano o con comillas simples. ``safe_load`` pliega el NEL (U+0085) a un
# espacio: la cadena vuelve distinta y el hash ya no se recalcula desde el fichero
# (spec 2026-10-04, relación 15). U+2028/U+2029 sobreviven en PyYAML pero YAML 1.2 no
# los trata como saltos: se escapan para que ningún lector los lea de otra forma.
_SALTOS_NO_FIABLES = frozenset("\x85\u2028\u2029")


class _FielDumper(yaml.SafeDumper):
    """``SafeDumper`` cuyo texto vuelve idéntico con ``yaml.safe_load``."""


def _represent_str(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    # Entre comillas dobles esos caracteres salen escapados (``\x85``, ``\u2028``) y el
    # resto del texto (acentos, ñ…) sigue legible para el humano.
    style = '"' if _SALTOS_NO_FIABLES.intersection(data) else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_FielDumper.add_representer(str, _represent_str)


def dump_yaml(data: dict) -> str:
    """Vuelca ``data`` a YAML de forma que ``yaml.safe_load`` lo devuelva idéntico.

    Es el volcado de todo YAML que el gate escribe para el humano y que se hashea
    (``review_request.yml``): ``yaml.safe_dump`` no lo garantiza para cadenas con
    U+0085, que son mojibake frecuente (un «…» de cp1252 leído como latin-1) y
    llegarán en títulos y rationales (spec 2026-10-04, relación 15).
    """
    return yaml.dump(data, Dumper=_FielDumper, allow_unicode=True, sort_keys=False)


class DecisionFileError(ValueError):
    """``decision.yml`` ilegible o inválido: mensaje accionable, no traceback."""


class RecordLabel(BaseModel):
    """Etiqueta humana de un registro en ``decision.yml`` (``records``; D1, D4).

    ``label: null`` cuenta como "no etiquetado", para que la plantilla pueda
    listar todos los registros. ``reason`` es obligatoria al excluir en FT y al
    rescatar un no recuperado.
    """

    model_config = ConfigDict(extra="forbid")

    label: Literal["include", "exclude"] | None = None
    reason: str | None = None


class FlagReview(BaseModel):
    """Adjudicación humana de una cita marcada por el verificador (``flags``; D8).

    Solo existe el veredicto ``false_positive``: si una marca es una
    alucinación real, el camino es rechazar (``approved: false``).
    ``verdict: null`` cuenta como "sin adjudicar".
    """

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["false_positive"] | None = None
    reason: str | None = None


class HumanDecision(BaseModel):
    """Contenido validado de ``<stage>/decision.yml`` (auditoría 2026-09-03, C1).

    ``request_sha256`` ata la decisión a la solicitud que el humano revisó
    (D4): si la solicitud cambia, una decisión vieja no se aplica.
    ``approved`` es un booleano YAML estricto: la cadena ``"false"`` ya no
    aprueba (``bool("false")`` es ``True``). ``records`` (solo en cribado) y
    ``flags`` (solo en ``reporte`` con citas marcadas) llevan las claves como
    texto: un id ``2019`` sin comillas se lee como número y se convierte. Los
    campos extra se conservan y viajan al ``detail`` del ledger.
    """

    model_config = ConfigDict(extra="allow")

    request_sha256: str
    approved: StrictBool
    actor: str = "human:desconocido"
    reason: str | None = None
    records: dict[str, RecordLabel] = Field(default_factory=dict)
    flags: dict[str, FlagReview] = Field(default_factory=dict)

    @field_validator("records", "flags", mode="before")
    @classmethod
    def _claves_como_texto(cls, value: object) -> object:
        """Convierte a texto las claves escalares (``2019:`` llega como ``2019``).

        Una clave que no es texto ni número (nula, binaria, una lista o un mapa) no
        es un id: se rechaza con un error de validación, que ``_read_decision``
        traduce a ``DecisionFileError``, en vez de volverla un texto sin sentido
        (``str(["a"])``) que luego parecería "un id desconocido".
        """
        if not isinstance(value, dict):
            return value
        for key in value:
            if not isinstance(key, str | int | float | date):
                raise ValueError(
                    f"la clave {key!r} ({type(key).__name__}) no es un id válido: las claves "
                    "son texto o números, no listas, mapas ni nulos"
                )
        return {str(k): v for k, v in value.items()}


@dataclass(frozen=True, slots=True)
class RecordHint:
    """Lo que la plantilla muestra de un registro (en comentarios saneados).

    Attributes:
        record_id: id del registro.
        title: título.
        proposal: etiqueta propuesta por la IA (``None`` si no hay: no recuperado).
        note: resumen de la propuesta (votos, criterio, motivo del no recuperado).
    """

    record_id: str
    title: str
    proposal: str | None
    note: str = ""


@dataclass(frozen=True, slots=True)
class RecordPolicy:
    """Qué se puede y qué se debe etiquetar en un gate de cribado (D1, D2, D9).

    Attributes:
        hints: un ``RecordHint`` por registro de la solicitud (son los ids válidos).
        must_label: ids que hay que etiquetar para aprobar (A0).
        must_resolve: ids ``unclear`` de FT: solo los resuelve un humano.
        rescue_ids: no recuperados; etiquetarlos es un rescate (razón obligatoria).
        reason_on_exclude: excluir exige razón (FT: va a la lista 16b).
    """

    hints: tuple[RecordHint, ...]
    must_label: frozenset[str] = frozenset()
    must_resolve: frozenset[str] = frozenset()
    rescue_ids: frozenset[str] = frozenset()
    reason_on_exclude: bool = False


@dataclass(frozen=True, slots=True)
class FlaggedClaim:
    """Una cita marcada por el verificador (``index`` = posición en ``checks``)."""

    index: int
    cited_id: str | None
    claim: str
    note: str | None = None


@dataclass(frozen=True, slots=True)
class FlagPolicy:
    """Citas marcadas que el humano debe adjudicar para aprobar el reporte (D8)."""

    flagged: tuple[FlaggedClaim, ...]


@dataclass(slots=True)
class GateResult:
    """Resultado de un gate.

    Attributes:
        status: ``approved`` | ``paused`` | ``rejected``.
        message: texto para el humano (pausa: qué revisar y cómo reanudar).
        request_sha256: hash de la solicitud vigente.
        actor: quién decidió (``None`` en una pausa).
        labels: etiquetas explícitas por registro de la decisión aprobada.
        flag_reviews: adjudicaciones de citas marcadas de la decisión aprobada.
    """

    status: GateStatus
    message: str
    request_sha256: str | None = None
    actor: str | None = None
    labels: dict[str, RecordLabel] = field(default_factory=dict)
    flag_reviews: dict[str, FlagReview] = field(default_factory=dict)


def _plain(text: str) -> str:
    """El texto en una sola línea, sin saltos, controles ni marcas de formato (D4).

    PyYAML y libyaml cierran un comentario con cualquier salto de línea de YAML 1.1
    (LF, CR, U+0085, U+2028, U+2029): lo que viniera detrás, p. ej. un
    ``approved: true`` dentro de un ``rationale``, sería una clave de verdad. Todo
    espacio (esos saltos incluidos) y todo carácter no imprimible (controles C0 y C1,
    sustitutos sueltos) pasa a un espacio, y los espacios se pliegan. Las marcas de
    formato (categoría Cf: U+00AD, ZWNJ, ZWJ, U+200B, U+FEFF, las de dirección…) no
    separan palabras, así que se borran: sustituirlas por un espacio partiría "intervención"
    en dos.
    """
    visible = (
        "" if unicodedata.category(ch) == "Cf" else ch if ch.isprintable() else " " for ch in text
    )
    return " ".join("".join(visible).split())


def _acotar(text: str, limit: int) -> str:
    """``_plain`` y, si pasa de ``limit`` caracteres, cortado con «…» dentro del límite."""
    plain = _plain(text)
    return plain if len(plain) <= limit else plain[: limit - 1] + "…"


def _comment(text: str, limit: int = _MAX_COMENTARIO) -> str:
    """Una línea de comentario YAML segura para texto del LLM o del registro (D4).

    La línea se sanea con ``_plain`` y se acota a ``limit`` caracteres como red de
    seguridad. El texto libre (título, afirmación, nota) se acota antes, campo a campo
    con ``_acotar``: cortar aquí la línea entera borraría lo que va detrás de un título
    largo.
    """
    return f"# {_acotar(text, limit)}"


def _key(text: str) -> str:
    """Clave YAML entre comillas dobles que ``yaml.safe_load`` devuelve idéntica (D4).

    Sin comillas, ``010`` se lee como el entero 8 (YAML 1.1), ``2019`` como número y
    ``yes`` como booleano. ``json.dumps(..., ensure_ascii=False)`` deja tal cual los
    caracteres fuera del plano básico (con ``ensure_ascii=True`` serían un par de
    escapes de sustitutos que PyYAML lee como dos caracteres sueltos), pero también
    deja crudos U+0085, U+2028 y U+2029 (saltos de línea de YAML 1.1: la clave se
    parte en dos) y los controles C1 y U+007F (``ReaderError``). Esos y todo carácter
    no imprimible se escriben como escape de comillas dobles de YAML.
    """
    return "".join(_yaml_char(ch) for ch in json.dumps(text, ensure_ascii=False))


def _yaml_char(ch: str) -> str:
    """El carácter si es imprimible; si no, su escape YAML de 4 u 8 dígitos hexadecimales."""
    if ch.isprintable():
        return ch
    code = ord(ch)
    return f"\\u{code:04x}" if code <= 0xFFFF else f"\\U{code:08x}"


def render_decision_template(
    *,
    stage: str,
    autonomy: str,
    request_sha256: str,
    records: RecordPolicy | None,
    flags: FlagPolicy | None,
) -> str:
    """``decision.template.yml``: la decisión a medio rellenar (D4).

    ``approved: null`` la hace inválida tal cual: aprobar tiene que ser un acto
    deliberado. Con ``records`` lista cada registro de la solicitud con
    ``label: null`` y, encima, un comentario con la propuesta de la IA, sus marcas
    (``obligatorio``, ``unclear``, ``no recuperado``), su título y su nota; con
    ``flags``, cada cita marcada con ``verdict: null`` y su comentario (id citado,
    motivo y afirmación). Un bloque sin entradas es ``{}`` (``records:`` a secas se
    leería como ``null`` y la decisión copiada no validaría); con ``None`` el bloque
    no aparece.

    Los valores son constantes (``null``, el hash hexadecimal): el único texto que
    llega de fuera va en comentarios de una línea (``_comment``) y en las claves
    (``_key``), por eso no pasa por ``dump_yaml``, cuyo volcado no pone cada
    registro en una línea con su comentario encima. Un título o un ``rationale``
    con saltos de línea no puede inyectar claves (``approved: true``). El texto
    libre se acota campo a campo (``_acotar``) y va detrás de lo estructurado: un
    título largo no se come la propuesta, las marcas ni el motivo. Una clave de más
    de 1024 caracteres va en forma explícita (``_entrada``).
    """
    lines = [
        _comment(f"Decisión humana del gate '{stage}' (autonomía {autonomy})."),
        "#",
        "# 1. Revisa review_request.yml, en esta misma carpeta.",
        "# 2. Copia este fichero como decision.yml y pon `approved: true` (aprobar)",
        "#    o `approved: false` (rechazar). Tal cual NO es válido: `approved: null`",
        "#    no aprueba ni rechaza.",
        "# 3. Pon tu nombre en `actor` (human:<nombre>) y, si quieres, una razón.",
        "# 4. Reanuda: revisia run --resume <carpeta de esta corrida>",
        "#",
        "# `request_sha256` ata la decisión a esta solicitud: si la solicitud cambia,",
        "# una decisión vieja no se aplica y la corrida vuelve a pausar.",
    ]
    if flags is not None:
        lines += [
            "#",
            "# Citas marcadas por el verificador: para APROBAR, adjudica cada una con",
            "# `verdict: false_positive` y una `reason`. Si alguna es una alucinación real,",
            "# rechaza (`approved: false`): no existe un veredicto «aceptar el riesgo» (D8).",
        ]
    if records is not None:
        lines += [
            "#",
            "# Registros: `label: include` o `label: exclude`, con `reason` (obligatoria al",
            "# excluir en texto completo y al rescatar un no recuperado). `label: null` deja",
            "# la propuesta de la IA como está: no es una decisión humana (D5).",
            f"# Obligatorio etiquetar: {len(records.must_label)} · `unclear` por resolver: "
            f"{len(records.must_resolve)} · no recuperados rescatables: {len(records.rescue_ids)}.",
        ]
    lines += [
        f"request_sha256: {json.dumps(request_sha256)}",
        "approved: null",
        'actor: "human:desconocido"',
        "reason: null",
    ]
    if records is not None:
        lines.append("records:" if records.hints else "records: {}")
        for hint in records.hints:
            marks = [
                text
                for ids, text in (
                    (records.must_label, "obligatorio"),
                    (records.must_resolve, "unclear: resuélvelo"),
                    (records.rescue_ids, "no recuperado: rescatable"),
                )
                if hint.record_id in ids
            ]
            # Lo estructurado (propuesta, marcas) primero; el texto libre (título, nota)
            # después y acotado campo a campo.
            parts = [
                f"propuesta IA: {_acotar(hint.proposal or '—', _MAX_PROPUESTA)}",
                *marks,
                f"«{_acotar(hint.title, _MAX_TEXTO)}»",
            ]
            if note := _acotar(hint.note, _MAX_NOTA):
                parts.append(note)
            lines.append(f"  {_comment(' · '.join(parts))}")
            lines += _entrada(hint.record_id, "{label: null, reason: null}")
    if flags is not None:
        lines.append("flags:" if flags.flagged else "flags: {}")
        for claim in flags.flagged:
            parts = [f"[{claim.index}] cita {_acotar(repr(claim.cited_id), _MAX_ID_CITADO)}"]
            if note := _acotar(claim.note or "", _MAX_NOTA):
                parts.append(note)
            parts.append(f"«{_acotar(claim.claim, _MAX_TEXTO)}»")
            lines.append(f"  {_comment(' · '.join(parts))}")
            lines += _entrada(str(claim.index), "{verdict: null, reason: null}")
    return "\n".join(lines) + "\n"


def _entrada(id_: str, valor: str) -> list[str]:
    """Las líneas YAML de ``id: valor`` con la clave de ``_key``.

    Una clave de más de ``_MAX_CLAVE_IMPLICITA`` caracteres (ya entrecomillada y con sus
    escapes) no cabe en una clave implícita de YAML (1024): dejaría ilegible toda la
    plantilla (``ScannerError``). Esa va en forma explícita, ``? "<id>"`` y, en la línea
    siguiente, ``: <valor>``, que ``yaml.safe_load`` lee igual.
    """
    clave = _key(id_)
    if len(clave) <= _MAX_CLAVE_IMPLICITA:
        return [f"  {clave}: {valor}"]
    return [f"  ? {clave}", f"  : {valor}"]


def _por_indice(key: str) -> tuple[int, int, str]:
    """Orden de las claves de ``flags``: los índices numéricos por valor ("2" antes que "10").

    Como texto ``"10" < "2"``; una clave que no es un entero decimal va después, por texto.
    """
    return (0, int(key), key) if key.isascii() and key.isdecimal() else (1, 0, key)


def _listed(items: list[str]) -> str:
    """Hasta ``_MAX_LISTED`` elementos y el total, para un mensaje de error."""
    shown = ", ".join(items[:_MAX_LISTED])
    more = f" … y {len(items) - _MAX_LISTED} más" if len(items) > _MAX_LISTED else ""
    return f"{shown}{more} ({len(items)} en total)"


def _validate(
    path: Path,
    decision: HumanDecision,
    *,
    records: RecordPolicy | None,
    flags: FlagPolicy | None,
) -> None:
    """Valida ``records`` y ``flags`` de una decisión cuyo hash coincide (spec §8).

    Lo estructural se comprueba siempre (``records``/``flags`` en un gate que no
    los admite). Con ``approved: false`` no se aplica ninguna etiqueta ni
    adjudicación (nunca acompañan a un ``reject``), así que el resto solo se
    comprueba al aprobar.

    Raises:
        DecisionFileError: con el motivo y los ids o índices afectados.
    """
    if decision.records and records is None:
        raise DecisionFileError(
            f"{path}: `records` solo vale en los gates de cribado (screening_ta, screening_ft); "
            "este gate se aprueba o rechaza por etapa."
        )
    if decision.flags and flags is None:
        raise DecisionFileError(
            f"{path}: `flags` solo vale en el gate `reporte` con citas marcadas por el "
            "verificador, y esta solicitud no tiene ninguna."
        )
    if not decision.approved:
        return
    if records is not None:
        valid = {h.record_id for h in records.hints}
        unknown = sorted(set(decision.records) - valid)
        if unknown:
            raise DecisionFileError(
                f"{path}: `records` con ids que no están en la solicitud: {_listed(unknown)}."
            )
        for record_id, label in decision.records.items():
            sin_razon = not (label.reason or "").strip()
            if label.label == "exclude" and records.reason_on_exclude and sin_razon:
                raise DecisionFileError(
                    f"{path}: {record_id!r} se excluye sin `reason`; en este gate la razón es "
                    "obligatoria (va a la lista de excluidos, PRISMA 2020 16b)."
                )
            if label.label is not None and record_id in records.rescue_ids and sin_razon:
                raise DecisionFileError(
                    f"{path}: {record_id!r} no se recuperó; etiquetarlo es un rescate y necesita "
                    "`reason` (cómo se obtuvo el texto completo, D2)."
                )
    if flags is not None:
        valid_index = {str(c.index) for c in flags.flagged}
        unknown = sorted(set(decision.flags) - valid_index, key=_por_indice)
        if unknown:
            raise DecisionFileError(
                f"{path}: `flags` con índices que no son citas marcadas: {_listed(unknown)}."
            )
    pending: list[str] = []
    if records is not None:
        labeled = {rid for rid, lab in decision.records.items() if lab.label is not None}
        pending += sorted((records.must_label | records.must_resolve) - labeled)
    if flags is not None:
        for claim in sorted(flags.flagged, key=lambda c: c.index):
            review = decision.flags.get(str(claim.index))
            done = (
                review is not None
                and review.verdict == "false_positive"
                and bool((review.reason or "").strip())
            )
            if not done:
                pending.append(f"cita {claim.index}")
    if pending:
        raise DecisionFileError(
            f"{path}: para aprobar falta etiquetar o adjudicar: {_listed(pending)}. Cada registro "
            "pendiente necesita `label` (include o exclude) y cada cita marcada `verdict: "
            "false_positive` con `reason`; si alguna cita marcada es real, rechaza "
            "(`approved: false`)."
        )


def _recorded(
    entries: list[DecisionEntry],
    *,
    stage: str,
    action: str,
    target: str | None,
    request_sha256: str,
    decision_sha256: str | None,
) -> bool:
    """¿Ya está en el ledger la tupla ``(stage, action, target, request, decision)``?"""
    return any(
        (
            e.stage,
            e.action,
            e.target,
            e.detail.get("request_sha256"),
            e.detail.get("decision_sha256"),
        )
        == (stage, action, target, request_sha256, decision_sha256)
        for e in entries
    )


def _register(
    run_ctx: RunContext,
    entries: list[DecisionEntry],
    *,
    stage: str,
    autonomy: str,
    decision: HumanDecision,
    request_sha256: str,
    decision_path: Path,
    labels: dict[str, RecordLabel],
    flag_reviews: dict[str, FlagReview],
    records: RecordPolicy | None,
    flags: FlagPolicy | None,
    force_human: bool,
) -> None:
    """Registra la decisión en el ledger, una sola vez (idempotente al reanudar).

    Con ``approve``, primero una ``label`` por etiqueta (en orden de id) y una
    ``flag_review`` por adjudicación (en orden de índice), después el
    ``approve`` (spec §4.3). Un ``reject`` va solo. Si la corrida cayó a medias,
    al reanudar solo se escriben las entradas que faltan.
    """
    decision_sha256 = canonical_sha256(decision.model_dump(mode="json"))
    action = "approve" if decision.approved else "reject"
    effective = summarize_gates(entries).get(stage)
    if effective is not None and (
        effective.action,
        effective.request_sha256,
        effective.decision_sha256,
    ) == (action, request_sha256, decision_sha256):
        return  # ya es la decisión efectiva: reanudar no la duplica
    if _recorded(
        entries,
        stage=stage,
        action=action,
        target=None,
        request_sha256=request_sha256,
        decision_sha256=decision_sha256,
    ):
        if decision.actor == AUTO_APPROVE_ACTOR:
            # La decisión es la sintética de --auto-approve: no hay decision.yml donde
            # cambiar un `reason`; lo que falta es una decisión humana.
            raise DecisionFileError(
                f"{stage}: la aprobación de demostración (--auto-approve) ya se usó para esta "
                "solicitud y después se registró otra decisión; el ledger no la repite. Para "
                f"continuar, escribe una decisión humana en {decision_path} (parte de "
                f"{TEMPLATE_FILE})."
            )
        raise DecisionFileError(
            f"{stage}: esta misma decisión ya se registró antes y después se cambió; para "
            "volver a ella, cambia `reason` en decision.yml (el ledger no repite una "
            "decisión idéntica)."
        )
    hashes = {"request_sha256": request_sha256, "decision_sha256": decision_sha256}
    pending: list[DecisionEntry] = []
    proposals = {h.record_id: h.proposal for h in records.hints} if records else {}
    for record_id in sorted(labels):
        label = labels[record_id]
        pending.append(
            DecisionEntry(
                stage=stage,
                actor=decision.actor,
                autonomy=autonomy,
                action="label",
                target=record_id,
                detail={
                    "from": proposals.get(record_id),
                    "to": label.label,
                    "reason": label.reason,
                    "rescue": bool(records and record_id in records.rescue_ids),
                    **hashes,
                },
            )
        )
    claims = {str(c.index): c for c in flags.flagged} if flags else {}
    for index in sorted(flag_reviews, key=int):
        review, claim = flag_reviews[index], claims[index]
        pending.append(
            DecisionEntry(
                stage=stage,
                actor=decision.actor,
                autonomy=autonomy,
                action="flag_review",
                target=f"flag:{index}",
                detail={
                    "cited_id": claim.cited_id,
                    "claim": claim.claim,
                    "verdict": review.verdict,
                    "reason": review.reason,
                    **hashes,
                },
            )
        )
    for entry in pending:  # tras una caída a medias, solo las que faltan
        if not _recorded(
            entries,
            stage=stage,
            action=entry.action,
            target=entry.target,
            request_sha256=request_sha256,
            decision_sha256=decision_sha256,
        ):
            run_ctx.ledger.append(entry)
    detail = {
        **decision.model_dump(
            exclude={"approved", "actor", "request_sha256", "records", "flags"},
            exclude_none=True,
        ),
        **hashes,
        "n_labels": len(labels),
        "forced_human": force_human,
    }
    run_ctx.ledger.append(
        DecisionEntry(
            stage=stage, actor=decision.actor, autonomy=autonomy, action=action, detail=detail
        )
    )


def _from_ledger(
    entries: list[DecisionEntry], stage: str, decision_sha256: str | None
) -> tuple[dict[str, RecordLabel], dict[str, FlagReview]]:
    """Etiquetas y adjudicaciones de una decisión ya registrada (el ledger manda)."""
    labels: dict[str, RecordLabel] = {}
    reviews: dict[str, FlagReview] = {}
    if decision_sha256 is None:
        return labels, reviews
    for e in entries:
        if e.stage != stage or e.detail.get("decision_sha256") != decision_sha256:
            continue
        if e.action == "label" and e.target is not None:
            labels[e.target] = RecordLabel(label=e.detail.get("to"), reason=e.detail.get("reason"))
        elif e.action == "flag_review" and e.target is not None:
            reviews[e.target.removeprefix("flag:")] = FlagReview(
                verdict=e.detail.get("verdict"), reason=e.detail.get("reason")
            )
    return labels, reviews


def _motivos_humano(
    records: RecordPolicy | None, flags: FlagPolicy | None, force_human: bool
) -> list[str]:
    """Por qué solo una decisión humana en ``decision.yml`` cierra el gate (M5, D8, D9).

    Con motivos, ``--auto-approve`` no sirve (pausaría otra vez) y la pausa los explica
    en lugar de sugerirlo. Solo nombra el bloque ``flags`` si hay citas marcadas que
    adjudicar en él (sin ``FlagPolicy`` o sin citas, la plantilla no lo trae o lo trae
    vacío), y ``records`` si hay registros ``unclear`` que resolver.
    """
    motivos = []
    if force_human and flags is not None and flags.flagged:
        motivos.append(
            "el verificador marcó citas y este gate exige una decisión humana (M5): adjudica "
            "cada una en `flags` (`verdict: false_positive` y `reason`) o rechaza "
            "(`approved: false`)"
        )
    elif force_human:
        motivos.append(
            "este gate exige una decisión humana (M5): aprueba (`approved: true`) o rechaza "
            "(`approved: false`) en decision.yml, con `actor: human:<nombre>`"
        )
    if records is not None and records.must_resolve:
        motivos.append(
            f"{len(records.must_resolve)} registro(s) `unclear` solo los resuelve un humano "
            "(D9): etiquétalos en `records` (`label: include` o `label: exclude`)"
        )
    return motivos


def review_gate(
    *,
    stage: str,
    autonomy: str,
    run_ctx: RunContext,
    review_payload: dict,
    auto_approve: bool,
    records: RecordPolicy | None = None,
    flags: FlagPolicy | None = None,
    force_human: bool = False,
) -> GateResult:
    """Aplica el checkpoint humano de una etapa según su autonomía.

    La solicitud es ``{schema_version, stage, autonomy, **review_payload}`` y su
    ``request_sha256`` es ``canonical_sha256`` de ese contenido: sin rutas
    absolutas ni horas, para que sea estable entre reanudaciones (spec §4.3).

    A2/A3 no pausan (registran ``auto-proceed`` y continúan). A0/A1 requieren
    una decisión: ``decision.yml`` con el hash vigente, la ya registrada en el
    ledger para esa solicitud, o ``auto_approve``; si no hay ninguna, pausan.

    ``records`` y ``flags`` habilitan la decisión por registro y por cita.
    ``--auto-approve`` aprueba con las etiquetas de la IA, salvo que haya
    registros que solo resuelve un humano (``must_resolve``): entonces pausa
    (D9). Con ``force_human`` (citas marcadas, M5) se ignoran ``auto_approve`` y
    una autonomía A2/A3, que pasa a A1 en la solicitud y el ledger, y solo vale una
    decisión humana (``actor`` que empieza por ``human:``) tanto al leer
    ``decision.yml`` como al reutilizar la del ledger. Cuando solo un
    ``decision.yml`` humano puede cerrar el gate (citas marcadas, ``unclear``), la
    pausa dice por qué y no ofrece ``--auto-approve``.

    Raises:
        ValueError: si ``review_payload`` trae alguna clave común de la solicitud
            (``schema_version``, ``stage``, ``autonomy``, ``request_sha256``): es un
            error de programación, no se pisa en silencio.
        DecisionFileError: si ``decision.yml`` es ilegible o inválido, o repite una
            decisión que el ledger ya no admite repetir.
    """
    pisadas = [clave for clave in _CLAVES_COMUNES if clave in review_payload]
    if pisadas:
        raise ValueError(
            f"{stage}: review_payload no puede traer {', '.join(pisadas)}: son claves comunes "
            "de la solicitud y pisarlas cambiaría en silencio lo que se hashea (error de "
            "programación)."
        )
    if force_human and autonomy in {"A2", "A3"}:
        autonomy = "A1"
    payload = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "stage": stage,
        "autonomy": autonomy,
        **review_payload,
    }
    request_sha256 = canonical_sha256(payload)
    entries = run_ctx.ledger.read_all()

    if autonomy in {"A2", "A3"}:
        if not _recorded(
            entries,
            stage=stage,
            action="auto-proceed",
            target=None,
            request_sha256=request_sha256,
            decision_sha256=None,
        ):
            run_ctx.ledger.append(
                DecisionEntry(
                    stage=stage,
                    actor=f"agent:{stage}",
                    autonomy=autonomy,
                    action="auto-proceed",
                    detail={
                        "reason": f"autonomía {autonomy}: ejecuta y notifica",
                        "request_sha256": request_sha256,
                    },
                )
            )
        return GateResult(
            "approved", f"{stage}: auto-proceed ({autonomy}).", request_sha256, f"agent:{stage}"
        )

    # A0/A1 → requiere humano.
    stage_dir = run_ctx.stage_dir(stage)
    run_ctx.write_text(
        f"{stage}/{REQUEST_FILE}", dump_yaml({"request_sha256": request_sha256, **payload})
    )
    run_ctx.write_text(
        f"{stage}/{TEMPLATE_FILE}",
        render_decision_template(
            stage=stage,
            autonomy=autonomy,
            request_sha256=request_sha256,
            records=records,
            flags=flags,
        ),
    )
    request_path = stage_dir / REQUEST_FILE
    decision_path = stage_dir / DECISION_FILE
    resume = f"Reanuda con: revisia run --resume {run_ctx.run_dir}"

    decision = _read_decision(decision_path)
    from_file = decision is not None
    if decision is not None and decision.request_sha256 != request_sha256:
        return GateResult(
            "paused",
            (
                f"Checkpoint humano en '{stage}': {decision_path} responde a otra solicitud "
                f"(request_sha256 {decision.request_sha256[:12]}…; la vigente es "
                f"{request_sha256[:12]}…). No se aplicó nada: revisa {request_path} y "
                f"rellena de nuevo la decisión desde {stage_dir / TEMPLATE_FILE}. {resume}"
            ),
            request_sha256,
        )
    if decision is None:
        effective = summarize_gates(entries).get(stage)
        if (
            effective is not None
            and effective.request_sha256 == request_sha256
            # Con `force_human` solo vale una decisión humana: una aprobación de
            # demostración de la misma solicitud no resuelve una cita marcada (M5, D8).
            and (not force_human or effective.actor.startswith(HUMAN_ACTOR_PREFIX))
        ):
            # El ledger manda: la decisión de esta solicitud ya está registrada.
            approved = effective.action != "reject"
            labels, reviews = _from_ledger(entries, stage, effective.decision_sha256)
            return GateResult(
                "approved" if approved else "rejected",
                f"{stage}: {'aprobado' if approved else 'rechazado'} por {effective.actor} "
                "(decisión registrada en el ledger).",
                request_sha256,
                effective.actor,
                labels,
                reviews,
            )
        motivos = _motivos_humano(records, flags, force_human)
        if motivos:
            # Solo un decision.yml humano cierra este gate: no se sugiere --auto-approve,
            # que volvería a pausar; si el humano lo pasó, se le dice que no aplica.
            aviso = "--auto-approve no aplica aquí. " if auto_approve else ""
            return GateResult(
                "paused",
                (
                    f"Checkpoint humano en '{stage}': {'; '.join(motivos)}. {aviso}Revisa "
                    f"{request_path}, rellena {stage_dir / TEMPLATE_FILE} y guárdalo como "
                    f"{decision_path}. {resume}"
                ),
                request_sha256,
            )
        if auto_approve:
            decision = HumanDecision(
                request_sha256=request_sha256, approved=True, actor=AUTO_APPROVE_ACTOR
            )
    if decision is None:
        return GateResult(
            "paused",
            (
                f"Checkpoint humano en '{stage}' ({autonomy}). Revisa {request_path}, rellena "
                f"{stage_dir / TEMPLATE_FILE} y guárdalo como {decision_path} (o vuelve a "
                f"correr con --auto-approve). {resume}"
            ),
            request_sha256,
        )

    if from_file:
        if force_human and not decision.actor.startswith(HUMAN_ACTOR_PREFIX):
            # "Humano" se define igual al entrar que al reutilizar del ledger (arriba): un
            # actor que no empiece por `human:` (`ana`, el de la aprobación de demostración)
            # se registraría como `forced_human` y luego el ledger no lo reutilizaría.
            raise DecisionFileError(
                f"{decision_path}: este gate exige una decisión humana (M5) y `actor` es "
                f"{decision.actor!r}: el actor debe ser `{HUMAN_ACTOR_PREFIX}<nombre>` "
                f"(p. ej. `actor: {HUMAN_ACTOR_PREFIX}ana`)."
            )
        # La sintética de --auto-approve no se valida: adopta las etiquetas de la
        # IA y no exige la completitud de A0 (D9).
        _validate(decision_path, decision, records=records, flags=flags)
    labels: dict[str, RecordLabel] = {}
    reviews: dict[str, FlagReview] = {}
    if decision.approved:
        labels = {rid: lab for rid, lab in decision.records.items() if lab.label is not None}
        reviews = dict(decision.flags) if flags is not None else {}
    _register(
        run_ctx,
        entries,
        stage=stage,
        autonomy=autonomy,
        decision=decision,
        request_sha256=request_sha256,
        decision_path=decision_path,
        labels=labels,
        flag_reviews=reviews,
        records=records,
        flags=flags,
        force_human=force_human,
    )
    if decision.approved:
        return GateResult(
            "approved",
            f"{stage}: aprobado por {decision.actor}.",
            request_sha256,
            decision.actor,
            labels,
            reviews,
        )
    return GateResult(
        "rejected", f"{stage}: rechazado por {decision.actor}.", request_sha256, decision.actor
    )


_DECISION_HINT = (
    "Se espera un mapa YAML con `request_sha256` (el de review_request.yml; parte de "
    "decision.template.yml), `approved: true` o `approved: false` (booleano, sin "
    "comillas) y, opcionalmente, `actor: human:<nombre>` y `reason: <texto>`."
)


def _read_decision(path: Path) -> HumanDecision | None:
    """Lee y valida ``decision.yml``; ``None`` si no existe.

    Raises:
        DecisionFileError: si el fichero está vacío, no es YAML válido, su raíz
            no es un mapa, falta ``request_sha256``, ``approved`` no es un
            booleano o ``records``/``flags`` traen campos desconocidos o claves
            que no son un id.
    """
    if not path.exists():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise DecisionFileError(f"{path}: YAML inválido ({exc}). {_DECISION_HINT}") from exc
    if raw is None:
        raise DecisionFileError(f"{path}: está vacío. {_DECISION_HINT}")
    if not isinstance(raw, dict):
        raise DecisionFileError(
            f"{path}: la raíz es {type(raw).__name__}, no un mapa. {_DECISION_HINT}"
        )
    try:
        return HumanDecision.model_validate(raw)
    except ValidationError as exc:
        detalle = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        raise DecisionFileError(f"{path}: decisión inválida ({detalle}). {_DECISION_HINT}") from exc
