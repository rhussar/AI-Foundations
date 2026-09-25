#!/usr/bin/env python3
import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_PARENT = ROOT.parent


def run_command(step_name: str, command: list[str], cwd: Path):
    print(f"\n=== {step_name} ===")
    print("Running:", " ".join(str(part) for part in command))
    result = subprocess.run(command, cwd=str(cwd), text=True)
    if result.returncode != 0:
        raise RuntimeError(f"'{step_name}' failed with exit code {result.returncode}")


def build_steps(root: Path):
    out_dir = root / "output"
    docs_dir = root / "hw1_spoke_and_wrench" / "pdfs"
    return [
        (
            "Problem 2: read_receipts.py",
            [
                sys.executable,
                str(root / "read_receipts.py"),
                "--docs-dir",
                str(docs_dir),
                "--out-dir",
                str(out_dir),
            ],
        ),
        (
            "Problem 3: read_bank.py",
            [
                sys.executable,
                str(root / "read_bank.py"),
                "--docs-dir",
                str(docs_dir),
                "--out-dir",
                str(out_dir),
            ],
        ),
        (
            "Problem 4: read_card.py",
            [
                sys.executable,
                str(root / "read_card.py"),
                "--docs-dir",
                str(docs_dir),
                "--out-dir",
                str(out_dir),
            ],
        ),
        (
            "Problem 5: reconcile.py",
            [
                sys.executable,
                str(root / "reconcile.py"),
                "--docs-dir",
                str(root / "hw1_spoke_and_wrench"),
                "--json-dir",
                str(out_dir),
                "--out-dir",
                str(out_dir),
            ],
        ),
        (
            "Problem 7: income_statement.py",
            [
                sys.executable,
                str(root / "income_statement.py"),
                "--json-dir",
                str(out_dir),
                "--out-dir",
                str(out_dir),
            ],
        ),
        (
            "Problem 8: report.py",
            [
                sys.executable,
                str(root / "report.py"),
                "--json-dir",
                str(out_dir),
                "--out",
                str(out_dir / "income_statement.html"),
            ],
        ),
    ]


def zip_folder(folder: Path, zip_path: Path):
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in sorted(folder.rglob("*")):
            if item.is_dir():
                continue
            relative = item.relative_to(folder.parent)
            zf.write(item, arcname=str(relative))

    print(f"\nCreated archive: {zip_path}")


def parse_args():
    parser = argparse.ArgumentParser(description="Run the Homework 1 pipeline in order and zip the folder when complete.")
    parser.add_argument("--folder", type=Path, default=ROOT, help="Homework 1 folder to run")
    parser.add_argument("--zip-name", type=str, default="HW 1.zip", help="Name of the zip archive to create in the parent directory")
    return parser.parse_args()


def main():
    args = parse_args()
    folder = args.folder.resolve()
    zip_path = (folder.parent / args.zip_name).resolve()

    if not folder.exists():
        raise FileNotFoundError(f"Folder not found: {folder}")

    for step_name, command in build_steps(folder):
        run_command(step_name, command, folder)

    zip_folder(folder, zip_path)
    print(f"\nCompleted successful run for {folder.name}.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
