"""Single command-line entry for the Generation_Workflow.

Usage: ``python -m content_pipeline.cli <command> [options]``.

The orchestration itself lives in :mod:`content_pipeline.orchestrator`; the
commands map onto the two jobs of ``.github/workflows/generate-draft.yml``,
which keep the model credential and the repository write token apart.

Commands
--------
``generate``
    Phase 1 (job ``generate``): inputs → Prompt_Store → Compliance_Checklist
    and gateway configuration → budget check → Model_Gateway (≤ 2 calls) →
    draft assembly and Article_Schema validation → stable key → bundle.
    Any failure exits non-zero before a bundle exists, so no Git change can
    follow. Prints redaction-safe audit values (branch, stable key, prompt,
    model, estimated/reserved cost, call count).
``verify-bundle``
    Re-validate a bundle against the workflow inputs and the
    Compliance_Checklist, and report ``branch`` / ``stable_key``.
``apply-draft``
    Phase 2 (job ``draft-branch``): re-validate, then create/update/keep the
    Content_File in a work tree checked out at ``draft/<stable_key>``; report
    ``action`` / ``path`` / ``requires_commit`` and write Pull Request
    creation instructions. The workflow's guarded shell step commits/pushes.

Workflow inputs are read from the environment variables in :data:`INPUT_ENV`
(passed via ``env:`` in the workflow, never interpolated into shell code).
``key=value`` results are appended to ``--github-output`` (normally
``$GITHUB_OUTPUT``); values are limited to hex digits, paths, identifiers and
fixed words. Error messages name fields, files or configuration keys only;
as a last line of defence the gateway credential is masked in all output.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import httpx

from .compliance import DEFAULT_POLICY_PATH, load_policy
from .draft_bundle import load_bundle
from .errors import PipelineError
from .git_change import WorkTreeBackend
from .orchestrator import DEFAULT_PROMPTS_DIR, generate_bundle, publish_review, redact_env_secrets
from .request import REQUEST_FIELDS, GenerationRequest, validate_request

# workflow_dispatch input name -> environment variable carrying it.
INPUT_ENV: dict[str, str] = {
    "topic": "GEN_TOPIC",
    "audience": "GEN_AUDIENCE",
    "keywords": "GEN_KEYWORDS",
    "prompt_name": "GEN_PROMPT_NAME",
    "prompt_version": "GEN_PROMPT_VERSION",
}
assert tuple(INPUT_ENV) == REQUEST_FIELDS

EXIT_OK = 0
EXIT_FAILED = 1


def inputs_from_env(env: Mapping[str, str]) -> dict[str, str | None]:
    return {name: env.get(var) for name, var in INPUT_ENV.items()}


def request_from_env(env: Mapping[str, str]) -> GenerationRequest:
    """Validate the five workflow inputs taken from ``env``."""
    return validate_request(inputs_from_env(env))


def _write_outputs(path: str | None, values: Mapping[str, str], env: Mapping[str, str]) -> None:
    for key, value in values.items():
        if "\n" in value or "\r" in value:  # pragma: no cover - values are constrained
            raise PipelineError(f"output {key} must be a single line")
    lines = redact_env_secrets("".join(f"{key}={value}\n" for key, value in values.items()), env)
    if path:
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(lines)
    sys.stdout.write(lines)


def _cmd_generate(args: argparse.Namespace, env: Mapping[str, str], seams: dict) -> int:
    prepared = generate_bundle(
        inputs_from_env(env),
        env,
        args.bundle_dir,
        policy_path=args.policy,
        prompts_dir=args.prompts_dir,
        **seams,
    )
    _write_outputs(args.github_output, prepared.audit(), env)
    return EXIT_OK


def _cmd_verify_bundle(args: argparse.Namespace, env: Mapping[str, str], seams: dict) -> int:
    draft = load_bundle(args.bundle_dir, request_from_env(env), load_policy(args.policy))
    _write_outputs(args.github_output, {"branch": draft.branch, "stable_key": draft.stable_key}, env)
    return EXIT_OK


def _cmd_apply_draft(args: argparse.Namespace, env: Mapping[str, str], seams: dict) -> int:
    draft = load_bundle(args.bundle_dir, request_from_env(env), load_policy(args.policy))
    review = publish_review(
        draft,
        WorkTreeBackend(args.repo),
        branch=args.branch,
        default_branch=args.default_branch,
        server_url=args.server_url,
        repository=args.repository,
    )
    Path(args.instructions_file).write_text(review.instructions, encoding="utf-8", newline="\n")
    outputs = {
        "action": review.change.action.value,
        "path": review.change.target.path,
        "requires_commit": "true" if review.change.requires_commit else "false",
    }
    if review.pr_url:
        outputs["pr_url"] = review.pr_url
    _write_outputs(args.github_output, outputs, env)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m content_pipeline.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    def common_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--bundle-dir", required=True)
        p.add_argument("--policy", default=str(DEFAULT_POLICY_PATH))
        p.add_argument("--github-output", default=None)

    gen = sub.add_parser("generate", help="generate and validate one draft bundle")
    common_args(gen)
    gen.add_argument("--prompts-dir", default=str(DEFAULT_PROMPTS_DIR))
    gen.set_defaults(handler=_cmd_generate)

    verify = sub.add_parser("verify-bundle", help="re-validate a draft bundle")
    common_args(verify)
    verify.set_defaults(handler=_cmd_verify_bundle)

    apply = sub.add_parser("apply-draft", help="apply a bundle to the draft branch work tree")
    common_args(apply)
    apply.add_argument("--repo", required=True)
    apply.add_argument("--branch", required=True)
    apply.add_argument("--default-branch", required=True)
    apply.add_argument("--server-url", required=True)
    apply.add_argument("--repository", required=True)
    apply.add_argument("--instructions-file", required=True)
    apply.set_defaults(handler=_cmd_apply_draft)
    return parser


def main(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Run one command. ``transport``/``sleep`` are test seams for ``generate``."""
    args = build_parser().parse_args(argv)
    environ = os.environ if env is None else env
    try:
        return args.handler(args, environ, {"transport": transport, "sleep": sleep})
    except PipelineError as exc:
        print(redact_env_secrets(f"error: {exc}", environ), file=sys.stderr)
        return EXIT_FAILED
    except Exception as exc:  # noqa: BLE001 - never print messages/tracebacks that could carry secrets
        print(f"error: unexpected {type(exc).__name__}", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
