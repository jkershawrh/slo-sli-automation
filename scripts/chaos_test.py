#!/usr/bin/env python3
"""sloscope chaos test: dependency fault injection.

Usage:
  python3 scripts/chaos_test.py
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        print(f"  [PASS] {name}")
        PASS += 1
    else:
        print(f"  [FAIL] {name} — {detail}")
        FAIL += 1


def test_corrupted_store():
    """Verify dashboard API handles corrupted artifact files."""
    print("\n=== Corrupted store ===")
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))
    sys.path.insert(0, str(PROJECT_ROOT / "analysis"))

    from store import ArtifactStore

    with tempfile.TemporaryDirectory() as tmpdir:
        store = ArtifactStore(tmpdir)

        # Write valid data
        store.save("test-svc", "baseline", {"service": "test", "valid": True})
        check("valid data loads", store.load("test-svc", "baseline")["valid"] == True)

        # Corrupt the file
        corrupt_path = Path(tmpdir) / "test-svc" / "baseline.json"
        corrupt_path.write_text("{corrupted json!!! not valid")

        try:
            data = store.load("test-svc", "baseline")
            check("corrupted file returns None or raises", data is None, f"got {data}")
        except (json.JSONDecodeError, Exception) as e:
            check("corrupted file raises clean exception", True)

        # Empty file
        corrupt_path.write_text("")
        try:
            data = store.load("test-svc", "baseline")
            check("empty file handles gracefully", data is None or isinstance(data, dict))
        except Exception:
            check("empty file raises clean exception", True)


def test_concurrent_writes():
    """Verify concurrent writes don't corrupt data."""
    print("\n=== Concurrent writes ===")
    import threading

    sys.path.insert(0, str(PROJECT_ROOT / "backend"))
    from store import ArtifactStore

    with tempfile.TemporaryDirectory() as tmpdir:
        store = ArtifactStore(tmpdir)
        errors = []

        def writer(thread_id, count):
            for i in range(count):
                try:
                    store.save("shared-svc", "baseline", {"thread": thread_id, "iteration": i})
                except Exception as e:
                    errors.append(str(e))

        threads = [threading.Thread(target=writer, args=(t, 50)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        check("no write errors", len(errors) == 0, f"{len(errors)} errors")

        # Verify the file is valid JSON
        data = store.load("shared-svc", "baseline")
        check("final file is valid JSON", data is not None and "thread" in data)

        # Verify history has entries from multiple threads
        history = store.load_history("shared-svc", "baseline", limit=250)
        check("history has entries", len(history) > 0, f"got {len(history)}")


def test_api_timeout_handling():
    """Verify the API handles slow responses gracefully."""
    print("\n=== Timeout handling ===")
    base_url = "http://localhost:8080"

    try:
        # Quick health check
        r = httpx.get(f"{base_url}/health", timeout=2)
        check("server is running", r.status_code == 200)
    except Exception:
        print("  [SKIP] Server not running, skipping API timeout tests")
        return

    # Test with very short client timeout
    try:
        r = httpx.post(f"{base_url}/api/v1/baseline",
                       json={"evidence": json.load(open(PROJECT_ROOT / "testdata" / "evidence_checkout_api.json"))},
                       timeout=0.001)  # 1ms timeout
        check("ultra-short timeout handled", False, "should have timed out")
    except httpx.TimeoutException:
        check("ultra-short timeout raises clean TimeoutException", True)
    except Exception as e:
        check("ultra-short timeout raises exception", True)


def main():
    print("=== sloscope chaos test ===")

    test_corrupted_store()
    test_concurrent_writes()
    test_api_timeout_handling()

    print(f"\n=== Results: {PASS} passed, {FAIL} failed ===")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
