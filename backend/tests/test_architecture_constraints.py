from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = REPO_ROOT / "modular_backend"
TARGET_MODEL_FILES = [
    MODULE_ROOT / "auth/models/request.py",
    MODULE_ROOT / "auth/models/response.py",
    MODULE_ROOT / "auth/models/interface.py",
    MODULE_ROOT / "communications/models/request.py",
    MODULE_ROOT / "communications/models/response.py",
    MODULE_ROOT / "communications/models/interface.py",
    MODULE_ROOT / "entities/models/request.py",
    MODULE_ROOT / "entities/models/response.py",
    MODULE_ROOT / "entities/models/interface.py",
    MODULE_ROOT / "views/models/request.py",
    MODULE_ROOT / "views/models/response.py",
    MODULE_ROOT / "views/models/interface.py",
    MODULE_ROOT / "workflow/models/request.py",
    MODULE_ROOT / "workflow/models/response.py",
    MODULE_ROOT / "workflow/models/interface.py",
]
OPTIONAL_DB_MODEL_MODULES = {"health"}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _runtime_py_files() -> list[Path]:
    paths: list[Path] = []
    for path in MODULE_ROOT.rglob("*.py"):
        normalized = str(path).replace("\\", "/")
        if "/tests/" in normalized:
            continue
        if "/docs/" in normalized:
            continue
        if "/agent_guidelines/" in normalized:
            continue
        paths.append(path)
    return sorted(paths)


def _active_modules() -> list[str]:
    modules: list[str] = []
    for path in MODULE_ROOT.iterdir():
        if not path.is_dir():
            continue
        if path.name.startswith("."):
            continue
        if (path / "controller.py").exists():
            modules.append(path.name)
    return sorted(modules)


def test_active_modules_follow_controller_manager_db_layout() -> None:
    missing: list[str] = []
    for module_name in _active_modules():
        module_root = MODULE_ROOT / module_name
        manager_path = module_root / "manager.py"
        db_models_path = module_root / "db_models.py"
        if not manager_path.exists():
            missing.append(str(manager_path))
        if module_name not in OPTIONAL_DB_MODEL_MODULES and not db_models_path.exists():
            missing.append(str(db_models_path))
    assert missing == []


def test_no_compatibility_alias_subclasses_remain() -> None:
    subclass_pattern = re.compile(r"class\s+\w+\(\w+(?:RestController|ServiceManager|ModelService)\)\s*:")
    offenders: list[str] = []
    for path in _runtime_py_files():
        for match in subclass_pattern.finditer(_read(path)):
            offenders.append(f"{path}:{match.start()}")
    assert offenders == []


def test_controllers_do_not_import_db_models_directly() -> None:
    offenders: list[str] = []
    for module_name in _active_modules():
        controller_file = MODULE_ROOT / module_name / "controller.py"
        if not controller_file.exists():
            continue
        content = _read(controller_file)
        if re.search(r"\bdb_models\b", content):
            offenders.append(str(controller_file))
    assert offenders == []


def test_managers_do_not_import_fastapi() -> None:
    offenders: list[str] = []
    import_pattern = re.compile(r"^\s*(from|import)\s+fastapi\b", re.MULTILINE)
    for module_name in _active_modules():
        manager_file = MODULE_ROOT / module_name / "manager.py"
        if not manager_file.exists():
            continue
        if import_pattern.search(_read(manager_file)):
            offenders.append(str(manager_file))
    assert offenders == []


def test_db_models_do_not_import_fastapi() -> None:
    offenders: list[str] = []
    import_pattern = re.compile(r"^\s*(from|import)\s+fastapi\b", re.MULTILINE)
    for module_name in _active_modules():
        db_file = MODULE_ROOT / module_name / "db_models.py"
        if not db_file.exists():
            continue
        if import_pattern.search(_read(db_file)):
            offenders.append(str(db_file))
    assert offenders == []


def test_target_contract_modules_are_pydantic_based() -> None:
    offenders: list[str] = []
    for path in TARGET_MODEL_FILES:
        content = _read(path)
        if "@dataclass" in content or "from dataclasses import" in content:
            offenders.append(str(path))
    assert offenders == []
