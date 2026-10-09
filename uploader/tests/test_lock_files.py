"""The requirements files, the lock files and pyproject.toml must not drift apart."""

import re
import tomllib
from pathlib import Path

UPLOADER = Path(__file__).resolve().parents[1]


def _name(spec: str) -> str:
    return re.split(r"[<>=!~\[; ]", spec.strip(), maxsplit=1)[0].lower().replace("_", "-")


def _requirements(path: Path) -> list[str]:
    """The requirement lines of a .in file, without comments and without -r/-c options."""
    lines = [ln.split("#", 1)[0].strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    return [ln for ln in lines if ln and not ln.startswith("-")]


def _pins(path: Path) -> dict[str, str]:
    return {
        m.group(1).lower().replace("_", "-"): m.group(2)
        for m in re.finditer(r"^([A-Za-z0-9_.\-]+)==(\S+?)(?: \\)?$", path.read_text(encoding="utf-8"), re.MULTILINE)
    }


def _pyproject() -> dict:
    return tomllib.loads((UPLOADER / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def test_runtime_requirements_in_matches_pyproject():
    assert sorted(_requirements(UPLOADER / "requirements.in")) == sorted(_pyproject()["dependencies"])


def test_every_dev_extra_is_in_the_dev_requirements_with_the_same_spec():
    in_file = _requirements(UPLOADER / "requirements-dev.in")
    for spec in _pyproject()["optional-dependencies"]["dev"]:
        assert spec in in_file, f"{spec} from pyproject.toml is missing in requirements-dev.in"


def test_every_pin_in_the_dev_lock_has_hashes():
    text = (UPLOADER / "requirements-dev.txt").read_text(encoding="utf-8")
    entries = re.split(r"\n(?=[A-Za-z0-9_.\-]+==)", text)
    pinned = [e for e in entries if re.match(r"[A-Za-z0-9_.\-]+==", e)]
    assert pinned
    assert all("--hash=sha256:" in e for e in pinned)


def test_dev_lock_keeps_the_exact_runtime_pins_of_the_image():
    runtime, dev = _pins(UPLOADER / "requirements.txt"), _pins(UPLOADER / "requirements-dev.txt")
    assert runtime
    assert {name: dev.get(name) for name in runtime} == runtime


def test_the_tools_ci_runs_are_locked():
    locked = _pins(UPLOADER / "requirements-dev.txt")
    for tool in ("pytest", "pytest-cov", "ruff", "mypy", "types-requests", "pip-audit", "pip", "setuptools"):
        assert tool in locked, f"{tool} is not in requirements-dev.txt"
