import argparse
import subprocess


def build_pytest_k(test_id: str | None, case_id: str | None) -> str | None:
    test_id = (test_id or "").strip()
    case_id = (case_id or "").strip()
    if test_id and case_id:
        return f"{test_id} and {case_id}"
    if test_id:
        return test_id
    if case_id:
        return case_id
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run georef evaluation pytest inside the Docker test container. "
            "This is a cross-platform wrapper around: docker compose run --rm test-backend pytest tests/test_georef_cases.py -v"
        )
    )
    parser.add_argument(
        "--test-id", default="", help="Filter by test id (used to build pytest -k)"
    )
    parser.add_argument(
        "--case-id", default="", help="Filter by case id (used to build pytest -k)"
    )
    parser.add_argument(
        "-k",
        dest="kexpr",
        default="",
        help="Raw pytest -k expression (overrides --test-id/--case-id)",
    )

    args = parser.parse_args()

    docker_cmd = [
        "docker",
        "compose",
        "run",
        "--rm",
        "test-backend",
        "pytest",
        "tests/test_georef_cases.py",
        "-v",
    ]

    kexpr = (args.kexpr or "").strip() or build_pytest_k(args.test_id, args.case_id)
    if kexpr:
        docker_cmd += ["-k", kexpr]

    print("Running:")
    print(" ".join(docker_cmd))

    completed = subprocess.run(docker_cmd)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
