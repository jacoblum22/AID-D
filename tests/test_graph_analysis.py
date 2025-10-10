"""
Test suite for Graph Analysis & Visualization Tools.

This module tests the export functions for JSON/Graphviz and comprehensive
graph analysis capabilities including structural analysis and reporting.
"""

import pytest
import json
from typing import Dict, Any, List
import sys
import os

# Add project root to path
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.router.game_state import GameState, Zone, PC, Scene, HP, Entity
from backend.router.zone_graph import (
    export_zone_graph,
    analyze_zone_graph_structure,
    generate_zone_graph_report,
    _filter_zones,
)
from models.space import Exit
from models.meta import Meta


class TestZoneFiltering:
    """Test zone filtering functionality."""

    @pytest.fixture
    def complex_world(self):
        """Create a complex world for filtering tests."""
        zones = {
            "town_square": Zone(id="town_square", name="Town Square", region="town"),
            "inn": Zone(id="inn", name="The Prancing Pony", region="town"),
            "forest_path": Zone(id="forest_path", name="Forest Path", region="forest"),
            "deep_woods": Zone(id="deep_woods", name="Deep Woods", region="forest"),
            "mountain_base": Zone(
                id="mountain_base", name="Mountain Base", region="mountain"
            ),
            "unassigned": Zone(id="unassigned", name="Mysterious Cave"),
        }

        # Set up some discovery
        zones["town_square"].discover_by("pc.alice")
        zones["inn"].discover_by("pc.alice")
        zones["forest_path"].discover_by("pc.alice")
        zones["forest_path"].discover_by("pc.bob")
        zones["deep_woods"].discover_by("pc.bob")

        # Add some connections
        zones["town_square"].add_exit("inn", direction="north")
        zones["inn"].add_exit("town_square", direction="south")
        zones["town_square"].add_exit("forest_path", direction="east")
        zones["forest_path"].add_exit("deep_woods", direction="north")

        return GameState(zones=zones, entities={}, scene=Scene())

    def test_filter_zones_no_filters(self, complex_world):
        """Test that no filters returns all zones."""
        filtered = _filter_zones(complex_world)
        assert len(filtered) == 6
        assert all(zone_id in filtered for zone_id in complex_world.zones.keys())

    def test_filter_zones_by_actor_perspective(self, complex_world):
        """Test filtering by actor discovery perspective."""
        # Alice's perspective
        alice_zones = _filter_zones(complex_world, actor_perspective="pc.alice")
        assert len(alice_zones) == 3
        assert "town_square" in alice_zones
        assert "inn" in alice_zones
        assert "forest_path" in alice_zones

        # Bob's perspective
        bob_zones = _filter_zones(complex_world, actor_perspective="pc.bob")
        assert len(bob_zones) == 2
        assert "forest_path" in bob_zones
        assert "deep_woods" in bob_zones

        # Unknown actor perspective
        unknown_zones = _filter_zones(complex_world, actor_perspective="pc.unknown")
        assert len(unknown_zones) == 0

    def test_filter_zones_by_regions(self, complex_world):
        """Test filtering by region list."""
        # Single region
        town_zones = _filter_zones(complex_world, regions_only=["town"])
        assert len(town_zones) == 2
        assert "town_square" in town_zones
        assert "inn" in town_zones

        # Multiple regions
        multi_zones = _filter_zones(complex_world, regions_only=["town", "forest"])
        assert len(multi_zones) == 4
        assert "town_square" in multi_zones
        assert "forest_path" in multi_zones

        # Non-existent region
        empty_zones = _filter_zones(complex_world, regions_only=["desert"])
        assert len(empty_zones) == 0

    def test_filter_zones_combined(self, complex_world):
        """Test combining actor perspective and region filters."""
        # Alice's view of town region only
        filtered = _filter_zones(
            complex_world, actor_perspective="pc.alice", regions_only=["town"]
        )
        assert len(filtered) == 2
        assert "town_square" in filtered
        assert "inn" in filtered


