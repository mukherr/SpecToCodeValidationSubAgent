"""
Tree-sitter based TypeScript API surface extractor.

Extracts Express/NestJS/Hono routes, interfaces, type aliases,
and class-based controllers using deterministic AST queries.
"""

import re

import tree_sitter

from .core import Endpoint, Language, Parameter, ServiceMethod, TypeDefinition, get_parser

ROUTE_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}

NESTJS_DECORATORS = {
    "Get": "GET", "Post": "POST", "Put": "PUT",
    "Delete": "DELETE", "Patch": "PATCH",
}

PARAM_DECORATORS = {
    "Param": "path", "Query": "query", "Body": "body",
    "Headers": "header",
}


class TypeScriptExtractor:
    def __init__(self):
        self.parser = get_parser(Language.TYPESCRIPT)

    def parse(self, source: bytes) -> tree_sitter.Tree:
        return self.parser.parse(source)

    def extract_endpoints(self, tree: tree_sitter.Tree, source: bytes, file_path: str) -> list[Endpoint]:
        endpoints = []
        root = tree.root_node

        # Express-style: app.get("/path", handler) or router.post("/path", handler)
        endpoints.extend(_extract_express_routes(root, source, file_path))

        # NestJS-style: class with @Controller and method decorators
        endpoints.extend(_extract_nestjs_routes(root, source, file_path))

        return endpoints

    def extract_types(self, tree: tree_sitter.Tree, source: bytes, file_path: str) -> list[TypeDefinition]:
        types = []
        root = tree.root_node

        # Interfaces
        for node in _find_nodes_by_type(root, "interface_declaration"):
            type_def = _extract_ts_interface(node, source, file_path)
            if type_def:
                types.append(type_def)

        # Type aliases
        for node in _find_nodes_by_type(root, "type_alias_declaration"):
            type_def = _extract_ts_type_alias(node, source, file_path)
            if type_def:
                types.append(type_def)

        # Classes (DTOs, entities)
        for node in _find_nodes_by_type(root, "class_declaration"):
            type_def = _extract_ts_class(node, source, file_path)
            if type_def:
                types.append(type_def)

        # Enums
        for node in _find_nodes_by_type(root, "enum_declaration"):
            type_def = _extract_ts_enum(node, source, file_path)
            if type_def:
                types.append(type_def)

        return types

    def extract_service_methods(self, tree: tree_sitter.Tree, source: bytes, file_path: str) -> list[ServiceMethod]:
        methods = []
        root = tree.root_node

        for class_node in _find_nodes_by_type(root, "class_declaration"):
            class_name = _get_ts_class_name(class_node, source)
            if not class_name or not class_name.endswith("Service"):
                continue

            for method_node in _find_nodes_by_type(class_node, "method_definition"):
                name = _get_method_name(method_node, source)
                if name.startswith("_") or name.startswith("#"):
                    continue
                params = _extract_ts_params(method_node, source)
                return_type = _get_ts_return_type(method_node, source)
                methods.append(ServiceMethod(
                    name=name,
                    file_path=file_path,
                    line_number=method_node.start_point[0] + 1,
                    parameters=params,
                    return_type=return_type,
                    interface_name=class_name,
                ))

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


def _extract_express_routes(root: tree_sitter.Node, source: bytes, file_path: str) -> list[Endpoint]:
    """Extract routes from Express/Hono-style: app.get('/path', handler)"""
    endpoints = []

    for call_node in _find_nodes_by_type(root, "call_expression"):
        text = _node_text(call_node, source)

        # Match: app.get("/path" or router.post("/path"
        for method in ROUTE_METHODS:
            pattern = rf'(\w+)\.{method}\s*\('
            match = re.match(pattern, text)
            if not match:
                continue

            # Extract path
            path_match = re.search(r'["\']([^"\']+)["\']', text)
            if not path_match:
                continue

            path = path_match.group(1)
            handler_name = _extract_handler_name(call_node, source)

            endpoints.append(Endpoint(
                http_method=method.upper(),
                path=path,
                handler_name=handler_name or f"anonymous_{method}",
                file_path=file_path,
                line_number=call_node.start_point[0] + 1,
                parameters=[],
                auth_required=False,
                roles=[],
                decorators=[],
            ))
            break

    return endpoints


