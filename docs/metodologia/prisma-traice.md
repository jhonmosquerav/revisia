---
fuente: "Holst D, Moenck K, Koch J, Schmedemann O, Schüppstuhl T. Transparent Reporting of AI in Systematic Literature Reviews: Development of the PRISMA-trAIce Checklist. JMIR AI. 2025;4:e80247"
doi: "10.2196/80247"
pmid: "41370833"
pmcid: "PMC12694947"
url_jmir: "https://ai.jmir.org/2025/1/e80247"
url_pmc: "https://pmc.ncbi.nlm.nih.gov/articles/PMC12694947/"
repo_oficial: "https://github.com/cqh4046/PRISMA-trAIce"
licencia_repo: "MIT"
comunidad: "https://discord.gg/DrDFBpEb53"
licencia_fuente: "CC-BY-4.0"
fecha_consulta: 2026-07-05
tipo: paper-revisado-por-pares
extraccion: doble-independiente-convergente
revista: "JMIR AI"
anio: 2025
fecha_publicacion: "2025-12-10"
recibido: "2025-07-07"
revisado: "2025-10-08"
aceptado: "2025-10-12"
editor_asignado: "Bradley Malin"
idioma_original: en
idioma_este_documento: es
nota_traduccion: "Todo el contenido en español de este documento es traducción/adaptación propia del original en inglés (ambas extracciones fechadas 2026-07-05). Las frases entre comillas seguidas de '(trad.)' son traducción directa de texto del paper; las citas breves conservadas en inglés se marcan como tales; las notas de los extractores se marcan explícitamente."
documentos_origen:
  - "kb-jmir-ai-e80247.md (ruta JMIR/GitHub)"
  - "kb-pmc12694947.md (ruta PMC/GitHub)"
relevancia_prisma_loop: "MUY ALTA — checklist de reporte para la IA como HERRAMIENTA metodológica dentro de una revisión sistemática; mapea 1:1 con lo que prisma-loop debe auto-documentar en cada corrida"
---

# PRISMA-trAIce: checklist para el reporte transparente de IA en revisiones sistemáticas de literatura

> **Documento canónico** producto de la fusión de dos extracciones independientes del mismo paper (rutas JMIR/GitHub y PMC/GitHub), convergentes en todo lo sustantivo. Las comillas con "(trad.)" indican traducción directa del inglés; el resto es paráfrasis fiel. Las discrepancias detectadas están consolidadas en §11.

## 1. Metadatos completos

| Campo | Valor |
|---|---|
| Título original | Transparent Reporting of AI in Systematic Literature Reviews: Development of the PRISMA-trAIce Checklist |
| Título (trad. propia) | Reporte transparente de la IA en revisiones sistemáticas de literatura: desarrollo del checklist PRISMA-trAIce |
| Autores | Dirk Holst, MSc (autor de correspondencia); Keno Moenck, MSc; Julian Koch, MSc; Ole Schmedemann, MSc; Thorsten Schüppstuhl, Prof. Dr. |
| Afiliación (todos) | Institute of Aircraft Production Technology, Hamburg University of Technology (TUHH), Hamburgo, Alemania |
| Revista / vol. / e-locator | JMIR AI · 2025 · Vol. 4 · e80247 |
| DOI / PMID / PMCID | 10.2196/80247 · 41370833 · PMC12694947 |
| Tipo de artículo | Original Paper — desarrollo metodológico / propuesta de guía de reporte (extensión de PRISMA 2020) |
| Fechas | Recibido 2025-07-07 · Revisado 2025-10-08 · Aceptado 2025-10-12 · Publicado 2025-12-10 |
| Editor asignado | Bradley Malin |
| Licencia del artículo | Creative Commons Attribution (CC BY 4.0), open access JMIR — se permite reproducción, adaptación y traducción con atribución |
| Financiación | Tasas de publicación cubiertas por el Open Access Fund de TUHH |
| Conflictos de interés | Ninguno declarado |
| Ética | No requirió comité de ética (propuesta metodológica, sin sujetos humanos/animales). Adhiere a la Declaración de Helsinki y a COPE. Los autores **declaran uso de IA generativa en la preparación del manuscrito** y "retienen la plena responsabilidad por la integridad científica y el contenido de este trabajo" (trad.) |
| Disponibilidad de datos | "Los datasets generados o analizados durante este estudio están disponibles en el repositorio de GitHub" (trad.) → `github.com/cqh4046/PRISMA-trAIce` (licencia MIT) |
| Material suplementario | Multimedia Appendix 1: "The PRISMA-trAIce statement — elaboration, explanation, and examples" (.docx, 28.6 KB) |

Notas de contexto (de los extractores):

