AGENTS
======

Purpose
-------
This document explains the specialized "agents" available to contributors and maintainers when using the Copilot CLI (task sub-agents). It describes when to use each agent type, recommended usage patterns, and concise examples for launching and interacting with agents for work in this repository (TheGroundZero/homelab-config-generator).

Available agent types
---------------------
- explore
  - Fast research/exploration agent for parallel, independent investigations.
  - Use for: finding references, exploring multiple unrelated ideas, quick surveys across the codebase.

- task
  - Executes commands and returns concise success/failure output (tests, builds, lints).
  - Use for: running CI-like work, targeted builds or test runs, installing deps.

- general-purpose
  - Full-capability agent in an isolated subprocess for complex multi-step tasks.
  - Use for: refactors, multi-step changes, or when you want a strong reasoning agent to act autonomously.

- code-review
  - Read-only reviewer focused on staged/branch diffs. Reports high-confidence code issues only.
  - Use for: PR reviews, large diffs where automated comment generation is desired.

- research
  - Thorough search agent that can fetch external sources and produce detailed findings with citations.
  - Use for: design research, dependency/security research, cross-repo investigations.

- security-review
  - Specialist read-only agent for explicit security vulnerability audits.
  - Use for: any request that explicitly asks for exploitable vulnerability hunting or security impact analysis.

When to pick which agent
------------------------
- If you need fast parallel lines of inquiry, pick explore.
- If you just need to run tests, build, or lint, pick task.
- If the job needs chaining, stateful context, and careful reasoning, pick general-purpose.
- For PR-focused issue detection, pick code-review.
- For deep external research, pick research.
- For vulnerability-specified investigations, pick security-review (mandatory for security audits).

Usage guidelines and best practices
----------------------------------
- Provide complete context in the agent prompt (repo path, files/PR numbers, exact goals). Agents are stateless; include what they need.
- Prefer background mode for long-running tasks so results arrive as notifications; use sync for quick, blocking requests.
- After launching a background agent, use read_agent to fetch results and write_agent to send follow-up instructions.
- For code edits: let the agent produce a patch or guided edits; always review diffs before commit.
- Do not ask security-review to perform anything other than read-only analysis; it must remain read-only.
- Never include secrets in prompts or checked-in files. Redact credentials before sharing.

Examples (conceptual)
---------------------
- Quick code review (background):
  copilot task --agent-type code-review --name "review-pr-123" --prompt "Review PR #123: focus on correctness of config generation and idempotence" --mode background

- Run tests (task, sync):
  copilot task --agent-type task --name "run-tests" --prompt "Run unit tests under tests/ and report failures" --mode sync

- Start deep research (research, background):
  copilot task --agent-type research --name "netplan-research" --prompt "Collect best practices for generating netplan YAML for multiple interfaces and provide sample templates" --mode background

Operational tips
----------------
- Keep prompts specific. The clearer the scope, the better the agent output.
- Batch independent tasks into parallel agents if you need multiple threads of work.
- If an agent fails repeatedly, stop it and run the investigation locally — do not blindly re-launch.

Maintainers
-----------
- Repo: TheGroundZero/homelab-config-generator
- If unsure which agent to use, ask a maintainer or open an issue describing the goal and urgency.

License & Safety
-----------------
- Agents may access repository files; do not surface secrets or private credentials in prompts.
- Follow the project's code of conduct and security disclosure process when reporting vulnerabilities.

Change history
--------------
- 2026-07-24: Initial AGENTS.md (generated)
