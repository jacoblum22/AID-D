"""Test tool catalog functionality including preconditions, argument suggestions, and schemas."""

import pytest
import sys
from pathlib import Path

# Dynamically insert the repository root into sys.path for test portability
ROOT = Path(__file__).resolve().parents[1]  # repo root
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backend.router.tool_catalog import TOOL_CATALOG, Tool, AskRollArgs
from backend.router.game_state import (
    GameState,
    PC,
    NPC,
    Zone,
    Scene,
    Utterance,
    Stats,
    HP,
)


@pytest.fixture
def sample_zones():
    """Create sample zones for testing."""
    return {
        "courtyard": Zone(
            id="courtyard",
            name="Courtyard",
            description="A stone courtyard with a guard post.",
            adjacent_zones=["threshold", "main_hall"],
        ),
        "threshold": Zone(
            id="threshold",
            name="Threshold",
            description="The entrance threshold to the manor.",
            adjacent_zones=["courtyard", "main_hall"],
        ),
    }


@pytest.fixture
def sample_entities():
    """Create sample entities for testing."""
    return {
        "pc.elara": PC(
            id="pc.elara",
            name="Elara",
            type="pc",
            current_zone="courtyard",
            stats=Stats(intelligence=16, dexterity=14),
            hp=HP(current=10, max=10),
            visible_actors=["npc.goblin"],
            has_weapon=True,
            inventory=["rope", "lockpicks"],
        ),
        "npc.goblin": NPC(
            id="npc.goblin",
            name="Goblin",
            type="npc",
            current_zone="courtyard",
            stats=Stats(strength=8, dexterity=12),
            hp=HP(current=5, max=5),
            visible_actors=["pc.elara"],
            has_weapon=True,
        ),
    }


@pytest.fixture
def sample_game_state(sample_entities, sample_zones):
    """Create a sample game state for testing."""
    return GameState(
        entities=sample_entities,
        zones=sample_zones,
        scene=Scene(id="forest_clearing"),
        current_actor="pc.elara",
        pending_action=None,
    )


@pytest.fixture
def sample_utterance():
    """Create a sample utterance for testing."""
    return Utterance(text="I want to sneak to the threshold", actor_id="pc.elara")


# List of tools that are fully implemented and should be tested normally
IMPLEMENTED_TOOLS = {"ask_roll"}

# Get list of all tool IDs
ALL_TOOL_IDS = {tool.id for tool in TOOL_CATALOG}

# List of tools that are placeholders and should be skipped
PLACEHOLDER_TOOLS = ALL_TOOL_IDS - IMPLEMENTED_TOOLS


def test_ask_roll_precondition(sample_game_state, sample_utterance):
    """Test ask_roll precondition (fully implemented tool)."""
    ask_roll_tool = next(tool for tool in TOOL_CATALOG if tool.id == "ask_roll")

    # Test with a simple utterance
    result = ask_roll_tool.precond(sample_game_state, sample_utterance)
    assert isinstance(result, bool), "ask_roll precondition should return boolean"


@pytest.mark.parametrize("tool_id", PLACEHOLDER_TOOLS)
def test_placeholder_tool_preconditions(tool_id, sample_game_state, sample_utterance):
    """Test preconditions for placeholder tools (should be skipped)."""
    pytest.skip(f"Tool '{tool_id}' is not yet fully implemented")


def test_ask_roll_argument_suggestions(sample_game_state, sample_utterance):
    """Test ask_roll argument suggestions (fully implemented tool)."""
    ask_roll_tool = next(tool for tool in TOOL_CATALOG if tool.id == "ask_roll")

    if ask_roll_tool.suggest_args:
        suggestions = ask_roll_tool.suggest_args(sample_game_state, sample_utterance)
        assert isinstance(suggestions, dict), "ask_roll suggestions should be a dict"

        # Check for basic structure
        assert "actor" in suggestions, "ask_roll should suggest actor"
        assert "action" in suggestions, "ask_roll should suggest action"

        # Validate suggested values
        assert suggestions["actor"] == "pc.elara", "Should suggest existing PC name"
        assert suggestions["action"] in [
            "sneak",
            "persuade",
            "athletics",
            "shove",
            "custom",
        ], "Should suggest valid action"


@pytest.mark.parametrize("tool_id", PLACEHOLDER_TOOLS)
def test_placeholder_tool_argument_suggestions(
    tool_id, sample_game_state, sample_utterance
):
    """Test argument suggestions for placeholder tools (should be skipped)."""
    pytest.skip(f"Tool '{tool_id}' is not yet fully implemented")


