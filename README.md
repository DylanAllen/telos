# Telos: AI-Native Execution Engine & Intent-to-Execution System

[![CI](https://github.com/dylanallen/telos/actions/workflows/ci.yml/badge.svg)](https://github.com/dylanallen/telos/actions)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Type Checking](https://img.shields.io/badge/types-strict-green.svg)](https://github.com/pydantic/pydantic)
[![Verification](https://img.shields.io/badge/SMT-Z3--Solver-purple.svg)](https://github.com/Z3Prover/z3)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **A post-text, AI-native programming paradigm.**  
> Bypassing human-readable text syntax in favor of direct, typed Abstract Syntax Trees (ASTs), formal SMT verification, sandboxed execution, and content-addressable storage.

---

## The Core Thesis

All traditional programming languages (C, Python, JavaScript, Rust), frameworks, and file hierarchies were engineered specifically to compensate for the cognitive limitations of the human brain:
- **Humans require text syntax**, which introduces syntax errors, indentation bugs, delimiter mismatches, and parsing ambiguities.
- **Humans have limited working memory**, forcing modular abstraction, descriptive variable naming, and directory hierarchies.

Large Language Models (LLMs) and autonomous agents operate differently:
1. **Agents operate natively on syntax trees and tokens, not text files.** Forcing an agent to emit formatted ASCII text files and parse compiler error logs is an inefficient translation tax.
2. **Abstract Syntax Trees (ASTs) eliminate syntax errors.** Constrained decoding against an algebraic AST schema drops syntax errors to zero by mathematical definition.
3. **Intent and Implementation are decoupled.** Humans specify *invariants, inputs, outputs, and constraints* (the "What"). Autonomous agents synthesize the *intermediate representation and execution graph* (the "How").
4. **Code is data; directories are obsolete.** Functions are content-addressed via cryptographic hashes of normalized AST nodes. There is no file system, no dependency hell, and no namespace collisions.

---

## System Architecture

```
+-------------------------------------------------------------+
|                      1. Intent Layer                        |
|  - Human Declarative Input (Natural Language or DIL YAML)   |
|  - Invariants, Pre/Post-conditions, Input/Output Schemas   |
+-------------------------------------------------------------+
                              │
                              ▼
+-------------------------------------------------------------+
|               2. Architect Agent (Validator)                |
|  - Socratic boundary clarification                          |
|  - Emits Formal Specification Contract                      |
+-------------------------------------------------------------+
                              │
                              ▼
+-------------------------------------------------------------+
|                 3. Builder Agent (Compiler)                 |
|  - Constrained Decoding via `instructor` + Pydantic v2      |
|  - Targets JSON-Serialized AST Schema (Algebraic Types)     |
+-------------------------------------------------------------+
                              │
                              ▼
+-------------------------------------------------------------+
|         4. Verification & Physics Engine (Sanity Loop)       |
|  - Static Type Checking across all branches                 |
|  - Z3 SMT Solver for Mathematical Invariants & Safety       |
|  - Sandboxed Evaluation (Tree-Walker / Wasm VM)             |
|  * If failed: programmatic diagnostic loop to Builder Agent |
+-------------------------------------------------------------+
                              │ (On Success)
                              ▼
+-------------------------------------------------------------+
|            5. Content-Addressed Storage (CAS)               |
|  - SHA-256 Hash of RFC-8785 Canonical AST                   |
|  - Immutable Key-Value Graph Store (SQLite / RocksDB)       |
+-------------------------------------------------------------+
```

---

## Roadmap & Implementation Status

| Phase | Milestone | Status | Description |
| :--- | :--- | :--- | :--- |
| **Phase 1** | **Core AST Schema & Local Interpreter** | ✅ Complete | Discriminated Pydantic v2 AST schema & sandboxed tree-walking runtime with step budgets. |
| **Phase 2** | **Static Type Checker & Z3 SMT Verifier** | ✅ Complete | Static branch type checker & formal verification of invariants and division safety with Z3 counterexamples. |
| **Phase 3** | **Builder Agent & Constrained Generation** | ✅ Complete | Agentic compiler using `instructor` to translate natural language intent to validated ASTs with zero syntax errors. |
| **Phase 4** | **The Closed Self-Healing Loop** | ✅ Complete | Autonomous closed loop: Builder $\to$ Type Checker $\to$ Z3 Verifier $\to$ Interpreter with automatic remediation. |
| **Phase 5** | **Content-Addressable Storage (CAS)** | ✅ Complete | RFC-8785 canonical serialization, SHA-256 hashing, and SQLite graph linking. |

---

## Quickstart

### Prerequisites
- Python 3.11+
- Virtual environment (`venv` recommended)

### Installation
```bash
git clone https://github.com/dylanallen/telos.git
cd telos

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

### Running Tests
Execute the comprehensive test suite across all implemented phases:
```bash
pytest -v
```

---

## Usage Examples

### 1. Pure AST Construction & Execution
```python
from src.schema.nodes import BinaryOp, LiteralInt
from src.runtime.interpreter import Interpreter

# Construct AST for: (12 * 4) + 8
ast = BinaryOp(
    op="add",
    left=BinaryOp(
        op="mul",
        left=LiteralInt(value=12),
        right=LiteralInt(value=4),
    ),
    right=LiteralInt(value=8),
)

interpreter = Interpreter()
result = interpreter.eval(ast)
print(result)  # Output: 56
```

### 2. Static Type Checking
```python
from src.schema.nodes import FunctionDeclaration, Parameter, ReturnStatement, BinaryOp, VariableRef
from src.verifier.type_checker import TypeChecker

# Define a typed function
func = FunctionDeclaration(
    name="add_numbers",
    parameters=[
        Parameter(name="a", param_type="int"),
        Parameter(name="b", param_type="int"),
    ],
    return_type="int",
    body=[
        ReturnStatement(
            value=BinaryOp(
                op="add",
                left=VariableRef(name="a"),
                right=VariableRef(name="b"),
            )
        )
    ],
)

checker = TypeChecker()
result = checker.check_function(func)
print(result.status)  # "APPROVED"
```

### 3. Formal Invariant Verification via Z3 SMT Solver
```python
from src.schema.nodes import FunctionDeclaration, Parameter, ReturnStatement, BinaryOp, VariableRef
from src.verifier.smt_solver import SMTVerifier

# Function divide(x: int, y: int) -> int with invariant "y != 0"
func = FunctionDeclaration(
    name="divide",
    parameters=[
        Parameter(name="x", param_type="int"),
        Parameter(name="y", param_type="int"),
    ],
    return_type="int",
    body=[
        ReturnStatement(
            value=BinaryOp(
                op="div",
                left=VariableRef(name="x"),
                right=VariableRef(name="y"),
            )
        )
    ],
    invariants=["y != 0"],
)

verifier = SMTVerifier()
# Unbound y can be 0, violating the invariant:
verification = verifier.verify_function(func, preconditions=None)

print(verification.status)          # "REJECTED"
print(verification.error_type)      # "INVARIANT_VIOLATION"
print(verification.counterexample)  # {"y": 0}
```

### 4. Natural Language Intent Compilation via Builder Agent
```python
from src.compiler.builder import BuilderAgent

agent = BuilderAgent()
ast = agent.build(
    "Write a function that calculates total cost given item_price, quantity, and tax_rate."
)

print(ast.name)        # "calculate_total_cost"
print(ast.parameters)  # item_price (float), quantity (int), tax_rate (float)
print(ast.return_type) # "float"
```

### 5. Autonomous Closed Self-Healing Loop
```python
from src.orchestration.loop import SelfHealingLoop

loop = SelfHealingLoop()
result = loop.run(
    intent="Divide x by y, and guarantee y can be 0 while the function never errors.",
    test_inputs={"x": 10, "y": 0},
)

print(result.status)    # "SUCCESS"
print(result.attempts)  # 2 (Attempt 1 intercepted by SMT, Attempt 2 synthesized guard)
print(result.output)    # 0
```

### 6. Content-Addressable Storage & Function Linking
```python
from src.schema.nodes import FunctionDeclaration, Parameter, ReturnStatement, BinaryOp, VariableRef, FunctionCall
from src.storage.cas import ContentAddressedStore
from src.runtime.interpreter import Interpreter, Environment

cas = ContentAddressedStore(":memory:")

# Store Function A: add(a, b) -> a + b
func_a = FunctionDeclaration(
    name="add",
    parameters=[Parameter(name="a", param_type="int"), Parameter(name="b", param_type="int")],
    return_type="int",
    body=[ReturnStatement(value=BinaryOp(op="add", left=VariableRef(name="a"), right=VariableRef(name="b")))],
)
hash_a = cas.put(func_a)

# Function B calls Function A by its content hash!
func_b = FunctionDeclaration(
    name="double_add",
    parameters=[Parameter(name="x", param_type="int")],
    return_type="int",
    body=[ReturnStatement(value=FunctionCall(target_hash=hash_a, arguments=[VariableRef(name="x"), VariableRef(name="x")]))],
)
hash_b = cas.put(func_b)

# Execute Function B: Interpreter traverses CAS automatically
interpreter = Interpreter(cas=cas)
env = Environment()
env.define("x", 21, "int")
print(interpreter.execute_function(func_b, env))  # Output: 42
```

---

## Project Structure

```
telos/
├── pyproject.toml              # Project dependencies and configurations
├── README.md                   # Repository documentation & guide
├── SPECIFICATION.md            # Detailed system design specification
├── CONTRIBUTING.md             # Contribution guidelines and engineering standards
├── LICENSE                     # MIT License
├── src/
│   ├── schema/                 # Algebraic AST node definitions
│   │   ├── nodes.py            # Pydantic v2 discriminated union models
│   │   └── __init__.py
│   ├── runtime/                # Sandboxed execution environment
│   │   ├── interpreter.py      # Tree-walking interpreter with instruction limits
│   │   └── __init__.py
│   ├── verifier/               # Pre-flight verification engine
│   │   ├── diagnostics.py      # Structured error payloads for self-healing
│   │   ├── type_checker.py     # Static branch type analysis
│   │   ├── smt_solver.py       # Z3 SMT solver for invariants & safety
│   │   └── __init__.py
│   ├── compiler/               # LLM compiler frontend
│   │   ├── builder.py          # Constrained generation using instructor
│   │   └── __init__.py
│   ├── orchestration/          # Closed-loop autonomous pipeline
│   │   ├── loop.py             # Self-healing orchestrator with retry budgets
│   │   └── __init__.py
│   └── storage/                # Content-Addressable Storage (CAS)
│       ├── cas.py              # RFC-8785 canonicalization & SQLite graph store
│       └── __init__.py
└── tests/
    ├── test_phase1.py          # Core AST & runtime evaluation tests (22 tests)
    ├── test_phase2.py          # Static typing & Z3 SMT verification tests (13 tests)
    ├── test_phase3.py          # Builder agent & constrained decoding tests (5 tests)
    ├── test_phase4.py          # Closed self-healing loop tests (4 tests)
    └── test_phase5.py          # Content-addressable storage & linking tests (5 tests)
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
