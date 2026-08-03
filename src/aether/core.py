from pathlib import Path
import runpy


def main():
    archive_entrypoint = Path(__file__).resolve().parents[2] / "archive" / "versions" / "aether.0.20.0.py"
    runpy.run_path(str(archive_entrypoint), run_name="__main__")


if __name__ == "__main__":
    main()