- Los autores provienen de un instituto de **ingeniería de producción aeronáutica**, no de medicina ni epidemiología. Eso explica el énfasis en que la checklist sea **agnóstica de disciplina**, a diferencia de las guías médicas previas.
- El nombre completo del repo oficial expande el acrónimo: *"PRISMA-trAIce: A Proposed Checklist for Transparent Reporting of Artificial Intelligence in Comprehensive Evidence-Synthesis"* — trAIce = **tr**ansparent reporting of **AI** in evidence synthesis (juego de palabras con *trace*/trazabilidad).

## 2. Problema, vacío normativo y objetivo

### El problema (adaptación propia del original)

- Las revisiones sistemáticas de literatura (RSL/SLR) son la base de la síntesis de evidencia en todas las disciplinas, pero exigen "búsquedas extensas en varias bases de datos científicas, que a menudo arrojan miles de publicaciones potencialmente relevantes" (trad.), cada una cribada manualmente por ≥2 revisores independientes, más extracción de datos y evaluación de calidad. El proceso es "metodológicamente exigente pero también extremadamente lento e intensivo en trabajo" (trad.).
- Los LLM recientes (el paper cita GPT-4 y Claude 3) "pueden reducir la carga de trabajo manual en un 50% a 75%" (trad., cifras de la literatura citada, no medidas por los autores), con potencial de **democratizar** la metodología SLR más allá de grupos de investigación bien financiados.
- Contradicción central: los LLM sufren debilidades conocidas — "alucinaciones" y "reproducción de sesgos de los datos de entrenamiento" (trad.) — que chocan con los principios nucleares de una RS: **transparencia, trazabilidad y confianza en los resultados**.

### El vacío que llena

- PRISMA 2020 es el estándar de reporte de RS, pero no contempla la IA como herramienta.
- La extensión anunciada **PRISMA-AI** (iniciativa previa homónima) se enfoca en la IA como **objeto de estudio** de la revisión (revisiones *sobre* IA en medicina clínica), no en la IA como **herramienta metodológica** del propio proceso de revisión.
- Conclusión de los autores: existe "una ausencia total de una guía para el uso de la IA como herramienta dentro del proceso de investigación aplicable a todas las disciplinas" (trad.).

### Objetivo y resultado central

**Objetivo declarado**: desarrollar y proponer una extensión tipo checklist, agnóstica de disciplina, a la declaración PRISMA 2020, que garantice el reporte transparente de la síntesis de evidencia asistida por IA.

**Resultado**: la checklist **PRISMA-trAIce**, organizada según la estructura de una RSL (título → resumen → introducción → métodos → resultados → discusión), más un **diagrama de flujo PRISMA adaptado** que separa decisiones de IA de decisiones humanas (§5).

## 3. Métodos de los autores (cómo se construyó la checklist)

Proceso de síntesis sistemática multi-etapa (NO fue un estudio Delphi ni una reunión formal de consenso — declarado explícitamente como limitación):

1. **Revisión de literatura dirigida** sobre guías de reporte de IA consolidadas y basadas en consenso, "principalmente obtenidas de la EQUATOR Network" (trad.) (Enhancing Quality and Transparency of Health Research). Términos: *artificial intelligence*, *machine learning*, *reporting guideline*.
2. **Selección de guías fuente** — seis marcos nucleares:
   - **CONSORT-AI** (ensayos clínicos con intervención de IA)
   - **SPIRIT-AI** (protocolos de ensayos con IA)
   - **TRIPOD+AI** y **TRIPOD-LLM** (modelos de predicción / estudios con LLM)
   - **DECIDE-AI** (evaluación clínica temprana de sistemas de apoyo a decisiones con IA)
   - **GAMER** (uso de IA generativa en investigación médica)
3. **Análisis de contenido cualitativo**: se extrajeron todos los ítems individuales de esas guías y se evaluó cada uno con la pregunta guía (trad. propia): *¿este principio de reporte es relevante y aplicable al uso de IA como herramienta metodológica en una RSL?* Se excluyeron ítems no pertinentes (p. ej., seguridad del paciente).
4. **Síntesis temática**: identificación de conceptos nucleares recurrentes, agrupación en clústeres temáticos (p. ej., "identificación de la herramienta de IA", "interacción humano-IA") y **mapeo de los clústeres a la estructura de PRISMA 2020** para integración sin fricción.

La factibilidad de los ítems se evaluó "con base en conocimiento experto, pero no ha sido validada mediante un estudio formal de usuarios" (trad.). Los autores posicionan el resultado como "una propuesta bien fundamentada que ofrece una solución inmediata y puede servir de base para un proceso de consenso formal posterior impulsado por la comunidad" (trad.).

## 4. La checklist PRISMA-trAIce — tabla definitiva

**Sobre el conteo de ítems**: el texto de Resultados del paper afirma verbatim *"It comprises 14 items"*, pero la Tabla 1 publica **17 rótulos** (T1, A1, I1, M1–M10, R1–R2, D1–D2), verificados de forma independiente por ambas extracciones. Este documento adopta **los 17 rótulos** como unidad de trabajo (detalle de la discrepancia en §11).

