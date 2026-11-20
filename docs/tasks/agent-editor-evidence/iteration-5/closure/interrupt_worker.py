"""Run a disposable QA worker and interrupt its first verified upload in one project."""
import argparse
import json
import os
import signal
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app import worker
from app.config import settings
from app.models.database import AsyncSessionLocal
from app.models.tables import Output, Project
from app.pipeline import rendering


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=UUID)
    parser.add_argument("boundary", type=Path)
    args = parser.parse_args()
    database = make_url(settings.database_url)
    if not (database.host in ("localhost", "127.0.0.1") and database.database.startswith("rep_closure_")
            and settings.s3_bucket_name.startswith("closure-") and not args.boundary.exists()):
        parser.error("Use an isolated local rep_closure_ database, closure- bucket and new boundary file.")

    original_probe = rendering._probe_artifacts

    async def interrupt_verified_upload(spec, key):
        violations, digest = await original_probe(spec, key)
        if not violations:
            async with AsyncSessionLocal() as db:
                project = await db.get(Project, args.project)
                if project and key.startswith(f"{project.user_id}/outputs/projects/{project.id}/"):
                    result = await db.scalars(select(Output).where(Output.project_id == project.id))
                    output = next((row for row in result if key.rsplit("/", 1)[1].startswith(f"{row.id}-")), None)
                    if output:
                        with args.boundary.open("x") as proof:
                            json.dump({"output": str(output.id), "version": str(output.composition_version_id),
                                       "status": str(output.render_status), "file": key, "sha256": digest,
                                       "violations": violations, "signal": "SIGKILL"}, proof)
                        os.kill(os.getpid(), signal.SIGKILL)
        return violations, digest

    rendering._probe_artifacts = interrupt_verified_upload
    worker.main()


if __name__ == "__main__":
    main()
