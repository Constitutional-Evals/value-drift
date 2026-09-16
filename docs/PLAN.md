# Implementation and execution plan

Spec: ../instruction.md. User authorizes independent implementation and paid compute within a cumulative $200 ceiling.

Architecture: a small Python package orchestrates file-backed reviews, fixed prompt data, sequential generation, full-parameter DPO, post-DPO introspection and full-parameter SFT. Durable run directories contain stage completion records and restartable artifacts. Only the lead controls paid infrastructure.

- [ ] Preparation: constitution/environment agent, model/training agent, data/measurement agent; inspect original OCT and official model.
- [ ] Integrate editing, generation, training and measurements; focused tests cover convergence, weight continuity, common DPO context, prompt isolation and budget guards.
- [ ] Independent implementation review; correct important findings before main trajectory.
- [ ] Provision one H200, smoke real CUDA inference and both full-parameter stages; record parameter counts, memory, throughput and cost.
- [ ] Freeze measured affordable recipe and prompt bank; full-information trajectory with baseline evaluation, explicit tools and at most five complete training rounds.
- [ ] Analyze every terminal result and failed attempt; seek independent feedback; implement highest-value justified improvement without reopening converged trajectories.
- [ ] Save useful checkpoints/data locally, terminate resources, reconcile spending and deliver evidence-backed report.

No manual constitutional revisions after C0. No adapter substitution. No altered protocol mid-trajectory. No previous review transcript enters subsequent reviews. Unchanged explicit finish is valid and terminal; malformed/truncated output is failure.