def _extract_nestjs_routes(root: tree_sitter.Node, source: bytes, file_path: str) -> list[Endpoint]:
    """Extract routes from NestJS-style controllers with decorators."""
    endpoints = []

    for class_node in _find_nodes_by_type(root, "class_declaration"):
        decorators = _get_ts_decorators(class_node, source)
        controller_path = _find_controller_path(decorators, source)
        if controller_path is None:
            continue

        for method_node in _find_nodes_by_type(class_node, "method_definition"):
            method_decorators = _get_ts_method_decorators(method_node, source)
            route_info = _find_nestjs_route(method_decorators, source)
            if not route_info:
                continue

            http_method, method_path = route_info
            full_path = _join_paths(controller_path, method_path)
            handler_name = _get_method_name(method_node, source)
            params = _extract_ts_params(method_node, source)
            return_type = _get_ts_return_type(method_node, source)

            request_body_type = None
            for p in params:
                if p.source == "body":
                    request_body_type = p.type
                    break

            endpoints.append(Endpoint(
                http_method=http_method,
                path=full_path,
                handler_name=handler_name,
                file_path=file_path,
                line_number=method_node.start_point[0] + 1,
                parameters=params,
                return_type=return_type,
                request_body_type=request_body_type,
                auth_required=_has_auth_guard(decorators + method_decorators, source),
                roles=_extract_nestjs_roles(decorators + method_decorators, source),
                decorators=[_node_text(d, source) for d in method_decorators],
            ))

    return endpoints


def _get_ts_decorators(node: tree_sitter.Node, source: bytes) -> list[tree_sitter.Node]:
    decorators = []
    for child in node.children:
        if child.type == "decorator":
            decorators.append(child)
    # Also check preceding siblings
    if node.parent:
        found = False
        for sibling in node.parent.children:
            if sibling == node:
                found = True
                break
            if sibling.type == "decorator":
                decorators.append(sibling)
    return decorators


def _get_ts_method_decorators(method_node: tree_sitter.Node, source: bytes) -> list[tree_sitter.Node]:
    decorators = []
    for child in method_node.children:
        if child.type == "decorator":
            decorators.append(child)
    return decorators


def _find_controller_path(decorators: list[tree_sitter.Node], source: bytes) -> str | None:
    for dec in decorators:
        text = _node_text(dec, source)
        match = re.search(r'@Controller\s*\(\s*["\']([^"\']*)["\']', text)
        if match:
            return match.group(1)
        if "@Controller" in text:
            return ""
    return None


def _find_nestjs_route(decorators: list[tree_sitter.Node], source: bytes) -> tuple[str, str] | None:
    for dec in decorators:
        text = _node_text(dec, source)
        for decorator_name, method in NESTJS_DECORATORS.items():
            match = re.search(rf'@{decorator_name}\s*\(\s*["\']?([^"\')\s]*)["\']?\s*\)', text)
            if match:
                return method, match.group(1)
            if f"@{decorator_name}()" in text or f"@{decorator_name}" in text:
                return method, ""
    return None


def _has_auth_guard(decorators: list[tree_sitter.Node], source: bytes) -> bool:
    for dec in decorators:
        text = _node_text(dec, source)
        if "UseGuards" in text or "AuthGuard" in text:
            return True
    return False


def _extract_nestjs_roles(decorators: list[tree_sitter.Node], source: bytes) -> list[str]:
    roles = []
    for dec in decorators:
        text = _node_text(dec, source)
        if "Roles" in text:
            roles.extend(re.findall(r'["\']([^"\']+)["\']', text))
    return roles


def _get_ts_class_name(class_node: tree_sitter.Node, source: bytes) -> str:
    for child in class_node.children:
        if child.type == "type_identifier":
            return _node_text(child, source)
        if child.type == "identifier":
            return _node_text(child, source)
    return ""


def _get_method_name(method_node: tree_sitter.Node, source: bytes) -> str:
    for child in method_node.children:
        if child.type == "property_identifier":
            return _node_text(child, source)
        if child.type == "identifier":
            return _node_text(child, source)
    return ""


def _extract_ts_params(node: tree_sitter.Node, source: bytes) -> list[Parameter]:
    params = []
    for child in node.children:
        if child.type == "formal_parameters":
            for param_node in child.children:
                if param_node.type in ("required_parameter", "optional_parameter"):
                    param = _parse_ts_param(param_node, source)
                    if param:
                        params.append(param)
    return params


def _parse_ts_param(param_node: tree_sitter.Node, source: bytes) -> Parameter | None:
    text = _node_text(param_node, source)
    name = ""
    param_type = ""
    source_kind = "body"

    # Check for NestJS parameter decorators
    for child in param_node.children:
        if child.type == "decorator":
            dec_text = _node_text(child, source)
            for dec_name, kind in PARAM_DECORATORS.items():
                if dec_name in dec_text:
                    source_kind = kind
                    break

    for child in param_node.children:
        if child.type == "identifier":
            name = _node_text(child, source)
        elif child.type == "type_annotation":
            for tc in child.children:
                if tc.type != ":":
                    param_type = _node_text(tc, source)

    # Skip framework params
    if name in ("req", "res", "next", "request", "response"):
        return None

    if name:
        return Parameter(name=name, type=param_type or "any", source=source_kind)
    return None


def _get_ts_return_type(node: tree_sitter.Node, source: bytes) -> str:
    for child in node.children:
        if child.type == "type_annotation":
            for tc in child.children:
                if tc.type != ":":
                    return _node_text(tc, source)
    return ""


