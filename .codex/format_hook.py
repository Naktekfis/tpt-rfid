"""Format files from a Codex Edit/Write PostToolUse event when tools exist."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PATCH_PATH = re.compile(r"^\*\*\* (?:Add|Update|Move to) File: (.+)$", re.M)


def changed_files(event):
    tool_input = event.get("tool_input") or {}
    paths = []
    if tool_input.get("file_path"):
        paths.append(tool_input["file_path"])
    paths.extend(PATCH_PATH.findall(tool_input.get("command") or ""))

    seen = set()
    for raw_path in paths:
        path = Path(raw_path)
        if not path.is_absolute():
            path = ROOT / path
        path = path.resolve()
        if os.path.commonpath((str(ROOT), str(path))) != str(ROOT):
            continue
        if path.is_file() and path not in seen:
            seen.add(path)
            yield path


def formatter_for(path):
    suffix = path.suffix
    if suffix == ".py" and shutil.which("ruff"):
        return ["ruff", "format", "--quiet", str(path)]
    if suffix == ".go" and shutil.which("gofmt"):
        return ["gofmt", "-w", str(path)]
    if suffix == ".rs" and shutil.which("rustfmt"):
        return ["rustfmt", "--quiet", str(path)]
    if suffix in {".c", ".cc", ".cpp", ".h", ".hpp"} and shutil.which("clang-format"):
        return ["clang-format", "-i", str(path)]
    if suffix == ".sh" and shutil.which("shfmt"):
        return ["shfmt", "-w", str(path)]
    prettier = ROOT / "node_modules" / ".bin" / "prettier"
    if suffix in {".js", ".jsx", ".ts", ".tsx", ".css", ".scss", ".json", ".vue", ".svelte"} and prettier.is_file():
        return [str(prettier), "--write", "--log-level", "warn", str(path)]
    return None


def main():
    try:
        event = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    for path in changed_files(event):
        command = formatter_for(path)
        if command:
            result = subprocess.run(command, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            if result.returncode:
                print(result.stderr.strip(), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
