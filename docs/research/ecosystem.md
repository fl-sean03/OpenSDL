# Ecosystem and prior art

OpenSDL should compose existing scientific infrastructure rather than recreate it.

## Closest laboratory frameworks

- **MADSci** provides modular nodes, workflows, experiments, resources, events, data, locations, CLI tooling, and observability. It is the strongest first production-orchestration integration target.
- **ARES OS**, **HELAO**, **AlabOS**, **ChemOS**, **IvoryOS**, **NIMO**, and related projects provide orchestration, user interfaces, closed-loop optimization, or domain-specific automation patterns.
- **EOS** and newer commercial platforms validate demand for complete self-driving-laboratory products, but OpenSDL remains runtime-neutral and repository-oriented.

## Lower-layer standards and tools

- **SiLA 2**, **OPC UA**, **EPICS**, **ROS 2**, **SCPI/VISA**, **Bluesky/Ophyd**, and **PyLabRobot** are integration targets.
- **AiiDA**, **atomate2/jobflow**, **pyiron**, **Parsl**, Slurm, containers, and cloud batch systems are compute targets.
- **W3C PROV-O** and **RO-Crate** inform provenance and portable research packages.
- **MCP** is an optional operator transport, not the internal architecture.

## OpenSDL’s specific role

The project concentrates on the portable layer spanning laboratory manifests, capability contracts, runtime-independent extensions, repository generation, physical and computational work, durable evidence, conformance, and implementation propagation.

Public projects should be evaluated continuously. Generic improvements should be contributed upstream where they belong rather than copied into OpenSDL.
