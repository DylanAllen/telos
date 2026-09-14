from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from src.compiler.builder import BuilderAgent
from src.runtime.interpreter import Environment, Interpreter, InterpreterError
from src.schema.nodes import FunctionDeclaration
from src.verifier.diagnostics import VerificationPhase, VerificationResult
from src.verifier.smt_solver import SMTVerifier
from src.verifier.type_checker import TypeChecker


LoopStatus = Literal["SUCCESS", "FAILED"]


class AttemptRecord(BaseModel):
    """Record of an individual iteration in the self-healing loop."""

    attempt_number: int
    phase_reached: Literal[
        "BUILDER", "STATIC_TYPE_CHECK", "SMT_SOLVER", "RUNTIME", "COMPLETED"
    ]
    ast_snapshot: Optional[Dict[str, Any]] = None
    diagnostic: Optional[VerificationResult] = None


class LoopResult(BaseModel):
    """Outcome and diagnostics of the closed self-healing loop."""

    status: LoopStatus
    ast: Optional[FunctionDeclaration] = None
    attempts: int
    history: List[AttemptRecord] = Field(default_factory=list)
    last_diagnostic: Optional[VerificationResult] = None
    output: Optional[Any] = None
    error_summary: Optional[str] = None


class SelfHealingLoop:
    """Closed loop connecting Builder, Type Checker, SMT Verifier, and Runtime Sandbox.

    Operates entirely autonomously: intercepts static type mismatches, formal invariant
    breaches, and runtime panics, constructs programmatic diagnostic error payloads,
    and reinvokes the Builder Agent for remediation up to max_retries.
    """

    def __init__(
        self,
        builder: Optional[BuilderAgent] = None,
        type_checker: Optional[TypeChecker] = None,
        smt_verifier: Optional[SMTVerifier] = None,
        interpreter: Optional[Interpreter] = None,
        max_retries: int = 3,
    ):
        self.builder = builder if builder is not None else BuilderAgent()
        self.type_checker = type_checker if type_checker is not None else TypeChecker()
        self.smt_verifier = smt_verifier if smt_verifier is not None else SMTVerifier()
        self.interpreter = interpreter if interpreter is not None else Interpreter()
        self.max_retries = max_retries

    def run(
        self,
        intent: str,
        test_inputs: Optional[Dict[str, Any]] = None,
        preconditions: Optional[List[str]] = None,
        check_division_safety: bool = True,
    ) -> LoopResult:
        """Execute the self-healing loop until formal convergence or retry exhaustion."""
        history: List[AttemptRecord] = []
        last_diagnostic: Optional[VerificationResult] = None
        last_ast: Optional[FunctionDeclaration] = None

        for attempt in range(1, self.max_retries + 1):
            # Phase 1: Builder synthesis (with feedback if previous attempt was rejected)
            try:
                ast = self.builder.build(intent, feedback=last_diagnostic)
                last_ast = ast
            except Exception as e:
                diag = VerificationResult.rejected(
                    phase="STATIC_TYPE_CHECK",
                    error_type="SCHEMA_DECODING_ERROR",
                    details=f"Failed to decode AST matching FunctionDeclaration schema: {e}",
                    instruction="Synthesize a valid JSON structure conforming strictly to FunctionDeclaration.",
                )
                last_diagnostic = diag
                history.append(
                    AttemptRecord(
                        attempt_number=attempt,
                        phase_reached="BUILDER",
                        diagnostic=diag,
                    )
                )
                continue

            ast_snapshot = ast.model_dump()

            # Phase 2: Static Type Check
            type_res = self.type_checker.check_function(ast)
            if type_res.status == "REJECTED":
                last_diagnostic = type_res
                history.append(
                    AttemptRecord(
                        attempt_number=attempt,
                        phase_reached="STATIC_TYPE_CHECK",
                        ast_snapshot=ast_snapshot,
                        diagnostic=type_res,
                    )
                )
                continue

            # Phase 3: Formal SMT Invariant Verification
            smt_res = self.smt_verifier.verify_function(
                ast,
                preconditions=preconditions,
                check_division_safety=check_division_safety,
            )
            if smt_res.status == "REJECTED":
                last_diagnostic = smt_res
                history.append(
                    AttemptRecord(
                        attempt_number=attempt,
                        phase_reached="SMT_SOLVER",
                        ast_snapshot=ast_snapshot,
                        diagnostic=smt_res,
                    )
                )
                continue

            # Phase 4: Sandboxed Runtime Evaluation (if concrete test_inputs provided)
            runtime_output = None
            if test_inputs is not None:
                env = Environment()
                param_types = {p.name: p.param_type for p in ast.parameters}
                for k, v in test_inputs.items():
                    var_type = param_types.get(k, "int")
                    env.define(k, v, var_type)

                try:
                    runtime_output = self.interpreter.execute_function(ast, env)
                except (InterpreterError, ZeroDivisionError, Exception) as e:
                    runtime_diag = VerificationResult.rejected(
                        phase="RUNTIME",
                        error_type=type(e).__name__,
                        details=f"Sandboxed runtime execution panicked: {e}",
                        instruction="Revise logic to eliminate runtime failure.",
                        failed_ast_snapshot=ast_snapshot,
                    )
                    last_diagnostic = runtime_diag
                    history.append(
                        AttemptRecord(
                            attempt_number=attempt,
                            phase_reached="RUNTIME",
                            ast_snapshot=ast_snapshot,
                            diagnostic=runtime_diag,
                        )
                    )
                    continue

            # Success: All verification layers approved
            history.append(
                AttemptRecord(
                    attempt_number=attempt,
                    phase_reached="COMPLETED",
                    ast_snapshot=ast_snapshot,
                    diagnostic=VerificationResult.approved(phase="RUNTIME"),
                )
            )

            return LoopResult(
                status="SUCCESS",
                ast=ast,
                attempts=attempt,
                history=history,
                output=runtime_output,
            )

        # Retries exhausted: Report contradiction and failure diagnostics
        error_summary = (
            f"Self-healing loop exhausted {self.max_retries} attempts without convergence. "
            f"Last failure in phase '{last_diagnostic.phase if last_diagnostic else 'UNKNOWN'}' "
            f"[{last_diagnostic.error_type if last_diagnostic else 'UNKNOWN'}]: "
            f"{last_diagnostic.details if last_diagnostic else 'N/A'}"
        )

        return LoopResult(
            status="FAILED",
            ast=last_ast,
            attempts=self.max_retries,
            history=history,
            last_diagnostic=last_diagnostic,
            error_summary=error_summary,
        )
