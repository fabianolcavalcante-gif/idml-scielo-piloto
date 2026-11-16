"""Operational helpers for the explicitly authorized 7C-08 IDML-only deployment."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path("/opt/idml-platform")
STAGE = ROOT / "releases/phase7-7c08-v1"


def run(*args: str) -> str:
    return subprocess.check_output(args, text=True)  # noqa: S603 - fixed operational commands


def snapshot() -> dict:
    ids = run("docker", "ps", "-q").split()
    rows = json.loads(run("docker", "inspect", *ids))
    result = {}
    for row in rows:
        name = row["Name"].lstrip("/")
        result[name] = {
            "id": row["Id"],
            "image": row["Config"]["Image"],
            "image_id": row["Image"],
            "started": row["State"]["StartedAt"],
            "restarts": row["RestartCount"],
            "health": row["State"].get("Health", {}).get("Status", "running"),
        }
        if name.startswith("idml-development-") and name.endswith(
            ("api-1", "worker-1", "openclaw-idml-1")
        ):
            environment = dict(
                value.split("=", 1) for value in row["Config"]["Env"] if "=" in value
            )
            result[name]["flags_disabled"] = all(
                environment.get(key, "false") == "false"
                for key in ("IDML_FEATURE_OPENCLAW", "IDML_FEATURE_AI_SWARM")
            )
            result[name]["provider_credential_present"] = any(
                environment.get(key) for key in ("OPENAI_API_KEY", "IDML_OPENAI_API_KEY")
            )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["before", "after", "set-tag"])
    args = parser.parse_args()
    if args.action == "set-tag":
        path = ROOT / ".env"
        lines = path.read_text().splitlines()
        lines = [line for line in lines if not line.startswith("IDML_IMAGE_TAG=")]
        path.write_text("\n".join([*lines, "IDML_IMAGE_TAG=phase7-7c08-v1", ""]))
        path.chmod(0o600)
        return
    current = snapshot()
    if args.action == "before":
        (STAGE / "before.json").write_text(json.dumps(current, indent=2))
        print("baseline recorded without credentials")
        return
    before = json.loads((STAGE / "before.json").read_text())
    changed = {"idml-development-api-1", "idml-development-worker-1"}
    unaffected = {
        name: value == current.get(name) for name, value in before.items() if name not in changed
    }
    dedicated = {name: row for name, row in current.items() if name.startswith("idml-development-")}
    assert all(unaffected.values()), "unrelated service changed"
    assert len(dedicated) == 5 and all(row["health"] == "healthy" for row in dedicated.values())
    assert all(
        not row.get("provider_credential_present") and row.get("flags_disabled", True)
        for row in dedicated.values()
    )
    assert all(current[name]["image"] == "idml-foundation:phase7-7c08-v1" for name in changed)
    counts = json.loads(
        run(
            "docker",
            "exec",
            "idml-development-api-1",
            "python",
            "-c",
            "import json,os; from sqlalchemy import create_engine,text; "
            "engine=create_engine(os.environ['IDML_DATABASE_URL']); "
            "connection=engine.connect(); "
            "print(json.dumps({table:connection.scalar(text('select count(*) from '+table)) "
            "for table in ('agent_runs','agent_proposals')})); "
            "connection.close(); engine.dispose()",
        )
    )
    sessions = int(
        run(
            "docker",
            "exec",
            "idml-development-openclaw-idml-1",
            "node",
            "-e",
            "const fs=require('fs'); "
            "const p='/home/node/.openclaw/agents/idml-evaluator/sessions/sessions.json'; "
            "console.log(fs.existsSync(p)?Object.keys(JSON.parse(fs.readFileSync(p,'utf8'))).length:0)",
        )
    )
    networks = set(run("docker", "network", "ls", "--format", "{{.Name}}").split())
    transient = networks & {
        "idml_development_openclaw_provider",
        "idml_development_openclaw_egress",
    }
    assert counts == {"agent_runs": 0, "agent_proposals": 0} and sessions == 0
    assert not transient
    runtime_roots = (
        "src",
        "config",
        "profiles",
        "schemas",
        "prompts",
        "openclaw",
        "vendor",
        "migrations",
    )
    expected = {
        path.relative_to(STAGE).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for name in runtime_roots
        for path in (STAGE / name).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    runtime_hashes = json.loads(
        run(
            "docker",
            "exec",
            "idml-development-api-1",
            "python",
            "-c",
            "import hashlib,json; from pathlib import Path; root=Path('/app'); "
            f"names={runtime_roots!r}; "
            "print(json.dumps({p.relative_to(root).as_posix():"
            "hashlib.sha256(p.read_bytes()).hexdigest() "
            "for n in names for p in (root/n).rglob('*') "
            "if p.is_file() and '__pycache__' not in p.parts}))",
        )
    )
    assert expected == runtime_hashes, "runtime differs from qualified source"
    report = {
        "stage": "7C-08",
        "unaffected_services": len(unaffected),
        "all_unaffected_services_unchanged": True,
        "services": dedicated,
        "agent_persistence": counts,
        "openclaw_sessions": sessions,
        "transient_provider_networks": len(transient),
        "runtime_source_files_verified": len(expected),
        "restricted_content_emitted": False,
        "release_ready": False,
    }
    (STAGE / "postcheck.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
