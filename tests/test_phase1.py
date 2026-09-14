import pytest

from src.runtime.interpreter import (
    ArgumentMismatchError,
    DivisionByZeroRuntimeError,
    Environment,
    FunctionNotFoundError,
    Interpreter,
    MissingReturnError,
    RuntimeTypeError,
    StepLimitExceededError,
    UndefinedVariableError,
)
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
    parse_ast_node,
)


# --- Phase 1 Specification Acceptance Test ---
def test_phase1_acceptance_criterion():
    """Phase 1 Acceptance Test from Specification:

    Construct an AST program in pure Python representing (12 * 4) + 8.
    Run it through the interpreter. Assert output equals 56.
    """
    # (12 * 4) + 8
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
    assert result == 56


# --- Literal Values Tests ---
def test_literals_evaluation():
    interpreter = Interpreter()

    assert interpreter.eval(LiteralInt(value=42)) == 42
    assert interpreter.eval(LiteralFloat(value=3.14)) == 3.14
    assert interpreter.eval(LiteralBool(value=True)) is True
    assert interpreter.eval(LiteralBool(value=False)) is False
    assert interpreter.eval(LiteralString(value="telos")) == "telos"


# --- Arithmetic Operations Tests ---
def test_binary_arithmetic():
    interpreter = Interpreter()

    # Addition
    assert interpreter.eval(BinaryOp(op="add", left=LiteralInt(value=5), right=LiteralInt(value=3))) == 8
    assert interpreter.eval(BinaryOp(op="add", left=LiteralFloat(value=1.5), right=LiteralFloat(value=2.5))) == 4.0
    assert interpreter.eval(BinaryOp(op="add", left=LiteralInt(value=1), right=LiteralFloat(value=2.5))) == 3.5
    assert interpreter.eval(BinaryOp(op="add", left=LiteralString(value="hello "), right=LiteralString(value="world"))) == "hello world"

    # Subtraction
    assert interpreter.eval(BinaryOp(op="sub", left=LiteralInt(value=10), right=LiteralInt(value=4))) == 6
    assert interpreter.eval(BinaryOp(op="sub", left=LiteralFloat(value=5.5), right=LiteralFloat(value=2.0))) == 3.5

    # Multiplication
    assert interpreter.eval(BinaryOp(op="mul", left=LiteralInt(value=6), right=LiteralInt(value=7))) == 42
    assert interpreter.eval(BinaryOp(op="mul", left=LiteralFloat(value=2.5), right=LiteralInt(value=4))) == 10.0

    # Division
    assert interpreter.eval(BinaryOp(op="div", left=LiteralInt(value=10), right=LiteralInt(value=2))) == 5
    assert interpreter.eval(BinaryOp(op="div", left=LiteralFloat(value=7.0), right=LiteralFloat(value=2.0))) == 3.5

    # Modulo
    assert interpreter.eval(BinaryOp(op="mod", left=LiteralInt(value=10), right=LiteralInt(value=3))) == 1


def test_division_by_zero():
    interpreter = Interpreter()

    with pytest.raises(DivisionByZeroRuntimeError):
        interpreter.eval(BinaryOp(op="div", left=LiteralInt(value=10), right=LiteralInt(value=0)))

    with pytest.raises(DivisionByZeroRuntimeError):
        interpreter.eval(BinaryOp(op="mod", left=LiteralInt(value=10), right=LiteralInt(value=0)))


def test_arithmetic_type_mismatches():
    interpreter = Interpreter()

    # int + string
    with pytest.raises(RuntimeTypeError):
        interpreter.eval(BinaryOp(op="add", left=LiteralInt(value=1), right=LiteralString(value="two")))

    # string - string
    with pytest.raises(RuntimeTypeError):
        interpreter.eval(BinaryOp(op="sub", left=LiteralString(value="a"), right=LiteralString(value="b")))

    # float % float (mod only for ints)
    with pytest.raises(RuntimeTypeError):
        interpreter.eval(BinaryOp(op="mod", left=LiteralFloat(value=5.5), right=LiteralFloat(value=2.0)))


