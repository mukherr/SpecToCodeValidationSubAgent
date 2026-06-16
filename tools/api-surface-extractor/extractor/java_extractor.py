"""
Tree-sitter based Java API surface extractor.

Extracts Spring Boot controllers, DTOs, service interfaces, and JPA entities
using deterministic AST queries — no LLM, no context window limits.
"""

import tree_sitter

from .core import Endpoint, Language, Parameter, ServiceMethod, TypeDefinition, get_parser

ROUTE_ANNOTATIONS = {
    "GetMapping", "PostMapping", "PutMapping", "DeleteMapping",
    "PatchMapping", "RequestMapping",
}

HTTP_METHOD_MAP = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "DeleteMapping": "DELETE",
    "PatchMapping": "PATCH",
}

AUTH_ANNOTATIONS = {"PreAuthorize", "Secured", "RolesAllowed"}

PARAM_SOURCE_ANNOTATIONS = {
    "PathVariable": "path",
    "RequestParam": "query",
    "RequestHeader": "header",
    "RequestBody": "body",
}


class JavaExtractor:
    def __init__(self):
        self.parser = get_parser(Language.JAVA)

    def parse(self, source: bytes) -> tree_sitter.Tree:
        return self.parser.parse(source)

    def extract_endpoints(self, tree: tree_sitter.Tree, source: bytes, file_path: str) -> list[Endpoint]:
        endpoints = []
        root = tree.root_node

        for class_node in _find_nodes_by_type(root, "class_declaration"):
            class_annotations = _get_annotations(class_node, source)
            base_path = _extract_request_mapping_path(class_annotations, source)
            class_roles = _extract_roles(class_annotations, source)

            for method_node in _find_nodes_by_type(class_node, "method_declaration"):
                method_annotations = _get_annotations(method_node, source)
                route_annotation = _find_route_annotation(method_annotations, source)
                if not route_annotation:
                    continue

                annotation_name = _get_annotation_name(route_annotation, source)
                http_method = HTTP_METHOD_MAP.get(annotation_name, "GET")

                if annotation_name == "RequestMapping":
                    http_method = _extract_request_mapping_method(route_annotation, source)

                method_path = _extract_annotation_path(route_annotation, source)
                full_path = _join_paths(base_path, method_path)

                handler_name = _get_method_name(method_node, source)
                params = _extract_method_parameters(method_node, source)
                return_type = _get_return_type(method_node, source)

                method_roles = _extract_roles(method_annotations, source)
                all_roles = class_roles + method_roles

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
                    auth_required=bool(all_roles) or _has_auth_annotation(class_annotations + method_annotations, source),
                    roles=all_roles,
                    decorators=[_node_text(a, source) for a in method_annotations],
                ))

        return endpoints

    def extract_types(self, tree: tree_sitter.Tree, source: bytes, file_path: str) -> list[TypeDefinition]:
        types = []
        root = tree.root_node

        for node in _find_nodes_by_type(root, "class_declaration"):
            types.append(_extract_type_def(node, source, file_path, "class"))

        for node in _find_nodes_by_type(root, "interface_declaration"):
            types.append(_extract_type_def(node, source, file_path, "interface"))

        for node in _find_nodes_by_type(root, "enum_declaration"):
            types.append(_extract_type_def(node, source, file_path, "enum"))

        for node in _find_nodes_by_type(root, "record_declaration"):
            types.append(_extract_type_def(node, source, file_path, "record"))

        return types

    def extract_service_methods(self, tree: tree_sitter.Tree, source: bytes, file_path: str) -> list[ServiceMethod]:
        methods = []
        root = tree.root_node

        for iface_node in _find_nodes_by_type(root, "interface_declaration"):
            iface_name = _get_type_name(iface_node, source)
            if not iface_name:
                continue

            for method_node in _find_nodes_by_type(iface_node, "method_declaration"):
                name = _get_method_name(method_node, source)
                params = _extract_method_parameters(method_node, source)
                return_type = _get_return_type(method_node, source)
                methods.append(ServiceMethod(
                    name=name,
                    file_path=file_path,
                    line_number=method_node.start_point[0] + 1,
                    parameters=params,
                    return_type=return_type,
                    interface_name=iface_name,
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


def _get_annotations(node: tree_sitter.Node, source: bytes) -> list[tree_sitter.Node]:
    annotations = []
    if node.type in ("class_declaration", "interface_declaration", "enum_declaration", "record_declaration"):
        for child in node.parent.children if node.parent else []:
            if child.type == "modifiers":
                for mod_child in child.children:
                    if mod_child.type in ("annotation", "marker_annotation"):
                        annotations.append(mod_child)
                break
    elif node.type == "method_declaration":
        for sibling in (node.parent.children if node.parent else []):
            if sibling == node:
                break
            if sibling.type == "modifiers":
                for mod_child in sibling.children:
                    if mod_child.type in ("annotation", "marker_annotation"):
                        annotations.append(mod_child)

        for child in node.children:
            if child.type == "modifiers":
                for mod_child in child.children:
                    if mod_child.type in ("annotation", "marker_annotation"):
                        annotations.append(mod_child)
    return annotations


def _get_annotation_name(annotation_node: tree_sitter.Node, source: bytes) -> str:
    for child in annotation_node.children:
        if child.type == "identifier":
            return _node_text(child, source)
        if child.type == "scoped_identifier":
            return _node_text(child, source).split(".")[-1]
    return ""


def _find_route_annotation(annotations: list[tree_sitter.Node], source: bytes) -> tree_sitter.Node | None:
    for ann in annotations:
        name = _get_annotation_name(ann, source)
        if name in ROUTE_ANNOTATIONS:
            return ann
    return None


def _extract_request_mapping_path(annotations: list[tree_sitter.Node], source: bytes) -> str:
    for ann in annotations:
        name = _get_annotation_name(ann, source)
        if name == "RequestMapping":
            return _extract_annotation_path(ann, source)
    return ""


def _extract_annotation_path(annotation_node: tree_sitter.Node, source: bytes) -> str:
    text = _node_text(annotation_node, source)
    # Handle @GetMapping("/path"), @GetMapping(value="/path"), @GetMapping(path="/path")
    import re
    # Match quoted strings inside the annotation
    matches = re.findall(r'"([^"]*)"', text)
    if matches:
        return matches[0]
    return ""


def _extract_request_mapping_method(annotation_node: tree_sitter.Node, source: bytes) -> str:
    text = _node_text(annotation_node, source)
    import re
    method_match = re.search(r'method\s*=\s*RequestMethod\.(\w+)', text)
    if method_match:
        return method_match.group(1)
    return "GET"


def _extract_roles(annotations: list[tree_sitter.Node], source: bytes) -> list[str]:
    roles = []
    import re
    for ann in annotations:
        name = _get_annotation_name(ann, source)
        if name in AUTH_ANNOTATIONS:
            text = _node_text(ann, source)
            role_matches = re.findall(r'"([^"]*)"', text)
            roles.extend(role_matches)
    return roles


def _has_auth_annotation(annotations: list[tree_sitter.Node], source: bytes) -> bool:
    for ann in annotations:
        name = _get_annotation_name(ann, source)
        if name in AUTH_ANNOTATIONS:
            return True
    return False


def _get_method_name(method_node: tree_sitter.Node, source: bytes) -> str:
    for child in method_node.children:
        if child.type == "identifier":
            return _node_text(child, source)
    return ""


def _get_return_type(method_node: tree_sitter.Node, source: bytes) -> str:
    for child in method_node.children:
        if child.type in ("type_identifier", "generic_type", "void_type",
                          "integral_type", "boolean_type", "array_type"):
            return _node_text(child, source)
    return ""


def _extract_method_parameters(method_node: tree_sitter.Node, source: bytes) -> list[Parameter]:
    params = []
    for child in method_node.children:
        if child.type == "formal_parameters":
            for param_node in child.children:
                if param_node.type == "formal_parameter":
                    param = _parse_formal_parameter(param_node, source)
                    if param:
                        params.append(param)
    return params


def _parse_formal_parameter(param_node: tree_sitter.Node, source: bytes) -> Parameter | None:
    param_type = ""
    param_name = ""
    source_kind = "body"

    for child in param_node.children:
        if child.type == "modifiers":
            for mod_child in child.children:
                if mod_child.type in ("annotation", "marker_annotation"):
                    ann_name = _get_annotation_name(mod_child, source)
                    if ann_name in PARAM_SOURCE_ANNOTATIONS:
                        source_kind = PARAM_SOURCE_ANNOTATIONS[ann_name]
        elif child.type in ("type_identifier", "generic_type", "integral_type",
                            "boolean_type", "array_type", "scoped_type_identifier"):
            param_type = _node_text(child, source)
        elif child.type == "identifier":
            param_name = _node_text(child, source)

    if param_name and param_type:
        # Skip framework-injected params
        if param_type in ("HttpServletRequest", "HttpServletResponse", "HttpSession",
                          "Principal", "Authentication", "BindingResult", "Model"):
            return None
        return Parameter(name=param_name, type=param_type, source=source_kind)
    return None


def _get_type_name(node: tree_sitter.Node, source: bytes) -> str:
    for child in node.children:
        if child.type == "identifier":
            return _node_text(child, source)
    return ""


def _extract_type_def(node: tree_sitter.Node, source: bytes, file_path: str, kind: str) -> TypeDefinition:
    name = _get_type_name(node, source)
    fields = []
    parent_types = []
    annotations = []

    # Extract parent types (extends/implements)
    for child in node.children:
        if child.type == "superclass":
            for sc_child in child.children:
                if sc_child.type == "type_identifier":
                    parent_types.append(_node_text(sc_child, source))
        elif child.type == "super_interfaces":
            for iface_child in child.children:
                if iface_child.type == "type_list":
                    for type_node in iface_child.children:
                        if type_node.type == "type_identifier":
                            parent_types.append(_node_text(type_node, source))

    # Extract fields from class body
    for child in node.children:
        if child.type == "class_body" or child.type == "interface_body":
            for member in child.children:
                if member.type == "field_declaration":
                    field = _extract_field(member, source)
                    if field:
                        fields.append(field)

    # Extract annotations
    ann_nodes = _get_annotations(node, source)
    annotations = [_node_text(a, source) for a in ann_nodes]

    return TypeDefinition(
        name=name,
        file_path=file_path,
        line_number=node.start_point[0] + 1,
        kind=kind,
        fields=fields,
        parent_types=parent_types,
        annotations=annotations,
    )


def _extract_field(field_node: tree_sitter.Node, source: bytes) -> Parameter | None:
    field_type = ""
    field_name = ""

    for child in field_node.children:
        if child.type in ("type_identifier", "generic_type", "integral_type",
                          "boolean_type", "array_type", "floating_point_type"):
            field_type = _node_text(child, source)
        elif child.type == "variable_declarator":
            for vc in child.children:
                if vc.type == "identifier":
                    field_name = _node_text(vc, source)

    if field_name and field_type:
        return Parameter(name=field_name, type=field_type)
    return None


def _join_paths(base: str, path: str) -> str:
    base = base.rstrip("/")
    path = path.lstrip("/") if path else ""
    if base and path:
        return f"{base}/{path}"
    return base or f"/{path}" if path else ""
