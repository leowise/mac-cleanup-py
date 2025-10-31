"""Security validation for custom modules."""

import ast
import importlib.util
from typing import Any, Dict, List, Optional, Set

from beartype import beartype  # pyright: ignore [reportUnknownVariableType]

from mac_cleanup.console import console


class CustomModuleSecurityError(Exception):
    """Exception raised when custom module security validation fails."""


class CustomModuleValidator:
    """Validates custom modules for security issues."""

    # Dangerous imports that should be flagged
    DANGEROUS_IMPORTS = {
        "os", "subprocess", "sys", "shutil", "pathlib",
        "importlib", "builtins", "pickle", "marshal",
        "socket", "urllib", "http", "ftplib", "telnetlib",
        "smtplib", "imaplib", "poplib", "xmlrpc", "ssl",
        "hashlib", "hmac", "secrets", "cryptography",
        "paramiko", "fabric", "ansible"
    }

    # Dangerous function calls
    DANGEROUS_FUNCTIONS = {
        "exec", "eval", "compile", "__import__",
        "open", "file", "input", "raw_input",
        "reload", "imp", "runpy"
    }

    # Allowed imports for cleanup operations
    ALLOWED_IMPORTS = {
        "mac_cleanup", "pathlib", "typing", "functools",
        "itertools", "collections", "re", "glob"
    }

    def __init__(self):
        self.warnings: List[str] = []
        self.errors: List[str] = []

    @beartype
    def validate_module_file(self, file_path: str) -> bool:
        """
        Validate a custom module file for security issues.

        :param file_path: Path to the Python file to validate
        :return: True if validation passes, False otherwise
        """
        self.warnings.clear()
        self.errors.clear()

        try:
            # Parse the AST
            with open(file_path, "r", encoding="utf-8") as f:
                source_code = f.read()

            tree = ast.parse(source_code, filename=file_path)

            # Analyze the AST
            self._analyze_ast(tree)

            # Check for dangerous patterns
            self._check_dangerous_patterns(source_code)

            # Return validation result
            return len(self.errors) == 0

        except SyntaxError as e:
            self.errors.append(f"Syntax error in {file_path}: {e}")
            return False
        except Exception as e:
            self.errors.append(f"Error validating {file_path}: {e}")
            return False

    def _analyze_ast(self, tree: ast.AST) -> None:
        """Analyze the AST for security issues."""
        analyzer = ASTSecurityAnalyzer(self.warnings, self.errors)
        analyzer.visit(tree)

    def _check_dangerous_patterns(self, source_code: str) -> None:
        """Check for dangerous patterns in source code."""
        # Check for shell execution patterns
        dangerous_patterns = [
            "subprocess", "os.system", "os.popen", "os.spawn",
            "commands.getstatusoutput", "commands.getoutput",
            "popen2", "popen3", "popen4"
        ]

        for pattern in dangerous_patterns:
            if pattern in source_code:
                self.warnings.append(f"Potentially dangerous pattern detected: {pattern}")

    def get_validation_report(self) -> Dict[str, Any]:
        """Get a validation report."""
        return {
            "valid": len(self.errors) == 0,
            "errors": self.errors.copy(),
            "warnings": self.warnings.copy(),
            "severity": "high" if self.errors else ("medium" if self.warnings else "low")
        }


class ASTSecurityAnalyzer(ast.NodeVisitor):
    """AST visitor that analyzes code for security issues."""

    def __init__(self, warnings: List[str], errors: List[str]):
        self.warnings = warnings
        self.errors = errors
        self.imported_modules: Set[str] = set()
        self.function_calls: Set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        """Check import statements."""
        for alias in node.names:
            module_name = alias.name.split(".")[0]
            self.imported_modules.add(module_name)

            if (module_name in CustomModuleValidator.DANGEROUS_IMPORTS and
                module_name not in CustomModuleValidator.ALLOWED_IMPORTS):
                self.warnings.append(f"Dangerous import detected: {module_name}")

        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Check from import statements."""
        if node.module:
            module_name = node.module.split(".")[0]
            self.imported_modules.add(module_name)

            if (module_name in CustomModuleValidator.DANGEROUS_IMPORTS and
                module_name not in CustomModuleValidator.ALLOWED_IMPORTS):
                self.warnings.append(f"Dangerous import from {module_name}")

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Check function calls."""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            self.function_calls.add(func_name)

            if func_name in CustomModuleValidator.DANGEROUS_FUNCTIONS:
                self.errors.append(f"Dangerous function call: {func_name}()")

        elif isinstance(node.func, ast.Attribute):
            # Handle method calls like os.system()
            if isinstance(node.func.value, ast.Name):
                module_name = node.func.value.id
                method_name = node.func.attr

                if module_name in self.imported_modules:
                    full_call = f"{module_name}.{method_name}"
                    if full_call in ["os.system", "subprocess.call", "subprocess.run"]:
                        self.errors.append(f"Dangerous system call: {full_call}()")

        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        """Check constant literals for potentially dangerous content."""
        # Check string literals for dangerous content
        if isinstance(node.value, str):
            dangerous_strings = ["rm -rf", "sudo", "chmod 777", "format", "mkfs"]
            if any(dangerous in node.value for dangerous in dangerous_strings):
                truncated_value = node.value[:50] + "..." if len(node.value) > 50 else node.value
                self.warnings.append(f"Potentially dangerous string literal: {truncated_value}")

        self.generic_visit(node)


@beartype
def validate_custom_module(file_path: str, *, show_warnings: bool = True) -> bool:
    """
    Validate a custom module file.

    :param file_path: Path to the module file
    :param show_warnings: Whether to display warnings to user
    :return: True if module is safe to load
    """
    validator = CustomModuleValidator()
    is_valid = validator.validate_module_file(file_path)
    report = validator.get_validation_report()

    if not is_valid:
        console.print(f"[danger]❌ Custom module {file_path} failed security validation:[/danger]")
        for error in report["errors"]:
            console.print(f"  [red]• {error}[/red]")

    if show_warnings and report["warnings"]:
        console.print(f"[warning]⚠️  Security warnings for {file_path}:[/warning]")
        for warning in report["warnings"]:
            console.print(f"  [yellow]• {warning}[/yellow]")

    return is_valid


# Global validator instance
_module_validator = CustomModuleValidator()


@beartype
def load_custom_module_safely(file_path: str) -> Optional[Any]:
    """
    Load a custom module with security validation.

    :param file_path: Path to the module file
    :return: Loaded module if safe, None otherwise
    """
    # First validate the module
    if not validate_custom_module(file_path):
        console.print("[danger]Refusing to load unsafe custom module.[/danger]")
        return None

    # If validation passes, load the module
    try:
        spec = importlib.util.spec_from_file_location("custom_module", file_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    except Exception as e:
        console.print(f"[danger]Error loading custom module {file_path}: {e}[/danger]")

    return None