**Sobre la obligatoriedad**: la Tabla 1 del paper NO clasifica los ítems por obligatoriedad; esos niveles provienen de la **versión viva en el repositorio GitHub oficial** (esquema *Mandatory · Highly Recommended · Recommended · Optional*). El desglose fino por cada ítem M individual no se extrajo con confianza — verificar contra el README del repo antes de usarlo como norma dura.

Traducción/adaptación fiel propia del inglés; etiquetas originales conservadas. Prefijo completo original: `P-trAIce`.

| Etiqueta | Sección RSL | Qué exige reportar (trad. propia) | Obligatoriedad (repo vivo) |
|---|---|---|---|
| **T1** | Título | Si las herramientas de IA tuvieron un papel sustancial en el proceso de revisión (p. ej., cribado primario, extracción de datos), considerar indicar el uso de asistencia de IA en el título o subtítulo. | Opcional |
| **A1** | Resumen | Resumir brevemente la(s) herramienta(s) de IA usadas, la(s) etapa(s) de la RSL en que se aplicaron y su papel principal. | Opcional |
| **I1** | Introducción | Exponer brevemente la justificación de usar herramientas de IA para tareas específicas de la revisión (p. ej., gestionar un gran volumen de literatura, mejorar la eficiencia, explorar métodos novedosos). | Recomendado |
| **M1** | Métodos · Protocolo y registro | Si se preespecificaron herramientas de IA o métodos asistidos por IA en el protocolo de la revisión, declararlo e indicar dónde puede accederse al protocolo. Reportar cualquier desviación del protocolo respecto al uso de IA. | Obligatorio/Muy recomendado (mixto)¹ |
| **M2** | Métodos · Identificación y acceso | Para cada herramienta o sistema de IA: (a) nombre, **número de versión** (si aplica) y desarrollador/proveedor; (b) detalles de **acceso** (URL, repositorio de software, disponibilidad comercial, instancia local); (c) si es herramienta o script de desarrollo propio, describir su funcionalidad central y cómo puede accederse o **replicarse** (enlace al repositorio de código, dataset o modelo base de un proceso de fine-tuning). | Obligatorio/Muy recomendado (mixto)¹ |
| **M3** | Métodos · Propósito y etapa de aplicación | Para cada herramienta de IA describir con claridad: (a) la(s) **etapa(s) específica(s) de la RSL** donde se aplicó (búsqueda, cribado, extracción de datos, evaluación de riesgo de sesgo, síntesis, redacción); (b) la(s) **tarea(s) precisa(s)** que la IA debía realizar en cada etapa. | Obligatorio/Muy recomendado (mixto)¹ |
| **M4** | Métodos · Datos de entrada | Describir los datos de entrada de cada herramienta: (a) para herramientas que aprenden o se afinan: origen, naturaleza y preparación de los datos usados para **entrenamiento, fine-tuning o calibración** específicos de esta revisión; (b) para herramientas aplicadas a los datos de la revisión: qué datos se alimentaron (resultados de búsqueda, resúmenes/abstracts, artículos a texto completo, datasets específicos para análisis). | Obligatorio/Muy recomendado (mixto)¹ |
| **M5** | Métodos · Datos de salida | Describir la salida generada por cada herramienta: **formato** (p. ej., JSON estructurado, texto plano, etiquetas de clasificación con puntajes de confianza) y detallar todo **post-procesamiento automatizado** aplicado a la salida cruda antes de presentarla a revisión o uso humano. | Obligatorio/Muy recomendado (mixto)¹ |
| **M6** | Métodos · Ingeniería de prompts (si aplica) | Para cada LLM/IA generativa: (a) los **prompts completos** por tarea; si son extensos, describir su estructura, instrucciones clave, contexto provisto (criterios de inclusión/exclusión, elementos PICO) y ejemplos few-shot; indicar dónde acceder a los prompts completos (material suplementario, repositorio); (b) **parámetros clave que influyen en la salida** (temperature, máximo de tokens, top-p); (c) el proceso de **refinamiento iterativo** de los prompts a partir de salidas iniciales o pruebas piloto. | Obligatorio/Muy recomendado (mixto)¹ |
| **M7** | Métodos · Detalles operativos y configuración | Para herramientas de IA distintas de LLM/GenAI (o además de los prompts): (a) algoritmos o modelos clave empleados (si se conocen y son relevantes); (b) configuraciones, parámetros o ajustes que puedan influir en el rendimiento (p. ej., **umbrales de clasificación** en herramientas de cribado, **parámetros del modelo de active learning**). | Obligatorio/Muy recomendado (mixto)¹ |
| **M8** | Métodos · Interacción humano-IA y supervisión | Describir el proceso de interacción y supervisión humana en cada etapa: (a) **cuántos revisores** interactuaron con/validaron las salidas de la IA por tarea; (b) si los revisores trabajaron de forma **independiente** al validar; (c) **calificaciones o entrenamiento** de los revisores para tareas asistidas por IA; (d) **cómo se presentaron** las salidas de la IA a los revisores; (e) **qué proporción de las salidas de la IA fue revisada/verificada manualmente**; (f) cómo se **resolvieron discrepancias** entre IA y revisores humanos, o entre varios humanos; (g) procesos de **calibración** de los revisores o de la herramienta; (h) el **procedimiento estándar de verificación humana** de salidas generadas por IA.² | Obligatorio/Muy recomendado (mixto)¹ |
| **M9** | Métodos · Evaluación del rendimiento de la IA | Describir los métodos para evaluar el rendimiento de la(s) herramienta(s) en las tareas específicas de la revisión (si es aplicable y factible): (a) el **estándar de referencia** usado (p. ej., decisiones humanas por consenso); (b) las **métricas** (exactitud/accuracy, sensibilidad, especificidad, precisión, recall, F1); (c) análisis de **sesgo del modelo o tasa de salidas erróneas**; (d) **pruebas piloto o fases de validación** previas a la implementación completa. | Obligatorio/Muy recomendado (mixto)¹ |
| **M10** | Métodos · Gobernanza de datos y ética | Describir cómo se gestionaron y almacenaron los datos manejados por las herramientas de IA (entrada, salida, intermedios) y las medidas de **privacidad, seguridad y cumplimiento de copyright/términos de servicio**, en especial al usar herramientas de IA de terceros basadas en la nube. | Obligatorio/Muy recomendado (mixto)¹ |
| **R1** | Resultados · Selección de estudios asistida por IA | El diagrama de flujo PRISMA y el texto deben **distinguir claramente** los registros/informes excluidos o incluidos por **decisiones de la herramienta de IA** frente a **decisiones de revisores humanos**, en cada etapa de cribado donde se usó IA. Reportar el número de registros procesados por la IA y los resultados de ese procesamiento. | Obligatorio (versión viva) |
| **R2** | Resultados · Métricas de rendimiento de la IA | Reportar los resultados de las evaluaciones de rendimiento de la(s) herramienta(s) para las tareas específicas de la revisión (según lo descrito en M9). Incluir resultados cuantitativos y **medidas de acuerdo entre IA y revisores humanos** si se evaluaron.³ | Obligatorio (versión viva) |
| **D1** | Discusión · Limitaciones del uso de IA | Discutir las limitaciones encontradas al usar la(s) herramienta(s) (problemas técnicos, sesgos identificados, retos de ingeniería de prompts, salidas inesperadas, límites de rendimiento en subtareas específicas) y cómo esas limitaciones pudieron influir en el proceso de revisión o en los hallazgos. | Recomendado |
| **D2** | Discusión · Implicaciones del uso de IA | Discutir brevemente la experiencia de usar herramientas de IA en la revisión: beneficios percibidos (ganancias de eficiencia, capacidad de manejar datasets más grandes) y retos. Reflexionar sobre la usabilidad de las herramientas y las implicaciones para revisiones futuras similares. | Opcional |

