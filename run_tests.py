"""
Automated Test Runner for Collaborative Whiteboard.
Executes all test cases in the tests/ directory with detailed reporting and metrics.
Compatible with standard Python test execution and pytest.
"""

import importlib
import inspect
import os
import sys
import time
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def run_all_tests():
    print("=" * 70)
    print("  RUNNING AUTOMATED TEST SUITE: COLLABORATIVE WHITEBOARD")
    print("=" * 70)

    test_dir = PROJECT_ROOT / "tests"
    test_files = sorted(test_dir.glob("test_*.py"))

    if not test_files:
        print("[ERROR] No test files found in tests/")
        return 1

    total_passed = 0
    total_failed = 0
    start_all = time.time()

    for tfile in test_files:
        module_name = f"tests.{tfile.stem}"
        print(f"\n[SUITE] {tfile.name}")
        try:
            mod = importlib.import_module(module_name)
        except Exception as e:
            print(f"  [ERROR] Failed to import {module_name}: {e}")
            total_failed += 1
            continue

        test_funcs = [
            (name, func)
            for name, func in inspect.getmembers(mod, inspect.isfunction)
            if name.startswith("test_")
        ]

        for name, func in test_funcs:
            t0 = time.time()
            try:
                func()
                elapsed = (time.time() - t0) * 1000
                print(f"  [PASS] {name} ({elapsed:.1f}ms)")
                total_passed += 1
            except Exception as e:
                elapsed = (time.time() - t0) * 1000
                print(f"  [FAIL] {name} ({elapsed:.1f}ms)")
                print(f"         Error: {type(e).__name__}: {e}")
                total_failed += 1

    total_elapsed = time.time() - start_all
    print("\n" + "=" * 70)
    print("  TEST EXECUTION SUMMARY")
    print("=" * 70)
    print(f"  Total Tests Executed : {total_passed + total_failed}")
    print(f"  Passed               : {total_passed}")
    print(f"  Failed               : {total_failed}")
    print(f"  Total Elapsed Time   : {total_elapsed:.2f}s")
    print("=" * 70)

    if total_failed == 0:
        print("  ALL TESTS PASSED SUCCESSFULLY!\n")
        return 0
    else:
        print("  SOME TESTS FAILED!\n")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
