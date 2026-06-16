"""
Tree-sitter based Python API surface extractor.

Extracts Flask/FastAPI/Django REST framework routes, Pydantic models,
dataclasses, and service functions using deterministic AST queries.
"""

import re

import tree_sitter

from .core import Endpoint, Language, Parameter, ServiceMethod, TypeDefinition, get_parser

ROUTE_DECORATORS = {
    "app.route", "app.get", "app.post", "app.put", "app.delete", "app.patch",
    "router.get", "router.post", "router.put", "router.delete", "router.patch",
    "api_view", "action",
    "bp.route", "bp.get", "bp.post", "bp.put", "bp.delete",
}

FASTAPI_METHOD_MAP = {
    "get": "GET", "post": "POST", "put": "PUT",
    "delete": "DELETE", "patch": "PATCH",
}

CLASS_MARKERS = {"BaseModel", "Schema", "Serializer", "dataclass"}


class PythonExtractor:
    def __init__(self):
        self.parser = get_parser(Language.PYTHON)

    def parse(self, source: bytes) -> tree_sitter.Tree:
        return self.parser.parse(source)

    def extract_endpoints(self, tree: tree_sitter.Tree, source: bytes, file_path: str) -> list[Endpoint]:
        endpoints = []
        root = tree.root_node

        for func_node in _find_nodes_by_type(root, "function_definition"):
            decorators = _get_decorators(func_node, source)
            route_info = _find_route_decorator(decorators, source)
            if not route_info:
                continue

            http_method, path = route_info
            handler_name = _get_function_name(func_node, source)
            params = _extract_function_params(func_node, source)
            return_type = _get_return_annotation(func_node, source)

            request_body_type = None
            for p in params:
                if p.source == "body":
                    request_body_type = p.type
                    break

            endpoints.append(Endpoint(
                http_method=http_method,
                path=path,
                handler_name=handler_name,
                file_path=file_path,
                line_number=func_node.start_point[0] + 1,
                parameters=params,
                return_type=return_type,
                request_body_type=request_body_type,
                auth_required=_has_auth_decorator(decorators, source),
                roles=_extract_roles_from_decorators(decorators, source),
                decorators=[_node_text(d, source) for d in decorators],
            ))

        # Handle class-based views (Django REST, Flask-RESTful)
        for class_node in _find_nodes_by_type(root, "class_declaration"):
            endpoints.extend(_extract_class_based_endpoints(class_node, source, file_path))

        return endpoints

    def extract_types(self, tree: tree_sitter.Tree, source: bytes, file_path: str) -> list[TypeDefinition]:
        types = []
        root = tree.root_node

        for class_node in _find_nodes_by_type(root, "class_definition"):
            type_def = _extract_python_type(class_node, source, file_path)
            if type_def:
                types.append(type_def)

        return types

    def extract_service_methods(self, tree: tree_sitter.Tree, source: bytes, file_path: str) -> list[ServiceMethod]:
        methods = []
        root = tree.root_node

        for class_node in _find_nodes_by_type(root, "class_definition"):
            class_name = _get_class_name(class_node, source)
            if not class_name or not class_name.endswith("Service"):
                continue

            for method_node in _find_nodes_by_type(class_node, "function_definition"):
                name = _get_function_name(method_node, source)
                if name.startswith("_"):
                    continue
                params = _extract_function_params(method_node, source)
                # Remove 'self' parameter
                params = [p for p in params if p.name != "self"]
                return_type = _get_return_annotation(method_node, source)
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


def _get_decorators(func_node: tree_sitter.Node, source: bytes) -> list[tree_sitter.Node]:
    decorators = []
    if func_node.parent and func_node.parent.type == "decorated_definition":
        for child in func_node.parent.children:
            if child.type == "decorator":
                decorators.append(child)
    return decorators


def _find_route_decorator(decorators: list[tree_sitter.Node], source: bytes) -> tuple[str, str] | None:
    for dec in decorators:
        text = _node_text(dec, source)
        # @app.get("/path"), @router.post("/path"), etc.
        for pattern, method in FASTAPI_METHOD_MAP.items():
            match = re.search(rf'\.{pattern}\s*\(\s*["\']([^"\']*)["\']', text)
            if match:
                return method, match.group(1)

        # @app.route("/path", methods=["GET"])
        route_match = re.search(r'\.route\s*\(\s*["\']([^"\']*)["\']', text)
        if route_match:
            path = route_match.group(1)
            method_match = re.search(r'methods\s*=\s*\[([^\]]*)\]', text)
            if method_match:
                methods_str = method_match.group(1)
                first_method = re.search(r'["\'](\w+)["\']', methods_str)
                method = first_method.group(1).upper() if first_method else "GET"
            else:
                method = "GET"
            return method, path

    return None


def _get_function_name(func_node: tree_sitter.Node, source: bytes) -> str:
    for child in func_node.children:
        if child.type == "identifier":
            return _node_text(child, source)
    return ""


def _extract_function_params(func_node: tree_sitter.Node, source: bytes) -> list[Parameter]:
    params = []
    for child in func_node.children:
        if child.type == "parameters":
            for param_node in child.children:
                if param_node.type in ("identifier", "typed_parameter",
                                        "default_parameter", "typed_default_parameter"):
                    param = _parse_python_param(param_node, source)
                    if param:
                        params.append(param)
    return params


