"""Operate package initialization."""
import sys


def _warn_python_version() -> None:
    """Print a gentle warning when running on untested Python versions."""
    if sys.version_info < (3, 9) or sys.version_info >= (3, 13):
        print(
            "This project is tested with Python 3.11. Please use Python 3.10–3.12, preferably 3.11.",
            file=sys.stderr,
        )


_warn_python_version()
