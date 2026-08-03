# opensdl-twin

Engine-neutral contracts for binding a laboratory's semantic resources and durable runtime events
to a versioned visual scene. This package contains no geometry, renderer, equipment catalog, or
execution path.

The v0alpha1 definition pins a GLB digest and names its entities, anchors, projection rules, and
optional authored-animation timeline. The loader confines the scene path to the definition
directory and recalculates its SHA-256 digest on each scene read.

Run projection requires the controller's recorded twin revision, canonical definition digest, and
scene digest to match the current binding. Historical definition and scene snapshots are not yet
retained, so replay across twin revisions remains future work.