Notas al pie de la tabla:

1. ¹ Los ítems M1–M10 aparecen en el README del repo como mezcla de *Mandatory* y *Highly Recommended*; el desglose ítem a ítem no se extrajo con confianza en ninguna de las dos pasadas — pendiente de verificación directa contra el repo.
2. ² En el texto fuente de M8 los últimos sub-ítems aparecen rotulados "f./g./f." (errata aparente del original); aquí se renumeran como g/h conservando el contenido íntegro.
3. ³ "Medidas de acuerdo" sugiere estadísticos tipo **kappa de Cohen**, pero el paper no fija un estadístico concreto (nota del extractor).

## 5. El diagrama de flujo PRISMA-trAIce (Figura 1)

Adaptación del diagrama de flujo PRISMA 2020 con estas modificaciones (adaptación propia):

- Distingue entre **herramientas administrativas basadas en reglas** (p. ej., deduplicación) y **sistemas de IA evaluativos** (que toman decisiones de inclusión/exclusión).
- Añade **campos separados** para reportar registros cribados por sistemas de IA vs. por revisores humanos — cita breve del original: *"the adapted diagram provides specific fields to report the number of records screened separately by AI systems versus human reviewers"*.
- Documenta por separado las **razones de exclusión según cada método** (IA vs. humano).
- Mantiene la estructura de flujo familiar de PRISMA 2020 para no romper la práctica establecida; aporta "una visión más granular e inmediata del rol de la IA en el proceso de cribado" (trad.).

