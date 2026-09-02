"""Static A3 guard against direct global loads of route path identifiers."""
from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
API_DIR = BACKEND / "app" / "api"

PROTECTED_MODELS = frozenset(
    {
        "Patient",
        "Event",
        "Artifact",
        "Highlight",
        "Task",
        "Comment",
        "ArtifactVersion",
        "PatientCheckInSession",
        "VoiceCaptureRecord",
        "RankingRun",
        "RankingDecision",
        "LearningSignal",
        "User",
    }
)

# These are the only code paths allowed to operate across all clinics. They are
# not HTTP request loaders and receive no RoleContext bypass flag.
PRIVILEGED_SCOPE_ALLOWLIST = {
    "app.db": {
        "migrate_phase_e_schema",
        "migrate_fa1_schema",
        "install_clinic_isolation_schema",
    },
    "app.patient_review": {"materialize_due_escalations"},
    "seed.seed": {"create_schema", "seed"},
    "seed.highlights": {"generate_highlights"},
}


def _route_path(function: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    for decorator in function.decorator_list:
        if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
            continue
        if decorator.func.attr not in {"get", "post", "put", "patch", "delete"}:
            continue
        if decorator.args and isinstance(decorator.args[0], ast.Constant):
            return str(decorator.args[0].value)
    return None


def find_route_bypasses(api_dir: Path = API_DIR) -> list[str]:
    findings: list[str] = []
    for path in sorted(api_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for function in (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            route_path = _route_path(function)
            if route_path is None:
                continue
            route_ids = set(re.findall(r"{([A-Za-z_][A-Za-z0-9_]*)}", route_path))
            if not route_ids:
                continue
            for node in ast.walk(function):
                if not isinstance(node, ast.Call) or len(node.args) < 2:
                    continue
                if not isinstance(node.func, ast.Attribute) or node.func.attr != "get":
                    continue
                model, identifier = node.args[0], node.args[1]
                if (
                    isinstance(model, ast.Name)
                    and model.id in PROTECTED_MODELS
                    and isinstance(identifier, ast.Name)
                    and identifier.id in route_ids
                ):
                    findings.append(
                        f"{path.relative_to(BACKEND).as_posix()}:{node.lineno}:"
                        f"{function.name} uses db.get({model.id}, {identifier.id})"
                    )
    return findings


def main() -> int:
    findings = find_route_bypasses()
    if findings:
        print("A3_SCOPE_BYPASS_FAIL")
        for finding in findings:
            print(finding)
        return 1
    print("A3_SCOPE_BYPASS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
