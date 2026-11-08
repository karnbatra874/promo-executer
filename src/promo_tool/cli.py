from __future__ import annotations
import argparse
import csv
from .config import ROOT, load_settings
from .pipeline import run
from .timemap import fit_calibration


def main() -> None:
    ap = argparse.ArgumentParser(prog="promo-tool")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="extract, QC and rank promos from a script")
    r.add_argument("script", help="script file or directory of episode files")
    r.add_argument("--out", default=str(ROOT / "data" / "output"))
    r.add_argument("--settings")
    r.add_argument("--dry-run", action="store_true", help="parse + time-map only, no API calls")
    r.add_argument("--max-chunks", type=int, help="limit chunks (cheap test runs)")

    c = sub.add_parser("calibrate", help="fit pacing calibration_factor from real footage durations")
    c.add_argument("--csv", default=str(ROOT / "data" / "calibration" / "actual_durations.csv"))
    c.add_argument("--settings")

    args = ap.parse_args()
    settings = load_settings(args.settings)

    if args.cmd == "run":
        llm = None
        if not args.dry_run:
            from .llm import LLM
            llm = LLM(settings["model"], settings["max_tokens"])
        run(args.script, args.out, settings, llm=llm, max_chunks=args.max_chunks)
    else:
        with open(args.csv, newline="", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if not r["promo_id"].startswith("EXAMPLE")]
        if not rows:
            print("No real rows yet. Replace the EXAMPLE row in the CSV with measured promos.")
            return
        print(f"calibration_factor: {fit_calibration(rows, settings['timing']):.3f}  "
              "(paste into config/settings.yaml -> timing.calibration_factor)")


if __name__ == "__main__":
    main()
