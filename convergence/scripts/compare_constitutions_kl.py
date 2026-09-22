#!/usr/bin/env python3
"""CLI: compute the next-token-KL approximation to metric 2 (K(C||C'))
between two constitutions, at a single fixed prompt (no scenario set).

Usage:
    python scripts/compare_constitutions_kl.py C.json C_prime.json
    python scripts/compare_constitutions_kl.py C.json C_prime.json --user-message "What should you do?"

Requires OPENAI_API_KEY (default) or OPENROUTER_API_KEY (with
CONVERGENCE_KL_PROVIDER=openrouter) to be set in the environment. Not
every model/provider supports the logprobs this needs -- see
convergence/prompted_models.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from convergence.constitutions import Constitution
from convergence.metrics.kl import PromptedKLMetric
from convergence.prompted_models import get_default_prompted_model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("constitution_a", type=Path, help="Path to C (JSON)")
    parser.add_argument("constitution_b", type=Path, help="Path to C' (JSON)")
    parser.add_argument(
        "--user-message",
        default=PromptedKLMetric.DEFAULT_USER_MESSAGE,
        help=f"Fixed user message to probe both constitutions with "
        f"(default: {PromptedKLMetric.DEFAULT_USER_MESSAGE!r})",
    )
    parser.add_argument(
        "--top-k", type=int, default=20, help="Number of top logprobs to request (default: 20)"
    )
    args = parser.parse_args()

    c1 = Constitution.from_json_file(args.constitution_a)
    c2 = Constitution.from_json_file(args.constitution_b)

    model = get_default_prompted_model()
    metric = PromptedKLMetric(model, user_message=args.user_message, top_k=args.top_k)

    forward = metric(c1, c2)
    backward = metric(c2, c1)

    print(f"Model: {model.model_id}")
    print(f"user message: {args.user_message!r}")
    print(f"K({c1!r} || {c2!r}) = {forward:.4f}")
    print(f"K({c2!r} || {c1!r}) = {backward:.4f}  (KL is asymmetric -- both directions shown)")
    print(f"symmetrized         = {0.5 * (forward + backward):.4f}")


if __name__ == "__main__":
    main()