# --- Comparison Operations Tests ---
def test_binary_comparisons():
    interpreter = Interpreter()

    assert interpreter.eval(BinaryOp(op="eq", left=LiteralInt(value=5), right=LiteralInt(value=5))) is True
    assert interpreter.eval(BinaryOp(op="eq", left=LiteralInt(value=5), right=LiteralInt(value=6))) is False
    assert interpreter.eval(BinaryOp(op="neq", left=LiteralInt(value=5), right=LiteralInt(value=6))) is True

    assert interpreter.eval(BinaryOp(op="lt", left=LiteralInt(value=3), right=LiteralInt(value=5))) is True
    assert interpreter.eval(BinaryOp(op="lte", left=LiteralInt(value=5), right=LiteralInt(value=5))) is True
    assert interpreter.eval(BinaryOp(op="gt", left=LiteralInt(value=10), right=LiteralInt(value=5))) is True
    assert interpreter.eval(BinaryOp(op="gte", left=LiteralInt(value=5), right=LiteralInt(value=5))) is True

    # String comparison
    assert interpreter.eval(BinaryOp(op="lt", left=LiteralString(value="apple"), right=LiteralString(value="banana"))) is True


def test_comparison_type_mismatches():
    interpreter = Interpreter()

    with pytest.raises(RuntimeTypeError):
        interpreter.eval(BinaryOp(op="lt", left=LiteralInt(value=5), right=LiteralString(value="5")))


# --- Variables & Environment Tests ---
def test_variable_assignment_and_retrieval():
    env = Environment()
    interpreter = Interpreter()

    # Assign variable x = 100
    stmt = AssignStatement(
        variable_name="x",
        variable_type="int",
        expression=LiteralInt(value=100),
    )
    interpreter.eval(stmt, env)
    assert env.get("x") == 100

    # Retrieve via VariableRef
    expr = VariableRef(name="x")
    assert interpreter.eval(expr, env) == 100

    # Reassign x = 200
    reassign_stmt = AssignStatement(
        variable_name="x",
        variable_type="int",
        expression=LiteralInt(value=200),
    )
    interpreter.eval(reassign_stmt, env)
    assert env.get("x") == 200


def test_variable_type_enforcement():
    env = Environment()
    interpreter = Interpreter()

    # Assign string to int variable should raise RuntimeTypeError
    with pytest.raises(RuntimeTypeError):
        interpreter.eval(
            AssignStatement(
                variable_name="num",
                variable_type="int",
                expression=LiteralString(value="not an int"),
            ),
            env,
        )


def test_undefined_variable():
    interpreter = Interpreter()
    with pytest.raises(UndefinedVariableError):
        interpreter.eval(VariableRef(name="unknown_var"))


def test_lexical_scoping_and_shadowing():
    parent_env = Environment()
    parent_env.define("x", 10, "int")

    child_env = parent_env.child_scope()
    assert child_env.get("x") == 10

    # Shadow x in child scope
    child_env.define("x", 99, "int")
    assert child_env.get("x") == 99
    assert parent_env.get("x") == 10


# --- Control Flow Tests (IfElse & Return) ---
def test_if_else_then_branch():
    interpreter = Interpreter()
    env = Environment()

    # if (5 > 2) { x = 1 } else { x = 2 }
    stmt = IfElseStatement(
        condition=BinaryOp(op="gt", left=LiteralInt(value=5), right=LiteralInt(value=2)),
        then_branch=[
            AssignStatement(variable_name="x", variable_type="int", expression=LiteralInt(value=1))
        ],
        else_branch=[
            AssignStatement(variable_name="x", variable_type="int", expression=LiteralInt(value=2))
        ],
    )
    interpreter.eval(stmt, env)
    # env is outer, branch executes in child scope, but if x was predefined in outer:
    # Let's test with x predefined in outer scope
    outer_env = Environment()
    outer_env.define("result", 0, "int")
    stmt_outer = IfElseStatement(
        condition=BinaryOp(op="gt", left=LiteralInt(value=5), right=LiteralInt(value=2)),
        then_branch=[
            AssignStatement(variable_name="result", variable_type="int", expression=LiteralInt(value=42))
        ],
        else_branch=[
            AssignStatement(variable_name="result", variable_type="int", expression=LiteralInt(value=99))
        ],
    )
    interpreter.eval(stmt_outer, outer_env)
    assert outer_env.get("result") == 42


def test_if_else_else_branch():
    outer_env = Environment()
    outer_env.define("result", 0, "int")
    interpreter = Interpreter()

    stmt = IfElseStatement(
        condition=BinaryOp(op="lt", left=LiteralInt(value=5), right=LiteralInt(value=2)),
        then_branch=[
            AssignStatement(variable_name="result", variable_type="int", expression=LiteralInt(value=42))
        ],
        else_branch=[
            AssignStatement(variable_name="result", variable_type="int", expression=LiteralInt(value=99))
        ],
    )
    interpreter.eval(stmt, outer_env)
    assert outer_env.get("result") == 99


def test_if_else_non_boolean_condition():
    interpreter = Interpreter()
    with pytest.raises(RuntimeTypeError):
        interpreter.eval(
            IfElseStatement(
                condition=LiteralInt(value=1),
                then_branch=[ReturnStatement(value=LiteralInt(value=10))],
            )
        )


