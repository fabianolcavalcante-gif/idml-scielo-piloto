"""Read-only capacity inventory of IDML resources; never emit environment secrets."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def command(*args: str) -> str:
    return subprocess.check_output(args, text=True, timeout=30)  # noqa: S603 - fixed inventory


def main() -> None:
    services = {}
    for name in ("api", "worker", "postgres", "redis", "openclaw-idml"):
        row = json.loads(command("docker", "inspect", f"idml-development-{name}-1"))[0]
        host = row["HostConfig"]
        services[name] = {
            "memory_bytes": host["Memory"],
            "nano_cpus": host["NanoCpus"],
            "pids_limit": host["PidsLimit"],
            "log_policy": host["LogConfig"],
            "health": row["State"].get("Health", {}).get("Status"),
        }
    settings = json.loads(
        command(
            "docker",
            "exec",
            "idml-development-api-1",
            "python",
            "-c",
            "import json; from idml_foundation.settings import Settings; s=Settings(); "
            "keys=('upload_max_bytes','zip_max_entries','zip_max_uncompressed_bytes','zip_max_ratio',"
            "'ai_max_concurrency','ai_max_attempts','ai_max_repair_cycles','ai_max_cost_microusd',"
            "'feature_openclaw','feature_ai_swarm'); "
            "print(json.dumps({k:getattr(s,k) for k in keys}))",
        )
    )
    jobs = json.loads(
        command(
            "docker",
            "exec",
            "idml-development-api-1",
            "python",
            "-c",
            "import json,os; from sqlalchemy import create_engine,text; "
            "engine=create_engine(os.environ['IDML_DATABASE_URL']); c=engine.connect(); "
            "query=text('select state,count(*) from jobs group by state'); "
            "print(json.dumps(dict(c.execute(query).all()))); "
            "c.close(); engine.dispose()",
        )
    )
    backups = Path("/opt/idml-platform/backups")
    storage = {
        "backup_directories": sum(p.is_dir() for p in backups.iterdir()),
        "backup_bytes": int(command("du", "-sb", str(backups)).split()[0]),
    }
    for name in ("artifacts", "postgres", "redis", "openclaw_state"):
        volume = json.loads(command("docker", "volume", "inspect", f"idml_development_{name}"))[0]
        storage[f"{name}_bytes"] = int(command("du", "-sb", volume["Mountpoint"]).split()[0])
    print(
        json.dumps(
            {
                "version": "phase7-v12-resource-inventory-1.0",
                "services": services,
                "settings": settings,
                "jobs_by_state": jobs,
                "storage": storage,
                "read_only_inventory": True,
                "restricted_content_emitted": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
