import pytest

from src.compiler.builder import BuilderAgent, default_cost_function_ast
from src.runtime.interpreter import Environment, Interpreter
from src.schema.nodes import (
    FunctionCall,
    FunctionDeclaration,
    LiteralFloat,
    LiteralInt,
)
from src.verifier.diagnostics import VerificationResult
from src.verifier.smt_solver import SMTVerifier
from src.verifier.type_checker import TypeChecker


# --- Phase 3 Specification Acceptance Test ---
def test_phase3_acceptance_criterion():
    """Phase 3 Acceptance Test from Specification:

    Send prompt: "Write a function that calculates total cost given item_price, quantity, and tax_rate."
    Confirm output parses directly into the validated Pydantic model.
    """
    agent = BuilderAgent()
    prompt = "Write a function that calculates total cost given item_price, quantity, and tax_rate."

    ast = agent.build(prompt)

    # 1. Output parses directly into validated FunctionDeclaration Pydantic model
    assert isinstance(ast, FunctionDeclaration)
    assert ast.name is not None
    assert len(ast.parameters) == 3

    param_names = [p.name for p in ast.parameters]
    assert "item_price" in param_names
    assert "quantity" in param_names
    assert "tax_rate" in param_names

    # 2. Verify static type safety via TypeChecker
    checker = TypeChecker()
    check_res = checker.check_function(ast)
    assert check_res.status == "APPROVED"

    # 3. Verify execution via Interpreter
    # item_price = 50.0, quantity = 2, tax_rate = 0.10
    # subtotal = 100.0, tax = 10.0 -> total = 110.0
    interpreter = Interpreter()
    env = Environment()
    env.define("item_price", 50.0, "float")
    env.define("quantity", 2, "int")
    env.define("tax_rate", 0.10, "float")

    total = interpreter.execute_function(ast, env)
    assert abs(total - 110.0) < 1e-6

    # 4. Verify SMT invariant verification
    verifier = SMTVerifier()
    # Invariant: return_value >= 0 holds for positive inputs
    res_smt = verifier.verify_function(
        ast,
        preconditions=["item_price >= 0", "quantity >= 0", "tax_rate >= 0"],
        check_division_safety=True,
    )
    assert res_smt.status == "APPROVED"


def test_builder_format_prompt_without_feedback():
    agent = BuilderAgent()
    messages = agent.format_prompt("Calculate tax")
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "Telos" in messages[0]["content"]
    assert "Calculate tax" in messages[1]["content"]


def test_builder_format_prompt_with_feedback():
    agent = BuilderAgent()
    feedback = VerificationResult.rejected(
        phase="STATIC_TYPE_CHECK",
        error_type="TYPE_MISMATCH",
        details="Incompatible types",
        node_path="body[0].expression",
        instruction="Convert string to int",
        counterexample={"x": 0},
    )

    messages = agent.format_prompt("Calculate tax", feedback)
    user_msg = messages[1]["content"]

    assert "[VERIFICATION FEEDBACK - PREVIOUS AST REJECTED]" in user_msg
    assert "STATIC_TYPE_CHECK" in user_msg
    assert "TYPE_MISMATCH" in user_msg
    assert "body[0].expression" in user_msg
    assert "Convert string to int" in user_msg
    assert "'x': 0" in user_msg


def test_builder_custom_mock_provider():
    def custom_provider(prompt: str, fb=None):
        return default_cost_function_ast()

    agent = BuilderAgent(mock_provider=custom_provider)
    ast = agent.build("Any prompt")
    assert isinstance(ast, FunctionDeclaration)
    assert ast.name == "calculate_total_cost"


def test_builder_error_when_no_client_and_no_mock():
    agent = BuilderAgent(mock_provider=lambda p, f: default_cost_function_ast())
    # Explicitly clear mock_provider and client to test failure mode
    agent.mock_provider = None
    agent.client = None

    with pytest.raises(RuntimeError, match="requires either an active instructor client"):
        agent.build("Calculate cost")
