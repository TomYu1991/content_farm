"""Draft generator for the content-pipeline-skeleton static blog.

Generated articles are always drafts that require human review in a Pull
Request before publishing. No database, queue or dynamic runtime is used.
"""

import sys

MIN_PYTHON = (3, 11)

if sys.version_info < MIN_PYTHON:  # pragma: no cover - guarded by requires-python
    raise RuntimeError("content_pipeline requires Python 3.11 or newer")

__version__ = "0.1.0"