def _parse_python_param(param_node: tree_sitter.Node, source: bytes) -> Parameter | None:
    text = _node_text(param_node, source)

    # Skip framework-injected params
    if text in ("self", "cls", "request", "db", "session"):
        return None

    name = ""
    param_type = ""
    default = None
    source_kind = "body"

    if param_node.type == "identifier":
        name = text
    elif param_node.type == "typed_parameter":
        for child in param_node.children:
            if child.type == "identifier":
                name = _node_text(child, source)
            elif child.type == "type":
                param_type = _node_text(child, source)
    elif param_node.type in ("default_parameter", "typed_default_parameter"):
        for child in param_node.children:
            if child.type == "identifier":
                name = _node_text(child, source)
            elif child.type == "type":
                param_type = _node_text(child, source)
            elif child.type not in ("=",):
                if not name:
                    name = _node_text(child, source)

    # Infer source from type hints (FastAPI pattern)
    if "Query" in param_type:
        source_kind = "query"
    elif "Path" in param_type:
        source_kind = "path"
    elif "Header" in param_type:
        source_kind = "header"

    if name:
        return Parameter(name=name, type=param_type or "Any", source=source_kind)
    return None


def _get_return_annotation(func_node: tree_sitter.Node, source: bytes) -> str:
    for child in func_node.children:
        if child.type == "type":
            return _node_text(child, source)
    return ""


def _has_auth_decorator(decorators: list[tree_sitter.Node], source: bytes) -> bool:
    auth_patterns = ("login_required", "auth_required", "requires_auth",
                     "permission_required", "Depends(get_current_user")
    for dec in decorators:
        text = _node_text(dec, source)
        for pattern in auth_patterns:
            if pattern in text:
                return True
    return False


def _extract_roles_from_decorators(decorators: list[tree_sitter.Node], source: bytes) -> list[str]:
    roles = []
    for dec in decorators:
        text = _node_text(dec, source)
        role_match = re.findall(r'(?:roles?|permission)\s*=\s*\[([^\]]*)\]', text)
        for match in role_match:
            roles.extend(re.findall(r'["\']([^"\']+)["\']', match))
    return roles


def _extract_class_based_endpoints(class_node: tree_sitter.Node, source: bytes, file_path: str) -> list[Endpoint]:
    """Extract endpoints from class-based views (Django REST ViewSets, Flask-RESTful)."""
    endpoints = []
    class_name = _get_class_name(class_node, source)
    if not class_name:
        return endpoints

    http_methods = {"get", "post", "put", "patch", "delete", "list", "create", "retrieve", "update", "destroy"}

    for method_node in _find_nodes_by_type(class_node, "function_definition"):
        name = _get_function_name(method_node, source)
        if name not in http_methods:
            continue

        method_map = {
            "get": "GET", "retrieve": "GET", "list": "GET",
            "post": "POST", "create": "POST",
            "put": "PUT", "update": "PUT",
            "patch": "PATCH",
            "delete": "DELETE", "destroy": "DELETE",
        }

        params = _extract_function_params(method_node, source)
        params = [p for p in params if p.name != "self"]
        return_type = _get_return_annotation(method_node, source)

        endpoints.append(Endpoint(
            http_method=method_map.get(name, "GET"),
            path=f"/{class_name.lower()}/",
            handler_name=f"{class_name}.{name}",
            file_path=file_path,
            line_number=method_node.start_point[0] + 1,
            parameters=params,
            return_type=return_type,
            auth_required=False,
            roles=[],
            decorators=[],
        ))

    return endpoints


def _get_class_name(class_node: tree_sitter.Node, source: bytes) -> str:
    for child in class_node.children:
        if child.type == "identifier":
            return _node_text(child, source)
    return ""


def _extract_python_type(class_node: tree_sitter.Node, source: bytes, file_path: str) -> TypeDefinition | None:
    class_name = _get_class_name(class_node, source)
    if not class_name:
        return None

    parent_types = []
    for child in class_node.children:
        if child.type == "argument_list":
            for arg in child.children:
                if arg.type == "identifier":
                    parent_types.append(_node_text(arg, source))

    # Determine if it's a type we care about (DTO, model, schema)
    is_relevant = any(p in CLASS_MARKERS for p in parent_types)
    decorators = _get_decorators(class_node, source)
    decorator_texts = [_node_text(d, source) for d in decorators]
    if any("dataclass" in d for d in decorator_texts):
        is_relevant = True

    if not is_relevant:
        return None

    fields = []
    for child in class_node.children:
        if child.type == "block":
            for stmt in child.children:
                if stmt.type == "expression_statement":
                    field = _extract_python_field(stmt, source)
                    if field:
                        fields.append(field)
                elif stmt.type == "type_alias_statement":
                    field = _extract_python_field(stmt, source)
                    if field:
                        fields.append(field)

    kind = "dataclass" if any("dataclass" in d for d in decorator_texts) else "class"

    return TypeDefinition(
        name=class_name,
        file_path=file_path,
        line_number=class_node.start_point[0] + 1,
        kind=kind,
        fields=fields,
        parent_types=parent_types,
        annotations=decorator_texts,
    )


def _extract_python_field(stmt_node: tree_sitter.Node, source: bytes) -> Parameter | None:
    text = _node_text(stmt_node, source).strip()
    # Match: field_name: type or field_name: type = default
    match = re.match(r'(\w+)\s*:\s*([^=]+?)(?:\s*=\s*(.+))?$', text)
    if match:
        name = match.group(1)
        field_type = match.group(2).strip()
        default = match.group(3).strip() if match.group(3) else None
        required = default is None or "..." in (default or "")
        return Parameter(name=name, type=field_type, required=required, default=default)
    return None
