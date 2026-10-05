"""Contexto de una corrida · carpeta ``runs/<slug>-<fecha>/`` reproducible.

Centraliza dónde se escriben los artefactos de una ejecución, registra cada
llamada a IA y escribe el ``manifest.yml`` que permite a otro investigador
reproducir (o entender la no-reproducibilidad de) la corrida.

Ola 1 (spec 2026-10-04 §7; auditoría 2026-09-03, A9): cada llamada llega a
``llm_calls.jsonl`` en cuanto se registra, no al final con el manifiesto (un
429 a mitad de corrida ya no las pierde); los JSON se escriben de forma atómica
y una corrida nueva nunca reutiliza una carpeta con contenido.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

from revisia.orchestration.journal import append_jsonl, read_jsonl
from revisia.provenance.ledger import DecisionLedger
from revisia.provenance.runmeta import RunMeta, utc_now_iso
from revisia.schemas.artifacts import LLMCall, LLMStage, RunInfo

# Procedencia que el motor escribe en todo manifiesto que produce (auditoría
# 2026-09-03, C3): distingue una corrida real de una reconstrucción a mano.
PROVENANCE_PIPELINE = "pipeline"
# Llamadas a IA de la corrida, una línea `LLMCall` por llamada (spec §4.2).
LLM_CALLS_FILE = "llm_calls.jsonl"
# Identidad, parámetros, huellas, historia y estado de la corrida (spec §4.3).
RUN_INFO_FILE = "run.json"


def resume_command(run_dir: str | Path) -> str:
    """El comando que reanuda una corrida, listo para pegar en una terminal.

    La ruta va entre comillas dobles si tiene espacios (``runs/mi revisión-T``): sin ellas
    el shell la parte en dos argumentos y el comando falla. Lo comparten el mensaje de una
    pausa (``hitl.review_gate``) y el de una interrupción (``RunInterrupted``).
    """
    ruta = str(run_dir)
    if any(ch.isspace() for ch in ruta):
        ruta = f'"{ruta}"'
    return f"revisia run --resume {ruta}"


class RunDirExistsError(FileExistsError):
    """La carpeta de una corrida nueva ya existe y tiene contenido.

    Con diarios, dos ``revisia run`` en el mismo segundo compartirían carpeta y
    el segundo reanudaría en silencio la corrida del primero.
    """


class LegacyRunError(ValueError):
    """La carpeta no tiene ``run.json``: corrida anterior a la Ola 1 (D13).

    Sin instantánea del protocolo ni de la búsqueda, reanudarla obligaría a
    repetir la búsqueda con resultados distintos de los que ya se cribaron.
    """


class RunInterrupted(RuntimeError):
    """La corrida se detuvo por un error a mitad (red, 429, bug): se reanuda (D14).

    Attributes:
        run_dir: carpeta de la corrida interrumpida.
        stage: etapa en curso cuando ocurrió el error.
        error: error original, redactado.
    """

    def __init__(self, run_dir: str | Path, stage: str | None, error: str) -> None:
        self.run_dir = Path(run_dir)
        self.stage = stage
        self.error = error
        donde = f" en '{stage}'" if stage else ""
        super().__init__(
            f"corrida interrumpida{donde}: {error}. Reanuda con: {resume_command(self.run_dir)}"
        )


class RunContext:
    """Estado y rutas de una ejecución concreta del pipeline."""

    def __init__(self, slug: str, runs_root: str | Path, timestamp: str) -> None:
        run_dir = Path(runs_root) / f"{slug}-{timestamp}"
        if run_dir.exists() and any(run_dir.iterdir()):
            raise RunDirExistsError(
                f"{run_dir} ya existe y no está vacía: una corrida nueva no reutiliza la "
                f"carpeta de otra. Para continuarla: revisia run --resume {run_dir}"
            )
        run_dir.mkdir(parents=True, exist_ok=True)
        self._setup(slug, timestamp, run_dir)

    @classmethod
    def open(cls, run_dir: str | Path) -> RunContext:
        """Reabre una corrida existente para reanudarla (slug y fecha de ``run.json``).

        Raises:
            FileNotFoundError: si la carpeta no existe.
            LegacyRunError: si no tiene ``run.json`` (corrida anterior a la Ola 1).
        """
        run_dir = Path(run_dir)
        if not run_dir.is_dir():
            raise FileNotFoundError(f"la carpeta {run_dir} no existe.")
        info_path = run_dir / RUN_INFO_FILE
        if not info_path.exists():
            raise LegacyRunError(
                f"{run_dir}: corrida anterior a la Ola 1 (sin run.json); no se puede reanudar. "
                "Empieza una nueva con `revisia run <protocolo>`."
            )
        info = RunInfo.model_validate_json(info_path.read_text(encoding="utf-8"))
        ctx = cls.__new__(cls)
        ctx._setup(info.slug, info.timestamp, run_dir)
        return ctx

    def _setup(self, slug: str, timestamp: str, run_dir: Path) -> None:
        self.slug = slug
        self.timestamp = timestamp
        self.run_dir = run_dir
        self.ledger = DecisionLedger(run_dir / "decisions_ledger.jsonl")
        self.llm_calls_path = run_dir / LLM_CALLS_FILE
        self.metas: list[LLMCall] = read_jsonl(self.llm_calls_path, LLMCall)

    def stage_dir(self, name: str) -> Path:
        path = self.run_dir / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def deliverable_dir(self) -> Path:
        path = self.run_dir / "deliverable"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def record_meta(
        self,
        meta: RunMeta,
        *,
        stage: LLMStage,
        record_id: str | None = None,
        role: str | None = None,
    ) -> LLMCall:
        """Registra una llamada a IA y la escribe al instante en ``llm_calls.jsonl``."""
        call = LLMCall.from_meta(meta, stage=stage, record_id=record_id, role=role)
        append_jsonl(self.llm_calls_path, call)
        self.metas.append(call)
        return call

    def write_text(self, relpath: str, content: str) -> Path:
        """Escribe un fichero de texto de forma atómica (temporal + ``os.replace``).

        Una caída a mitad nunca deja un JSON o YAML a medias: o queda el
        anterior o el nuevo.
        """
        path = self.run_dir / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
        return path

    def write_json(self, relpath: str, data: object) -> Path:
        return self.write_text(relpath, json.dumps(data, ensure_ascii=False, indent=2))

    def write_manifest(
        self,
        *,
        protocol_snapshot: dict,
        counts: dict,
        autonomy_effective: dict[str, str] | None = None,
        final_gate: dict | None = None,
        extra: dict | None = None,
    ) -> Path:
        """Escribe ``manifest.yml`` con todo lo necesario para reproducir.

        ``llm_calls`` sale de ``llm_calls.jsonl`` (todas las líneas, en orden),
        no de memoria: una corrida reanudada incluye las llamadas de todas sus
        invocaciones. Bloques de la Ola 1 (spec §4.3): ``autonomy_effective``
        (autonomía con la que se aplicó cada gate) y ``final_gate``, más ``run``
        (de ``run.json``) si la corrida lo tiene.
        """
        calls = read_jsonl(self.llm_calls_path, LLMCall)
        run_block: dict = {}
        info_path = self.run_dir / RUN_INFO_FILE
        if info_path.exists():
            info = RunInfo.model_validate_json(info_path.read_text(encoding="utf-8"))
            run_block["run"] = {
                "started_utc": info.started_utc,
                "resumes": list(info.resumes),
                "engine_version": info.engine_version,
                "python_version": info.python_version,
                "status": info.status,
            }
        manifest = {
            "slug": self.slug,
            "created_utc": utc_now_iso(),
            "timestamp": self.timestamp,
            "provenance": PROVENANCE_PIPELINE,
            "protocol": protocol_snapshot,
            "counts": counts,
            "llm_calls": [c.model_dump(mode="json") for c in calls],
            "models_used": sorted({f"{c.provider}:{c.model}" for c in calls}),
            "deterministic_token_level": (all(c.deterministic for c in calls) if calls else True),
            **run_block,
            "autonomy_effective": dict(autonomy_effective or {}),
            "final_gate": dict(final_gate or {"forced_human": False, "reason": None}),
            **(extra or {}),
        }
        # La procedencia no es configurable desde `extra`: la fija el motor.
        manifest["provenance"] = PROVENANCE_PIPELINE
        return self.write_text(
            "manifest.yml", yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False)
        )
