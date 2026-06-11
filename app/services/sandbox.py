import os
import subprocess
import tempfile
import uuid
from pathlib import Path


class SandboxExecutor:
    """Execute code in a restricted local sandbox directory."""

    def __init__(self, sandbox_dir: str):
        self.sandbox_dir = Path(sandbox_dir).resolve()
        os.makedirs(self.sandbox_dir, exist_ok=True)

    def _ensure_in_sandbox(self, path: str) -> Path:
        """Ensure the resolved path is within the sandbox directory."""
        resolved = Path(path).resolve()
        if not str(resolved).startswith(str(self.sandbox_dir)):
            raise ValueError(f"Path {path} is outside the sandbox directory")
        return resolved

    def execute_python(self, code: str, timeout: int = 30) -> dict:
        """Execute Python code in the sandbox."""
        script_path = self.sandbox_dir / f"script_{uuid.uuid4().hex}.py"
        try:
            script_path.write_text(code, encoding="utf-8")
            result = subprocess.run(
                ["python", str(script_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.sandbox_dir),
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": "Execution timed out", "returncode": -1}
        finally:
            if script_path.exists():
                script_path.unlink()

    def execute_shell(self, command: str, timeout: int = 30) -> dict:
        """Execute a shell command in the sandbox."""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.sandbox_dir),
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": "Execution timed out", "returncode": -1}

    def read_file(self, filename: str) -> str:
        """Read a file from the sandbox directory."""
        path = self._ensure_in_sandbox(self.sandbox_dir / filename)
        if not path.exists():
            return f"File not found: {filename}"
        return path.read_text(encoding="utf-8", errors="replace")

    def write_file(self, filename: str, content: str) -> str:
        """Write a file to the sandbox directory."""
        path = self._ensure_in_sandbox(self.sandbox_dir / filename)
        path.write_text(content, encoding="utf-8")
        return f"File written: {filename}"

    def list_files(self, subdir: str = ".") -> list:
        """List files in the sandbox directory."""
        target = self._ensure_in_sandbox(self.sandbox_dir / subdir)
        files = []
        for item in target.iterdir():
            prefix = "[D]" if item.is_dir() else "[F]"
            files.append(f"{prefix} {item.name}")
        return files
