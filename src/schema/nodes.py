from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, TypeAdapter


# --- Primitive Types ---
PrimitiveType = Literal["int", "float", "bool", "string"]


# --- Literal Values ---
class LiteralInt(BaseModel):
    kind: Literal["lit_int"] = "lit_int"
    value: int

class LiteralFloat(BaseModel):
    kind: Literal["lit_float"] = "lit_float"
    value: float

class LiteralBool(BaseModel):
    kind: Literal["lit_bool"] = "lit_bool"
    value: bool

class LiteralString(BaseModel):
    kind: Literal["lit_string"] = "lit_string"
    value: str

LiteralNode = Annotated[
    Union[LiteralInt, LiteralFloat, LiteralBool, LiteralString],
    Field(discriminator="kind")
]


# --- Expressions & Operations ---
BinaryOpType = Literal[
    "add", "sub", "mul", "div", "mod",
    "eq", "neq", "lt", "lte", "gt", "gte"
]

class VariableRef(BaseModel):
    kind: Literal["var_ref"] = "var_ref"
    name: str

class BinaryOp(BaseModel):
    kind: Literal["binary_op"] = "binary_op"
    op: BinaryOpType
    left: ExpressionNode
    right: ExpressionNode

class FunctionCall(BaseModel):
    kind: Literal["call"] = "call"
    target_hash: str = Field(description="Content-addressed hash of the callee AST")
    arguments: List[ExpressionNode]

ExpressionNode = Annotated[
    Union[
        LiteralInt,
        LiteralFloat,
        LiteralBool,
        LiteralString,
        VariableRef,
        BinaryOp,
        FunctionCall,
    ],
    Field(discriminator="kind")
]


# --- Statements & Control Flow ---
class AssignStatement(BaseModel):
    kind: Literal["assign"] = "assign"
    variable_name: str
    variable_type: PrimitiveType
    expression: ExpressionNode

class IfElseStatement(BaseModel):
    kind: Literal["if_else"] = "if_else"
    condition: ExpressionNode
    then_branch: List[StatementNode]
    else_branch: Optional[List[StatementNode]] = None

class ReturnStatement(BaseModel):
    kind: Literal["return"] = "return"
    value: ExpressionNode

StatementNode = Annotated[
    Union[AssignStatement, IfElseStatement, ReturnStatement],
    Field(discriminator="kind")
]


# --- Top-Level Module / Function Definition ---
class Parameter(BaseModel):
    name: str
    param_type: PrimitiveType

class FunctionDeclaration(BaseModel):
    kind: Literal["function"] = "function"
    name: str
    parameters: List[Parameter] = Field(default_factory=list)
    return_type: PrimitiveType
    body: List[StatementNode] = Field(default_factory=list)
    invariants: List[str] = Field(
        default_factory=list,
        description="SMT-verifiable assertions (e.g., 'return_value >= 0')"
    )


# Any AST Node Discriminated Union
AnyASTNode = Annotated[
    Union[
        LiteralInt,
        LiteralFloat,
        LiteralBool,
        LiteralString,
        VariableRef,
        BinaryOp,
        FunctionCall,
        AssignStatement,
        IfElseStatement,
        ReturnStatement,
        FunctionDeclaration,
    ],
    Field(discriminator="kind")
]


# Resolve recursive model definitions
BinaryOp.model_rebuild()
FunctionCall.model_rebuild()
IfElseStatement.model_rebuild()


# Type Adapters for validation and serialization
expression_adapter: TypeAdapter[ExpressionNode] = TypeAdapter(ExpressionNode)
statement_adapter: TypeAdapter[StatementNode] = TypeAdapter(StatementNode)
ast_node_adapter: TypeAdapter[AnyASTNode] = TypeAdapter(AnyASTNode)


def parse_ast_node(data: Union[Dict[str, Any], str, BaseModel]) -> AnyASTNode:
    """Parse a dictionary, JSON string, or model into a validated AST node."""
    if isinstance(data, BaseModel):
        return data  # type: ignore
    if isinstance(data, str):
        return ast_node_adapter.validate_json(data)
    return ast_node_adapter.validate_python(data)