def test_return_statement_unwinds():
    interpreter = Interpreter()
    statements = [
        AssignStatement(variable_name="a", variable_type="int", expression=LiteralInt(value=10)),
        ReturnStatement(value=VariableRef(name="a")),
        AssignStatement(variable_name="a", variable_type="int", expression=LiteralInt(value=999)),
    ]
    result = interpreter.eval(statements)
    assert result == 10


# --- Function Declaration & Invocation Tests ---
def test_function_execution():
    interpreter = Interpreter()

    # Function add_two(a: int, b: int) -> int { return a + b }
    func = FunctionDeclaration(
        name="add_two",
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

    interpreter.register_function("sha256:func_add_two", func)

    # Call add_two(15, 27) -> 42
    call = FunctionCall(
        target_hash="sha256:func_add_two",
        arguments=[LiteralInt(value=15), LiteralInt(value=27)],
    )
    result = interpreter.eval(call)
    assert result == 42


def test_function_missing_return():
    interpreter = Interpreter()
    func = FunctionDeclaration(
        name="no_return",
        parameters=[],
        return_type="int",
        body=[
            AssignStatement(variable_name="temp", variable_type="int", expression=LiteralInt(value=1))
        ],
    )
    with pytest.raises(MissingReturnError):
        interpreter.eval(func)


def test_function_return_type_mismatch():
    interpreter = Interpreter()
    func = FunctionDeclaration(
        name="bad_return",
        parameters=[],
        return_type="int",
        body=[ReturnStatement(value=LiteralString(value="not an int"))],
    )
    with pytest.raises(RuntimeTypeError):
        interpreter.eval(func)


def test_function_argument_count_mismatch():
    interpreter = Interpreter()
    func = FunctionDeclaration(
        name="needs_two",
        parameters=[
            Parameter(name="a", param_type="int"),
            Parameter(name="b", param_type="int"),
        ],
        return_type="int",
        body=[ReturnStatement(value=LiteralInt(value=0))],
    )
    interpreter.register_function("sha256:needs_two", func)

    with pytest.raises(ArgumentMismatchError):
        interpreter.eval(
            FunctionCall(
                target_hash="sha256:needs_two",
                arguments=[LiteralInt(value=1)],
            )
        )


def test_function_not_found():
    interpreter = Interpreter()
    with pytest.raises(FunctionNotFoundError):
        interpreter.eval(
            FunctionCall(target_hash="sha256:does_not_exist", arguments=[])
        )


# --- Safety Limits & Budget Tests ---
def test_step_limit_budget():
    # Set step limit very low to ensure budget enforcement
    interpreter = Interpreter(max_steps=2)

    # (1 + 2) + 3 takes more than 2 steps
    expr = BinaryOp(
        op="add",
        left=BinaryOp(op="add", left=LiteralInt(value=1), right=LiteralInt(value=2)),
        right=LiteralInt(value=3),
    )
    with pytest.raises(StepLimitExceededError):
        interpreter.eval(expr)


# --- JSON Serialization & Round-Trip Parsing Tests ---
def test_ast_json_parsing_and_execution():
    raw_ast = {
        "kind": "function",
        "name": "calculate_discount",
        "parameters": [
            {"name": "price", "param_type": "float"},
            {"name": "discount_rate", "param_type": "float"},
        ],
        "return_type": "float",
        "body": [
            {
                "kind": "assign",
                "variable_name": "discount",
                "variable_type": "float",
                "expression": {
                    "kind": "binary_op",
                    "op": "mul",
                    "left": {"kind": "var_ref", "name": "price"},
                    "right": {"kind": "var_ref", "name": "discount_rate"},
                },
            },
            {
                "kind": "return",
                "value": {
                    "kind": "binary_op",
                    "op": "sub",
                    "left": {"kind": "var_ref", "name": "price"},
                    "right": {"kind": "var_ref", "name": "discount"},
                },
            },
        ],
        "invariants": ["return_value >= 0"],
    }

    parsed_func = parse_ast_node(raw_ast)
    assert isinstance(parsed_func, FunctionDeclaration)
    assert parsed_func.name == "calculate_discount"

    # Register and invoke
    interpreter = Interpreter()
    interpreter.register_function("sha256:calc_disc", parsed_func)

    call_node = FunctionCall(
        target_hash="sha256:calc_disc",
        arguments=[LiteralFloat(value=100.0), LiteralFloat(value=0.15)],
    )

    result = interpreter.eval(call_node)
    assert abs(result - 85.0) < 1e-9
