# SteamZero 2.0.0rc1

- Source: `085169f471866fbb61530c777d368729002b6868` (`main`)
- Release identity: `2.0.0rc1-085169f47186`
- CI run: `33972409839` (all required gates green)
- Wheel SHA-256: `37c5cd666da6c2d28f8da68da0a3825c345686ae63d65843b05afc05ba6e5c37`
- Governed rollback and roll-forward completed; rollback remains available as
  `2.0.0rc1-bf23fd7dd62f`.
- Physical launcher validation completed with keyboard-only input: Steam search,
  real Steam game launch, controlled close, and launcher recovery.
- Read-only post-activation checks: version `2.0.0rc1`, socket/service `active`,
  doctor with zero pending operations and zero stale jobs.
- Known non-blocking doctor warnings remain: one orphan staging tree and direct
  boot inspection unavailable due to permission.

Evidence: `CANONICAL-CERTIFICATION.json`, `CANONICAL-CYCLE.json`,
`CANONICAL-PHYSICAL-VALIDATION.json`, and captures `04` through `07` in this
directory.
