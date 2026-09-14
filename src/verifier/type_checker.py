from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Union

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
from src.verifier.diagnostics import VerificationResult


class TypeEnvironment:
    """Lexically-scoped static type environment."""

    def __init__(self, parent: Optional[TypeEnvironment] = None):
        self.parent: Optional[TypeEnvironment] = parent
        self.bindings: Dict[str, PrimitiveType] = {}

    def define(self, name: str, var_type: PrimitiveType) -> None:
        """Define or update variable in the current scope."""
        self.bindings[name] = var_type

    def lookup(self, name: str) -> Optional[PrimitiveType]:
        """Look up variable type in current or parent scopes."""
        if name in self.bindings:
            return self.bindings[name]
        if self.parent is not None:
            return self.parent.lookup(name)
        return None

    def child_scope(self) -> TypeEnvironment:
        """Create a nested type environment child scope."""
        return TypeEnvironment(parent=self)


class TypeChecker:
    """Static type analyzer for AST expressions, statements, and function declarations."""

    def __init__(self, function_registry: Optional[Dict[str, FunctionDeclaration]] = None):
        self.function_registry: Dict[str, FunctionDeclaration] = (
            dict(function_registry) if function_registry else {}
        )

    def register_function(self, identifier: str, func: FunctionDeclaration) -> None:
        """Register a known function declaration for cross-function type verification."""
        self.function_registry[identifier] = func

    def check_expression(
        self, expr: ExpressionNode, env: TypeEnvironment, path: str = "expression"
    ) -> Tuple[Optional[PrimitiveType], Optional[VerificationResult]]:
        """Infer the type of an expression or return a diagnostic failure."""
        if isinstance(expr, LiteralInt):
            return "int", None
        if isinstance(expr, LiteralFloat):
            return "float", None
        if isinstance(expr, LiteralBool):
            return "bool", None
        if isinstance(expr, LiteralString):
            return "string", None

        if isinstance(expr, VariableRef):
            var_type = env.lookup(expr.name)
            if var_type is None:
                return None, VerificationResult.rejected(
                    phase="STATIC_TYPE_CHECK",
                    error_type="UNDEFINED_VARIABLE",
                    details=f"Variable '{expr.name}' is referenced before assignment or declaration",
                    node_path=path,
                    instruction=f"Declare or assign variable '{expr.name}' before referencing it.",
                    failed_ast_snapshot=expr.model_dump(),
                )
            return var_type, None

        if isinstance(expr, BinaryOp):
            left_type, err = self.check_expression(expr.left, env, f"{path}.left")
            if err:
                return None, err
            right_type, err = self.check_expression(expr.right, env, f"{path}.right")
            if err:
                return None, err

            op = expr.op

            # Arithmetic operations
            if op == "add":
                if left_type == "int" and right_type == "int":
                    return "int", None
                if left_type in ("int", "float") and right_type in ("int", "float"):
                    return "float", None
                if left_type == "string" and right_type == "string":
                    return "string", None
                return None, VerificationResult.rejected(
                    phase="STATIC_TYPE_CHECK",
                    error_type="TYPE_MISMATCH",
                    details=f"BinaryOp 'add' received operands of incompatible types: {left_type} and {right_type}",
                    node_path=path,
                    instruction=f"Fix node {path}. Cast or convert operands to compatible types.",
                    failed_ast_snapshot=expr.model_dump(),
                )

            if op in ("sub", "mul"):
                if left_type == "int" and right_type == "int":
                    return "int", None
                if left_type in ("int", "float") and right_type in ("int", "float"):
                    return "float", None
                return None, VerificationResult.rejected(
                    phase="STATIC_TYPE_CHECK",
                    error_type="TYPE_MISMATCH",
                    details=f"BinaryOp '{op}' requires numeric operands, received {left_type} and {right_type}",
                    node_path=path,
                    instruction=f"Ensure both operands for '{op}' are numeric (int or float).",
                    failed_ast_snapshot=expr.model_dump(),
                )

            if op == "div":
                if left_type == "int" and right_type == "int":
                    return "int", None
                if left_type in ("int", "float") and right_type in ("int", "float"):
                    return "float", None
                return None, VerificationResult.rejected(
                    phase="STATIC_TYPE_CHECK",
                    error_type="TYPE_MISMATCH",
                    details=f"BinaryOp 'div' requires numeric operands, received {left_type} and {right_type}",
                    node_path=path,
                    instruction=f"Ensure both operands for 'div' are numeric (int or float).",
                    failed_ast_snapshot=expr.model_dump(),
                )

            if op == "mod":
                if left_type == "int" and right_type == "int":
                    return "int", None
                return None, VerificationResult.rejected(
                    phase="STATIC_TYPE_CHECK",
                    error_type="TYPE_MISMATCH",
                    details=f"BinaryOp 'mod' requires integer operands, received {left_type} and {right_type}",
                    node_path=path,
                    instruction=f"Ensure both operands for 'mod' are integers.",
                    failed_ast_snapshot=expr.model_dump(),
                )

            # Equality operations
            if op in ("eq", "neq"):
                if {left_type, right_type} <= {"int", "float"} or left_type == right_type:
                    return "bool", None
                return None, VerificationResult.rejected(
                    phase="STATIC_TYPE_CHECK",
                    error_type="TYPE_MISMATCH",
                    details=f"BinaryOp '{op}' received operands of incompatible types: {left_type} and {right_type}",
                    node_path=path,
                    instruction=f"Ensure compared types are comparable.",
                    failed_ast_snapshot=expr.model_dump(),
                )

            # Ordering comparisons
            if op in ("lt", "lte", "gt", "gte"):
                if {left_type, right_type} <= {"int", "float"}:
                    return "bool", None
                if left_type == "string" and right_type == "string":
                    return "bool", None
                return None, VerificationResult.rejected(
                    phase="STATIC_TYPE_CHECK",
                    error_type="TYPE_MISMATCH",
                    details=f"BinaryOp '{op}' requires numeric or string operands, received {left_type} and {right_type}",
                    node_path=path,
                    instruction=f"Ensure both operands for '{op}' are both numbers or both strings.",
                    failed_ast_snapshot=expr.model_dump(),
                )

            return None, VerificationResult.rejected(
                phase="STATIC_TYPE_CHECK",
                error_type="UNKNOWN_OPERATOR",
                details=f"Unknown binary operator '{op}'",
                node_path=path,
                failed_ast_snapshot=expr.model_dump(),
            )

        if isinstance(expr, FunctionCall):
            target_func = self.function_registry.get(expr.target_hash)
            if target_func is None:
                return None, VerificationResult.rejected(
                    phase="STATIC_TYPE_CHECK",
                    error_type="UNDEFINED_FUNCTION",
                    details=f"Function target hash '{expr.target_hash}' not found in registry",
                    node_path=path,
                    instruction=f"Ensure the called function hash '{expr.target_hash}' exists in the CAS / registry.",
                    failed_ast_snapshot=expr.model_dump(),
                )

            if len(expr.arguments) != len(target_func.parameters):
                return None, VerificationResult.rejected(
                    phase="STATIC_TYPE_CHECK",
                    error_type="ARGUMENT_COUNT_MISMATCH",
                    details=(
                        f"Function '{target_func.name}' expects {len(target_func.parameters)} arguments, "
                        f"received {len(expr.arguments)}"
                    ),
                    node_path=path,
                    instruction=f"Supply exactly {len(target_func.parameters)} arguments.",
                    failed_ast_snapshot=expr.model_dump(),
                )

            for i, (arg, param) in enumerate(zip(expr.arguments, target_func.parameters)):
                arg_type, err = self.check_expression(arg, env, f"{path}.arguments[{i}]")
                if err:
                    return None, err
                if arg_type != param.param_type and not (param.param_type == "float" and arg_type == "int"):
                    return None, VerificationResult.rejected(
                        phase="STATIC_TYPE_CHECK",
                        error_type="TYPE_MISMATCH",
                        details=(
                            f"Argument {i} ('{param.name}') of function '{target_func.name}' expects type "
                            f"'{param.param_type}', but received '{arg_type}'"
                        ),
                        node_path=f"{path}.arguments[{i}]",
                        instruction=f"Cast or convert argument {i} to '{param.param_type}'.",
                        failed_ast_snapshot=arg.model_dump(),
                    )

            return target_func.return_type, None

        return None, VerificationResult.rejected(
            phase="STATIC_TYPE_CHECK",
            error_type="UNKNOWN_NODE",
            details=f"Unknown expression node type '{type(expr)}'",
            node_path=path,
        )

    def check_statement(
        self,
        stmt: StatementNode,
        env: TypeEnvironment,
        expected_return_type: PrimitiveType,
        path: str,
    ) -> Tuple[bool, Optional[VerificationResult]]:
        """Validate a statement node. Returns (definitely_returns, Optional[VerificationResult])."""
        if isinstance(stmt, AssignStatement):
            expr_type, err = self.check_expression(stmt.expression, env, f"{path}.expression")
            if err:
                return False, err

            # Check type compatibility
            compatible = (expr_type == stmt.variable_type) or (
                stmt.variable_type == "float" and expr_type == "int"
            )
            if not compatible:
                return False, VerificationResult.rejected(
                    phase="STATIC_TYPE_CHECK",
                    error_type="TYPE_MISMATCH",
                    details=(
                        f"Cannot assign expression of type '{expr_type}' to variable '{stmt.variable_name}' "
                        f"declared as '{stmt.variable_type}'"
                    ),
                    node_path=f"{path}.expression",
                    instruction=(
                        f"Fix node {path}.expression. Ensure the value type matches "
                        f"declared variable type '{stmt.variable_type}'."
                    ),
                    failed_ast_snapshot=stmt.model_dump(),
                )

            existing_type = env.lookup(stmt.variable_name)
            if existing_type is not None and existing_type != stmt.variable_type:
                return False, VerificationResult.rejected(
                    phase="STATIC_TYPE_CHECK",
                    error_type="VARIABLE_REDECLARATION",
                    details=(
                        f"Variable '{stmt.variable_name}' was previously declared as '{existing_type}', "
                        f"cannot redeclare as '{stmt.variable_type}'"
                    ),
                    node_path=path,
                    instruction=f"Maintain consistent type '{existing_type}' for variable '{stmt.variable_name}'.",
                    failed_ast_snapshot=stmt.model_dump(),
                )

            env.define(stmt.variable_name, stmt.variable_type)
            return False, None

        if isinstance(stmt, IfElseStatement):
            cond_type, err = self.check_expression(stmt.condition, env, f"{path}.condition")
            if err:
                return False, err
            if cond_type != "bool":
                return False, VerificationResult.rejected(
                    phase="STATIC_TYPE_CHECK",
                    error_type="TYPE_MISMATCH",
                    details=f"Condition expression must evaluate to 'bool', received '{cond_type}'",
                    node_path=f"{path}.condition",
                    instruction=f"Ensure condition at {path}.condition produces a boolean value.",
                    failed_ast_snapshot=stmt.condition.model_dump(),
                )

            # Check then branch
            then_env = env.child_scope()
            then_returns, err = self._check_block(
                stmt.then_branch, then_env, expected_return_type, f"{path}.then_branch"
            )
            if err:
                return False, err

            # Check else branch if present
            else_returns = False
            if stmt.else_branch is not None:
                else_env = env.child_scope()
                else_returns, err = self._check_block(
                    stmt.else_branch, else_env, expected_return_type, f"{path}.else_branch"
                )
                if err:
                    return False, err

            # Both branches must definitely return for the if-else statement to definitely return
            return (then_returns and else_returns), None

        if isinstance(stmt, ReturnStatement):
            expr_type, err = self.check_expression(stmt.value, env, f"{path}.value")
            if err:
                return False, err

            compatible = (expr_type == expected_return_type) or (
                expected_return_type == "float" and expr_type == "int"
            )
            if not compatible:
                return False, VerificationResult.rejected(
                    phase="STATIC_TYPE_CHECK",
                    error_type="RETURN_TYPE_MISMATCH",
                    details=(
                        f"Function declared return type '{expected_return_type}', "
                        f"but ReturnStatement returned value of type '{expr_type}'"
                    ),
                    node_path=f"{path}.value",
                    instruction=(
                        f"Fix node {path}.value. Ensure returned expression conforms "
                        f"to expected return type '{expected_return_type}'."
                    ),
                    failed_ast_snapshot=stmt.model_dump(),
                )
            return True, None

        return False, VerificationResult.rejected(
            phase="STATIC_TYPE_CHECK",
            error_type="UNKNOWN_NODE",
            details=f"Unknown statement node type '{type(stmt)}'",
            node_path=path,
        )

    def _check_block(
        self,
        statements: List[StatementNode],
        env: TypeEnvironment,
        expected_return_type: PrimitiveType,
        path_prefix: str,
    ) -> Tuple[bool, Optional[VerificationResult]]:
        """Validate a sequence of statements."""
        has_returned = False
        for i, stmt in enumerate(statements):
            stmt_path = f"{path_prefix}[{i}]"
            returns, err = self.check_statement(stmt, env, expected_return_type, stmt_path)
            if err:
                return False, err
            if returns:
                has_returned = True
                # Any statements after an unconditional return in the same block are dead code
                break
        return has_returned, None

    def check_function(self, func: FunctionDeclaration) -> VerificationResult:
        """Validate an entire function declaration statically."""
        env = TypeEnvironment()

        # Define all function parameters in the root environment
        for param in func.parameters:
            env.define(param.name, param.param_type)

        definitely_returns, err = self._check_block(
            func.body, env, func.return_type, "body"
        )
        if err:
            return err

        if not definitely_returns:
            last_index = len(func.body) - 1 if func.body else 0
            return VerificationResult.rejected(
                phase="STATIC_TYPE_CHECK",
                error_type="MISSING_RETURN",
                details=(
                    f"Function '{func.name}' lacks a guaranteed return statement on all execution paths "
                    f"matching declared return type '{func.return_type}'"
                ),
                node_path=f"body[{last_index}]" if func.body else "body",
                instruction=f"Add a final ReturnStatement returning a value of type '{func.return_type}'.",
                failed_ast_snapshot=func.model_dump(),
            )

        return VerificationResult.approved(phase="STATIC_TYPE_CHECK")
