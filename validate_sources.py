"""
Validate every company-board slug in config.yaml.

Hits each Greenhouse / Lever / Ashby endpoint and reports which slugs return
JSON and which 404 (dead/renamed), so you can fix or drop them. The live scraper
already skips dead slugs automatically; this just gives you a clean summary.

Run:  python validate_sources.py
"""
from scraper.sources.company_boards import validate


def main() -> None:
    rows = validate()
    if not rows:
        print("No companies configured in config.yaml.")
        return

    ok = [r for r in rows if r["status"] == "OK"]
    dead = [r for r in rows if r["status"] != "OK"]

    print(f"\nValidated {len(rows)} board slugs — {len(ok)} OK, {len(dead)} need attention\n")
    print(f"  {'ATS':<11}{'SLUG':<16}{'STATUS':<22}{'JOBS':>6}{'BD':>5}")
    print("  " + "-" * 58)
    for r in rows:
        print(f"  {r['ats']:<11}{r['slug']:<16}{r['status']:<22}{r['jobs']:>6}{r['relevant']:>5}")

    if dead:
        print("\nFix or remove these slugs in config.yaml:")
        for r in dead:
            print(f"  - {r['ats']}: {r['slug']}  ({r['status']})")


if __name__ == "__main__":
    main()