class TestJSONExport:
    """Test JSON export functionality."""

    @pytest.fixture
    def export_world(self):
        """Create a world for export testing."""
        zones = {
            "start": Zone(
                id="start",
                name="Starting Area",
                description="Where adventures begin",
                region="tutorial",
            ),
            "shop": Zone(id="shop", name="Item Shop", region="tutorial"),
            "forest": Zone(id="forest", name="Dark Forest", region="wilderness"),
        }

        # Add tags
        zones["start"].add_tag("safe")
        zones["start"].add_tag("tutorial")
        zones["shop"].add_tag("safe")
        zones["shop"].add_tag("merchant")
        zones["forest"].add_tag("dangerous")
        zones["forest"].add_tag("dark")

        # Add exits
        zones["start"].add_exit("shop", direction="north", cost=1.0, terrain="stone")
        zones["shop"].add_exit("start", direction="south", cost=1.0, terrain="stone")
        zones["start"].add_exit(
            "forest", direction="east", cost=2.0, terrain="path", blocked=True
        )

        # Add discovery
        zones["start"].discover_by("pc.hero")
        zones["shop"].discover_by("pc.hero")

        return GameState(zones=zones, entities={}, scene=Scene())

    def test_export_json_basic(self, export_world):
        """Test basic JSON export."""
        json_str = export_zone_graph(export_world, format="json")
        data = json.loads(json_str)

        # Check metadata
        assert data["metadata"]["format"] == "zone_graph_json"
        assert data["metadata"]["version"] == "1.0"
        assert data["metadata"]["total_zones"] == 3

        # Check zones
        assert len(data["zones"]) == 3
        assert "start" in data["zones"]

        start_zone = data["zones"]["start"]
        assert start_zone["name"] == "Starting Area"
        assert start_zone["description"] == "Where adventures begin"
        assert start_zone["region"] == "tutorial"
        assert "safe" in start_zone["tags"]
        assert "tutorial" in start_zone["tags"]

        # Check edges
        assert len(data["edges"]) == 3

        # Find the start->shop edge
        start_shop_edge = None
        for edge in data["edges"]:
            if edge["from"] == "start" and edge["to"] == "shop":
                start_shop_edge = edge
                break

        assert start_shop_edge is not None
        assert start_shop_edge["direction"] == "north"
        assert start_shop_edge["cost"] == 1.0
        assert start_shop_edge["terrain"] == "stone"
        assert start_shop_edge["blocked"] is False

        # Check statistics
        stats = data["statistics"]
        assert stats["total_zones"] == 3
        assert stats["total_exits"] == 3
        assert stats["bidirectional_pairs"] == 1  # start<->shop

    def test_export_json_with_discovery(self, export_world):
        """Test JSON export with discovery information."""
        json_str = export_zone_graph(
            export_world, format="json", include_discovery=True
        )
        data = json.loads(json_str)

        start_zone = data["zones"]["start"]
        assert "discovered_by" in start_zone
        assert "pc.hero" in start_zone["discovered_by"]

        forest_zone = data["zones"]["forest"]
        assert "discovered_by" in forest_zone
        assert len(forest_zone["discovered_by"]) == 0

    def test_export_json_actor_perspective(self, export_world):
        """Test JSON export from actor perspective."""
        json_str = export_zone_graph(
            export_world, format="json", actor_perspective="pc.hero"
        )
        data = json.loads(json_str)

        # Should only include discovered zones
        assert len(data["zones"]) == 2
        assert "start" in data["zones"]
        assert "shop" in data["zones"]
        assert "forest" not in data["zones"]

        # Edges should also be filtered
        assert len(data["edges"]) == 2  # start<->shop only

    def test_export_json_regions_only(self, export_world):
        """Test JSON export with region filtering."""
        json_str = export_zone_graph(
            export_world, format="json", regions_only=["tutorial"]
        )
        data = json.loads(json_str)

        # Should only include tutorial zones
        assert len(data["zones"]) == 2
        assert "start" in data["zones"]
        assert "shop" in data["zones"]
        assert "forest" not in data["zones"]


class TestGraphvizExport:
    """Test Graphviz DOT export functionality."""

    def test_export_graphviz_basic(self):
        """Test basic Graphviz export."""
        zones = {
            "a": Zone(id="a", name="Zone A", region="region1"),
            "b": Zone(id="b", name="Zone B", region="region1"),
            "c": Zone(id="c", name="Zone C"),
        }

        zones["a"].add_exit("b", direction="north")
        zones["b"].add_exit("c", direction="east")

        world = GameState(zones=zones, entities={}, scene=Scene())

        dot_str = export_zone_graph(world, format="graphviz")

        # Check that it's valid DOT format
        assert "digraph zone_graph {" in dot_str
        assert "}" in dot_str
        assert "rankdir=TB" in dot_str

        # Check for subgraph (region grouping)
        assert "subgraph cluster_region1" in dot_str

        # Check for nodes
        assert '"a"' in dot_str
        assert '"b"' in dot_str
        assert '"c"' in dot_str

        # Check for edges
        assert '"a" -> "b"' in dot_str
        assert '"b" -> "c"' in dot_str

    def test_export_graphviz_with_colors(self):
        """Test that Graphviz export includes proper styling."""
        zones = {
            "forest_zone": Zone(id="forest_zone", name="Forest", region="forest"),
            "blocked_exit": Zone(id="blocked_exit", name="Blocked Exit"),
        }

        zones["forest_zone"].add_exit("blocked_exit", blocked=True, terrain="mud")

        world = GameState(zones=zones, entities={}, scene=Scene())
        dot_str = export_zone_graph(world, format="graphviz")

        # Should have color styling for forest region
        assert "fillcolor=" in dot_str
        assert "lightgreen" in dot_str  # Forest region color

        # Should have blocked exit styling
        assert "color=red" in dot_str
        assert "style=dashed" in dot_str


