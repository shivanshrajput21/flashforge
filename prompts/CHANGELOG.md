# Prompt Changelog

Track prompt iterations, observed failure modes, and metrics across versions.

| Version | Problem observed | What I changed | Valid-JSON rate | Usable-card rate |
| :--- | :--- | :--- | :--- | :--- |
| **v1** | Baseline | Initial simple prompt | - | - |
| **v2** | Non-JSON text / unconstrained output in v1 | Added strict JSON array instruction, exact key names, difficulty enum, and one-shot example | - | - |
| **v3** | Trivia/shallow definitions in v2; need deeper conceptual rigor | Prioritized mechanisms, cause-and-effect reasoning, comparisons, strict anti-trivia rules, standalone question clarity, source fidelity, and internal quality filtering | - | - |

## Version Details

### v1 (Baseline)
- Minimal prompt asking for question-and-answer pairs without structural constraints.
- Used to benchmark baseline model behavior and establish parse failure rates without formatting instructions.

### v2 (JSON Schema Enforcement)
- Added explicit JSON array formatting instructions with forbidden markdown fence directives.
- Defined required keys (`question`, `answer`, `topic`, `difficulty`) and enum restrictions for difficulty (`easy`, `medium`, `hard`).
- Added one-shot JSON example.

### v3 (Conceptual Depth & Quality Filtering)
- **Design Objectives**:
  - Elevate flashcard utility from rote definition recall to deep conceptual understanding.
  - Test mechanisms, relationships, causality, processes, and trade-offs rather than superficial vocabulary.
  - Strict anti-trivia rules: reject low-yield facts and redundant cards.
  - Enforce standalone clarity: every question is self-contained and answerable without original context.
  - Strict source fidelity: adhere strictly to provided text without hallucination.
  - Maintain concise answers strictly within the 40-word limit while retaining high technical fidelity.
- **Output Compatibility**:
  - Preserves exact JSON schema (`question`, `answer`, `topic`, `difficulty`) for full compatibility with Pydantic validation, Streamlit UI, CSV/Anki exporters, and benchmark tools.

## Benchmark Results
*(To be populated after running `compare_prompts.py` across benchmark test corpus)*


