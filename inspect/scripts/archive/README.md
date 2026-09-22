# Archived scripts

Kept so the history is auditable. **Do not run these**, each is superseded, and the
first two would produce misleading results if executed today.

| Script | Why it's dead |
|---|---|
| `first_run.sh` | Written when the project called the Anthropic API directly. It does not set `-M strict_tools=false`, `--max-tokens 32000`, `--timeout 300`, or `--max-retries 3`, the four flags every run now requires (see the README's "Four flags that are not optional"). Superseded by `../run_experiment.sh`. |
| `probe.sh` | Same era, same missing flags. It was a cost-measurement probe; `run_experiment.sh` reports measured cost directly, so there's nothing left for it to do. |
| `run2.sh` | Never executed. A full ~680-run sweep costing roughly $38. It isn't broken, it just answers a question the two completed experiments have already reshaped, so a broad sweep would mostly buy precision on things already known qualitatively. See `docs/GUIDE.md` Part 6. |

The most important difference between these and `run_experiment.sh` is the flag set.
Running `first_run.sh` or `probe.sh` against an OpenAI model fails outright on the tool
schema; against an Anthropic model it silently produces near-zero reasoning while the log
still claims `reasoning_effort: high`.
