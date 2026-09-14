# Contributing to Telos

Thank you for your interest in contributing to **Telos: The AI-Native Execution Engine**!

Telos is built upon a fundamental architectural premise: **Software should not be authored, parsed, or maintained as human-oriented ASCII text files.** Instead, autonomous agents synthesize and verify algebraic Abstract Syntax Trees directly.

---

## Core Engineering Principles

1. **No Human Code Syntax**: Never add code generators that emit text Python/Rust/JS code strings as execution targets. The target representation is always the structured AST schema.
2. **Mathematical Correctness by Construction**: Schema validation via Pydantic v2 discriminated unions eliminates syntax errors. Invariants must be formally verified using SMT (Z3).
3. **Strict Bottom-Up Phasing**: Components must strictly build on validated lower layers:
   - Phase 1: Core AST Schema & Local Interpreter
   - Phase 2: Static Type Checker & Z3 SMT Verifier
   - Phase 3: Builder Agent & Constrained Generation
   - Phase 4: The Closed Self-Healing Loop
   - Phase 5: Content-Addressable Storage (CAS)
4. **100% Test Coverage**: Every feature, statement type, expression operator, and verifier check must be covered by automated tests under `tests/`.

---

## Development Setup

### 1. Clone & Set Up Virtual Environment
```bash
git clone https://github.com/dylanallen/telos.git
cd telos

python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -e ".[dev]"
```

### 3. Run Tests
```bash
pytest -v
```

---

## Pull Request Guidelines

- Ensure `pytest -v` passes with zero failures or warnings.
- Keep commits focused, descriptive, and atomic.
- Include unit tests for any new AST nodes, verifier capabilities, or execution behaviors.
- Follow PEP 8 and use type hints throughout the codebase.