def _extract_handler_name(call_node: tree_sitter.Node, source: bytes) -> str:
    """Try to extract the handler function name from a route registration call."""
    args = None
    for child in call_node.children:
        if child.type == "arguments":
            args = child
            break
    if not args:
        return ""

    # Look for identifier after the path string
    found_string = False
    for child in args.children:
        if child.type == "string":
            found_string = True
        elif found_string and child.type == "identifier":
            return _node_text(child, source)
    return ""


def _extract_ts_interface(node: tree_sitter.Node, source: bytes, file_path: str) -> TypeDefinition | None:
    name = ""
    fields = []
    parent_types = []

    for child in node.children:
        if child.type == "type_identifier":
            name = _node_text(child, source)
        elif child.type == "extends_type_clause":
            for ext_child in child.children:
                if ext_child.type == "type_identifier":
                    parent_types.append(_node_text(ext_child, source))
        elif child.type == "object_type" or child.type == "interface_body":
            fields = _extract_object_type_fields(child, source)

    if not name:
        return None

    return TypeDefinition(
        name=name,
        file_path=file_path,
        line_number=node.start_point[0] + 1,
        kind="interface",
        fields=fields,
        parent_types=parent_types,
        annotations=[],
    )


def _extract_ts_type_alias(node: tree_sitter.Node, source: bytes, file_path: str) -> TypeDefinition | None:
    name = ""
    fields = []

    for child in node.children:
        if child.type == "type_identifier":
            name = _node_text(child, source)
        elif child.type == "object_type":
            fields = _extract_object_type_fields(child, source)

    if not name:
        return None

    return TypeDefinition(
        name=name,
        file_path=file_path,
        line_number=node.start_point[0] + 1,
        kind="type_alias",
        fields=fields,
        parent_types=[],
        annotations=[],
    )


def _extract_ts_class(node: tree_sitter.Node, source: bytes, file_path: str) -> TypeDefinition | None:
    name = _get_ts_class_name(node, source)
    if not name:
        return None

    fields = []
    parent_types = []

    for child in node.children:
        if child.type == "class_heritage":
            for hc in child.children:
                if hc.type == "extends_clause":
                    for ext in hc.children:
                        if ext.type == "identifier" or ext.type == "type_identifier":
                            parent_types.append(_node_text(ext, source))
                elif hc.type == "implements_clause":
                    for impl in hc.children:
                        if impl.type == "type_identifier":
                            parent_types.append(_node_text(impl, source))
        elif child.type == "class_body":
            for member in child.children:
                if member.type == "public_field_definition":
                    field = _extract_ts_class_field(member, source)
                    if field:
                        fields.append(field)

    decorators = _get_ts_decorators(node, source)

    return TypeDefinition(
        name=name,
        file_path=file_path,
        line_number=node.start_point[0] + 1,
        kind="class",
        fields=fields,
        parent_types=parent_types,
        annotations=[_node_text(d, source) for d in decorators],
    )


def _extract_ts_enum(node: tree_sitter.Node, source: bytes, file_path: str) -> TypeDefinition | None:
    name = ""
    for child in node.children:
        if child.type == "identifier":
            name = _node_text(child, source)
            break

    if not name:
        return None

    return TypeDefinition(
        name=name,
        file_path=file_path,
        line_number=node.start_point[0] + 1,
        kind="enum",
        fields=[],
        parent_types=[],
        annotations=[],
    )


def _extract_object_type_fields(node: tree_sitter.Node, source: bytes) -> list[Parameter]:
    fields = []
    for child in node.children:
        if child.type == "property_signature":
            field = _parse_property_signature(child, source)
            if field:
                fields.append(field)
    return fields


def _parse_property_signature(node: tree_sitter.Node, source: bytes) -> Parameter | None:
    name = ""
    field_type = ""
    required = True

    for child in node.children:
        if child.type == "property_identifier":
            name = _node_text(child, source)
        elif child.type == "?":
            required = False
        elif child.type == "type_annotation":
            for tc in child.children:
                if tc.type != ":":
                    field_type = _node_text(tc, source)

    if name:
        return Parameter(name=name, type=field_type or "any", required=required)
    return None


def _extract_ts_class_field(node: tree_sitter.Node, source: bytes) -> Parameter | None:
    name = ""
    field_type = ""

    for child in node.children:
        if child.type == "property_identifier":
            name = _node_text(child, source)
        elif child.type == "type_annotation":
            for tc in child.children:
                if tc.type != ":":
                    field_type = _node_text(tc, source)

    if name:
        return Parameter(name=name, type=field_type or "any")
    return None


def _join_paths(base: str, path: str) -> str:
    base = base.rstrip("/")
    path = path.lstrip("/") if path else ""
    if base and path:
        return f"/{base}/{path}"
    elif base:
        return f"/{base}"
    elif path:
        return f"/{path}"
    return "/"
