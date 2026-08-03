# CLI and generator instructions

- Keep command behavior in typed implementation code. Skills and templates must reference commands
  that exist.
- A generated laboratory must include concise agent instructions, validated local skills, and thin
  Claude Code compatibility files.
- Keep generated repositories simulator-first. Do not claim pinned dependencies or a generated
  lockfile unless the generator creates them.
- Add a cold-render test for every scaffold file or generator invariant.
- Test generated workflows through the same public CLI and runtime paths that users receive.
