"""ASTRA Offline Policy Compliance Scanner.

Statically checks codebase for prohibited external network calls, remote API dependencies,
or unapproved dynamic downloads in runtime code paths (Rules 1 & 2).
"""

import sys
import re
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Directories subject to strict offline inspection
TARGET_DIRS = ["backend", "ml", "geospatial", "frontend/src"]

# Prohibited imports and SDKs
FORBIDDEN_IMPORTS = [
    (r"\bimport\s+openai\b", "Direct OpenAI SDK import"),
    (r"\bfrom\s+openai\b", "Direct OpenAI SDK import"),
    (r"\bimport\s+anthropic\b", "Direct Anthropic SDK import"),
    (r"\bfrom\s+anthropic\b", "Direct Anthropic SDK import"),
    (r"\bgoogle\.generativeai\b", "Direct Google GenAI SDK import"),
    (r"\btorch\.hub\.load\s*\(\s*['\"][^'\"]+/[^'\"]+", "Remote torch.hub dynamic weight download"),
]

# Patterns for runtime external URLs (excluding localhost, loopback, docs, and XML namespaces)
FORBIDDEN_URL_REGEX = re.compile(
    r"https?://(?!localhost|127\.0\.0\.1|0\.0\.0\.0|www\.w3\.org|json-schema\.org)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)

# Allowed file extensions
INSPECT_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx"}


def scan_file(filepath: Path) -> list[str]:
    violations = []
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return [f"Could not read file {filepath}: {e}"]

    # Check forbidden imports
    for pattern, desc in FORBIDDEN_IMPORTS:
        if re.search(pattern, content):
            violations.append(f"{filepath}: Prohibited dependency found - {desc}")

    # Check external URLs in code (ignore comments or docstrings if possible, or flag for review)
    for line_idx, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        # Skip pure comment lines in python or js
        if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
            continue
        matches = FORBIDDEN_URL_REGEX.findall(line)
        for match in matches:
            violations.append(f"{filepath}:{line_idx} External network URL detected: {match}")

    return violations


def main():
    root_dir = Path(__file__).resolve().parent.parent
    all_violations = []
    files_scanned = 0

    print("==================================================")
    print("ASTRA Offline Compliance Scanner (Rule 1 & Rule 2)")
    print("==================================================")

    for dir_name in TARGET_DIRS:
        target_path = root_dir / dir_name
        if not target_path.exists():
            continue
        for ext in INSPECT_EXTS:
            for file_path in target_path.rglob(f"*{ext}"):
                files_scanned += 1
                v = scan_file(file_path)
                all_violations.extend(v)

    print(f"Scanned {files_scanned} source files.")

    if all_violations:
        print("\n[VIOLATIONS DETECTED] (Offline Policy Breached):")
        for v in all_violations:
            print(f"  - {v}")
        sys.exit(1)
    else:
        print("\n[PASSED]: Zero prohibited external runtime APIs or remote downloads found.")
        print("System strictly adheres to ASTRA Offline Policy.")
        sys.exit(0)



if __name__ == "__main__":
    main()