Implicación operativa (R1 + Figura 1) — el reporte debe registrar por etapa:

- N.º de registros procesados por la IA y desenlace de ese procesamiento.
- N.º de registros excluidos/incluidos por decisión de IA vs. por decisión humana, **por separado**.

`[Nota de los extractores]` El repo GitHub publica el diagrama en `.png` y `.webp` reutilizables (licencia MIT); la imagen no se extrajo pero está disponible allí.

## 6. Qué aporta a un sistema agéntico de revisiones sistemáticas (mapeo a prisma-loop)

`[Elaboración propia de los extractores a partir del paper — no es contenido del artículo]`

### 6.1 Requisitos de diseño derivados (checklist → arquitectura)

1. **Pre-especificación en el protocolo (M1)**: declarar *ex ante* el uso de agentes/IA en el protocolo de la revisión (PROSPERO/OSF) y reportar desviaciones — funciona como anti p-hacking metodológico. Sugiere mantener una **plantilla de protocolo** con sección de IA pre-redactada.
2. **Manifiesto de herramientas (M2)**: cada corrida debe registrar nombre, versión exacta del modelo/herramienta, desarrollador y forma de acceso. Para componentes propios, apuntar al **commit del repo** (más dataset o modelo base si hubo fine-tuning).
3. **Bitácora por etapa (M3)**: log estructurado de qué agente/modelo intervino en cada fase PRISMA (búsqueda, cribado título/abstract, texto completo, extracción, riesgo de sesgo, síntesis, redacción) y con qué tarea exacta.
4. **Trazabilidad de entradas (M4)**: persistir qué datos vio cada modelo (queries, abstracts, textos completos) — el "qué se le dio" es tan reportable como el "qué devolvió".
5. **Salidas estructuradas + post-proceso declarado (M5)**: emitir JSON con etiquetas y puntajes de confianza; documentar cualquier filtro/normalización automática entre la salida cruda del LLM y lo que ve el humano.
6. **Prompts como artefactos de primera clase (M6)**: versionar los prompts completos (con criterios de elegibilidad/PICO embebidos y ejemplos few-shot), registrar temperature/max tokens/top-p, y documentar cada iteración de refinamiento. Publicarlos en el material suplementario o repositorio de la revisión.
7. **Configuración de componentes no-LLM (M7)**: registrar también umbrales de clasificación, parámetros de active learning y ajustes de cualquier herramienta no generativa del pipeline.
8. **Human-in-the-loop cuantificado (M8)**: el sistema debe poder responder — cuántos humanos validaron, si validaron de forma independiente, **qué proporción de decisiones de la IA fue verificada manualmente**, y cómo se resolvieron discrepancias (regla de desempate), más calibración. Esto exige **contadores nativos, no reconstrucción a posteriori**. El paper fija la postura de fondo: "el control de calidad humano riguroso es obligatorio" (trad.).
9. **Evaluación contra estándar de referencia (M9/R2)**: incluir una fase de calibración/piloto contra decisiones humanas por consenso, reportando accuracy, sensibilidad, especificidad, precisión, recall y F1, más acuerdo IA-humano (p. ej., kappa). En cribado de RS, la **sensibilidad** (no perder estudios elegibles) es la métrica crítica.
10. **Diagrama de flujo bifurcado (R1)**: el generador del flow diagram debe separar los conteos de exclusión por IA vs. por humano en cada etapa — exactamente el formato del diagrama PRISMA-trAIce. Nunca fusionar en un solo número las exclusiones de la máquina y las del humano.
11. **Gobernanza de datos (M10)**: declarar dónde se almacenan entradas/salidas/intermedios, y el cumplimiento de términos de servicio y copyright al enviar textos completos a APIs de terceros en la nube.
12. **Secciones automáticas de transparencia (T1, A1, I1, D1, D2)**: el redactor del informe final debe insertar por defecto la mención de asistencia de IA en título/resumen, la justificación del uso en la introducción, y las limitaciones e implicaciones del uso de IA en la discusión.

### 6.2 Aplicación directa a prisma-loop

- **Mapa 1:1 con el reporte de corrida**: prisma-loop puede auto-generar el cumplimiento de los 17 rótulos en cada ejecución — M2 (modelo/versión/proveedor por agente), M6 (prompts completos + temperature/top-p, ya versionados en config), M5 (formatos JSON de salida + post-procesado), M8 (gold HITL: cuántos humanos, proporción verificada, resolución de discrepancias), M9/R2 (métricas contra gold set), R1 (flow diagram con conteos IA vs. humano separados).
- **El flow diagram extendido es implementable de inmediato**: prisma-loop ya distingue qué exclusiones son del driver y cuáles del humano; basta emitir los campos separados.
- **M1 sugiere plantilla de protocolo**: pre-declarar el uso de agentes en el protocolo PROSPERO/OSF antes de la corrida.
- **Estándar complementario, no competidor**: trAIce es *reporting*, no *conducta*; convive con PRISMA 2020 y con las métricas internas de prisma-loop.
- **Es una guía viva en GitHub con licencia MIT**: se puede vendorear el checklist como asset versionado y rastrear sus releases anuales.

