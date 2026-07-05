# Protocolo de revisión sistemática · plantilla PRISMA-P

> Plantilla de los **17 ítems de PRISMA-P 2015** (Moher et al., *Syst Rev*
> 2015;4:1, doi:10.1186/2046-4053-4-1 · Shamseer et al., BMJ 2015;349:g7647).
> Complétala ANTES de ejecutar la búsqueda y **preregístrala** (PROSPERO/OSF);
> luego copia el ID a `registration:` en `protocol.yml`. Los campos marcados
> `→ protocol.yml` se rellenan/sincronizan con tu configuración ejecutable.

## Sección 1 · Información administrativa

- **1a · Título — identificación:** _(identifica el documento como protocolo de
  revisión sistemática)_
- **1b · Título — actualización:** _(¿es actualización de una revisión previa?
  Si usas `--brain`, el cerebro registrará el delta entre corridas)_
- **2 · Registro:** _(registro y número: PROSPERO CRD… / OSF DOI…)_ → `protocol.yml: registration`
- **3a · Autores — contacto:** _(nombres, filiaciones, email del corresponsal)_
- **3b · Contribuciones:** _(quién diseña, criba, extrae, arbitra, redacta;
  declara qué etapas asiste la IA y quién supervisa cada una — trAIce M8)_
- **4 · Enmiendas:** _(plan para documentar enmiendas al protocolo; el ledger
  de prisma-loop registra desviaciones operativas con timestamp)_
- **5a · Fuentes de apoyo:** _(financiación)_
- **5b · Patrocinador:** _(si aplica)_
- **5c · Rol del patrocinador/financiador:** _(en el diseño y la publicación)_

## Sección 2 · Introducción

- **6 · Justificación:** _(por qué esta revisión, en el contexto de lo conocido)_
- **7 · Objetivos:** _(pregunta explícita con el marco elegido)_ → `protocol.yml: question`

## Sección 3 · Métodos

- **8 · Criterios de elegibilidad:** _(diseños, poblaciones, idiomas, ventana
  temporal, publicación)_ → `inclusion_exclusion.yml` y `protocol.yml: search_window`
- **9 · Fuentes de información:** _(bases, registros, literatura gris, contacto
  con autores)_ → `protocol.yml: databases` (+ import RIS/BibTeX)
- **10 · Estrategia de búsqueda:** _(cadena completa de al menos una base, tal
  que sea repetible — PRISMA-S)_ → `search_strings/<base>.txt`
- **11a · Gestión de registros:** _(software y flujo de datos; prisma-loop
  produce `runs/<slug>-<fecha>/` con manifiesto reproducible)_
- **11b · Proceso de selección:** _(cuántos revisores, independencia, cómo se
  resuelven desacuerdos; declara el papel del cribado IA: propone, no decide —
  autonomía A1 máx. y gold humano con κ)_
- **11c · Proceso de extracción:** _(formularios piloto, doble extracción —
  prisma-loop hace doble extracción del 20% con κ de presencia)_ → `extraction_form.yml`
- **12 · Ítems de datos:** _(variables a extraer, supuestos y simplificaciones)_ → `extraction_form.yml`
- **13 · Desenlaces y priorización:** _(desenlaces principales/adicionales con
  justificación)_
- **14 · Riesgo de sesgo:** _(herramienta acorde al diseño, cómo se usa en la
  síntesis; el juicio final es humano — A0)_ → `protocol.yml: rob_tool`
- **15a · Criterios de síntesis cuantitativa:** _(cuándo se hará meta-análisis)_ → `effects.yml` (si procede)
- **15b · Métodos de síntesis:** _(medida del efecto, modelo fijo/aleatorio,
  heterogeneidad I²/τ²)_
- **15c · Análisis adicionales:** _(subgrupos, sensibilidad, meta-regresión —
  para análisis avanzados: export `effects_metafor.csv` → metafor)_
- **15d · Síntesis no cuantitativa:** _(tipo de resumen planificado — SWiM)_
- **16 · Meta-sesgos:** _(sesgo de publicación/reporte selectivo; Egger si k
  suficiente, funnel plot)_
- **17 · Confianza en la evidencia acumulada:** _(GRADE u otro marco de
  certeza)_

---

> **Uso de IA (declaración anticipada, PRISMA-trAIce):** especifica aquí qué
> etapas asistirá la IA, con qué modelos/proveedores, con qué supervisión
> humana y contra qué gold standard se evaluará el cribado. La corrida emitirá
> la declaración verificable en `deliverable/checklist_traice.md` y la
> auditoría (`prisma-loop audit`) comprobará la evidencia.
