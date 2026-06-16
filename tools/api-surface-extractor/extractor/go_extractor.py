"""
Tree-sitter based Go API surface extractor.

Extracts net/http, gin, echo, chi, and fiber routes, struct types,
and interface definitions using deterministic AST queries.
"""

import re

import tree_sitter

from .core import Endpoint, Language, Parameter, ServiceMethod, TypeDefinition, get_parser

ROUTER_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}


class GoExtractor:
    def __init__(self):
        self.parser = get_parser(Language.GO)

    def parse(self, source: bytes) -> tree_sitter.Tree:
        return self.parser.parse(source)

    def extract_endpoints(self, tree: tree_sitter.Tree, source: bytes, file_path: str) -> list[Endpoint]:
        endpoints = []
        root = tree.root_node

        for call_node in _find_nodes_by_type(root, "call_expression"):
            endpoint = _try_parse_route_registration(call_node, source, file_path)
            if endpoint:
                endpoints.append(endpoint)

        return endpoints

    def extract_types(self, tree: tree_sitter.Tree, source: bytes, file_path: str) -> list[TypeDefinition]:
        types = []
        root = tree.root_node

        for node in _find_nodes_by_type(root, "type_declaration"):
            for spec in node.children:
                if spec.type == "type_spec":
                    type_def = _extract_type_spec(spec, source, file_path)
                    if type_def:
                        types.append(type_def)

        return types

    def extract_service_methods(self, tree: tree_sitter.Tree, source: bytes, file_path: str) -> list[ServiceMethod]:
        methods = []
        root = tree.root_node

        # Extract interface methods
        for node in _find_nodes_by_type(root, "type_declaration"):
            for spec in node.children:
                if spec.type == "type_spec":
                    iface_methods = _extract_interface_methods(spec, source, file_path)
                    methods.extend(iface_methods)

        return methods


def _find_nodes_by_type(node: tree_sitter.Node, type_name: str) -> list[tree_sitter.Node]:
    results = []
    if node.type == type_name:
        results.append(node)
    for child in node.children:
        results.extend(_find_nodes_by_type(child, type_name))
    return results