## 7. Gobernanza del estándar: la "guía viva" (living guideline)

**Racional**: los procesos formales de consenso (Delphi) son tan lentos que, dada la velocidad de evolución de la IA, "un proceso de consenso formal, aunque es el estándar, corre el riesgo de entregar una guía meticulosamente elaborada para un panorama tecnológico ya obsoleto" (trad.). Argumento central de los autores (trad. propia): *el riesgo inmediato del uso no transparente de herramientas de IA pesa más que el riesgo de introducir una guía preliminar bien razonada*.

Infraestructura y mecanismo de actualización:

- **Repositorio GitHub** (`github.com/cqh4046/PRISMA-trAIce`, licencia MIT): "la única fuente de verdad del checklist, permitiendo un desarrollo transparente y con control de versiones" (trad.). Clasifica los ítems por obligatoriedad (Mandatory / Highly Recommended / Recommended / Optional) — dimensión ausente de la tabla del paper.
- **Hub comunitario en Discord** (`discord.gg/DrDFBpEb53`): "colaboración rápida y de baja fricción" (trad.).
- **Ciclos anuales de revisión** que incorporan retroalimentación de la comunidad.
- **Hoja de ruta en 3 fases** (según el repo): (1) movilización comunitaria para consenso experto, (2) registro en la red EQUATOR, (3) validación Delphi formal. Los contribuidores son elegibles para coautoría en la publicación de consenso prevista.
- **Visión final**: constituir "un comité directivo formal a partir de miembros dedicados de la comunidad experta, al que en última instancia se transferirá la custodia del estándar" (trad.).

## 8. Posicionamiento frente a marcos previos

Dos distinciones definen el nicho de PRISMA-trAIce:

1. **Distinción de foco**: CONSORT-AI, SPIRIT-AI, TRIPOD+AI, TRIPOD-LLM y DECIDE-AI regulan la IA como **objeto/intervención de investigación** — "la IA es el sujeto de la investigación… guían el reporte del desempeño e impacto de la IA como desenlace del estudio" (trad.); PRISMA-AI (iniciativa previa) apunta a revisiones *sobre* IA. PRISMA-trAIce regula la IA como **herramienta metodológica del propio proceso de síntesis de evidencia**.
2. **Distinción de alcance**: GAMER ofrece "recomendaciones valiosas" pero está "explícitamente adaptada al campo de la medicina" (trad.). PRISMA-trAIce es **agnóstica de disciplina**, como extensión del estándar PRISMA 2020 de adopción universal (aplicable en ingeniería, ciencias sociales, etc.).

| Marco | Foco | Diferencia con PRISMA-trAIce |
|---|---|---|
| PRISMA 2020 | Reporte de RS (sin IA) | Base estructural que trAIce extiende |
| PRISMA-AI (anunciada) | RS **sobre** IA en medicina clínica | IA como objeto de estudio, no como herramienta |
| CONSORT-AI / SPIRIT-AI | Ensayos clínicos con intervención de IA | IA como sujeto de la investigación |
| TRIPOD+AI / TRIPOD-LLM | Modelos de predicción / estudios con LLM | Ídem: IA como sujeto |
| DECIDE-AI | Evaluación clínica temprana de sistemas de decisión con IA | Ídem |
| GAMER | IA generativa en investigación médica | Valiosa pero limitada a medicina |
| **PRISMA-trAIce** | **IA como herramienta del proceso de revisión** | **Agnóstica de disciplina + específica de RSL**; "directamente integrable en el flujo de trabajo establecido de las revisiones sistemáticas en cualquier campo" (trad.) |

Frase de cierre del posicionamiento: "Al enfocarse en la IA como herramienta metodológica de manera agnóstica a la disciplina y específica para SLR, PRISMA-trAIce complementa las guías existentes y atiende una necesidad crítica no cubierta de transparencia en la próxima generación de síntesis de evidencia." (trad.)

## 9. Limitaciones

### Declaradas por los autores

1. **Sin consenso formal**: la checklist "es el resultado de una adaptación sistemática, no de un ejercicio formal de construcción de consenso a gran escala, como un estudio Delphi" (trad.), ni de una reunión de expertos.
2. **Ítems sin validación empírica**: "aunque anclados en principios establecidos, sus ítems aún no han sido validados empíricamente en contextos de investigación diversos" (trad.).
3. **Factibilidad no probada con usuarios**: se evaluó con conocimiento experto del equipo, sin estudio formal de usuarios.

