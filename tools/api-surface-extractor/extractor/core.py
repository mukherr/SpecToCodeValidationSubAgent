"""
Core extraction engine using tree-sitter for deterministic AST-based
API surface discovery across multiple languages.

Extracts: route definitions, controller methods, DTOs/request-response types,
service interfaces, middleware/auth configuration.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol

import tree_sitter


class Language(Enum):
    JAVA = "java"
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    GO = "go"
    CSHARP = "c_sharp"


@dataclass
class Parameter:
    name: str
    type: str
    required: bool = True
    default: str | None = None
    source: str = "body"  # body, path, query, header


@dataclass
class Endpoint:
    http_method: str
    path: str
    handler_name: str
    file_path: str
    line_number: int
    parameters: list[Parameter] = field(default_factory=list)
    return_type: str | None = None
    request_body_type: str | None = None
    response_type: str | None = None
    auth_required: bool = False
    roles: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)


@dataclass
class TypeDefinition:
    name: str
    file_path: str
    line_number: int
    kind: str  # class, interface, struct, enum, dataclass
    fields: list[Parameter] = field(default_factory=list)
    parent_types: list[str] = field(default_factory=list)
    annotations: list[str] = field(default_factory=list)


@dataclass
class ServiceMethod:
    name: str
    file_path: str
    line_number: int
    parameters: list[Parameter] = field(default_factory=list)
    return_type: str | None = None
    interface_name: str | None = None


@dataclass
class ExtractionResult:
    endpoints: list[Endpoint] = field(default_factory=list)
    types: list[TypeDefinition] = field(default_factory=list)
    service_methods: list[ServiceMethod] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class LanguageExtractor(Protocol):
    """Protocol for language-specific extractors."""

    def extract_endpoints(self, tree: tree_sitter.Tree, source: bytes, file_path: str) -> list[Endpoint]: ...
    def extract_types(self, tree: tree_sitter.Tree, source: bytes, file_path: str) -> list[TypeDefinition]: ...
    def extract_service_methods(self, tree: tree_sitter.Tree, source: bytes, file_path: str) -> list[ServiceMethod]: ...


def detect_language(file_path: Path) -> Language | None:
    suffix_map = {
        ".java": Language.JAVA,
        ".py": Language.PYTHON,
        ".ts": Language.TYPESCRIPT,
        ".tsx": Language.TYPESCRIPT,
        ".go": Language.GO,
        ".cs": Language.CSHARP,
    }
    return suffix_map.get(file_path.suffix)


def get_parser(language: Language) -> tree_sitter.Parser:
    parser = tree_sitter.Parser()
    lang = _load_language(language)
    parser.language = lang
    return parser


def _load_language(language: Language) -> tree_sitter.Language:
    if language == Language.JAVA:
        import tree_sitter_java
        return tree_sitter.Language(tree_sitter_java.language())
    elif language == Language.PYTHON:
        import tree_sitter_python
        return tree_sitter.Language(tree_sitter_python.language())
    elif language == Language.TYPESCRIPT:
        import tree_sitter_typescript
        return tree_sitter.Language(tree_sitter_typescript.language_typescript())
    elif language == Language.GO:
        import tree_sitter_go
        return tree_sitter.Language(tree_sitter_go.language())
    elif language == Language.CSHARP:
        import tree_sitter_c_sharp
        return tree_sitter.Language(tree_sitter_c_sharp.language())
    raise ValueError(f"Unsupported language: {language}")