def test_ask_roll_schema():
    """Test ask_roll schema validation (fully implemented tool)."""
    ask_roll_tool = next(tool for tool in TOOL_CATALOG if tool.id == "ask_roll")
    schema = ask_roll_tool.args_schema

    # Check that schema is a class (Pydantic model)
    assert hasattr(
        schema, "__pydantic_core_schema__"
    ), "ask_roll schema should be a Pydantic model"

    # Verify it's the correct class
    assert schema == AskRollArgs, "ask_roll schema should be AskRollArgs"

    # Test valid ask_roll data
    valid_data = {
        "actor": "pc.elara",
        "action": "sneak",
        "target": None,
        "zone_target": "threshold",
        "style": 1,
        "domain": "d6",
        "dc_hint": 15,
    }
    instance = AskRollArgs(**valid_data)
    assert instance.actor == "pc.elara"
    assert instance.action == "sneak"
    assert instance.zone_target == "threshold"
    assert instance.style == 1
    assert instance.domain == "d6"
    assert instance.dc_hint == 15


@pytest.mark.parametrize("tool_id", PLACEHOLDER_TOOLS)
def test_placeholder_tool_schemas(tool_id):
    """Test schemas for placeholder tools (should be skipped)."""
    pytest.skip(f"Tool '{tool_id}' is not yet fully implemented")


def test_all_tools_have_required_attributes():
    """Test that all tools in the catalog have the required structure."""
    required_attrs = ["id", "desc", "precond", "args_schema"]

    for tool in TOOL_CATALOG:
        for attr in required_attrs:
            assert hasattr(tool, attr), f"{tool.id} should have '{attr}' attribute"

        # Check that precond is callable
        assert callable(tool.precond), f"{tool.id} precond should be callable"

        # Check that args_schema is a class
        assert isinstance(
            tool.args_schema, type
        ), f"{tool.id} args_schema should be a class"


def test_tool_catalog_not_empty():
    """Test that the tool catalog is not empty."""
    assert len(TOOL_CATALOG) > 0, "Tool catalog should not be empty"
    assert any(
        tool.id == "ask_roll" for tool in TOOL_CATALOG
    ), "ask_roll should be in the tool catalog"


def test_tool_ids_are_unique():
    """Test that all tool IDs are unique."""
    tool_ids = [tool.id for tool in TOOL_CATALOG]
    assert len(tool_ids) == len(set(tool_ids)), "All tool IDs should be unique"


def test_tool_preconditions_return_boolean(sample_game_state, sample_utterance):
    """Test that all tool preconditions return boolean values."""
    for tool in TOOL_CATALOG:
        if tool.id in IMPLEMENTED_TOOLS:
            result = tool.precond(sample_game_state, sample_utterance)
            assert isinstance(
                result, bool
            ), f"{tool.id} precondition should return boolean"


def test_tool_suggestions_return_dict_when_present(sample_game_state, sample_utterance):
    """Test that all tool argument suggestion functions return dictionaries when present."""
    for tool in TOOL_CATALOG:
        if tool.id in IMPLEMENTED_TOOLS and tool.suggest_args:
            suggestions = tool.suggest_args(sample_game_state, sample_utterance)
            assert isinstance(
                suggestions, dict
            ), f"{tool.id} suggestions should be a dict"


def test_tool_schemas_are_pydantic_models():
    """Test that all tool schemas are Pydantic model classes."""
    for tool in TOOL_CATALOG:
        if tool.id in IMPLEMENTED_TOOLS:
            schema = tool.args_schema
            assert hasattr(
                schema, "__pydantic_core_schema__"
            ), f"{tool.id} schema should be a Pydantic model"


def test_utterance_has_actionable_verb_method():
    """Test that Utterance has the has_actionable_verb method used by preconditions."""
    utterance = Utterance(text="I want to sneak", actor_id="pc.elara")

    # Check if the method exists
    assert hasattr(
        utterance, "has_actionable_verb"
    ), "Utterance should have has_actionable_verb method"

    # Test that it returns a boolean
    result = utterance.has_actionable_verb()
    assert isinstance(result, bool), "has_actionable_verb should return boolean"


def test_attack_args_suggestion_no_current_actor():
    """Test that suggest_attack_args returns empty dict when no current actor exists."""
    from backend.router.tool_catalog import suggest_attack_args

    # Create state with no current_actor
    state_no_actor = GameState(
        entities={}, zones={}, current_actor=None, pending_action=None
    )
    
    utterance = Utterance(text="I attack", actor_id="pc.test")
    
    # Should return empty dict instead of None values that would fail validation
    result = suggest_attack_args(state_no_actor, utterance)
    
    assert isinstance(result, dict), "Should return a dictionary"
    assert result == {}, "Should return empty dict when no current actor"
    
    # Verify this avoids Pydantic validation issues
    from backend.router.tool_catalog import AttackArgs
    
    # Empty dict should not contain None values that would fail validation
    # This tests the fix where we return {} instead of {"actor": None, "target": None, ...}
    if result:  # Only validate if not empty
        try:
            AttackArgs(**result)
        except Exception as e:
            # Should not have validation errors about None values
            assert "none is not an allowed value" not in str(e).lower(), f"Should not have None validation errors: {e}"
