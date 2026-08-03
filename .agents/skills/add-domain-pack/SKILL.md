---
name: add-domain-pack
description: Create a namespaced scientific domain pack without changing OpenSDL core execution semantics. Use when adding scientific models, units, standards, or schemas for a domain.
---

# Add a domain pack

## Inputs

- domain-pack name
- destination directory, default `domain-packs`

## Procedure

1. Run `.agents/skills/add-domain-pack/run.sh NAME [DESTINATION]`.
2. Replace the generated generic model with precise scientific models.
3. Document units, external standards, valid ranges, and known ambiguities.
4. Add valid and invalid fixtures plus schema compatibility tests.
5. Register the pack in an example or organization manifest.
6. Run the repository test, schema, and boundary checks.

## Completion

The pack is namespaced, installable, schema-exported, documented, and exercised by an example or
manifest fixture.

## Stop conditions

Stop if the proposed feature changes workflow or runtime lifecycle semantics. Put that behavior in
the domain-neutral platform before referencing it from a domain pack.
