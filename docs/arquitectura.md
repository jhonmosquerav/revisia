# Esquema de funcionamiento

Una revisión sistemática end-to-end pasa por **tres planos**: el flujo PRISMA
(agentes mono-tarea con autonomía declarada), la **defensa en profundidad**
(verificación → HITL → gold → auditoría) y la **memoria** (living review).

## El flujo completo

```mermaid
flowchart TB
    subgraph PREP["📋 Preparación (humano · A0)"]
        NEW["revisia new &lt;slug&gt;<br/>protocolo + PRISMA-P + preregistro"]
    end

    subgraph PIPE["⚙️ Pipeline (revisia run · un agente por etapa)"]
        BUS["🔎 busqueda · A2<br/>OpenAlex · Crossref · Semantic Scholar ·<br/>Europe PMC + import RIS/BibTeX"]
        DED["♻️ dedup · A2 (determinista)"]
        SCR["🤖 screening T/A · A1<br/>ensemble multi-modelo · voto pro-recall"]
        FT["📄 full-text OA→MD + screening · A0"]
        EXT["📊 extracción (+doble 20% · κ) · A0"]
        ROB["⚖️ riesgo de sesgo (RoB2/ROBINS-I/…) · A0"]
        MA["📈 meta-análisis (si effects.yml) · A2<br/>IV fijo/aleatorio · I²/τ² · Egger"]
        SIN["✍️ síntesis narrativa (SWiM) · A1"]
        REP["📦 reporte · A1"]
    end

    subgraph GUARD["🛡️ Defensa en profundidad"]
        VER["Verificador anti-alucinación<br/>(grounding por cita)"]
        HITL["Checkpoints humanos ✋<br/>ledger append-only"]
        GOLD["Gold standard escalonado<br/>recall · lost-evidence · MCC · κ"]
        AUD["revisia audit<br/>PASS/WARN/FAIL vs 2020/-S/trAIce"]
    end

    subgraph OUT["📤 Entregable (runs/&lt;slug&gt;-&lt;fecha&gt;/deliverable)"]
        DEL["documento.md · metodologia.md<br/>flow diagram oficial (razones + IA/humano)<br/>checklists 2020 · resúmenes · PRISMA-S · trAIce<br/>tabla extracción · RoB · forest/funnel · .bib<br/>interop: robvis · metafor · PRISMA2020"]
    end

    subgraph MEM["🧠 Memoria (--brain · patrón cerebro)"]
        BRAIN["genome/events.jsonl · wiki semantic/episodic · raw<br/>recall → living review (flow actualizado v3)"]
    end

    CHECK["🔍 revisia check &lt;manuscrito&gt;<br/>adherencia 27 ítems (estilo PRISMA-Check)"]

    EXP["📄 revisia export<br/>documento único: HTML autocontenido / PDF"]

    NEW --> BUS --> DED --> SCR --> FT --> EXT --> ROB --> MA --> SIN --> REP --> DEL
    SCR -.-> VER
    SIN -.-> VER
    VER -.-> HITL
    SCR -.-> GOLD
    HITL -.-> PIPE
    DEL --> AUD
    DEL --> BRAIN
    BRAIN -. memoria previa: aviso + flow updated .-> NEW
    DEL --> CHECK
    DEL --> EXP
```

## Los tres contratos del sistema

1. **Motor ↔ config**: el código (`revisia/`) no sabe nada de tu revisión;
   tu revisión (`protocols/<slug>/`) no contiene código. `protocol.yml` declara
   pregunta, bases, herramienta RoB, **proveedor LLM por etapa** y **autonomía
   por etapa** (A0–A3; el juicio nunca supera A1).
2. **Toda llamada a IA deja huella**: `RunMeta` (modelo, versión, seed,
   temperatura, hash de prompt/respuesta) + `decisions_ledger.jsonl` (quién
   decidió qué, con qué autonomía, cuándo). El manifiesto reconstruye la corrida.
3. **Nada se afirma sin evidencia**: las citas pasan grounding antes del gate
   humano; las métricas se calculan contra gold humano (nunca "accuracy"); la
   auditoría verifica artefactos en disco, no promesas.

## Dónde está cada cosa

| Plano | Módulos | Comandos |
|---|---|---|
| Pipeline | `agents/` · `orchestration/` | `run` |
| Defensa | `rag/` (grounding) · `provenance/` · `audit.py` · `metrics.py` | `audit` · `gold-template` · `validate` |
| Memoria | `memory/` (patrón [cerebro](https://github.com/jhonmosquerav/cerebro)) | `brain` · `run --brain` |
| Reporte | `exports/` (flow oficial, checklists, interop, documento único) | `run` (emite todo) · `export` (HTML autocontenido / PDF) |
| Adherencia | `check.py` | `check` |
| Config | `protocols/_TEMPLATE/` (protocol.yml · PRISMA-P · gold · effects) | `new` |
