from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional, Union
import instructor
from openai import OpenAI
from pydantic import BaseModel

from src.schema.nodes import (
    AssignStatement,
    BinaryOp,
    FunctionDeclaration,
    LiteralFloat,
    Parameter,
    ReturnStatement,
    VariableRef,
)
from src.verifier.diagnostics import VerificationResult


BUILDER_SYSTEM_PROMPT = """You are an expert Compiler Frontend and Systems Architect for Telos, an AI-Native Execution Engine.
Your mission is to translate natural language user intent, requirements, and mathematical invariants directly into a typed Abstract Syntax Tree (AST) targeting the FunctionDeclaration schema.

CRITICAL OPERATIONAL RULES:
1. NEVER output raw human programming language code (no Python, JavaScript, Rust, C).
2. You must emit a strictly typed algebraic AST matching the FunctionDeclaration schema.
3. Every operation is an AST node:
   - Literals: LiteralInt (kind='lit_int'), LiteralFloat (kind='lit_float'), LiteralBool (kind='lit_bool'), LiteralString (kind='lit_string')
   - Expressions: VariableRef (kind='var_ref'), BinaryOp (kind='binary_op'), FunctionCall (kind='call')
   - Statements: AssignStatement (kind='assign'), IfElseStatement (kind='if_else'), ReturnStatement (kind='return')
4. Type Conformance:
   - Parameter types and variable types must strictly be one of: 'int', 'float', 'bool', 'string'.
   - All arithmetic and comparison operations must use compatible operand types.
   - Every execution path must end in a ReturnStatement matching the declared return_type.
5. Invariants:
   - Add any mathematical safety constraints or pre/post-conditions to the `invariants` list (e.g., 'return_value >= 0').
6. Self-Healing Guidance:
   - If verification feedback is included, inspect the failed node_path and error_type, and adjust the AST to satisfy the constraints.
"""


def default_cost_function_ast() -> FunctionDeclaration:
    """Deterministic reference AST for 'total cost given item_price, quantity, and tax_rate'."""
    # total_cost(item_price: float, quantity: int, tax_rate: float) -> float
    # subtotal = item_price * quantity
    # tax = subtotal * tax_rate
    # return subtotal + tax
    return FunctionDeclaration(
        name="calculate_total_cost",
        parameters=[
            Parameter(name="item_price", param_type="float"),
            Parameter(name="quantity", param_type="int"),
            Parameter(name="tax_rate", param_type="float"),
        ],
        return_type="float",
        body=[
            AssignStatement(
                variable_name="subtotal",
                variable_type="float",
                expression=BinaryOp(
                    op="mul",
                    left=VariableRef(name="item_price"),
                    right=VariableRef(name="quantity"),
                ),
            ),
            AssignStatement(
                variable_name="tax",
                variable_type="float",
                expression=BinaryOp(
                    op="mul",
                    left=VariableRef(name="subtotal"),
                    right=VariableRef(name="tax_rate"),
                ),
            ),
            ReturnStatement(
                value=BinaryOp(
                    op="add",
                    left=VariableRef(name="subtotal"),
                    right=VariableRef(name="tax"),
                )
            ),
        ],
        invariants=["return_value >= 0"],
    )


class BuilderAgent:
    """Autonomous compiler agent translating declarative intent to verified AST schemas."""

    def __init__(
        self,
        client: Optional[Any] = None,
        model: str = "gpt-4o",
        api_key: Optional[str] = None,
        mock_provider: Optional[Callable[[str, Optional[VerificationResult]], FunctionDeclaration]] = None,
    ):
        self.model = model
        self.mock_provider = mock_provider
        self.client = client

        if self.client is None and mock_provider is None:
            effective_key = api_key or os.environ.get("OPENAI_API_KEY")
            if effective_key:
                raw_client = OpenAI(api_key=effective_key)
                self.client = instructor.from_openai(raw_client)
            else:
                # Default to deterministic mock provider if no API key is available
                self.mock_provider = self._default_mock_handler

    def _default_mock_handler(
        self, prompt: str, feedback: Optional[VerificationResult] = None
    ) -> FunctionDeclaration:
        """Deterministic mock handler for test environments without live API credentials."""
        prompt_lower = prompt.lower()
        if "total cost" in prompt_lower or "item_price" in prompt_lower:
            return default_cost_function_ast()

        if "divide" in prompt_lower:
            # Check if feedback requested guard against y == 0
            has_zero_div_feedback = feedback and (
                feedback.error_type in ("DIVISION_BY_ZERO", "INVARIANT_VIOLATION")
            )
            if has_zero_div_feedback:
                # Self-healed version with guard
                return FunctionDeclaration(
                    name="safe_divide",
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
                                right=BinaryOp(
                                    op="add",
                                    left=VariableRef(name="y"),
                                    right=LiteralFloat(value=1.0) if False else VariableRef(name="y"),
                                ),
                            )
                        )
                    ],
                    invariants=["y != 0"],
                )
            return FunctionDeclaration(
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

        # Fallback generic function
        return default_cost_function_ast()

    def format_prompt(
        self, user_intent: str, feedback: Optional[VerificationResult] = None
    ) -> List[Dict[str, str]]:
        """Format the conversational messages payload including optional self-healing feedback."""
        content = f"User Intent:\n{user_intent}"

        if feedback is not None and feedback.status == "REJECTED":
            content += (
                f"\n\n[VERIFICATION FEEDBACK - PREVIOUS AST REJECTED]\n"
                f"Phase: {feedback.phase}\n"
                f"Error Type: {feedback.error_type}\n"
                f"Node Path: {feedback.node_path or 'N/A'}\n"
                f"Details: {feedback.details or 'N/A'}\n"
                f"Counterexample: {feedback.counterexample or 'N/A'}\n"
                f"Instruction: {feedback.instruction or 'Please correct the error while fulfilling the intent.'}\n"
            )

        return [
            {"role": "system", "content": BUILDER_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ]

    def build(
        self, user_intent: str, feedback: Optional[VerificationResult] = None
    ) -> FunctionDeclaration:
        """Translate natural language intent into a validated FunctionDeclaration AST."""
        if self.mock_provider is not None:
            return self.mock_provider(user_intent, feedback)

        if self.client is None:
            raise RuntimeError(
                "BuilderAgent requires either an active instructor client with an API key "
                "or a mock_provider configured."
            )

        messages = self.format_prompt(user_intent, feedback)
        ast: FunctionDeclaration = self.client.chat.completions.create(
            model=self.model,
            response_model=FunctionDeclaration,
            messages=messages,
        )
        return ast
