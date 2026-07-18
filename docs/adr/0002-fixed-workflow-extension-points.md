# Skeletons configure workflows only through fixed, plugin-owned extension points

Skeletons need to vary deck behavior (citations on/off + CSL style, mind map, galleries
mode, exam focus, polish-pass subset, and injecting their author-guide.md / diagram-style.md
into agent prompts) — but the workflows must stay canonical so every deck runs the same
tested pipeline with the same quality gates (grounding critic, lint, verified visuals).
We decided skeleton.json may only set the enumerated extension points; control flow, agent
roles, output schemas, retries, and gates are plugin-only. A skeleton cannot ship its own
prompts-as-steps or workflow code.

Rejected: skeleton-supplied extra Enrich agents (each skeleton becomes an untested pipeline;
gates stop being guarantees). When a real skeleton needs a new step, the plugin releases a
new named extension point — generalize by extraction, same discipline as the rest of the
project.

Status: superseded (2026-07-16) — skeletons and extension points were culled with the
agentic-framework pivot (`architecture_proposal.md`, D19); per-deck-type variation now
comes from storytelling skills, per-deck configuration from the deck context.
