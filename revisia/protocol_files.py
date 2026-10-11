"""Ficheros auxiliares del protocolo, validados al cargar (revisión final de la Ola 1, A3).

``gold.yml``, ``effects.yml``, ``inclusion_exclusion.yml`` y ``extraction_form.yml`` se leían
con ``yaml.safe_load(...) or {}`` justo donde se usaban, y un fichero con otra forma fallaba
tarde: un gold en forma de lista, o con claves mixtas número/texto (``TypeError`` en el
``sorted`` de ``gold.json``); ``"false"`` entre comillas leído como verdadero por
``bool(val)``; un ``effects.yml`` con un solo estudio, sin ``yi``/``vi`` o con varianza ≤ 0 que
reventaba la síntesis después de gastar el LLM; unos criterios o un formulario en forma de
lista; una fecha YAML sin comillas en el formulario (``ejemplo: 2021-03-15``) que rompía
``canonical_sha256`` tras los gates de cribado. Cada uno salía como rc 3 «reanuda» y fallaba
igual en cada reanudación: un bucle sin salida.

Aquí cada fichero tiene su forma esperada y :func:`load_protocol_files` los valida todos de una
vez: lanza :class:`ProtocolFilesError` (rc 2, error de configuración) con lo que hay que corregir
en cada uno. La usan el preflight (``validate``/``run``, antes de crear la carpeta; D10) y el
pipeline justo después de ``ensure_snapshot``, sobre ``00_protocol/``, que es la única fuente de
estos ficheros durante la corrida (D3). Las fechas del formulario y de los criterios se
normalizan a texto ISO al cargar: no son JSON nativo y entran en los hashes del diario.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, StrictBool, ValidationError, model_validator

from revisia.config import rechazar_claves_de_fusion
from revisia.meta_analysis import meta_analyze
from revisia.schemas.effects import EffectInput, Measure

GOLD_FILE = "gold.yml"
EFFECTS_FILE = "effects.yml"
CRITERIA_FILE = "inclusion_exclusion.yml"
FORM_FILE = "extraction_form.yml"

# Recorte de un valor citado en un mensaje (un escalar enorme no debe inundar la consola).
_MAX_VALOR = 80

# TypeVar clásico y no PEP 695 (`def f[T]`): la suite también corre en 3.11.
ModelT = TypeVar("ModelT", bound=BaseModel)


class ProtocolFilesError(ValueError):
    """Algún fichero auxiliar del protocolo no tiene la forma esperada (rc 2 en el CLI).

    Attributes:
        problems: un problema por fichero, ``"<fichero>: <qué corregir>"``.
    """

    def __init__(self, problems: list[str]) -> None:
        self.problems = list(problems)
        super().__init__(
            "ficheros del protocolo con errores: " + "; ".join(self.problems) + ". Corrígelos y "
            "vuelve a lanzar la orden (si la corrida ya empezó con ellos, empieza una nueva con "
            "`revisia run <protocolo>`)."
        )


def _corto(value: object) -> str:
    texto = repr(value)
    return texto if len(texto) <= _MAX_VALOR else texto[: _MAX_VALOR - 1] + "…"


def _clave_json(key: object, where: str) -> str:
    """Una clave de mapa como texto, igual que la escribiría JSON (``json.dumps``).

    Una fecha YAML sin comillas como clave pasa a texto ISO; un número, a su texto JSON.
    """
    if isinstance(key, str):
        return key
    if isinstance(key, datetime | date):
        return key.isoformat()
    if isinstance(key, bool | int) or key is None:
        return json.dumps(key)
    if isinstance(key, float) and math.isfinite(key):
        return json.dumps(key)
    raise ValueError(f"{where}: clave {_corto(key)} no representable en JSON")


def json_nativo(value: object, where: str) -> Any:
    """``value`` con solo tipos JSON: fechas a texto ISO, claves a texto, tuplas a listas.

    Los hashes de la Ola 1 (``canonical_sha256``) rechazan lo que no es JSON: una fecha YAML
    sin comillas (``2021-03-15``) en el formulario rompía el diario de extracción después de
    los gates de cribado. Un número no finito (``.nan``) o un tipo binario (``!!binary``,
    ``!!set``) es un error con su ubicación.

    Raises:
        ValueError: si hay un valor que JSON no puede representar.
    """
    if isinstance(value, str | bool | int) or value is None:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{where}: número no finito ({_corto(value)})")
        return value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            texto = _clave_json(key, where)
            if texto in out:
                raise ValueError(f"{where}: clave {texto!r} repetida")
            out[texto] = json_nativo(item, f"{where}.{texto}")
        return out
    if isinstance(value, list | tuple):
        return [json_nativo(item, f"{where}[{i}]") for i, item in enumerate(value)]
    raise ValueError(f"{where}: valor {type(value).__name__} no representable en JSON")


def _mapa_raiz(data: object, esperado: str) -> dict:
    """La raíz de un fichero: un mapa (vacío si el documento está vacío)."""
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"la raíz es {type(data).__name__}, no un mapa: se espera {esperado}")
    return data


class GoldFile(BaseModel):
    """``gold.yml``: ``gold: {id: true|false}`` (o el mapa en la raíz).

    Los ids pasan a texto (como en ``gold.json``: un id numérico era una clave entera que
    rompía el ``sorted`` junto a las de texto) y cada etiqueta es un booleano YAML sin comillas:
    ``"false"`` entre comillas es texto y ``bool("false")`` lo leía como incluir.
    """

    gold: dict[str, StrictBool] = {}

    @model_validator(mode="before")
    @classmethod
    def _forma(cls, data: object) -> object:
        raiz = _mapa_raiz(data, "`gold: {id: true|false}`")
        etiquetas = raiz.get("gold", raiz)
        if etiquetas is None:
            return {"gold": {}}
        if not isinstance(etiquetas, dict):
            raise ValueError(
                f"`gold` es {type(etiquetas).__name__}, no un mapa: se espera "
                '`gold: {"<id>": true}` con un id por línea'
            )
        ids: dict[str, object] = {}
        for key, value in etiquetas.items():
            if not isinstance(key, str | int) or isinstance(key, bool):
                raise ValueError(
                    f"id {_corto(key)} no es texto ni un número: escríbelo entre comillas"
                )
            texto = str(key)
            if texto in ids:
                raise ValueError(f"id {texto!r} repetido (como número y como texto)")
            if not isinstance(value, bool):
                raise ValueError(
                    f"{texto!r}: {_corto(value)} no es true/false (booleano YAML, sin comillas)"
                )
            ids[texto] = value
        return {"gold": ids}


class EffectsFile(BaseModel):
    """``effects.yml``: medida, presentación y efectos por estudio (§8.1).

    Con efectos declarados, el meta-análisis tiene que poder calcularse: al menos dos
    estudios (k ≥ 2), los datos de la medida elegida y varianza positiva y finita. Hasta
    ahora eso se descubría en la síntesis, después de gastar el LLM.
    """

    measure: Measure = "precomputed"
    display: str = "raw"
    effects: list[EffectInput] = []

    @model_validator(mode="before")
    @classmethod
    def _forma(cls, data: object) -> object:
        raiz = _mapa_raiz(data, "`measure`, `effects: [...]`")
        if raiz.get("effects") is None:
            return {**raiz, "effects": []}
        return raiz

    @model_validator(mode="after")
    def _calculable(self) -> EffectsFile:
        if not self.effects:
            return self
        if len(self.effects) < 2:
            raise ValueError(
                f"`effects` declara {len(self.effects)} estudio: el meta-análisis necesita al "
                "menos 2 (k ≥ 2); añade estudios o quita `effects`"
            )
        for effect in self.effects:
            try:
                yi, vi = effect.to_yi_vi(self.measure)
            except (ValueError, ArithmeticError) as exc:
                motivo = str(exc).rstrip(".")
                if not motivo.startswith(effect.study_id):
                    motivo = f"{effect.study_id}: {motivo}"
                raise ValueError(motivo) from exc
            if not (math.isfinite(yi) and math.isfinite(vi)):
                raise ValueError(f"{effect.study_id}: efecto o varianza no finitos")
            if vi <= 0:
                raise ValueError(
                    f"{effect.study_id}: varianza no positiva ({vi:g}); vi tiene que ser > 0"
                )
        try:
            meta_analyze(self.effects, self.measure)
        except (ValueError, ArithmeticError) as exc:
            raise ValueError(f"el meta-análisis no se puede calcular: {exc}") from exc
        return self


class CriteriaFile(BaseModel):
    """``inclusion_exclusion.yml``: ``criteria: {dimensión: {inclusion, exclusion}}``.

    El mapa puede ir bajo ``criteria`` o en la raíz (como lo leía el pipeline). Cada dimensión
    vale un mapa, una lista o un texto; las fechas pasan a texto ISO.
    """

    criteria: dict[str, Any] = {}

    @model_validator(mode="before")
    @classmethod
    def _forma(cls, data: object) -> object:
        raiz = _mapa_raiz(data, "`criteria: {dimensión: {inclusion, exclusion}}`")
        criterios = raiz.get("criteria", raiz)
        if criterios is None:
            return {"criteria": {}}
        if not isinstance(criterios, dict):
            raise ValueError(
                f"`criteria` es {type(criterios).__name__}, no un mapa: se espera "
                "`criteria: {dimensión: {inclusion: ..., exclusion: ...}}`"
            )
        return {"criteria": json_nativo(criterios, "criteria")}


class FormFile(BaseModel):
    """``extraction_form.yml``: ``fields: [{key, descripcion, ...}]``.

    Cada campo es un mapa con ``key`` de texto; sus valores pasan a JSON nativo (las fechas, a
    texto ISO) porque el formulario entra en el ``input_sha256`` del diario de extracción.
    """

    fields: list[dict[str, Any]] = []

    @model_validator(mode="before")
    @classmethod
    def _forma(cls, data: object) -> object:
        raiz = _mapa_raiz(data, "`fields: [{key, descripcion}]`")
        campos = raiz.get("fields")
        if campos is None:
            return {"fields": []}
        if not isinstance(campos, list):
            raise ValueError(
                f"`fields` es {type(campos).__name__}, no una lista: se espera "
                "`fields: [{key: ..., descripcion: ...}]`"
            )
        normalizados = []
        for i, campo in enumerate(campos):
            if not isinstance(campo, dict):
                raise ValueError(f"fields[{i}] es {type(campo).__name__}, no un mapa")
            if not isinstance(campo.get("key"), str) or not campo["key"].strip():
                raise ValueError(f"fields[{i}] sin `key` de texto")
            normalizados.append(json_nativo(campo, f"fields[{i}]"))
        return {"fields": normalizados}


@dataclass(frozen=True)
class ProtocolFiles:
    """Los ficheros auxiliares del protocolo, ya validados.

    Attributes:
        gold: etiquetas del gold humano (id → incluir).
        effects: los efectos del meta-análisis, o ``None`` si el protocolo no declara ninguno.
        criteria: criterios de inclusión/exclusión por dimensión.
        form_fields: campos del formulario de extracción.
    """

    gold: dict[str, bool] = field(default_factory=dict)
    effects: EffectsFile | None = None
    criteria: dict[str, Any] = field(default_factory=dict)
    form_fields: list[dict[str, Any]] = field(default_factory=list)


def _detalle(exc: ValidationError) -> str:
    """El primer error de pydantic como ``campo: motivo`` (y cuántos más hay)."""
    errores = exc.errors()
    primero = errores[0] if errores else {}
    campo = ".".join(str(parte) for parte in primero.get("loc", ()))
    motivo = str(primero.get("msg", "")).removeprefix("Value error, ")
    mas = f" (+{len(errores) - 1} más)" if len(errores) > 1 else ""
    return (f"{campo}: {motivo}" if campo else motivo) + mas


def _leer(path: Path) -> object:
    """El documento YAML de ``path`` (``None`` si no existe o está vacío).

    Rechaza las claves de fusión (``<<``) como ``protocol.yml`` (``config.load_protocol``): el
    auditor no las admite al releer ``00_protocol/``, y un ``effects.yml`` que el motor
    aceptara y el auditor no pudiera leer dejaría sus relaciones sin verificar.

    Raises:
        ValueError: si no se puede leer como UTF-8, no es YAML válido o trae claves de fusión.
    """
    if not path.is_file():
        return None
    try:
        texto = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(
            f"no se puede leer como UTF-8 ({type(exc).__name__}); guárdalo en UTF-8"
        ) from exc
    try:
        rechazar_claves_de_fusion(texto, path.name)
    except yaml.YAMLError as exc:
        raise ValueError(_posicion(exc)) from exc
    try:
        return yaml.safe_load(texto)
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML no válido: {_posicion(exc)}") from exc


def _posicion(exc: yaml.YAMLError) -> str:
    """El problema de un error de YAML con su línea y columna (si las trae)."""
    marca = getattr(exc, "problem_mark", None)
    donde = f" (línea {marca.line + 1}, columna {marca.column + 1})" if marca else ""
    problema = getattr(exc, "problem", None) or type(exc).__name__
    return f"{problema}{donde}"


def load_protocol_files(protocol_dir: str | Path) -> ProtocolFiles:
    """Lee y valida los cuatro ficheros auxiliares de ``protocol_dir`` (A3).

    Un fichero ausente es su valor vacío (sin gold, sin meta-análisis, sin criterios, sin
    formulario), como antes.

    Raises:
        ProtocolFilesError: con un problema por cada fichero que no tiene la forma esperada.
    """
    base = Path(protocol_dir)
    problems: list[str] = []
    gold = _validar(base, GOLD_FILE, GoldFile, problems)
    effects = _validar(base, EFFECTS_FILE, EffectsFile, problems)
    criteria = _validar(base, CRITERIA_FILE, CriteriaFile, problems)
    form = _validar(base, FORM_FILE, FormFile, problems)
    if gold is None or effects is None or criteria is None or form is None:
        raise ProtocolFilesError(problems)
    return ProtocolFiles(
        gold=dict(gold.gold),
        effects=effects if effects.effects else None,
        criteria=criteria.criteria,
        form_fields=form.fields,
    )


def _validar(  # noqa: UP047 - TypeVar clásico: la suite también corre en 3.11
    base: Path, nombre: str, modelo: type[ModelT], problems: list[str]
) -> ModelT | None:
    """``nombre`` validado con ``modelo``; ``None`` (y su problema anotado) si no valida."""
    try:
        return modelo.model_validate(_leer(base / nombre))
    except ValidationError as exc:
        problems.append(f"{nombre}: {_detalle(exc)}")
    except ValueError as exc:
        problems.append(f"{nombre}: {exc}")
    return None
