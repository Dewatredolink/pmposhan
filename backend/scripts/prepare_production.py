
from __future__ import annotations
import argparse
import json
import os
import sys
from sqlalchemy import MetaData, Table, inspect, select, delete, func, or_, String, cast
from app.db.session import engine

DEMO_MARKERS = (
    "sample", "demo", "test school", "sample-udise", "sample001", "नमुना"
)

def _lower_expr(col):
    return func.lower(cast(col, String))

def _marker_clause(table, columns):
    clauses = []
    for name in columns:
        if name not in table.c:
            continue
        col = table.c[name]
        for marker in DEMO_MARKERS:
            clauses.append(_lower_expr(col).like(f"%{marker.lower()}%"))
    return or_(*clauses) if clauses else None

def main():
    p = argparse.ArgumentParser(description="PM POSHAN production cleanup scanner")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--confirm", action="store_true")
    args = p.parse_args()

    md = MetaData()
    md.reflect(bind=engine)
    tables = md.tables

    if "schools" not in tables:
        print(json.dumps({
            "ok": False,
            "error": "schools table not found",
            "tables_seen": sorted(tables.keys())
        }, indent=2, ensure_ascii=False))
        sys.exit(2)

    schools = tables["schools"]
    school_clause = _marker_clause(
        schools,
        ["code", "udise_code", "name_en", "name_mr", "village"]
    )

    with engine.begin() as conn:
        sample_rows = []
        if school_clause is not None:
            sample_rows = [dict(r._mapping) for r in conn.execute(select(schools).where(school_clause)).all()]

        sample_ids = [r["id"] for r in sample_rows if "id" in r]
        dependent_counts = {}

        if sample_ids:
            for tname, tbl in tables.items():
                if "school_id" in tbl.c:
                    n = conn.execute(
                        select(func.count()).select_from(tbl).where(tbl.c.school_id.in_(sample_ids))
                    ).scalar_one()
                    if n:
                        dependent_counts[tname] = int(n)

        report = {
            "mode": "DRY_RUN" if args.dry_run else "CONFIRM",
            "demo_school_candidates": [
                {
                    k: r.get(k) for k in
                    ["id","code","udise_code","name_en","name_mr","village","cluster_id"]
                    if k in r
                } for r in sample_rows
            ],
            "demo_school_count": len(sample_rows),
            "dependent_rows_by_table": dependent_counts,
            "notes": [
                "Only records linked to clearly demo/sample schools are considered.",
                "No real school is selected merely because it has 2026-27 data.",
                "Keycloak demo users are NOT deleted by this database script.",
                "Recipe masters are NOT deleted by this script."
            ]
        }

        if args.dry_run:
            print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
            return

        # Destructive mode is intentionally gated.
        if os.getenv("ALLOW_PRODUCTION_CLEANUP") != "YES":
            report["ok"] = False
            report["error"] = (
                "CONFIRM BLOCKED. Set ALLOW_PRODUCTION_CLEANUP=YES only after reviewing "
                "the --dry-run output and taking a PostgreSQL backup."
            )
            print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
            sys.exit(3)

        if not sample_ids:
            report["ok"] = True
            report["deleted"] = {}
            report["message"] = "No demo/sample school candidates found. Nothing deleted."
            print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
            return

        deleted = {}
        # Delete child tables first. Do not touch hierarchy masters or recipe masters here.
        for tname, tbl in tables.items():
            if tname == "schools":
                continue
            if "school_id" in tbl.c:
                result = conn.execute(delete(tbl).where(tbl.c.school_id.in_(sample_ids)))
                if result.rowcount:
                    deleted[tname] = int(result.rowcount)

        result = conn.execute(delete(schools).where(schools.c.id.in_(sample_ids)))
        deleted["schools"] = int(result.rowcount or 0)

        report["ok"] = True
        report["deleted"] = deleted
        report["message"] = (
            "Demo/sample school-linked database rows removed. "
            "Keycloak users and seed configuration still require separate cleanup."
        )
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))

if __name__ == "__main__":
    main()
