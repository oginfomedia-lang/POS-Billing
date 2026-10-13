"""
Standalone backup worker — alternative to APScheduler for cron/systemd.

Usage:
    python backup_worker.py backup      # run one pg_dump now
    python backup_worker.py replication # save one replication snapshot
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app

app = create_app()


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "backup"

    with app.app_context():
        if command == "backup":
            from app.extensions import db
            from app.models.user import User
            from app.services import backup_service

            user = db.session.execute(
                db.select(User).filter_by(role="admin").limit(1)
            ).scalar_one_or_none()
            if not user:
                print("ERROR: No admin user found.", file=sys.stderr)
                sys.exit(1)
            run = backup_service.create_backup(user)
            print(f"Backup: {run.filename} — {run.status}")

        elif command == "replication":
            from app.services import replication_service
            snap = replication_service.snapshot_replication()
            print(f"Replication snapshot #{snap.id}: healthy={snap.is_healthy} lag_bytes={snap.lag_bytes}")

        else:
            print(f"Unknown command: {command}. Use 'backup' or 'replication'.", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
