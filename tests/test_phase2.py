import pytest

from src.schema.nodes import (
    AssignStatement,
    BinaryOp,
    FunctionCall,
    FunctionDeclaration,
    IfElseStatement,
    LiteralBool,
    LiteralFloat,
    LiteralInt,
    LiteralString,
    Parameter,
    ReturnStatement,
    VariableRef,
)
from src.verifier.smt_solver import SMTVerifier
from src.verifier.type_checker import TypeChecker


# --- Phase 2 Specification Acceptance Test ---
def test_phase2_acceptance_criterion():
    """Phase 2 Acceptance Test from Specification:

    Build an AST that computes division by variable y.
    Add invariant y != 0.
    Run verifier with unbound y to confirm Z3 finds counterexample y = 0 and rejects the AST.
    """
    # Function divide(x: int, y: int) -> int { return x / y } with invariant "y != 0"
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
    result = verifier.verify_function(func, preconditions=None)

    # Must reject because unbound y has counterexample y = 0
    assert result.status == "REJECTED"
    assert result.phase == "SMT_SOLVER"
    assert result.counterexample is not None
    assert result.counterexample.get("y") == 0


# --- Static Type Checker Tests ---
def test_type_checker_valid_function():
    func = FunctionDeclaration(
        name="compute_total",
        parameters=[
            Parameter(name="price", param_type="float"),
            Parameter(name="qty", param_type="int"),
        ],
        return_type="float",
        body=[
            AssignStatement(
                variable_name="subtotal",
                variable_type="float",
                expression=BinaryOp(
                    op="mul",
                    left=VariableRef(name="price"),
                    right=VariableRef(name="qty"),
                ),
            ),
            ReturnStatement(value=VariableRef(name="subtotal")),
        ],
    )

    checker = TypeChecker()
    res = checker.check_function(func)
    assert res.status == "APPROVED"


def test_type_checker_incompatible_binary_op():
    func = FunctionDeclaration(
        name="bad_add",
        parameters=[
            Parameter(name="a", param_type="int"),
            Parameter(name="s", param_type="string"),
        ],
        return_type="int",
        body=[
            ReturnStatement(
                value=BinaryOp(
                    op="add",
                    left=VariableRef(name="a"),
                    right=VariableRef(name="s"),
                )
            )
        ],
    )

    checker = TypeChecker()
    res = checker.check_function(func)
    assert res.status == "REJECTED"
    assert res.error_type == "TYPE_MISMATCH"
    assert res.node_path == "body[0].value"


def test_type_checker_assignment_mismatch():
    func = FunctionDeclaration(
        name="bad_assign",
        parameters=[Parameter(name="x", param_type="int")],
        return_type="int",
        body=[
            AssignStatement(
                variable_name="count",
                variable_type="int",
                expression=LiteralString(value="invalid_number"),
            ),
            ReturnStatement(value=VariableRef(name="count")),
        ],
    )

    checker = TypeChecker()
    res = checker.check_function(func)
    assert res.status == "REJECTED"
    assert res.error_type == "TYPE_MISMATCH"
    assert res.node_path == "body[0].expression"


def test_type_checker_missing_return():
    func = FunctionDeclaration(
        name="no_return",
        parameters=[],
        return_type="int",
        body=[
            AssignStatement(
                variable_name="x",
                variable_type="int",
                expression=LiteralInt(value=10),
            )
        ],
    )

    checker = TypeChecker()
    res = checker.check_function(func)
    assert res.status == "REJECTED"
    assert res.error_type == "MISSING_RETURN"


def test_type_checker_return_type_mismatch():
    func = FunctionDeclaration(
        name="wrong_return",
        parameters=[],
        return_type="int",
        body=[ReturnStatement(value=LiteralString(value="not_an_int"))],
    )

    checker = TypeChecker()
    res = checker.check_function(func)
    assert res.status == "REJECTED"
    assert res.error_type == "RETURN_TYPE_MISMATCH"
    assert res.node_path == "body[0].value"


def test_type_checker_undefined_variable():
    func = FunctionDeclaration(
        name="ghost_var",
        parameters=[],
        return_type="int",
        body=[ReturnStatement(value=VariableRef(name="phantom"))],
    )

    checker = TypeChecker()
    res = checker.check_function(func)
    assert res.status == "REJECTED"
    assert res.error_type == "UNDEFINED_VARIABLE"
    assert res.node_path == "body[0].value"


def test_type_checker_if_branch_returns():
    # If one branch returns but the other does not, it should be rejected as missing return
    func = FunctionDeclaration(
        name="partial_branch_return",
        parameters=[Parameter(name="cond", param_type="bool")],
        return_type="int",
        body=[
            IfElseStatement(
                condition=VariableRef(name="cond"),
                then_branch=[ReturnStatement(value=LiteralInt(value=1))],
                else_branch=[
                    AssignStatement(
                        variable_name="temp",
                        variable_type="int",
                        expression=LiteralInt(value=2),
                    )
                ],
            )
        ],
    )

    checker = TypeChecker()
    res = checker.check_function(func)
    assert res.status == "REJECTED"
    assert res.error_type == "MISSING_RETURN"


