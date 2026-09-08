"""python -m scripts.run_maintenance [--once | --retry JOB_ID | --status]."""
import argparse
import json
import time
from datetime import datetime

from sqlalchemy import select
from app.db import engine, SessionLocal
from app.maintenance import jobs, sweep
from app.notifications import sweep as notification_sweep


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--retry")
    args = parser.parse_args()
    jobs.create(engine, checkfirst=True)
    if args.status or args.retry:
        with SessionLocal() as db:
            if args.retry:
                result = db.execute(jobs.update().where(jobs.c.job_id == args.retry,
                    jobs.c.status == "failed").values(status="pending", attempts=0,
                    due_at=datetime.now(), error_code=None))
                db.commit()
                print(json.dumps({"retried": result.rowcount}))
            else:
                for job in db.execute(select(jobs)).mappings():
                    print(json.dumps(dict(job), default=str))
        return
    while True:
        try:
            print(json.dumps({"maintenance_completed": sweep(SessionLocal)}))
        except Exception:
            print(json.dumps({"error_code": "maintenance_discovery_failed"}))
        try:
            notification_sweep(SessionLocal)
        except Exception:
            print(json.dumps({"error_code": "notification_sweep_failed"}))
        if args.once:
            return
        time.sleep(60)


if __name__ == "__main__":
    main()
