import pytest

from src.compiler.builder import BuilderAgent
from src.orchestration.loop import SelfHealingLoop
from src.schema.nodes import (
    AssignStatement,
    BinaryOp,
    FunctionDeclaration,
    IfElseStatement,
    LiteralInt,
    LiteralString,
    Parameter,
    ReturnStatement,
    VariableRef,
)
from src.verifier.diagnostics import VerificationResult


# --- Phase 4 Specification Acceptance Test ---
def test_phase4_acceptance_criterion_self_healing():
    """Phase 4 Acceptance Test from Specification:

    Prompt the Builder with a deliberate contradiction:
    "Divide x by y, and guarantee y can be 0 while the function never errors."
    Observe the loop intercepting the Z3 failure, sending feedback to the agent,
    and resolving the contradiction via conditional guard.
    """
    # 1. Simulate Builder Agent behavior across feedback rounds:
    # Round 1: Naive division x / y without guard (triggers Z3 division by zero failure)
    # Round 2: After receiving Z3 feedback (counterexample y = 0), synthesizes safe guard:
    #          if (y == 0) return 0 else return x / y
    call_count = 0

    def adaptive_builder(prompt: str, feedback: VerificationResult = None) -> FunctionDeclaration:
        nonlocal call_count
        call_count += 1

        if feedback is not None and feedback.error_type in ("DIVISION_BY_ZERO", "INVARIANT_VIOLATION"):
            # Self-healed AST: conditional guard against y == 0
            return FunctionDeclaration(
                name="safe_divide",
                parameters=[
                    Parameter(name="x", param_type="int"),
                    Parameter(name="y", param_type="int"),
                ],
                return_type="int",
                body=[
                    IfElseStatement(
                        condition=BinaryOp(
                            op="eq",
                            left=VariableRef(name="y"),
                            right=LiteralInt(value=0),
                        ),
                        then_branch=[ReturnStatement(value=LiteralInt(value=0))],
                        else_branch=[
                            ReturnStatement(
                                value=BinaryOp(
                                    op="div",
                                    left=VariableRef(name="x"),
                                    right=VariableRef(name="y"),
                                )
                            )
                        ],
                    )
                ],
            )

        # Naive division (triggers Z3 error)
        return FunctionDeclaration(
            name="naive_divide",
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
            invariants=[],
        )

    builder = BuilderAgent(mock_provider=adaptive_builder)
    loop = SelfHealingLoop(builder=builder, max_retries=3)

    prompt = "Divide x by y, and guarantee y can be 0 while the function never errors."
    result = loop.run(intent=prompt, test_inputs={"x": 10, "y": 0})

    # Assertions:
    # 1. Closed loop converged successfully
    assert result.status == "SUCCESS"
    assert result.attempts == 2

    # 2. History shows Attempt 1 was intercepted by SMT_SOLVER with counterexample y = 0
    assert len(result.history) == 2
    attempt1 = result.history[0]
    assert attempt1.phase_reached == "SMT_SOLVER"
    assert attempt1.diagnostic.error_type == "DIVISION_BY_ZERO"
    assert attempt1.diagnostic.counterexample.get("y") == 0

    # 3. Attempt 2 completed all verification and executed in sandbox
    attempt2 = result.history[1]
    assert attempt2.phase_reached == "COMPLETED"

    # 4. Verified safe execution in sandbox runtime with y = 0
    assert result.output == 0

    # Also test with non-zero y
    result_nonzero = loop.run(intent=prompt, test_inputs={"x": 10, "y": 2})
    assert result_nonzero.output == 5