def test_type_checker_cross_function_call():
    callee = FunctionDeclaration(
        name="square",
        parameters=[Parameter(name="n", param_type="int")],
        return_type="int",
        body=[
            ReturnStatement(
                value=BinaryOp(
                    op="mul", left=VariableRef(name="n"), right=VariableRef(name="n")
                )
            )
        ],
    )

    caller_good = FunctionDeclaration(
        name="caller_good",
        parameters=[],
        return_type="int",
        body=[
            ReturnStatement(
                value=FunctionCall(
                    target_hash="sha256:sq",
                    arguments=[LiteralInt(value=5)],
                )
            )
        ],
    )

    caller_bad_type = FunctionDeclaration(
        name="caller_bad_type",
        parameters=[],
        return_type="int",
        body=[
            ReturnStatement(
                value=FunctionCall(
                    target_hash="sha256:sq",
                    arguments=[LiteralString(value="hello")],
                )
            )
        ],
    )

    checker = TypeChecker()
    checker.register_function("sha256:sq", callee)

    assert checker.check_function(caller_good).status == "APPROVED"

    res_bad = checker.check_function(caller_bad_type)
    assert res_bad.status == "REJECTED"
    assert res_bad.error_type == "TYPE_MISMATCH"


# --- SMT Invariant Verification Tests ---
def test_smt_universal_invariant_holds():
    """Verify that an invariant holding under preconditions is approved (unsat)."""
    # add_positive(a: int, b: int) -> int { return a + b }
    # Preconditions: a > 0, b > 0
    # Invariant: return_value > 0
    func = FunctionDeclaration(
        name="add_positive",
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
        invariants=["return_value > 0"],
    )

    verifier = SMTVerifier()
    res = verifier.verify_function(
        func, preconditions=["a > 0", "b > 0"], check_division_safety=False
    )
    assert res.status == "APPROVED"


def test_smt_invariant_violated_with_counterexample():
    """Verify that a breached invariant is rejected with concrete counterexample."""
    # square(x: int) -> int { return x * x }
    # Invariant: return_value > 0  (Violated when x == 0, since 0 * 0 = 0)
    func = FunctionDeclaration(
        name="square",
        parameters=[Parameter(name="x", param_type="int")],
        return_type="int",
        body=[
            ReturnStatement(
                value=BinaryOp(
                    op="mul",
                    left=VariableRef(name="x"),
                    right=VariableRef(name="x"),
                )
            )
        ],
        invariants=["return_value > 0"],
    )

    verifier = SMTVerifier()
    res = verifier.verify_function(func)
    assert res.status == "REJECTED"
    assert res.error_type == "INVARIANT_VIOLATION"
    assert res.counterexample is not None
    assert res.counterexample.get("x") == 0


def test_smt_conditional_branching_invariant():
    """Verify invariants through conditional branching (abs_val function)."""
    # abs_val(n: int) -> int: if (n < 0) return -1 * n else return n
    # Invariant: return_value >= 0
    func = FunctionDeclaration(
        name="abs_val",
        parameters=[Parameter(name="n", param_type="int")],
        return_type="int",
        body=[
            IfElseStatement(
                condition=BinaryOp(
                    op="lt", left=VariableRef(name="n"), right=LiteralInt(value=0)
                ),
                then_branch=[
                    ReturnStatement(
                        value=BinaryOp(
                            op="mul",
                            left=LiteralInt(value=-1),
                            right=VariableRef(name="n"),
                        )
                    )
                ],
                else_branch=[ReturnStatement(value=VariableRef(name="n"))],
            )
        ],
        invariants=["return_value >= 0"],
    )

    verifier = SMTVerifier()
    res = verifier.verify_function(func)
    assert res.status == "APPROVED"


def test_smt_division_by_zero_safety():
    """Verify implicit division-by-zero detection when divisor is unconstrained."""
    func = FunctionDeclaration(
        name="safe_div_candidate",
        parameters=[
            Parameter(name="x", param_type="int"),
            Parameter(name="denom", param_type="int"),
        ],
        return_type="int",
        body=[
            ReturnStatement(
                value=BinaryOp(
                    op="div",
                    left=VariableRef(name="x"),
                    right=VariableRef(name="denom"),
                )
            )
        ],
        invariants=[],
    )

    verifier = SMTVerifier()

    # Without precondition: denom could be 0 -> Rejected
    unconstrained_res = verifier.verify_function(func, check_division_safety=True)
    assert unconstrained_res.status == "REJECTED"
    assert unconstrained_res.error_type == "DIVISION_BY_ZERO"
    assert unconstrained_res.counterexample.get("denom") == 0

    # With precondition: denom != 0 -> Approved
    constrained_res = verifier.verify_function(
        func, preconditions=["denom != 0"], check_division_safety=True
    )
    assert constrained_res.status == "APPROVED"
