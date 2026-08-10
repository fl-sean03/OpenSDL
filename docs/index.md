# OpenSDL

OpenSDL provides a common implementation shape for laboratories that combine physical experiments, robotics, human work, data systems, scientific computing, and closed-loop decision-making.

The framework is executable today in a simulator-only profile. Start with the [quick start](getting-started/quickstart.md), then create an organization-specific repository with the project generator.

These pages are built from `main` in
[fl-sean03/OpenSDL](https://github.com/fl-sean03/OpenSDL) on every push. They describe an alpha as it
currently stands rather than a released version, and no contract here is stable between releases —
[compatibility and versioning](reference/compatibility.md) says which surfaces are public and what
each guarantees today. Every command assumes a checkout of that repository.

## Design goals

- start with one local process and SQLite;
- replace components through explicit interfaces;
- preserve intended and executed state separately;
- treat physical and computational work through one capability model;
- make complete simulation and replay normal development requirements;
- support human, scripted, optimized, and model-driven operation through the same contracts;
- keep organization data and deployment state outside the public framework repository.