Los autores **reencuadran** estas limitaciones como justificación de "un enfoque más moderno y ágil de fijación de estándares" (trad.) — guía viva ahora, consenso comunitario después — no como defecto a corregir por la vía tradicional.

### Observadas por los extractores (no declaradas en el paper)

- La síntesis de fuentes es 100% de origen médico-clínico (red EQUATOR), aunque el resultado se proclama agnóstico de disciplina.
- Los autores provienen de ingeniería de producción aeronáutica, no de epidemiología.
- Existe la inconsistencia interna 14 vs. 17 ítems (§11).
- El artículo **no evalúa herramientas concretas** (Rayyan, ASReview, Elicit, Covidence, DistillerSR no se mencionan) ni reporta métricas empíricas propias (recall/precision/kappa): es una guía de **reporte**, no un benchmark. Los porcentajes de 50–75% de reducción de carga provienen de la literatura citada en su introducción.

## 10. Conclusiones del artículo

- "La integración de la IA en las revisiones sistemáticas marca un momento disruptivo en la síntesis de evidencia: promete eficiencia pero exige un compromiso renovado con el rigor." (trad.)
- La ausencia de reporte estandarizado es "una amenaza crítica para la transparencia y la confiabilidad de estas revisiones asistidas por IA" (trad.).
- PRISMA-trAIce "provee una herramienta fundacional para atender este desafío, con el objetivo de mejorar de inmediato la transparencia mientras allana el camino hacia un estándar formal respaldado por la comunidad" (trad.); los autores invitan explícitamente a la comunidad científica a sumarse a un proceso de consenso de ciencia abierta.

## 11. Nota única de discrepancias y procedencia de la extracción

Este documento fusiona **dos extracciones independientes** realizadas el 2026-07-05: una por la ruta JMIR→PMC+GitHub y otra por la ruta PMC (5 pases seccionales de WebFetch)+GitHub. Ambas convergieron en todo el contenido sustantivo (metadatos, 17 rótulos, texto de cada ítem, métodos, gobernanza), lo que eleva la confianza del documento. Discrepancias y cabos sueltos, consolidados:

1. **14 vs. 17 ítems (inconsistencia INTERNA del paper, no entre extracciones)**: el texto de Resultados dice verbatim *"It comprises 14 items"*, pero la Tabla 1 enumera **17 rótulos** (T1, A1, I1, M1–M10, R1–R2, D1–D2), verificados independientemente por ambas extracciones (una de ellas contó dos veces). Dos reconciliaciones aritméticas posibles, ninguna confirmada por el paper: (a) 14 = 17 menos los 3 ítems Opcionales (T1, A1, D2); (b) 14 = Métodos+Resultados+Discusión (10+2+2), con T1/A1/I1 como ítems de encabezado adicionales. **Decisión canónica: trabajar con los 17 rótulos**, que es lo que publica la Tabla 1 y el repo vivo.
2. **Niveles de obligatoriedad**: NO provienen de la tabla del paper sino del README del repositorio GitHub (guía viva, esquema Mandatory/Highly Recommended/Recommended/Optional). Fiables para T1/A1 (Opcional), I1/D1 (Recomendado), D2 (Opcional) y R1/R2 (Obligatorio); el desglose por cada M individual no se extrajo con confianza en ninguna pasada.
3. **Errata de sub-rotulado en M8**: el texto fuente rotula los últimos sub-ítems "f./g./f." (aparente errata del original); se renumeraron aquí como g/h sin pérdida de contenido.
4. **Referencia JAMIA (doi:10.1093/jamia/ocaf030)**: una extracción la registra como "Li M et al." y la otra como "Li Y, Datta S, Rastegar-Mojarad M, et al."; el DOI coincide. Discrepancia menor de inicial de autor sin resolver — el DOI es el identificador confiable.
5. **Fuente efectiva única**: ambas rutas terminaron extrayendo del espejo PMC (el HTML de ai.jmir.org es una SPA que no renderiza para fetchers, el PDF descargado no tenía capa de texto extraíble y Europe PMC solo devolvió su interfaz). La "independencia" fue de procedimiento (pases y prompts distintos), no de fuente física; la verificación cruzada con el repo GitHub sí fue común a ambas.
6. **No obtenido (pendientes)**: (a) el contenido del **Multimedia Appendix 1** ("elaboration, explanation, and examples", .docx 28.6 KB) — contiene la explicación extendida y ejemplos por ítem; descargable desde la página del artículo o el repo; (b) el **mapeo ítem→guía fuente** (de cuál de CONSORT-AI/TRIPOD-LLM/etc. deriva cada ítem) — la Tabla 1 no lo incluye; (c) el mapeo de ítems trAIce a números de ítem de PRISMA 2020 — confirmado que NO existe en la Tabla 1; (d) la imagen de la **Figura 1** (disponible en el repo en .png/.webp, MIT); (e) el texto verbatim en inglés de párrafos completos (la extracción pasó por un modelo intermedio que condensa).
7. **Verificación negativa**: el artículo **no cita** RAISE ni CANGARU (verificado contra la lista de referencias del espejo PMC).