def _node_text(node: tree_sitter.Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8")


def _try_parse_route_registration(call_node: tree_sitter.Node, source: bytes, file_path: str) -> Endpoint | None:
    text = _node_text(call_node, source)

    # Pattern 1: gin/echo/fiber style — r.GET("/path", handler)
    for method in ROUTER_METHODS:
        pattern = rf'(\w+)\.{method}\s*\(\s*["\']([^"\']+)["\']'
        match = re.match(pattern, text)
        if match:
            path = match.group(2)
            handler_name = _extract_go_handler_name(text)
            return Endpoint(
                http_method=method,
                path=path,
                handler_name=handler_name,
                file_path=file_path,
                line_number=call_node.start_point[0] + 1,
                parameters=[],
                auth_required=False,
                roles=[],
                decorators=[],
            )

    # Pattern 2: chi/mux style — r.Get("/path", handler)
    for method in ("Get", "Post", "Put", "Delete", "Patch", "Head", "Options"):
        pattern = rf'(\w+)\.{method}\s*\(\s*["\']([^"\']+)["\']'
        match = re.match(pattern, text)
        if match:
            path = match.group(2)
            handler_name = _extract_go_handler_name(text)
            return Endpoint(
                http_method=method.upper(),
                path=path,
                handler_name=handler_name,
                file_path=file_path,
                line_number=call_node.start_point[0] + 1,
                parameters=[],
                auth_required=False,
                roles=[],
                decorators=[],
            )

    # Pattern 3: net/http style — http.HandleFunc("/path", handler)
    handle_match = re.match(r'(?:http\.HandleFunc|mux\.HandleFunc)\s*\(\s*["\']([^"\']+)["\']', text)
    if handle_match:
        path = handle_match.group(1)
        handler_name = _extract_go_handler_name(text)
        return Endpoint(
            http_method="ANY",
            path=path,
            handler_name=handler_name,
            file_path=file_path,
            line_number=call_node.start_point[0] + 1,
            parameters=[],
            auth_required=False,
            roles=[],
            decorators=[],
        )

    return None


def _extract_go_handler_name(text: str) -> str:
    # Look for the handler argument (last identifier before closing paren)
    parts = re.findall(r'(\w+(?:\.\w+)?)\s*\)', text)
    if parts:
        return parts[-1]
    return "anonymous"


def _extract_type_spec(spec_node: tree_sitter.Node, source: bytes, file_path: str) -> TypeDefinition | None:
    name = ""
    kind = ""
    fields = []

    for child in spec_node.children:
        if child.type == "type_identifier":
            name = _node_text(child, source)
        elif child.type == "struct_type":
            kind = "struct"
            fields = _extract_struct_fields(child, source)
        elif child.type == "interface_type":
            kind = "interface"

    if not name or not kind:
        return None

    return TypeDefinition(
        name=name,
        file_path=file_path,
        line_number=spec_node.start_point[0] + 1,
        kind=kind,
        fields=fields,
        parent_types=[],
        annotations=[],
    )


def _extract_struct_fields(struct_node: tree_sitter.Node, source: bytes) -> list[Parameter]:
    fields = []
    for child in struct_node.children:
        if child.type == "field_declaration_list":
            for field_node in child.children:
                if field_node.type == "field_declaration":
                    field = _parse_struct_field(field_node, source)
                    if field:
                        fields.append(field)
    return fields


def _parse_struct_field(field_node: tree_sitter.Node, source: bytes) -> Parameter | None:
    name = ""
    field_type = ""
    source_kind = "body"

    for child in field_node.children:
        if child.type == "field_identifier":
            name = _node_text(child, source)
        elif child.type in ("type_identifier", "pointer_type", "slice_type",
                            "array_type", "map_type", "qualified_type"):
            field_type = _node_text(child, source)
        elif child.type == "raw_string_literal" or child.type == "interpreted_string_literal":
            # Struct tags — extract json name and binding info
            tag_text = _node_text(child, source)
            json_match = re.search(r'json:"(\w+)', tag_text)
            if json_match:
                name = json_match.group(1) if not name else name
            # Check for binding/form/uri tags for source
            if "uri:" in tag_text:
                source_kind = "path"
            elif "form:" in tag_text or "query:" in tag_text:
                source_kind = "query"
            elif "header:" in tag_text:
                source_kind = "header"

    if name and field_type:
        required = True
        if "omitempty" in _node_text(field_node, source):
            required = False
        return Parameter(name=name, type=field_type, required=required, source=source_kind)
    return None


def _extract_interface_methods(spec_node: tree_sitter.Node, source: bytes, file_path: str) -> list[ServiceMethod]:
    methods = []
    iface_name = ""

    for child in spec_node.children:
        if child.type == "type_identifier":
            iface_name = _node_text(child, source)
        elif child.type == "interface_type":
            for member in child.children:
                if member.type == "method_spec":
                    method = _parse_interface_method(member, source, file_path, iface_name)
                    if method:
                        methods.append(method)

    return methods


def _parse_interface_method(method_node: tree_sitter.Node, source: bytes, file_path: str, iface_name: str) -> ServiceMethod | None:
    name = ""
    params = []
    return_type = ""

    for child in method_node.children:
        if child.type == "field_identifier":
            name = _node_text(child, source)
        elif child.type == "parameter_list":
            params = _extract_go_params(child, source)
        elif child.type == "simple_type" or child.type == "type_identifier":
            return_type = _node_text(child, source)
        elif child.type == "parameter_list" and return_type == "":
            # Second parameter_list is return types
            return_type = _node_text(child, source)

    if not name:
        return None

    return ServiceMethod(
        name=name,
        file_path=file_path,
        line_number=method_node.start_point[0] + 1,
        parameters=params,
        return_type=return_type,
        interface_name=iface_name,
    )


def _extract_go_params(param_list_node: tree_sitter.Node, source: bytes) -> list[Parameter]:
    params = []
    for child in param_list_node.children:
        if child.type == "parameter_declaration":
            name = ""
            param_type = ""
            for pc in child.children:
                if pc.type == "identifier":
                    name = _node_text(pc, source)
                elif pc.type in ("type_identifier", "pointer_type", "slice_type",
                                 "qualified_type", "interface_type"):
                    param_type = _node_text(pc, source)
            if param_type:
                # Skip context.Context
                if "Context" in param_type:
                    continue
                params.append(Parameter(name=name or "_", type=param_type))
    return params
