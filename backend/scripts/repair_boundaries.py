"""Run from backend: python -m scripts.repair_boundaries (preview by default)."""
import argparse
import json

from sqlalchemy import select
from app.db import SessionLocal, engine
from app.models import Patient
from app.boundary_repair import apply_patient, repairs, restore_patient
from app.repeated_mentions import repetition_changes, scoped_highlights


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clinic-id")
    parser.add_argument("--patient-id")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--restore")
    parser.add_argument("--mode", choices=["repetition"], default="repetition")
    args = parser.parse_args()
    if args.restore and not args.apply:
        parser.error("--restore requires --apply")
    if args.apply:
        repairs.create(engine, checkfirst=True)
    with SessionLocal() as db:
        if args.restore:
            restored = restore_patient(db, args.restore)
            db.commit()
            print(json.dumps({"repair_id": args.restore, "restored": restored}))
            return
        query = select(Patient).order_by(Patient.patient_id)
        if args.clinic_id:
            query = query.where(Patient.clinic_id == args.clinic_id)
        if args.patient_id:
            query = query.where(Patient.patient_id == args.patient_id)
        ids = [(p.patient_id, p.clinic_id) for p in db.scalars(query)]
    for patient_id, clinic_id in ids:
        with SessionLocal() as db:
            count = len(repetition_changes(db, patient_id, clinic_id, legacy=args.mode == "repetition"))
            semantic_count = 0
            repair_id = apply_patient(db, db.get(Patient, patient_id), mode=args.mode) if args.apply else None
            if args.apply:
                db.commit()
            print(json.dumps({"patient_id": patient_id, "clinic_id": clinic_id,
                              "current_repetition_change_count": count, "semantic_update_count": semantic_count,
                              "repair_id": repair_id}))


if __name__ == "__main__":
    main()
