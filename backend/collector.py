"""Live collection through the tested Go collector, without guessed resource ratios."""
import json
import sys
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))

from evidence_constraints import require_coverage
from schemas.validate import validate


def _name(value):
    if len(value) > 63 or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", value):
        raise ValueError("Service and namespace must be Kubernetes names")


def configured_lookback():
    """Operator-selected interval; HTTP callers cannot choose arbitrary query costs."""
    value = os.environ.get("SLOSCOPE_LOOKBACK", "1h")
    match = re.fullmatch(r"([1-9][0-9]*)([smhd])", value)
    if not match:
        raise ValueError("SLOSCOPE_LOOKBACK must be an integer duration in s/m/h/d")
    seconds = int(match.group(1)) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[match.group(2)]
    if not 120 <= seconds <= 30 * 86400:
        raise ValueError("SLOSCOPE_LOOKBACK must be between 2m and 30d")
    return value


def _normalized_window(value):
    seconds = int(value[:-1]) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[value[-1]]
    for unit, multiplier in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds % multiplier == 0:
            return str(seconds // multiplier) + unit
    return str(seconds) + "s"


def collect_evidence(service, namespace):
    _name(service)
    _name(namespace)
    lookback = configured_lookback()
    root = Path(__file__).resolve().parent.parent
    binary = os.environ.get("SLOSCOPE_BINARY", shutil.which("sloscope") or str(root / "bin/sloscope"))
    with tempfile.TemporaryDirectory(prefix="sloscope-collect-") as directory:
        try:
            subprocess.run([binary, "generate", "--service", service, "--namespace", namespace,
                            "--lookback", lookback, "--out", directory, "--dry-run"],
                           cwd=root, check=True, capture_output=True, timeout=120)
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError("Configured evidence collector failed") from exc
        evidence = json.loads((Path(directory) / "evidence.json").read_text())
    validate(evidence, "evidence")
    if evidence["lookback_window"] != _normalized_window(lookback):
        raise ValueError("Collector returned a different lookback window")
    if evidence["service"] != service or evidence["namespace"] != namespace:
        raise ValueError("Collector returned a different service or namespace")
    if evidence.get("coverage_ratio", 0) < 0.8:
        raise ValueError("Insufficient measured coverage for live collection")
    return evidence


def collect_and_store(service, namespace, store):
    from baseline import compute_baseline
    from deviation import compute_drift_signal
    evidence = collect_evidence(service, namespace)
    current = compute_baseline(evidence)
    require_coverage(current)
    reference = store.load(service, "baseline")
    if reference and reference.get("namespace") != namespace:
        raise ValueError("Stored reference belongs to a different namespace")
    if reference:
        signal = compute_drift_signal({"baseline": reference, "live_evidence": evidence})
        store.save(service, "drift-signal", signal)
    else:
        store.save(service, "baseline", current)
    store.save(service, "current-baseline", current)
    return {"status": "ok", "service": service,
            "reference": "preserved" if reference else "initialized",
            "drift_computed": reference is not None}


def main():
    import argparse
    from .store import ArtifactStore
    parser = argparse.ArgumentParser(description="Collect a window without replacing the reference baseline")
    parser.add_argument("--service", required=True)
    parser.add_argument("--namespace", required=True)
    args = parser.parse_args()
    print(json.dumps(collect_and_store(args.service, args.namespace, ArtifactStore()), sort_keys=True))


if __name__ == "__main__":
    main()
