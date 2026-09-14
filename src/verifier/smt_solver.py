from __future__ import annotations

import ast as py_ast
from typing import Any, Dict, List, Optional, Tuple, Union
import z3

from src.schema.nodes import (
    AssignStatement,
    BinaryOp,
    ExpressionNode,
    FunctionDeclaration,
    IfElseStatement,
    LiteralBool,
    LiteralFloat,
    LiteralInt,
    LiteralString,
    ReturnStatement,
    StatementNode,
    VariableRef,
)
from src.verifier.diagnostics import VerificationResult


class SymbolicExecutionError(Exception):
    """Internal error during symbolic AST translation."""
    pass


class SMTVerifier:
    """Z3 SMT Solver for formal verification of AST invariants and runtime safety constraints."""

    def __init__(self):
        pass

    def _create_symbolic_var(self, name: str, var_type: str) -> Any:
        """Instantiate a Z3 symbolic variable corresponding to a Telos primitive type."""
        if var_type == "int":
            return z3.Int(name)
        if var_type == "float":
            return z3.Real(name)
        if var_type == "bool":
            return z3.Bool(name)
        if var_type == "string":
            return z3.String(name)
        raise SymbolicExecutionError(f"Unsupported symbolic variable type: '{var_type}'")

    def _eval_expression_symbolic(
        self,
        expr: ExpressionNode,
        env: Dict[str, Any],
        path: str,
        division_checks: List[Tuple[Any, str]],
    ) -> Any:
        """Translate an AST expression node into a Z3 symbolic expression."""
        if isinstance(expr, LiteralInt):
            return z3.IntVal(expr.value)
        if isinstance(expr, LiteralFloat):
            return z3.RealVal(expr.value)
        if isinstance(expr, LiteralBool):
            return z3.BoolVal(expr.value)
        if isinstance(expr, LiteralString):
            return z3.StringVal(expr.value)

        if isinstance(expr, VariableRef):
            if expr.name not in env:
                raise SymbolicExecutionError(
                    f"Variable '{expr.name}' not bound in symbolic environment"
                )
            return env[expr.name]

        if isinstance(expr, BinaryOp):
            left = self._eval_expression_symbolic(
                expr.left, env, f"{path}.left", division_checks
            )
            right = self._eval_expression_symbolic(
                expr.right, env, f"{path}.right", division_checks
            )
            op = expr.op

            # Arithmetic
            if op == "add":
                return left + right
            if op == "sub":
                return left - right
            if op == "mul":
                return left * right
            if op == "div":
                # Track divisor for division-by-zero check
                division_checks.append((right, path))
                return left / right
            if op == "mod":
                division_checks.append((right, path))
                return left % right

            # Comparisons
            if op == "eq":
                return left == right
            if op == "neq":
                return left != right
            if op == "lt":
                return left < right
            if op == "lte":
                return left <= right
            if op == "gt":
                return left > right
            if op == "gte":
                return left >= right

            raise SymbolicExecutionError(f"Unsupported binary operator in Z3: '{op}'")

        raise SymbolicExecutionError(f"Unsupported AST node in Z3 translation: '{type(expr)}'")

    def _execute_body_symbolic(
        self,
        body: List[StatementNode],
        env: Dict[str, Any],
        path_prefix: str,
        division_checks: List[Tuple[Any, str]],
    ) -> Tuple[Dict[str, Any], Optional[Any]]:
        """Symbolically execute a list of statements, producing updated state and return expression."""
        current_env = dict(env)
        return_expr: Optional[Any] = None

        for i, stmt in enumerate(body):
            stmt_path = f"{path_prefix}[{i}]"

            if isinstance(stmt, AssignStatement):
                val = self._eval_expression_symbolic(
                    stmt.expression, current_env, f"{stmt_path}.expression", division_checks
                )
                current_env[stmt.variable_name] = val

            elif isinstance(stmt, IfElseStatement):
                cond = self._eval_expression_symbolic(
                    stmt.condition, current_env, f"{stmt_path}.condition", division_checks
                )

                then_env, then_ret = self._execute_body_symbolic(
                    stmt.then_branch, current_env, f"{stmt_path}.then_branch", division_checks
                )

                else_env: Dict[str, Any] = current_env
                else_ret: Optional[Any] = None
                if stmt.else_branch:
                    else_env, else_ret = self._execute_body_symbolic(
                        stmt.else_branch, current_env, f"{stmt_path}.else_branch", division_checks
                    )

                # Merge variable states across branches using z3.If
                all_keys = set(then_env.keys()) | set(else_env.keys())
                merged_env: Dict[str, Any] = {}
                for k in all_keys:
                    v_then = then_env.get(k, current_env.get(k))
                    v_else = else_env.get(k, current_env.get(k))
                    if v_then is not None and v_else is not None:
                        if v_then is v_else:
                            merged_env[k] = v_then
                        else:
                            merged_env[k] = z3.If(cond, v_then, v_else)
                    elif v_then is not None:
                        merged_env[k] = v_then
                    elif v_else is not None:
                        merged_env[k] = v_else

                current_env = merged_env

                # Merge returns if both branches returned
                if then_ret is not None and else_ret is not None:
                    return_expr = z3.If(cond, then_ret, else_ret)
                elif then_ret is not None:
                    return_expr = then_ret
                elif else_ret is not None:
                    return_expr = else_ret

            elif isinstance(stmt, ReturnStatement):
                val = self._eval_expression_symbolic(
                    stmt.value, current_env, f"{stmt_path}.value", division_checks
                )
                return_expr = val
                break

        return current_env, return_expr

    def _parse_invariant_to_z3(
        self, invariant_str: str, symbols: Dict[str, Any]
    ) -> Any:
        """Parse a declarative invariant string expression into a Z3 boolean proposition."""
        try:
            parsed = py_ast.parse(invariant_str, mode="eval")
        except Exception as e:
            raise SymbolicExecutionError(f"Failed to parse invariant string '{invariant_str}': {e}")

        def _walk(node: py_ast.AST) -> Any:
            if isinstance(node, py_ast.Expression):
                return _walk(node.body)

            if isinstance(node, py_ast.Constant):
                val = node.value
                if isinstance(val, bool):
                    return z3.BoolVal(val)
                if isinstance(val, int):
                    return z3.IntVal(val)
                if isinstance(val, float):
                    return z3.RealVal(val)
                if isinstance(val, str):
                    return z3.StringVal(val)
                return val

            if isinstance(node, py_ast.Name):
                name = node.id
                # Map standard aliases
                if name in ("return_value", "result"):
                    if "return_value" in symbols:
                        return symbols["return_value"]
                    if "result" in symbols:
                        return symbols["result"]
                if name in symbols:
                    return symbols[name]
                raise SymbolicExecutionError(
                    f"Unknown symbol '{name}' in invariant '{invariant_str}'"
                )

            if isinstance(node, py_ast.UnaryOp):
                operand = _walk(node.operand)
                if isinstance(node.op, py_ast.Not):
                    return z3.Not(operand)
                if isinstance(node.op, py_ast.USub):
                    return -operand
                raise SymbolicExecutionError(f"Unsupported unary operator in invariant: {type(node.op)}")

            if isinstance(node, py_ast.BinOp):
                left = _walk(node.left)
                right = _walk(node.right)
                if isinstance(node.op, py_ast.Add):
                    return left + right
                if isinstance(node.op, py_ast.Sub):
                    return left - right
                if isinstance(node.op, py_ast.Mult):
                    return left * right
                if isinstance(node.op, py_ast.Div):
                    return left / right
                if isinstance(node.op, py_ast.Mod):
                    return left % right
                raise SymbolicExecutionError(f"Unsupported binary operator in invariant: {type(node.op)}")

            if isinstance(node, py_ast.BoolOp):
                values = [_walk(val) for val in node.values]
                if isinstance(node.op, py_ast.And):
                    return z3.And(*values)
                if isinstance(node.op, py_ast.Or):
                    return z3.Or(*values)
                raise SymbolicExecutionError(f"Unsupported boolean operator in invariant: {type(node.op)}")

            if isinstance(node, py_ast.Compare):
                left = _walk(node.left)
                comparisons = []
                current_left = left
                for op, comp in zip(node.ops, node.comparators):
                    right = _walk(comp)
                    if isinstance(op, py_ast.Eq):
                        comparisons.append(current_left == right)
                    elif isinstance(op, py_ast.NotEq):
                        comparisons.append(current_left != right)
                    elif isinstance(op, py_ast.Lt):
                        comparisons.append(current_left < right)
                    elif isinstance(op, py_ast.LtE):
                        comparisons.append(current_left <= right)
                    elif isinstance(op, py_ast.Gt):
                        comparisons.append(current_left > right)
                    elif isinstance(op, py_ast.GtE):
                        comparisons.append(current_left >= right)
                    else:
                        raise SymbolicExecutionError(f"Unsupported comparison operator: {type(op)}")
                    current_left = right

                if len(comparisons) == 1:
                    return comparisons[0]
                return z3.And(*comparisons)

            raise SymbolicExecutionError(f"Unsupported AST node in invariant: {type(node)}")

        return _walk(parsed)

    def _extract_counterexample(
        self, model: z3.ModelRef, param_vars: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract concrete values from a Z3 satisfying model for all parameter variables."""
        counterexample: Dict[str, Any] = {}
        for name, var in param_vars.items():
            val = model.eval(var, model_completion=True)
            if z3.is_int(val):
                counterexample[name] = val.as_long()
            elif z3.is_real(val):
                # Convert Z3 rational / algebraic number to float
                try:
                    num = val.as_fraction()
                    counterexample[name] = float(num)
                except Exception:
                    counterexample[name] = float(val.as_decimal(6).rstrip("?"))
            elif z3.is_bool(val):
                counterexample[name] = z3.is_true(val)
            elif z3.is_string(val):
                counterexample[name] = val.as_string()
            else:
                counterexample[name] = str(val)
        return counterexample

    def verify_function(
        self,
        func: FunctionDeclaration,
        preconditions: Optional[List[str]] = None,
        check_division_safety: bool = True,
    ) -> VerificationResult:
        """Formally verify mathematical invariants and runtime safety on a function declaration."""
        # 1. Initialize symbolic parameter variables
        param_vars: Dict[str, Any] = {}
        for param in func.parameters:
            param_vars[param.name] = self._create_symbolic_var(
                param.name, param.param_type
            )

        # 2. Symbolically execute function body
        division_checks: List[Tuple[Any, str]] = []
        try:
            final_env, return_expr = self._execute_body_symbolic(
                func.body, param_vars, "body", division_checks
            )
        except SymbolicExecutionError as e:
            return VerificationResult.rejected(
                phase="SMT_SOLVER",
                error_type="SYMBOLIC_TRANSLATION_ERROR",
                details=str(e),
                failed_ast_snapshot=func.model_dump(),
            )

        # Build symbol table for invariant resolution
        symbols: Dict[str, Any] = dict(final_env)
        if return_expr is not None:
            symbols["return_value"] = return_expr
            symbols["result"] = return_expr

        # 3. Translate preconditions
        precond_formulas: List[Any] = []
        if preconditions:
            for pre in preconditions:
                try:
                    formula = self._parse_invariant_to_z3(pre, symbols)
                    precond_formulas.append(formula)
                except SymbolicExecutionError as e:
                    return VerificationResult.rejected(
                        phase="SMT_SOLVER",
                        error_type="PRECONDITION_PARSE_ERROR",
                        details=str(e),
                        failed_ast_snapshot=func.model_dump(),
                    )

        # 4. Check declared mathematical invariants
        for invariant_str in func.invariants:
            try:
                inv_formula = self._parse_invariant_to_z3(invariant_str, symbols)
            except SymbolicExecutionError as e:
                return VerificationResult.rejected(
                    phase="SMT_SOLVER",
                    error_type="INVARIANT_PARSE_ERROR",
                    details=str(e),
                    failed_ast_snapshot=func.model_dump(),
                )

            # Assert preconditions and NOT(invariant)
            solver = z3.Solver()
            for pre in precond_formulas:
                solver.add(pre)
            solver.add(z3.Not(inv_formula))

            check_res = solver.check()
            if check_res == z3.sat:
                model = solver.model()
                counterexample = self._extract_counterexample(model, param_vars)
                return VerificationResult.rejected(
                    phase="SMT_SOLVER",
                    error_type="INVARIANT_VIOLATION",
                    details=(
                        f"Invariant '{invariant_str}' violated for function '{func.name}' "
                        f"under counterexample: {counterexample}"
                    ),
                    counterexample=counterexample,
                    instruction=(
                        f"Constrain inputs with preconditions or revise logic to ensure "
                        f"invariant '{invariant_str}' holds for all valid inputs."
                    ),
                    failed_ast_snapshot=func.model_dump(),
                )

        # 5. Check implicit division safety (divisor != 0)
        if check_division_safety:
            for divisor_expr, div_path in division_checks:
                solver = z3.Solver()
                for pre in precond_formulas:
                    solver.add(pre)
                solver.add(divisor_expr == 0)

                if solver.check() == z3.sat:
                    model = solver.model()
                    counterexample = self._extract_counterexample(model, param_vars)
                    return VerificationResult.rejected(
                        phase="SMT_SOLVER",
                        error_type="DIVISION_BY_ZERO",
                        details=(
                            f"Potential division by zero detected at node '{div_path}' "
                            f"under counterexample: {counterexample}"
                        ),
                        node_path=div_path,
                        counterexample=counterexample,
                        instruction=(
                            f"Add a precondition or conditional guard ensuring divisor at "
                            f"'{div_path}' cannot be zero."
                        ),
                        failed_ast_snapshot=func.model_dump(),
                    )

        return VerificationResult.approved(phase="SMT_SOLVER")
