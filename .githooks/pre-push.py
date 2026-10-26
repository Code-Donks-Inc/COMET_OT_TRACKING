
#!/usr/bin/env python3
"""Pre-push safety checks for the OT Vulnerability Intelligence platform."""

import os
import pathlib
import subprocess
import sys

PROTECTED_BRANCH = "refs/heads/main"

BLOCKED_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
}

BLOCKED_SUFFIXES = (
    ".dump",
    ".backup",
    ".pgdump",
    ".tar.gz",
    ".pem",
    ".key",
)

BLOCKED_DIRECTORIES = {
    "backups",
    ".venv",
    "venv",
}

ZERO_SHA = "0" * 40


def git(*args):
    """Run Git and return its output."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def fail(message):
    """Block the push with an explanation."""
    print(f"BLOCKED: {message}", file=sys.stderr)
    sys.exit(1)


def is_blocked(filename):
    """Check whether a filename is prohibited."""
    path = pathlib.PurePosixPath(filename)
    name = path.name.lower()
    parts = {part.lower() for part in path.parts}

    return (
        name in BLOCKED_NAMES
        or name.startswith(".env.")
        or name.endswith(BLOCKED_SUFFIXES)
        or bool(parts & BLOCKED_DIRECTORIES)
    )


def check_push_updates(push_updates):
    """Prevent direct updates to the protected main branch."""
    for local_ref, local_sha, remote_ref, remote_sha in push_updates:
        if remote_ref == PROTECTED_BRANCH:
            fail(
                "Direct pushes to main are prohibited. "
                "Create a feature branch and open a pull request."
            )


def check_commit_history(push_updates):
    """Inspect newly introduced commits for prohibited files."""
    for local_ref, local_sha, remote_ref, remote_sha in push_updates:

        # Branch deletion does not introduce new commits.
        if set(local_sha) == {"0"}:
            continue

        if set(remote_sha) == {"0"}:
            # For a new branch, inspect commits not reachable
            # from any locally known remote-tracking branch.
            revisions = [
                local_sha,
                "--not",
                "--remotes",
            ]
        else:
            revisions = [
                f"{remote_sha}..{local_sha}",
            ]

        commits = git("rev-list", *revisions).splitlines()

        for commit in commits:
            changed_files = git(
                "diff-tree",
                "--root",
                "--no-commit-id",
                "--name-only",
                "-r",
                commit,
            ).splitlines()

            for filename in changed_files:
                if is_blocked(filename):
                    fail(
                        f"Sensitive file found in commit "
                        f"{commit[:12]}: {filename}"
                    )


def check_tracked_files():
    """Inspect currently tracked files for prohibited paths."""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True,
        check=True,
    )

    filenames = [
        name.decode("utf-8", errors="surrogateescape")
        for name in result.stdout.split(b"\0")
        if name
    ]

    for filename in filenames:
        if is_blocked(filename):
            fail(f"Sensitive or generated file is tracked: {filename}")

    return filenames


def check_python_syntax(filenames):
    """Validate Python syntax without creating cache files."""
    for filename in filenames:
        if not filename.endswith(".py"):
            continue

        try:
            source = pathlib.Path(filename).read_bytes()
            compile(source, filename, "exec")
        except (SyntaxError, OSError) as exc:
            fail(f"Python validation failed in {filename}: {exc}")


def main():
    print("Running OT Vulnerability Intelligence pre-push checks...")

    push_updates = []

    for line in sys.stdin:
        parts = line.split()

        if len(parts) != 4:
            fail("Unexpected Git pre-push input.")

        local_ref, local_sha, remote_ref, remote_sha = parts

        push_updates.append(
            (local_ref, local_sha, remote_ref, remote_sha)
        )

    check_push_updates(push_updates)
    check_commit_history(push_updates)

    filenames = check_tracked_files()
    check_python_syntax(filenames)

    print("PASS: Pre-push checks completed.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        fail(f"Git command failed: {exc}")
