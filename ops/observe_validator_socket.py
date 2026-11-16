"""Two sequential synthetic smoke requests; no production service changes or private corpus."""

import json
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from validator_broker import command, reserve

STAGE = Path(__file__).resolve().parent
IMAGE = "sha256:4fcf47666812a6b45dbafe5baecc44dcdb6393ac7b4893568b44e1683cf2ed86"


def snapshot():
    ids = command("docker", "ps", "-q").split()
    return {
        r["Id"]: (r["State"]["StartedAt"], r["RestartCount"])
        for r in json.loads(command("docker", "inspect", *ids))
    }


def main():
    case = sys.argv[1] if len(sys.argv) > 1 else "incomplete"
    if case not in {"incomplete", "complete", "real"}:
        raise ValueError("invalid synthetic case")
    baseline = snapshot()
    rows = []
    for name in ("packtools", "spsvalidator"):
        reserve(STAGE, starting=True)
        client_name = "idml-validator-smoke-" + uuid4().hex
        broker = subprocess.Popen(  # noqa: S603 - fixed qualification command
            [  # noqa: S607
                "python3",
                str(STAGE / "validator_broker.py"),
                "--socket",
                str(STAGE / "broker.sock"),
                "--work",
                str(STAGE / "work"),
                "--registry",
                str(STAGE / "validator-registry-v1.json"),
                "--once",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(30):
                if (STAGE / "broker.sock").exists():
                    break
                if broker.poll() is not None:
                    raise RuntimeError("broker_start_failed")
                time.sleep(0.1)
            client = subprocess.run(  # noqa: S603 - fixed isolated synthetic client
                [  # noqa: S607
                    "docker",
                    "run",
                    "--rm",
                    "--name",
                    client_name,
                    "--network=none",
                    "--read-only",
                    "--user=10001:10001",
                    "--memory=128m",
                    "--memory-swap=128m",
                    "--cpus=0.15",
                    "--pids-limit=32",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--log-driver=none",
                    "-v",
                    f"{STAGE}:/qualification:ro",
                    IMAGE,
                    "python",
                    "/qualification/smoke_validator_socket.py",
                    name,
                    case,
                ],
                capture_output=True,
                timeout=660,
            )
            output = json.loads(client.stdout)
            output["client_exit_code"] = client.returncode
            rows.append(output)
            broker.wait(timeout=10)
        finally:
            subprocess.run(  # noqa: S603 - exact unique client from this run only
                ["docker", "rm", "-f", client_name],  # noqa: S607
                capture_output=True,
                timeout=15,
                check=False,
            )
            if broker.poll() is None:
                broker.terminate()
                broker.wait(timeout=10)
            broker.stdout.close()
    result = {
        "version": "h1-validator-socket-smoke-1.1",
        "case": case,
        "executions_completed": all(row.get("status") == "completed" for row in rows),
        "cases": rows,
        "existing_services_unchanged": baseline == snapshot(),
        "socket_removed": not (STAGE / "broker.sock").exists(),
        "scratch_empty": not any((STAGE / "work").iterdir()),
        "private_corpus_used": case == "real",
        "production_activated": False,
    }
    print(json.dumps(result))
    raise SystemExit(
        0
        if all(row.get("transport_completed") and row["client_exit_code"] == 0 for row in rows)
        and (case == "incomplete" or result["executions_completed"])
        and result["existing_services_unchanged"]
        and result["socket_removed"]
        and result["scratch_empty"]
        else 1
    )


if __name__ == "__main__":
    main()
