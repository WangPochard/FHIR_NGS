import argparse
import subprocess
import sys


def parse_args():
    parser = argparse.ArgumentParser(description="FHIR NGS Converter")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", "-p", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", default=False)
    return parser.parse_args()


def main():
    args = parse_args()
    cmd = [
        sys.executable, "-m", "uvicorn",
        "app.main:app",
        "--host", args.host,
        "--port", str(args.port),
    ]
    if args.reload:
        cmd.append("--reload")
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
