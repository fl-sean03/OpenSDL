# OpenSDL

OpenSDL provides a common implementation shape for laboratories that combine physical experiments, robotics, human work, data systems, scientific computing, and closed-loop decision-making.

The framework is executable today in a simulator-only profile. Start with the [quick start](getting-started/quickstart.md), then create an organization-specific repository with the project generator.

## Design goals

- start with one local process and SQLite;
- replace components through explicit interfaces;
- preserve intended and executed state separately;
- treat physical and computational work through one capability model;
- make complete simulation and replay normal development requirements;
- support human, scripted, optimized, and model-driven operation through the same contracts;
- keep organization data and deployment state outside the public framework repository.