## 12. Referencias clave citadas (selección para automatización de RS con IA)

### Guías de reporte fuente de PRISMA-trAIce

1. Page MJ, McKenzie JE, Bossuyt PM, et al. *The PRISMA 2020 statement: an updated guideline for reporting systematic reviews*. BMJ. 2021;372:n71. doi:10.1136/bmj.n71 — el estándar base que PRISMA-trAIce extiende.
2. Liu X, Cruz Rivera S, Moher D, Calvert MJ, Denniston AK. *Reporting guidelines for clinical trial reports for interventions involving artificial intelligence: the CONSORT-AI extension*. Nat Med. 2020;26(9):1364–1374. doi:10.1038/s41591-020-1034-x
3. Cruz Rivera S, Liu X, Chan AW, et al. *Guidelines for clinical trial protocols for interventions involving artificial intelligence: the SPIRIT-AI extension*. Nat Med. 2020;26(9):1351–1363. doi:10.1038/s41591-020-1037-7
4. Collins GS, Moons KGM, Dhiman P, et al. *TRIPOD+AI statement: updated guidance for reporting clinical prediction models that use regression or machine learning methods*. BMJ. 2024;385:e078378. doi:10.1136/bmj-2023-078378
5. Gallifant J, Afshar M, Ameen S, et al. *The TRIPOD-LLM reporting guideline for studies using large language models*. Nat Med. 2025;31(1):60–69. doi:10.1038/s41591-024-03425-5
6. Vasey B, Nagendran M, Campbell B, et al. *Reporting guideline for the early stage clinical evaluation of decision support systems driven by artificial intelligence: DECIDE-AI*. BMJ. 2022;377:e070904. doi:10.1136/bmj-2022-070904
7. Luo X, Tham YC, Giuffrè M, et al. *Reporting guideline for the use of generative artificial intelligence tools in MEdical research: the GAMER statement*. BMJ Evid Based Med. 2025. doi:10.1136/bmjebm-2025-113825

### LLM/IA aplicados a revisiones sistemáticas

8. Delgado-Chaves FM, Jennings MJ, Atalaia A, et al. *Transforming literature screening: the emerging role of large language models in systematic reviews*. PNAS. 2025;122(2):e2411962122. doi:10.1073/pnas.2411962122
9. Li M [o Li Y según extracción, ver §11.4], Datta S, Rastegar-Mojarad M, et al. *Enhancing systematic literature reviews with generative artificial intelligence: development, applications, and performance evaluation*. J Am Med Inform Assoc. 2025;32(4):616–625. doi:10.1093/jamia/ocaf030
10. Lieberum JL, Toews M, Metzendorf MI, et al. *Large language models for conducting systematic reviews: on the rise, but not yet ready for use — a scoping review*. J Clin Epidemiol. 2025;181:111746. doi:10.1016/j.jclinepi.2025.111746
11. Abogunrin S, Muir JM, Zerbini C, Sarri G. *How much can we save by applying artificial intelligence in evidence synthesis?* Front Pharmacol. 2025;16:1454245. doi:10.3389/fphar.2025.1454245
12. Michelson M, Reuter K. *The significant cost of systematic reviews and meta-analyses: a call for greater involvement of machine learning*. Contemp Clin Trials Commun. 2019;16:100443. doi:10.1016/j.conctc.2019.100443

### Riesgos, alucinaciones y ética

13. Siemens W, von Elm E, Binder H, et al. *Opportunities, challenges and risks of using artificial intelligence for evidence synthesis*. BMJ Evid Based Med. 2025. doi:10.1136/bmjebm-2024-113320
14. Kim Y, et al. *Medical hallucination in foundation models and their impact on healthcare*. (preprint). doi:10.48550/arXiv.2503.05777
15. Asgari E, Montaña-Brown N, Dubois M, et al. *A framework to assess clinical safety and hallucination rates of LLMs for medical text summarisation*. NPJ Digit Med. 2025;8(1):274. doi:10.1038/s41746-025-01670-7

### Recurso vivo

16. Repositorio oficial (guía viva, fuente única de verdad del checklist): https://github.com/cqh4046/PRISMA-trAIce (licencia MIT) · Comunidad: https://discord.gg/DrDFBpEb53

## 13. Abreviaturas del artículo

AI (inteligencia artificial) · CONSORT-AI · DECIDE-AI · EQUATOR · GAMER · PRISMA · PRISMA-AI · PRISMA-trAIce · SLR (systematic literature review) · SPIRIT-AI · TRIPOD · TRIPOD+AI · TRIPOD-LLM
