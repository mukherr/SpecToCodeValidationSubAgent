"""
Codebase scanner — walks the file tree, dispatches to language-specific
extractors, and aggregates results into a unified ExtractionResult.

This is the main orchestration layer. It:
1. Discovers all source files (respecting .gitignore)
2. Filters to public-surface files (controllers, routes, DTOs, service interfaces)
3. Parses each file with tree-sitter
4. Delegates to language-specific extractors
5. Returns a complete ExtractionResult
"""

import fnmatch
from pathlib import Path

from .core import ExtractionResult, Language, detect_language
from .go_extractor import GoExtractor
from .java_extractor import JavaExtractor
from .python_extractor import PythonExtractor
from .typescript_extractor import TypeScriptExtractor

# File patterns that indicate public API surface (controllers, routes, DTOs)
SURFACE_PATTERNS = {
    Language.JAVA: [
        "*Controller.java", "*Resource.java", "*Endpoint.java",
        "*Request.java", "*Response.java", "*Dto.java", "*DTO.java",
        "*Service.java", "*ServiceImpl.java",
        "*Entity.java",
    ],
    Language.PYTHON: [
        "*views.py", "*routes.py", "*api.py", "*endpoints.py", "*router.py",
        "*schemas.py", "*models.py", "*serializers.py",
        "*service.py", "*services.py",
    ],
    Language.TYPESCRIPT: [
        "*.controller.ts", "*.routes.ts", "*.router.ts",
        "*.dto.ts", "*.entity.ts", "*.model.ts",
        "*.service.ts", "*.interface.ts",
    ],
    Language.GO: [
        "*handler*.go", "*router*.go", "*routes*.go",
        "*model*.go", "*dto*.go", "*service*.go",
        "*controller*.go",
    ],
}

# Directories to always skip
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "target", "build", "dist", ".gradle", ".mvn", "vendor",
    ".idea", ".vscode", ".settings", "bin", "obj",
}


class Scanner:
    def __init__(self, root_path: Path, scan_all: bool = False):
        self.root = root_path
        self.scan_all = scan_all
        self._extractors = {
            Language.JAVA: JavaExtractor(),
            Language.PYTHON: PythonExtractor(),
            Language.TYPESCRIPT: TypeScriptExtractor(),
            Language.GO: GoExtractor(),
        }

    def scan(self) -> ExtractionResult:
        result = ExtractionResult()
        files = self._discover_files()

        for file_path in files:
            language = detect_language(file_path)
            if not language:
                continue

            extractor = self._extractors.get(language)
            if not extractor:
                continue

            try:
                source = file_path.read_bytes()
                tree = extractor.parse(source)
                rel_path = str(file_path.relative_to(self.root))

                result.endpoints.extend(
                    extractor.extract_endpoints(tree, source, rel_path)
                )
                result.types.extend(
                    extractor.extract_types(tree, source, rel_path)
                )
                result.service_methods.extend(
                    extractor.extract_service_methods(tree, source, rel_path)
                )
            except Exception as e:
                result.errors.append(f"{file_path}: {e}")

        return result

    def _discover_files(self) -> list[Path]:
        files = []
        for path in self._walk(self.root):
            language = detect_language(path)
            if not language:
                continue
            if self.scan_all or self._matches_surface_pattern(path, language):
                files.append(path)
        return sorted(files)

    def _walk(self, directory: Path):
        try:
            for entry in directory.iterdir():
                if entry.name in SKIP_DIRS:
                    continue
                if entry.is_dir():
                    yield from self._walk(entry)
                elif entry.is_file():
                    yield entry
        except PermissionError:
            pass

    def _matches_surface_pattern(self, path: Path, language: Language) -> bool:
        patterns = SURFACE_PATTERNS.get(language, [])
        filename = path.name
        return any(fnmatch.fnmatch(filename, pattern) for pattern in patterns)