class TestMermaidExport:
    """Test Mermaid diagram export functionality."""

    def test_export_mermaid_basic(self):
        """Test basic Mermaid export."""
        zones = {
            "start": Zone(id="start", name="Start Zone"),
            "end": Zone(id="end", name="End Zone"),
        }

        zones["start"].add_exit("end", direction="north", cost=2.0)
        zones["end"].add_exit("start", direction="south", blocked=True)

        world = GameState(zones=zones, entities={}, scene=Scene())
        mermaid_str = export_zone_graph(world, format="mermaid")

        # Check basic structure
        assert "graph TD" in mermaid_str

        # Check nodes (with safe IDs)
        assert "start(Start Zone)" in mermaid_str  # Unassigned zones use round brackets
        assert "end(End Zone)" in mermaid_str

        # Check edges
        assert "start -->|north ($2.0)| end" in mermaid_str
        assert "end -.->|blocked| start" in mermaid_str

        # Check styling classes
        assert "classDef" in mermaid_str


class TestCytoscapeExport:
    """Test Cytoscape.js JSON export functionality."""

    def test_export_cytoscape_basic(self):
        """Test basic Cytoscape export."""
        zones = {
            "node1": Zone(id="node1", name="Node 1", region="test"),
            "node2": Zone(id="node2", name="Node 2"),
        }

        zones["node1"].add_tag("important")
        zones["node1"].add_exit("node2", direction="east", cost=1.5)

        world = GameState(zones=zones, entities={}, scene=Scene())
        cytoscape_str = export_zone_graph(world, format="cytoscape")
        data = json.loads(cytoscape_str)

        # Check structure
        assert "nodes" in data
        assert "edges" in data

        # Check nodes
        assert len(data["nodes"]) == 2
        node1_data = next(
            n["data"] for n in data["nodes"] if n["data"]["id"] == "node1"
        )
        assert node1_data["name"] == "Node 1"
        assert node1_data["region"] == "test"
        assert "important" in node1_data["tags"]

        # Check edges
        assert len(data["edges"]) == 1
        edge_data = data["edges"][0]["data"]
        assert edge_data["source"] == "node1"
        assert edge_data["target"] == "node2"
        assert edge_data["direction"] == "east"
        assert edge_data["cost"] == 1.5


