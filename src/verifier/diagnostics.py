from __future__ import annotations

from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field


VerificationPhase = Literal["STATIC_TYPE_CHECK", "SMT_SOLVER", "RUNTIME"]
VerificationStatus = Literal["APPROVED", "REJECTED"]


class VerificationResult(BaseModel):
    """Structured diagnostics payload for AST verification and self-healing loop."""

    status: VerificationStatus
    phase: VerificationPhase
    node_path: Optional[str] = Field(
        default=None,
        description="Path within the AST where the diagnostic occurred, e.g. 'body[0].expression.right'",
    )
    error_type: Optional[str] = Field(
        default=None,
        description="Categorical error code, e.g. 'TYPE_MISMATCH', 'INVARIANT_VIOLATION', 'DIVISION_BY_ZERO'",
    )
    details: Optional[str] = Field(
        default=None,
        description="Human- and agent-readable description of the verification failure",
    )
    counterexample: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Concrete variable values found by SMT solver that violate invariant",
    )
    failed_ast_snapshot: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Snapshot of the AST or sub-AST where the issue was detected",
    )
    instruction: Optional[str] = Field(
        default=None,
        description="Actionable instruction guiding the Builder Agent on how to fix the error",
    )

    @classmethod
    def approved(cls, phase: VerificationPhase) -> VerificationResult:
        """Create a successful approval result."""
        return cls(status="APPROVED", phase=phase)

    @classmethod
    def rejected(
        cls,
        phase: VerificationPhase,
        error_type: str,
        details: str,
        node_path: Optional[str] = None,
        instruction: Optional[str] = None,
        counterexample: Optional[Dict[str, Any]] = None,
        failed_ast_snapshot: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """Create a rejected diagnostic result."""
        return cls(
            status="REJECTED",
            phase=phase,
            error_type=error_type,
            details=details,
            node_path=node_path,
            instruction=instruction,
            counterexample=counterexample,
            failed_ast_snapshot=failed_ast_snapshot,
        )
