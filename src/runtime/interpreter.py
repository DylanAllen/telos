from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from src.schema.nodes import (
    AssignStatement,
    BinaryOp,
    ExpressionNode,
    FunctionCall,
    FunctionDeclaration,
    IfElseStatement,
    LiteralBool,
    LiteralFloat,
    LiteralInt,
    LiteralString,
    PrimitiveType,
    ReturnStatement,
    StatementNode,
    VariableRef,
)


# --- Exceptions ---
class InterpreterError(Exception):
    """Base exception for all interpreter runtime errors."""
    pass


class RuntimeTypeError(InterpreterError):
    """Raised when an operation or assignment encounters a type mismatch."""
    pass


class UndefinedVariableError(InterpreterError):
    """Raised when a referenced variable does not exist in scope."""
    pass


class DivisionByZeroRuntimeError(InterpreterError):
    """Raised when division or modulo by zero occurs."""
    pass


class StepLimitExceededError(InterpreterError):
    """Raised when the interpreter exceeds the configured step execution budget."""
    pass


class FunctionNotFoundError(InterpreterError):
    """Raised when a called function hash is not present in the registry."""
    pass


class ArgumentMismatchError(InterpreterError):
    """Raised when function call arguments do not match parameter declarations."""
    pass


class MissingReturnError(InterpreterError):
    """Raised when a function body ends without returning a value."""
    pass


class _ReturnSignal(Exception):
    """Internal control flow signal used to unwind the stack on ReturnStatement."""
    def __init__(self, value: Any):
        self.value = value


# --- Type Checking Helper ---
def check_type_conformance(value: Any, expected_type: PrimitiveType) -> bool:
    """Verify that a runtime value strictly conforms to an expected primitive type."""
    if expected_type == "bool":
        return isinstance(value, bool)
    if expected_type == "int":
        # In Python, bool is a subclass of int, so explicitly exclude bool
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "float":
        # Allow ints to be treated as floats or strict floats
        return (isinstance(value, float) or isinstance(value, int)) and not isinstance(value, bool)
    if expected_type == "string":
        return isinstance(value, str)
    return False


def get_value_type_name(value: Any) -> str:
    """Return the name of the primitive type of a runtime value."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    return type(value).__name__


# --- Environment / Scope Map ---
class Environment:
    """Lexically-scoped execution environment maintaining variable bindings and declared types."""

    def __init__(self, parent: Optional[Environment] = None):
        self.parent: Optional[Environment] = parent
        self.bindings: Dict[str, Any] = {}
        self.types: Dict[str, PrimitiveType] = {}

    def define(self, name: str, value: Any, var_type: PrimitiveType) -> None:
        """Define a new variable binding in the current scope."""
        if not check_type_conformance(value, var_type):
            raise RuntimeTypeError(
                f"Cannot assign value of type '{get_value_type_name(value)}' to variable '{name}' "
                f"of type '{var_type}'"
            )
        # Convert int to float if var_type is float
        if var_type == "float" and isinstance(value, int) and not isinstance(value, bool):
            value = float(value)

        self.bindings[name] = value
        self.types[name] = var_type

    def assign(self, name: str, value: Any) -> None:
        """Assign or update a variable in the nearest enclosing scope where it exists, or define it."""
        if name in self.bindings:
            expected_type = self.types[name]
            if not check_type_conformance(value, expected_type):
                raise RuntimeTypeError(
                    f"Cannot assign value of type '{get_value_type_name(value)}' to variable '{name}' "
                    f"of type '{expected_type}'"
                )
            if expected_type == "float" and isinstance(value, int) and not isinstance(value, bool):
                value = float(value)
            self.bindings[name] = value
            return

        if self.parent is not None:
            self.parent.assign(name, value)
            return

        raise UndefinedVariableError(f"Cannot assign to undefined variable '{name}'")

    def get(self, name: str) -> Any:
        """Retrieve a variable's value from the current or ancestor scopes."""
        if name in self.bindings:
            return self.bindings[name]
        if self.parent is not None:
            return self.parent.get(name)
        raise UndefinedVariableError(f"Variable '{name}' is not defined")

    def get_type(self, name: str) -> Optional[PrimitiveType]:
        """Retrieve the declared type of a variable."""
        if name in self.types:
            return self.types[name]
        if self.parent is not None:
            return self.parent.get_type(name)
        return None

    def child_scope(self) -> Environment:
        """Create a new nested child environment."""
        return Environment(parent=self)