def test_phase4_acceptance_criterion_unresolvable_contradiction_reporting():
    """Verify that when an invariant contradiction cannot be resolved within max_retries,

    the loop halts cleanly and reports the exact diagnostic failure history.
    """
    # A stubborn model that never fixes the division by zero
    def stubborn_builder(prompt: str, feedback: VerificationResult = None) -> FunctionDeclaration:
        return FunctionDeclaration(
            name="stubborn_divide",
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

    builder = BuilderAgent(mock_provider=stubborn_builder)
    loop = SelfHealingLoop(builder=builder, max_retries=3)

    result = loop.run("Divide x by y, and guarantee y can be 0 while the function never errors.")

    assert result.status == "FAILED"
    assert result.attempts == 3
    assert len(result.history) == 3
    for attempt in result.history:
        assert attempt.phase_reached == "SMT_SOLVER"
        assert attempt.diagnostic.counterexample.get("y") == 0

    assert "exhausted 3 attempts" in result.error_summary
    assert "DIVISION_BY_ZERO" in result.error_summary or "INVARIANT_VIOLATION" in result.error_summary


# --- Type Checking Self-Healing Tests ---
def test_self_healing_type_mismatch():
    """Verify self-healing when the first attempt has a static type error."""
    round_idx = 0

    def type_recovering_builder(prompt: str, feedback: VerificationResult = None) -> FunctionDeclaration:
        nonlocal round_idx
        round_idx += 1

        if feedback is not None and feedback.error_type == "TYPE_MISMATCH":
            # Repaired AST: int + int
            return FunctionDeclaration(
                name="repaired_sum",
                parameters=[Parameter(name="a", param_type="int")],
                return_type="int",
                body=[
                    ReturnStatement(
                        value=BinaryOp(
                            op="add",
                            left=VariableRef(name="a"),
                            right=LiteralInt(value=10),
                        )
                    )
                ],
            )

        # Faulty AST: int + string
        return FunctionDeclaration(
            name="broken_sum",
            parameters=[Parameter(name="a", param_type="int")],
            return_type="int",
            body=[
                ReturnStatement(
                    value=BinaryOp(
                        op="add",
                        left=VariableRef(name="a"),
                        right=LiteralString(value="10"),
                    )
                )
            ],
        )

    builder = BuilderAgent(mock_provider=type_recovering_builder)
    loop = SelfHealingLoop(builder=builder, max_retries=3)

    result = loop.run("Add 10 to a", test_inputs={"a": 5})

    assert result.status == "SUCCESS"
    assert result.attempts == 2
    assert result.history[0].phase_reached == "STATIC_TYPE_CHECK"
    assert result.history[0].diagnostic.error_type == "TYPE_MISMATCH"
    assert result.output == 15


# --- Runtime Error Self-Healing Tests ---
def test_self_healing_runtime_step_limit():
    """Verify self-healing when runtime sandbox triggers a step limit exceeded error."""
    attempt_idx = 0

    def runtime_recovering_builder(prompt: str, feedback: VerificationResult = None) -> FunctionDeclaration:
        nonlocal attempt_idx
        attempt_idx += 1

        if feedback is not None and feedback.phase == "RUNTIME":
            # Simplified one-step calculation
            return FunctionDeclaration(
                name="simple_add",
                parameters=[Parameter(name="n", param_type="int")],
                return_type="int",
                body=[ReturnStatement(value=VariableRef(name="n"))],
            )

        # Deeply nested operations that consume many steps
        nested = BinaryOp(op="add", left=LiteralInt(value=1), right=LiteralInt(value=1))
        for _ in range(10):
            nested = BinaryOp(op="add", left=nested, right=LiteralInt(value=1))

        return FunctionDeclaration(
            name="heavy_add",
            parameters=[Parameter(name="n", param_type="int")],
            return_type="int",
            body=[ReturnStatement(value=nested)],
        )

    builder = BuilderAgent(mock_provider=runtime_recovering_builder)
    # Set max_steps very small so first attempt panics in runtime
    from src.runtime.interpreter import Interpreter
    small_interpreter = Interpreter(max_steps=3)

    loop = SelfHealingLoop(
        builder=builder,
        interpreter=small_interpreter,
        max_retries=3,
    )

    result = loop.run("Compute value", test_inputs={"n": 42})
    assert result.status == "SUCCESS"
    assert result.attempts == 2
    assert result.history[0].phase_reached == "RUNTIME"
    assert result.history[0].diagnostic.error_type == "StepLimitExceededError"
    assert result.output == 42