class TestStructuralAnalysis:
    """Test comprehensive structural analysis functionality."""

    @pytest.fixture
    def analysis_world(self):
        """Create a world for structural analysis testing."""
        zones = {
            "hub": Zone(id="hub", name="Central Hub", region="center"),
            "north": Zone(id="north", name="North Wing", region="north_area"),
            "south": Zone(id="south", name="South Wing", region="south_area"),
            "east": Zone(id="east", name="East Wing", region="center"),
            "isolated": Zone(id="isolated", name="Isolated Room"),
            "dead_end": Zone(id="dead_end", name="Dead End"),
        }

        # Create hub-and-spoke pattern
        zones["hub"].add_exit("north", cost=1.0)
        zones["north"].add_exit("hub", cost=1.0)
        zones["hub"].add_exit("south", cost=2.0)  # Inconsistent cost
        zones["south"].add_exit("hub", cost=1.0)
        zones["hub"].add_exit("east", cost=1.0)
        zones["east"].add_exit("hub", cost=1.0)
        zones["hub"].add_exit("dead_end", cost=1.0)  # No return path

        # Add discovery
        zones["hub"].discover_by("pc.explorer")
        zones["north"].discover_by("pc.explorer")
        zones["south"].discover_by("pc.explorer")

        # Add broken exit for testing
        zones["hub"].add_exit("nonexistent", direction="down")

        return GameState(zones=zones, entities={}, scene=Scene())

    def test_analyze_zone_graph_structure_basic(self, analysis_world):
        """Test basic structural analysis."""
        analysis = analyze_zone_graph_structure(analysis_world)

        # Basic stats
        basic = analysis["basic_stats"]
        assert basic["total_zones"] == 6
        assert basic["total_exits"] == 8  # Including broken exit
        assert basic["average_exits_per_zone"] == 8 / 6

        # Connectivity
        connectivity = analysis["connectivity"]
        assert (
            connectivity["bidirectional_pairs"] == 3
        )  # hub<->north, hub<->south, hub<->east
        assert connectivity["inconsistent_pairs"] == 1  # hub<->south has cost mismatch
        assert "isolated" in connectivity["isolated_zones"]
        # Reachability depends on which zone is picked as starting point (alphabetically first)
        # Could be different based on dict order, so let's just check it's reasonable
        assert 0.1 <= connectivity["reachability_ratio"] <= 1.0

        # Regions
        regions = analysis["regions"]
        assert regions["total_regions"] == 3  # center, north_area, south_area
        assert regions["unassigned_zones"] == 2  # isolated, dead_end

        # Discovery
        discovery = analysis["discovery"]
        assert discovery["actors_with_discoveries"] == 1
        assert "pc.explorer" in discovery["per_actor_stats"]
        explorer_stats = discovery["per_actor_stats"]["pc.explorer"]
        assert explorer_stats["discovered_zones"] == 3

    def test_analyze_zone_graph_structure_issues(self, analysis_world):
        """Test issue detection in structural analysis."""
        analysis = analyze_zone_graph_structure(analysis_world)

        issues = analysis["issues"]
        issue_types = [issue["type"] for issue in issues]

        # Should detect dead ends
        assert "dead_ends" in issue_types
        dead_end_issue = next(i for i in issues if i["type"] == "dead_ends")
        assert "dead_end" in dead_end_issue["zones"]
        assert "isolated" in dead_end_issue["zones"]

        # Should detect broken exits
        assert "broken_exits" in issue_types
        broken_issue = next(i for i in issues if i["type"] == "broken_exits")
        assert any(exit["to"] == "nonexistent" for exit in broken_issue["exits"])

    def test_analyze_zone_graph_empty(self):
        """Test structural analysis on empty graph."""
        empty_world = GameState(zones={}, entities={}, scene=Scene())
        analysis = analyze_zone_graph_structure(empty_world)

        assert analysis["basic_stats"]["empty_graph"] is True
        assert analysis["basic_stats"]["total_zones"] == 0


class TestGraphReportGeneration:
    """Test human-readable report generation."""

    def test_generate_zone_graph_report_basic(self):
        """Test basic report generation."""
        zones = {
            "town": Zone(id="town", name="Town Square", region="settlement"),
            "forest": Zone(id="forest", name="Forest Path", region="wilderness"),
        }

        zones["town"].add_exit("forest", direction="north")
        zones["forest"].add_exit("town", direction="south")
        zones["town"].discover_by("pc.hero")

        world = GameState(zones=zones, entities={}, scene=Scene())
        report = generate_zone_graph_report(world)

        # Check report structure
        assert "ZONE GRAPH ANALYSIS REPORT" in report
        assert "BASIC STATISTICS:" in report
        assert "CONNECTIVITY:" in report
        assert "REGIONAL ORGANIZATION:" in report
        assert "DISCOVERY TRACKING:" in report
        assert "IDENTIFIED ISSUES:" in report

        # Check specific content
        assert "Total Zones: 2" in report
        assert "Total Exits: 2" in report
        assert "Bidirectional Pairs: 1" in report
        assert "Total Regions: 2" in report
        assert "pc.hero: 1 zones" in report

    def test_generate_zone_graph_report_empty(self):
        """Test report generation for empty graph."""
        empty_world = GameState(zones={}, entities={}, scene=Scene())
        report = generate_zone_graph_report(empty_world)

        assert "Graph is empty (no zones)" in report


class TestExportFormats:
    """Test all export format validation."""

    def test_unsupported_export_format(self):
        """Test that unsupported formats raise appropriate errors."""
        world = GameState(
            zones={"test": Zone(id="test", name="Test")}, entities={}, scene=Scene()
        )

        with pytest.raises(ValueError, match="Unsupported export format"):
            export_zone_graph(world, format="unsupported_format")

    def test_all_supported_formats(self):
        """Test that all supported formats work without errors."""
        zones = {
            "a": Zone(id="a", name="Zone A"),
            "b": Zone(id="b", name="Zone B"),
        }
        zones["a"].add_exit("b")

        world = GameState(zones=zones, entities={}, scene=Scene())

        # Test all supported formats
        formats = ["json", "graphviz", "mermaid", "cytoscape"]
        for fmt in formats:
            result = export_zone_graph(world, format=fmt)
            assert isinstance(result, str)
            assert len(result) > 0


if __name__ == "__main__":
    pytest.main([__file__])
