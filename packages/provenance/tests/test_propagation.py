from opensdl_provenance import PropagationDefinition, PropagationEdge, PropagationGraph, PropagationNode


def test_transitive_impact() -> None:
    graph = PropagationGraph(PropagationDefinition(nodes=[
        PropagationNode(id="schema", paths=["packages/core/**"]),
        PropagationNode(id="adapter", paths=["adapters/**"]),
        PropagationNode(id="docs", paths=["docs/**"]),
    ], edges=[
        PropagationEdge(source="schema", target="adapter", reason="adapters implement contracts"),
        PropagationEdge(source="adapter", target="docs", reason="integration docs describe adapters"),
    ]))
    impact = graph.affected(["packages/core/src/opensdl_core/models.py"])
    assert impact.affected_nodes == ["adapter", "docs", "schema"]


def test_repository_graph_covers_domain_pack_changes() -> None:
    from pathlib import Path

    root = Path(__file__).parents[3]
    graph = PropagationGraph.from_file(root / "propagation.yaml")
    impact = graph.affected([
        "domain-packs/materials/src/opensdl_domain_materials/models.py"
    ])
    assert {"domain-packs", "examples", "documentation"} <= set(
        impact.affected_nodes
    )
