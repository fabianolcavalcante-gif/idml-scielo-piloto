import argparse
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from idml_foundation.database import SessionLocal, session_scope
from idml_foundation.domain.common import canonical_bytes
from idml_foundation.domain.corpus import load_manifest, verify_manifest
from idml_foundation.models import Membership, Organization, User
from idml_foundation.pipeline.service import DeterministicPipeline
from idml_foundation.rbac import Role
from idml_foundation.security import hash_password, normalize_email


def bootstrap(
    organization_slug: str,
    organization_name: str,
    email: str,
    factory: sessionmaker[Session] = SessionLocal,
) -> None:
    password = os.environ.get("IDML_BOOTSTRAP_PASSWORD")
    if not password:
        raise SystemExit("IDML_BOOTSTRAP_PASSWORD is required")
    with session_scope(factory) as db:
        organization = db.scalar(select(Organization).where(Organization.slug == organization_slug))
        if organization is None:
            organization = Organization(slug=organization_slug, name=organization_name)
            db.add(organization)
            db.flush()
        normalized = normalize_email(email)
        user = db.scalar(select(User).where(User.email == normalized))
        if user is None:
            user = User(email=normalized, password_hash=hash_password(password))
            db.add(user)
            db.flush()
        membership = db.scalar(
            select(Membership).where(
                Membership.organization_id == organization.id,
                Membership.user_id == user.id,
            )
        )
        if membership is None:
            db.add(
                Membership(
                    organization_id=organization.id,
                    user_id=user.id,
                    role=Role.ORG_ADMIN.value,
                )
            )
    print("bootstrap completed")


def convert_idml(
    input_path: Path,
    output_path: Path,
    report_path: Path,
    raw_path: Path | None = None,
    canonical_path: Path | None = None,
) -> None:
    result = DeterministicPipeline().run(
        input_path.read_bytes(),
        logical_name=input_path.name,
    )
    for path in (output_path, report_path, raw_path, canonical_path):
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(result.xml)
    report_path.write_bytes(canonical_bytes(result.validation))
    if raw_path is not None:
        raw_path.write_bytes(canonical_bytes(result.raw))
    if canonical_path is not None:
        canonical_path.write_bytes(canonical_bytes(result.canonical))
    print(
        f"pipeline_valid={str(result.validation.valid).lower()} "
        f"issues={len(result.validation.issues)} xml_sha256={result.validation.xml_sha256}"
    )
    if not result.validation.valid:
        raise SystemExit(2)


def main() -> None:
    parser = argparse.ArgumentParser(prog="idml-admin")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("bootstrap")
    command.add_argument("--organization-slug", required=True)
    command.add_argument("--organization-name", required=True)
    command.add_argument("--email", required=True)
    corpus = commands.add_parser("corpus-verify")
    corpus.add_argument("--manifest", type=Path, required=True)
    corpus.add_argument("--root", type=Path, required=True)
    convert = commands.add_parser("pipeline-convert")
    convert.add_argument("--input", type=Path, required=True)
    convert.add_argument("--output", type=Path, required=True)
    convert.add_argument("--report", type=Path, required=True)
    convert.add_argument("--raw", type=Path)
    convert.add_argument("--canonical", type=Path)
    args = parser.parse_args()
    if args.command == "bootstrap":
        bootstrap(args.organization_slug, args.organization_name, args.email)
    elif args.command == "corpus-verify":
        result = verify_manifest(load_manifest(args.manifest), args.root)
        valid_count = sum(item.valid for item in result.artifacts)
        print(
            f"corpus={result.corpus_id} valid={str(result.valid).lower()} "
            f"artifacts={valid_count}/{len(result.artifacts)}"
        )
        if not result.valid:
            raise SystemExit(2)
    elif args.command == "pipeline-convert":
        convert_idml(args.input, args.output, args.report, args.raw, args.canonical)


if __name__ == "__main__":
    main()