# --- Tree-Walking Interpreter ---
class Interpreter:
    """Sandboxed tree-walking AST interpreter with instruction budget and strict typing."""

    def __init__(
        self,
        max_steps: int = 10_000,
        function_registry: Optional[Dict[str, FunctionDeclaration]] = None,
        cas: Optional[Any] = None,
    ):
        self.max_steps: int = max_steps
        self.step_count: int = 0
        self.function_registry: Dict[str, FunctionDeclaration] = (
            dict(function_registry) if function_registry else {}
        )
        self.cas = cas

    def register_function(self, identifier: str, func: FunctionDeclaration) -> None:
        """Register a function declaration by its hash or name."""
        self.function_registry[identifier] = func

    def _tick(self) -> None:
        """Increment step counter and enforce execution budget limit."""
        self.step_count += 1
        if self.step_count > self.max_steps:
            raise StepLimitExceededError(
                f"Execution exceeded maximum step limit of {self.max_steps} steps"
            )

    def eval_expression(self, expr: ExpressionNode, env: Environment) -> Any:
        """Evaluate an AST expression node within an environment."""
        self._tick()

        if isinstance(expr, LiteralInt):
            return expr.value
        if isinstance(expr, LiteralFloat):
            return expr.value
        if isinstance(expr, LiteralBool):
            return expr.value
        if isinstance(expr, LiteralString):
            return expr.value
        if isinstance(expr, VariableRef):
            return env.get(expr.name)
        if isinstance(expr, BinaryOp):
            return self._eval_binary_op(expr, env)
        if isinstance(expr, FunctionCall):
            return self._eval_function_call(expr, env)

        raise InterpreterError(f"Unknown expression node type: {type(expr)}")

    def _eval_binary_op(self, node: BinaryOp, env: Environment) -> Any:
        """Evaluate a binary operation node with strict operand typing."""
        left = self.eval_expression(node.left, env)
        right = self.eval_expression(node.right, env)

        left_type = get_value_type_name(left)
        right_type = get_value_type_name(right)
        op = node.op

        # Arithmetic operations
        if op == "add":
            if left_type == "int" and right_type == "int":
                return left + right
            if left_type in ("int", "float") and right_type in ("int", "float"):
                return float(left) + float(right)
            if left_type == "string" and right_type == "string":
                return left + right
            raise RuntimeTypeError(
                f"Operator 'add' not supported between types '{left_type}' and '{right_type}'"
            )

        if op in ("sub", "mul"):
            if left_type == "int" and right_type == "int":
                return left - right if op == "sub" else left * right
            if left_type in ("int", "float") and right_type in ("int", "float"):
                return (
                    float(left) - float(right)
                    if op == "sub"
                    else float(left) * float(right)
                )
            raise RuntimeTypeError(
                f"Operator '{op}' not supported between types '{left_type}' and '{right_type}'"
            )

        if op == "div":
            if right == 0:
                raise DivisionByZeroRuntimeError("Division by zero")
            if left_type == "int" and right_type == "int":
                # In typed systems (Wasm/Rust), integer division yields integer
                return left // right
            if left_type in ("int", "float") and right_type in ("int", "float"):
                return float(left) / float(right)
            raise RuntimeTypeError(
                f"Operator 'div' not supported between types '{left_type}' and '{right_type}'"
            )

        if op == "mod":
            if right == 0:
                raise DivisionByZeroRuntimeError("Modulo by zero")
            if left_type == "int" and right_type == "int":
                return left % right
            raise RuntimeTypeError(
                f"Operator 'mod' requires integer operands, received '{left_type}' and '{right_type}'"
            )

        # Comparison operations
        if op in ("eq", "neq"):
            # Allow comparison between numbers, or between identical types
            if {left_type, right_type} <= {"int", "float"} or left_type == right_type:
                return (left == right) if op == "eq" else (left != right)
            raise RuntimeTypeError(
                f"Comparison '{op}' not supported between types '{left_type}' and '{right_type}'"
            )

        if op in ("lt", "lte", "gt", "gte"):
            if {left_type, right_type} <= {"int", "float"}:
                if op == "lt":
                    return left < right
                if op == "lte":
                    return left <= right
                if op == "gt":
                    return left > right
                if op == "gte":
                    return left >= right
            if left_type == "string" and right_type == "string":
                if op == "lt":
                    return left < right
                if op == "lte":
                    return left <= right
                if op == "gt":
                    return left > right
                if op == "gte":
                    return left >= right
            raise RuntimeTypeError(
                f"Ordered comparison '{op}' not supported between types '{left_type}' and '{right_type}'"
            )

        raise InterpreterError(f"Unsupported binary operator: '{op}'")

    def _eval_function_call(self, node: FunctionCall, env: Environment) -> Any:
        """Evaluate a function call by looking up the target hash in the registry or CAS."""
        func = self.function_registry.get(node.target_hash)
        if func is None and self.cas is not None:
            retrieved = self.cas.get(node.target_hash)
            if isinstance(retrieved, FunctionDeclaration):
                self.function_registry[node.target_hash] = retrieved
                func = retrieved

        if func is None:
            raise FunctionNotFoundError(
                f"Function with target hash '{node.target_hash}' not found in registry or CAS store"
            )

        if len(node.arguments) != len(func.parameters):
            raise ArgumentMismatchError(
                f"Function '{func.name}' expects {len(func.parameters)} arguments, "
                f"received {len(node.arguments)}"
            )

        arg_values = [self.eval_expression(arg, env) for arg in node.arguments]
        call_env = Environment()

        for param, val in zip(func.parameters, arg_values):
            call_env.define(param.name, val, param.param_type)

        return self.execute_function(func, call_env, reset_steps=False)

    def execute_statement(self, stmt: StatementNode, env: Environment) -> None:
        """Execute a statement node within an environment. May raise _ReturnSignal."""
        self._tick()

        if isinstance(stmt, AssignStatement):
            val = self.eval_expression(stmt.expression, env)
            existing_type = env.get_type(stmt.variable_name)
            if existing_type is not None:
                if existing_type != stmt.variable_type:
                    raise RuntimeTypeError(
                        f"Cannot redeclare variable '{stmt.variable_name}' of type '{existing_type}' "
                        f"as type '{stmt.variable_type}'"
                    )
                env.assign(stmt.variable_name, val)
            else:
                env.define(stmt.variable_name, val, stmt.variable_type)
            return

        if isinstance(stmt, IfElseStatement):
            cond_val = self.eval_expression(stmt.condition, env)
            if not isinstance(cond_val, bool):
                raise RuntimeTypeError(
                    f"If-else condition must evaluate to 'bool', received '{get_value_type_name(cond_val)}'"
                )

            branch_env = env.child_scope()
            if cond_val:
                for s in stmt.then_branch:
                    self.execute_statement(s, branch_env)
            elif stmt.else_branch:
                for s in stmt.else_branch:
                    self.execute_statement(s, branch_env)
            return

        if isinstance(stmt, ReturnStatement):
            val = self.eval_expression(stmt.value, env)
            raise _ReturnSignal(val)

        raise InterpreterError(f"Unknown statement node type: {type(stmt)}")

    def execute_function(
        self,
        func: FunctionDeclaration,
        env: Optional[Environment] = None,
        reset_steps: bool = True,
    ) -> Any:
        """Execute a function declaration and validate the return type."""
        if reset_steps:
            self.step_count = 0

        func_env = env if env is not None else Environment()

        try:
            for stmt in func.body:
                self.execute_statement(stmt, func_env)
        except _ReturnSignal as ret:
            result = ret.value
            if not check_type_conformance(result, func.return_type):
                raise RuntimeTypeError(
                    f"Function '{func.name}' declared return type '{func.return_type}', "
                    f"but returned value of type '{get_value_type_name(result)}'"
                )
            if func.return_type == "float" and isinstance(result, int) and not isinstance(result, bool):
                result = float(result)
            return result

        raise MissingReturnError(
            f"Function '{func.name}' ended without returning a value"
        )

    def eval(
        self,
        node: Union[ExpressionNode, StatementNode, FunctionDeclaration, List[StatementNode]],
        env: Optional[Environment] = None,
        reset_steps: bool = True,
    ) -> Any:
        """Universal entry point to evaluate expressions, statements, functions, or blocks."""
        if reset_steps:
            self.step_count = 0
        eval_env = env if env is not None else Environment()

        if isinstance(node, (LiteralInt, LiteralFloat, LiteralBool, LiteralString, VariableRef, BinaryOp, FunctionCall)):
            return self.eval_expression(node, eval_env)

        if isinstance(node, FunctionDeclaration):
            return self.execute_function(node, eval_env)

        if isinstance(node, list):
            try:
                for stmt in node:
                    self.execute_statement(stmt, eval_env)
                return None
            except _ReturnSignal as ret:
                return ret.value

        if isinstance(node, (AssignStatement, IfElseStatement, ReturnStatement)):
            try:
                self.execute_statement(node, eval_env)
                return None
            except _ReturnSignal as ret:
                return ret.value

        raise InterpreterError(f"Cannot evaluate unsupported node type: {type(node)}")
