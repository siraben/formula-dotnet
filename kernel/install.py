"""Install the FORMULA Jupyter kernel spec.

Usage:
    python -m kernel.install [--user | --prefix PREFIX]

This registers the FORMULA kernel with Jupyter so it appears
in the kernel selection dropdown.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile

KERNEL_SPEC = {
    "argv": [sys.executable, "-m", "kernel", "-f", "{connection_file}"],
    "display_name": "Formula",
    "language": "formula",
}


def install_kernel_spec(user: bool = True, prefix: str | None = None) -> str:
    """Install the FORMULA kernel spec.

    Returns:
        The path where the kernel spec was installed.
    """
    from jupyter_client.kernelspec import KernelSpecManager

    ksm = KernelSpecManager()

    with tempfile.TemporaryDirectory() as tmpdir:
        kernel_dir = os.path.join(tmpdir, "formula")
        os.makedirs(kernel_dir)

        # Write kernel.json
        with open(os.path.join(kernel_dir, "kernel.json"), "w") as f:
            json.dump(KERNEL_SPEC, f, indent=2)

        # Copy icon if available
        icon_src = os.path.join(os.path.dirname(__file__), "res", "4ml-icon.png")
        if os.path.isfile(icon_src):
            shutil.copy(icon_src, os.path.join(kernel_dir, "logo-64x64.png"))

        return ksm.install_kernel_spec(
            kernel_dir,
            kernel_name="formula",
            user=user,
            prefix=prefix,
        )


def main():
    parser = argparse.ArgumentParser(
        description="Install the FORMULA Jupyter kernel spec."
    )
    parser.add_argument(
        "--user",
        action="store_true",
        default=True,
        help="Install to the per-user kernel spec directory (default).",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default=None,
        help="Install to a specific prefix directory.",
    )
    args = parser.parse_args()

    if args.prefix:
        user = False
    else:
        user = args.user

    dest = install_kernel_spec(user=user, prefix=args.prefix)
    print(f"Installed FORMULA kernel spec to: {dest}")


if __name__ == "__main__":
    main()
