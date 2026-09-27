"""Render the checked-in AWS JSON templates outside the repository."""

import json
import os
from pathlib import Path


DEPLOYMENT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = Path("/tmp/document-qa-deployment")
TEMPLATES = [
    Path("task-definition.template.json"),
    Path("iam/ecs-tasks-trust-policy.json"),
    Path("iam/execution-role-policy.template.json"),
]


def main() -> None:
    values = {
        "AWS_ACCOUNT_ID": os.environ["AWS_ACCOUNT_ID"],
        "AWS_REGION": os.environ.get("AWS_REGION", "us-east-1"),
        "IMAGE_URI": os.environ["IMAGE_URI"],
        "RUNTIME_SECRET_ARN": os.environ["RUNTIME_SECRET_ARN"],
    }

    for relative_path in TEMPLATES:
        source = DEPLOYMENT_DIR / relative_path
        rendered = source.read_text()
        for name, value in values.items():
            rendered = rendered.replace("${" + name + "}", value)

        if "${" in rendered:
            raise ValueError(f"Unfilled template value in {relative_path}")

        parsed = json.loads(rendered)
        destination = OUTPUT_DIR / relative_path.parent / relative_path.name.replace(
            ".template", ""
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(parsed, indent=2) + "\n")
        print(f"Rendered {relative_path} to {destination}")


if __name__ == "__main__":
    main()
