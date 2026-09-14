import os
import tempfile
import pytest

from src.runtime.interpreter import Environment, Interpreter
from src.schema.nodes import (
    AssignStatement,
    BinaryOp,
    FunctionCall,
    FunctionDeclaration,
    LiteralFloat,
    LiteralInt,
    Parameter,
    ReturnStatement,
    VariableRef,
)
from src.storage.cas import (
    ContentAddressedStore,
    canonicalize_ast,
    compute_ast_hash,
)
from src.verifier.type_checker import TypeChecker


# --- Phase 5 Specification Acceptance Test ---
def test_phase5_acceptance_criterion():
    """Phase 5 Acceptance Test from Specification:

    Store Function A (Add) in the database. Retrieve its hash.
    Author Function B (Compute Total) whose AST references Function A's hash.
    Execute Function B and verify that the interpreter traverses the CAS to execute Function A.
    """
    cas = ContentAddressedStore(":memory:")

    # 1. Author Function A: add(a: int, b: int) -> int { return a + b }
    func_a = FunctionDeclaration(
        name="add",
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

    hash_a = cas.put(func_a)
    assert hash_a.startswith("sha256:")
    assert cas.contains(hash_a)

    # 2. Author Function B: compute_total(base: int, tax: int) -> int { return add(base, tax) }
    func_b = FunctionDeclaration(
        name="compute_total",
        parameters=[
            Parameter(name="base", param_type="int"),
            Parameter(name="tax", param_type="int"),
        ],
        return_type="int",
        body=[
            ReturnStatement(
                value=FunctionCall(
                    target_hash=hash_a,
                    arguments=[VariableRef(name="base"), VariableRef(name="tax")],
                )
            )
        ],
    )

    hash_b = cas.put(func_b)
    assert hash_b.startswith("sha256:")
    assert hash_b != hash_a

    # 3. Verify dependency graph edges in CAS
    deps = cas.get_dependencies(hash_b)
    assert deps == [hash_a]

    dependents = cas.get_dependents(hash_a)
    assert dependents == [hash_b]

    # 4. Verify static type checking traverses CAS
    checker = TypeChecker(cas=cas)
    check_res = checker.check_function(func_b)
    assert check_res.status == "APPROVED"

    # 5. Execute Function B in the interpreter with CAS linked
    # Notice: function_registry is completely EMPTY; interpreter must traverse CAS!
    interpreter = Interpreter(cas=cas)
    env = Environment()
    env.define("base", 100, "int")
    env.define("tax", 15, "int")

    result = interpreter.execute_function(func_b, env)
    assert result == 115


# --- Canonical Serialization & Hashing Tests ---
def test_canonical_serialization_determinism():
    """Verify RFC-8785 canonical serialization produces deterministic bytes regardless of dict key order."""
    dict_1 = {"b": 2, "a": 1, "nested": {"z": 26, "y": 25}}
    dict_2 = {"a": 1, "nested": {"y": 25, "z": 26}, "b": 2}

    canon_1 = canonicalize_ast(dict_1)
    canon_2 = canonicalize_ast(dict_2)

    assert canon_1 == canon_2
    assert canon_1 == b'{"a":1,"b":2,"nested":{"y":25,"z":26}}'

    hash_1 = compute_ast_hash(dict_1)
    hash_2 = compute_ast_hash(dict_2)
    assert hash_1 == hash_2
    assert hash_1.startswith("sha256:")


# --- Deduplication Tests ---
def test_cas_deduplication():
    """Verify storing identical AST nodes multiple times resolves to the same hash and deduplicates."""
    cas = ContentAddressedStore(":memory:")

    literal = LiteralInt(value=42)
    hash_1 = cas.put(literal)
    hash_2 = cas.put(literal)

    assert hash_1 == hash_2

    cursor = cas.conn.execute("SELECT COUNT(*) FROM ast_nodes")
    count = cursor.fetchone()[0]
    assert count == 1


# --- On-Disk Persistence Tests ---
def test_cas_disk_persistence():
    """Verify CAS persistence across separate database connections on disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_cas.db")

        # Session 1: Store function
        cas1 = ContentAddressedStore(db_path)
        func = FunctionDeclaration(
            name="identity",
            parameters=[Parameter(name="x", param_type="int")],
            return_type="int",
            body=[ReturnStatement(value=VariableRef(name="x"))],
        )
        stored_hash = cas1.put(func)
        cas1.close()

        # Session 2: Retrieve from distinct connection
        cas2 = ContentAddressedStore(db_path)
        assert cas2.contains(stored_hash)
        retrieved = cas2.get(stored_hash)
        assert isinstance(retrieved, FunctionDeclaration)
        assert retrieved.name == "identity"
        cas2.close()


# --- Multiple Dependency Graph Edges ---
def test_cas_multiple_call_sites():
    """Verify indexing of multiple call sites and dependency traversal."""
    cas = ContentAddressedStore(":memory:")

    # Function A: square
    func_sq = FunctionDeclaration(
        name="square",
        parameters=[Parameter(name="x", param_type="int")],
        return_type="int",
        body=[
            ReturnStatement(
                value=BinaryOp(
                    op="mul", left=VariableRef(name="x"), right=VariableRef(name="x")
                )
            )
        ],
    )
    hash_sq = cas.put(func_sq)

    # Function B: sum_of_squares(a, b) -> square(a) + square(b)
    func_sum_sq = FunctionDeclaration(
        name="sum_of_squares",
        parameters=[
            Parameter(name="a", param_type="int"),
            Parameter(name="b", param_type="int"),
        ],
        return_type="int",
        body=[
            ReturnStatement(
                value=BinaryOp(
                    op="add",
                    left=FunctionCall(
                        target_hash=hash_sq, arguments=[VariableRef(name="a")]
                    ),
                    right=FunctionCall(
                        target_hash=hash_sq, arguments=[VariableRef(name="b")]
                    ),
                )
            )
        ],
    )
    hash_sum_sq = cas.put(func_sum_sq)

    deps = cas.get_dependencies(hash_sum_sq)
    assert len(deps) == 2
    assert deps[0] == hash_sq
    assert deps[1] == hash_sq

    # Execute via interpreter traversing CAS
    interpreter = Interpreter(cas=cas)
    env = Environment()
    env.define("a", 3, "int")
    env.define("b", 4, "int")

    res = interpreter.execute_function(func_sum_sq, env)
    assert res == 25  # 3^2 + 4^2 = 9 + 16 = 25
