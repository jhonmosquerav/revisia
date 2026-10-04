"""Checks de calidad del cribado y de la síntesis: ``gold``, ``grounding``."""

from __future__ import annotations

from revisia.audit.artifacts import AuditContext
from revisia.audit.model import Verdict


def check_gold(ctx: AuditContext) -> Verdict:
    """trAIce M9/R2: métricas del cribado IA contra un gold humano."""
    loaded = ctx.art.json("03_screening/metrics.json")
    if not loaded.present:
        return "WARN", (
            "Sin gold standard: no hay recall/kappa del cribado IA vs humano. "
            "Crea gold.yml (revisia gold-template) antes de publicar."
        )
    if not loaded.ok or not isinstance(loaded.value, dict):
        return "WARN", "metrics.json ilegible."
    metrics = loaded.value
    recall = metrics.get("recall")
    kappa = metrics.get("cohen_kappa")
    # mcc solo cuenta como indefinido si la clave está presente y es null: un
    # metrics.json de formato antiguo (sin "mcc") no debe convertir un PASS
    # previo en WARN.
    mcc_indefinido = "mcc" in metrics and metrics.get("mcc") is None
    # La matriz cuenta como presente solo si sus cuatro celdas son enteras.
    matriz = {k: metrics.get(k) for k in ("tp", "fp", "fn", "tn")}
    tiene_matriz = all(k in metrics for k in matriz)
    legible = tiene_matriz and all(
        isinstance(v, int) and not isinstance(v, bool) for v in matriz.values()
    )
    una_sola_clase = legible and (
        matriz["tp"] + matriz["fn"] == 0 or matriz["tn"] + matriz["fp"] == 0
    )
    if tiene_matriz and not legible:
        return "WARN", (
            f"Métricas vs gold humano: recall={recall} · metrics.json con matriz de confusión "
            "ilegible (tp/fp/fn/tn con algún valor no numérico)."
        )
    if kappa is None or mcc_indefinido or una_sola_clase:
        return "WARN", (
            f"Métricas vs gold humano: recall={recall} · kappa/mcc no calculable: métricas "
            "indefinidas o no informativas (el gold o la IA asignaron una sola clase). Amplía "
            "el gold con registros relevantes e irrelevantes."
        )
    return "PASS", (
        f"Métricas vs gold humano: recall={recall} · kappa={kappa} (accuracy omitida a propósito)."
    )


def check_grounding(ctx: AuditContext) -> Verdict:
    """trAIce M8/M9: verificación anti-alucinación de la síntesis."""
    loaded = ctx.art.json("06_synthesis/verification.json")
    if not loaded.present:
        return "WARN", "Sin verification.json: la síntesis no pasó por el verificador."
    if not loaded.ok or not isinstance(loaded.value, dict):
        return "WARN", "verification.json ilegible."
    if loaded.value.get("hallucination_flagged"):
        return "WARN", (
            "El verificador marcó citas posiblemente no fundamentadas: revisar antes de usar."
        )
    return "PASS", "Grounding de citas verificado sin banderas."
