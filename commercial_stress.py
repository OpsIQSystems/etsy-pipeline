"""Run the SAME exhaustive 9-scenario buyer stress test (as simulate_buyer.py)
on just the Commercial analyzer, so it meets the identical quality bar."""
import os
import shutil
import tempfile

import simulate_buyer as sb
import creator
from build_commercial import COMMERCIAL

FNAME = creator.safe_filename(COMMERCIAL["suggested_etsy_title"])
XLSX = os.path.join(creator.PRODUCTS_DIR, f"{FNAME}.xlsx")


def main():
    scenarios = sb.ALL_SCENARIOS
    print(f"[*] Stress-testing Commercial analyzer across {len(scenarios)} scenarios\n")
    inputs, formulas = sb.map_cells(XLSX)
    print(f"  sections={len(set(s for s,_ in formulas))}  inputs={len(inputs)}  formulas={len(formulas)}")

    tmp = tempfile.mkdtemp(prefix="comm_stress_")
    profile = os.path.join(tmp, "prof")
    # stage all scenario files
    for sc in scenarios:
        sb.build_scenario_wb(XLSX, inputs, sc, os.path.join(tmp, f"comm__{sc}.xlsx"))

    proc = sb.start_soffice(profile)
    try:
        print("   ", sb.batch_recalc(tmp))
    finally:
        try: proc.terminate()
        except Exception: pass

    value_history = {fc: set() for fc in formulas}
    total_err = 0
    for sc in scenarios:
        path = os.path.join(tmp, f"comm__{sc}.xlsx")
        values, errors, uncomputed = sb.read_formula_values(path, formulas)
        for fc, v in values.items():
            value_history[fc].add(repr(v))
        if errors:
            total_err += len(errors)
            for sheet, coord, ev in errors[:5]:
                print(f"    [{sc}] [ERROR] {sheet}!{coord} -> {ev}")
        if uncomputed and sc in ("baseline", "zeros", "ones", "huge"):
            print(f"    [{sc}] [WARN] {len(uncomputed)} formula(s) returned no value")
    dead = [fc for fc, vals in value_history.items() if len(vals) <= 1]

    shutil.rmtree(tmp, ignore_errors=True)
    print("\n" + "=" * 60)
    print(f"error-cell occurrences: {total_err}")
    print(f"unresponsive formulas (constant across all scenarios): {len(dead)}/{len(formulas)}")
    verdict = "PASS - same standard as the catalog" if total_err == 0 and len(dead) < len(formulas) else "NEEDS REVIEW"
    print(f"RESULT: {verdict}")
    print("=" * 60)


if __name__ == "__main__":
    main()
