from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel
import rfc8785

from src.schema.nodes import (
    AnyASTNode,
    FunctionCall,
    FunctionDeclaration,
    parse_ast_node,
)


def canonicalize_ast(node: Union[BaseModel, Dict[str, Any]]) -> bytes:
    """Serialize an AST node to canonical UTF-8 bytes adhering to RFC-8785 (JCS)."""
    if isinstance(node, BaseModel):
        data = node.model_dump(mode="json")
    elif isinstance(node, dict):
        data = node
    else:
        raise TypeError(f"Cannot canonicalize unsupported type: {type(node)}")

    # Deterministic RFC-8785 serialization
    return rfc8785.dumps(data)


def compute_ast_hash(node: Union[BaseModel, Dict[str, Any]]) -> str:
    """Compute cryptographic SHA-256 content-address for an AST node: sha256:<hex>."""
    canonical_bytes = canonicalize_ast(node)
    hash_hex = hashlib.sha256(canonical_bytes).hexdigest()
    return f"sha256:{hash_hex}"


def _find_call_targets(data: Any) -> List[str]:
    """Recursively traverse a dictionary or AST structure to locate all FunctionCall target hashes."""
    targets: List[str] = []

    if isinstance(data, dict):
        if data.get("kind") == "call" and "target_hash" in data:
            targets.append(data["target_hash"])
        for v in data.values():
            targets.extend(_find_call_targets(v))
    elif isinstance(data, list):
        for item in data:
            targets.extend(_find_call_targets(item))
    elif isinstance(data, BaseModel):
        targets.extend(_find_call_targets(data.model_dump(mode="json")))

    return targets


class ContentAddressedStore:
    """Immutable, content-addressable SQLite storage for verified AST logic nodes."""

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS ast_nodes (
        hash TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        canonical_json BLOB NOT NULL,
        return_type TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS ast_edges (
        parent_hash TEXT NOT NULL,
        child_hash TEXT NOT NULL,
        call_site_index INTEGER NOT NULL,
        PRIMARY KEY (parent_hash, child_hash, call_site_index),
        FOREIGN KEY(parent_hash) REFERENCES ast_nodes(hash)
    );

    CREATE INDEX IF NOT EXISTS idx_ast_nodes_kind ON ast_nodes(kind);
    """

    def __init__(self, db_path: Union[str, Path] = ":memory:"):
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema tables and indexes."""
        with self.conn:
            self.conn.executescript(self.SCHEMA_SQL)

    def put(self, node: Union[AnyASTNode, BaseModel, Dict[str, Any]]) -> str:
        """Store a validated AST node, compute its hash, and record dependency edges."""
        canonical_bytes = canonicalize_ast(node)
        node_hash = f"sha256:{hashlib.sha256(canonical_bytes).hexdigest()}"

        if isinstance(node, dict):
            kind = node.get("kind", "unknown")
            return_type = node.get("return_type", "void")
            raw_dict = node
        else:
            kind = getattr(node, "kind", "unknown")
            return_type = getattr(node, "return_type", "void")
            raw_dict = node.model_dump(mode="json")

        with self.conn:
            # 1. Insert AST node (idempotent: content addressing ensures hash matches content)
            self.conn.execute(
                """
                INSERT OR IGNORE INTO ast_nodes (hash, kind, canonical_json, return_type)
                VALUES (?, ?, ?, ?)
                """,
                (node_hash, kind, canonical_bytes, return_type),
            )

            # 2. Extract and index outgoing function call edges
            child_hashes = _find_call_targets(raw_dict)
            for call_index, child_hash in enumerate(child_hashes):
                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO ast_edges (parent_hash, child_hash, call_site_index)
                    VALUES (?, ?, ?)
                    """,
                    (node_hash, child_hash, call_index),
                )

        return node_hash

    def get(self, node_hash: str) -> Optional[AnyASTNode]:
        """Retrieve and parse an AST node by its content hash."""
        cursor = self.conn.execute(
            "SELECT canonical_json FROM ast_nodes WHERE hash = ?",
            (node_hash,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        canonical_bytes: bytes = row[0]
        json_data = json.loads(canonical_bytes.decode("utf-8"))
        return parse_ast_node(json_data)

    def contains(self, node_hash: str) -> bool:
        """Check if an AST node hash is present in the CAS store."""
        cursor = self.conn.execute(
            "SELECT 1 FROM ast_nodes WHERE hash = ?",
            (node_hash,),
        )
        return cursor.fetchone() is not None

    def get_dependencies(self, parent_hash: str) -> List[str]:
        """Get all child function hashes invoked by the given parent AST."""
        cursor = self.conn.execute(
            "SELECT child_hash FROM ast_edges WHERE parent_hash = ? ORDER BY call_site_index",
            (parent_hash,),
        )
        return [row[0] for row in cursor.fetchall()]

    def get_dependents(self, child_hash: str) -> List[str]:
        """Get all parent function hashes that invoke the given child AST."""
        cursor = self.conn.execute(
            "SELECT parent_hash FROM ast_edges WHERE child_hash = ?",
            (child_hash,),
        )
        return [row[0] for row in cursor.fetchall()]

    def close(self) -> None:
        """Close the SQLite database connection."""
        self.conn.close()
