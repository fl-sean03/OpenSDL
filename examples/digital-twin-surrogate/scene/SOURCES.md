# Scene sources and provenance

The surrogate cell is original procedural geometry. The build script uses Blender primitives,
curves, text, materials, and animation authored for OpenSDL. Published equipment dimensions and
operating behavior set its scale and motion references.

No manufacturer CAD, product photographs, textures, logos, or copied meshes are included. The
scene identifies itself as an OpenSDL Flex-class reference and does not claim to be a manufacturer
model, certified layout, or as-built survey.

Sources were reviewed on 2026-08-03.

## Equipment references

| Source | Scene use |
|---|---|
| [Opentrons Flex system specifications](https://docs.opentrons.com/flex/system-description/specs/) | Deck slot geometry, gantry-served working slots, and machine scale. The reference scene lays those slots out along an open bench line instead of inside the enclosed workstation envelope, so no enclosure, glazing, or hood is reproduced |
| [Flex pipettes](https://docs.opentrons.com/flex/system-description/pipettes/) | 8-channel 5–1000 µL instrument class and eight-tip operation |
| [Flex gripper](https://docs.opentrons.com/flex/system-description/gripper/) | Independent gantry-mounted gripper and parallel-jaw labware handling |
| [Flex Stacker](https://docs.opentrons.com/flex/modules/stacker/) | 385.5 × 106 × 955.5 mm tower-and-track envelope and side-mounted shuttle arrangement |
| [Heater-Shaker product specifications](https://opentrons.com/products/heater-shaker-module) | 152 × 90 × 82 mm module; 200–3000 rpm range; 2 mm orbital pattern; active plate clamping |
| [Heater-Shaker instruction manual](https://docs.opentrons.com/flex/modules/heater-shaker/) | Flex installation, module behavior, and physical specifications |
| [Absorbance plate reader](https://docs.opentrons.com/flex/modules/absorbance-plate-reader/) | 155.3 × 95.5 × 57 mm module, 96 detectors, gripper-moved lid, and column-3 placement |
| [Moving labware with the Python API](https://docs.opentrons.com/python-api/moving-labware/) | Gripper transfers between deck slots, modules, adapters, and staging positions |
| [Plate-reader Python API](https://docs.opentrons.com/python-api/modules/absorbance-plate-reader/) | Required lid close before initialization and gripper lid motion between columns 3 and 4 |
| [Flex Stacker Python API](https://docs.opentrons.com/python-api/modules/flex-stacker/) | Column-4 Stacker loading, shuttle retrieval, and storage from the deck |

## Deck and labware data

OpenSDL pinned the source-data links below to Opentrons commit
[`f03fe656`](https://github.com/Opentrons/opentrons/commit/f03fe6567fac237e3da4f5604604621d953672e3).

| Source | Scene use |
|---|---|
| [Flex deck definition](https://raw.githubusercontent.com/Opentrons/opentrons/f03fe6567fac237e3da4f5604604621d953672e3/shared-data/deck/definitions/5/ot3_standard.json) | 164 mm horizontal slot pitch, 107 mm vertical slot pitch, and 128 × 86 mm slot bounds |
| [NEST 96-well plate definition](https://raw.githubusercontent.com/Opentrons/opentrons/f03fe6567fac237e3da4f5604604621d953672e3/shared-data/labware/definitions/2/nest_96_wellplate_200ul_flat/5.json) | 127.6 × 85.4 × 14.3 mm plate envelope and 8 × 12 well ordering |

The build script records meters in a right-handed, Z-up source frame. Blender exports a Y-up GLB
for runtime delivery. Named anchors preserve the OpenSDL coordinate mapping.

## Format references

- [Blender glTF 2.0 exporter](https://docs.blender.org/manual/en/latest/addons/import_export/scene_gltf2.html)
- [Khronos glTF specification and tools](https://www.khronos.org/gltf/)

## Asset-use decision

The public [Opentrons OT-2 hardware repository](https://github.com/Opentrons/ot2) was reviewed as
research context. OpenSDL did not import its CAD. It describes a different robot generation, and no
license file was visible in the repository at review time. GitHub's
[repository licensing guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)
explains that reuse rights do not follow from public visibility alone.

Manufacturer documentation and images were used as visual and behavioral references only. Product
and company names belong to their respective owners. OpenSDL is not affiliated with or endorsed by
Opentrons.

Future laboratory repositories can use owner-supplied or licensed CAD after they record permission,
confidentiality, units, coordinate registration, and modifications. Those assets stay with that
laboratory and do not enter a framework catalog.
