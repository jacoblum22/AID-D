"""
Staged Planner - Clean 3-Stage LLM Architecture for Action Planning

This module implements a cleaner separation of concerns for LLM-based planning:

Stage 0: Context Preloader - Extract minimal world state
Stage 1: Intent Parser - Map utterances to tool names (no world context)  
Stage 2: Argument Filler - Fill tool arguments using constrained valid values
Stage 3: Executor - Deterministic tool execution (handled by router)

Benefits:
- Clean separation of concerns
- Better debuggability  
- Prevents hallucinated arguments
- Scalable as tools/world grows
- Faster inference with smaller prompts
"""

import json
import logging
from typing import Dict, Any, List, Optional, get_origin, get_args
from dataclasses import dataclass
from openai import OpenAI
import inspect
from pydantic import BaseModel
from pydantic.fields import FieldInfo

from .game_state import GameState, Utterance
from .tool_catalog import TOOL_CATALOG

logger = logging.getLogger(__name__)


class SchemaIntrospector:
    """Utility for extracting constraints from Pydantic tool schemas."""
    
    @staticmethod
    def extract_field_constraints(field_info, field_name: str) -> Dict[str, Any]:
        """Extract constraint information from a Pydantic FieldInfo."""
        constraints = {}
        
        # Get the annotation (field type)
        field_type = field_info.annotation
        
        # Handle Literal types
        origin = get_origin(field_type)
        args = get_args(field_type)
        
        # Check for Literal types
        if origin is not None and 'Literal' in str(origin):
            constraints["type"] = "literal"
            constraints["choices"] = list(args)
            return constraints
        
        # Handle Union types (Optional[T] is Union[T, None])
        if origin is Union:
            # Filter out None type for Optional
            non_none_args = [arg for arg in args if arg is not type(None)]
            if len(non_none_args) == 1:
                field_type = non_none_args[0]
                origin = get_origin(field_type)
                args = get_args(field_type)
                constraints["optional"] = True
                
                # Check if the remaining type is Literal
                if origin is not None and 'Literal' in str(origin):
                    constraints["type"] = "literal"
                    constraints["choices"] = list(get_args(field_type))
                    return constraints
        
        # Handle basic types
        if field_type == str:
            constraints["type"] = "string"
        elif field_type == int:
            constraints["type"] = "integer"
            
            # Extract range constraints from metadata
            if hasattr(field_info, 'metadata') and field_info.metadata:
                for meta in field_info.metadata:
                    if hasattr(meta, 'ge'):  # Greater or equal (min)
                        constraints["min"] = meta.ge
                    if hasattr(meta, 'le'):  # Less or equal (max)
                        constraints["max"] = meta.le
            
            # Default range if no constraints found
            if "min" not in constraints:
                constraints["min"] = 0
            if "max" not in constraints:
                constraints["max"] = 10
                
        elif field_type == float:
            constraints["type"] = "number"
        elif field_type == bool:
            constraints["type"] = "boolean"
            constraints["choices"] = [True, False]
        elif origin is list or field_type == list:
            constraints["type"] = "array"
        
        # Add default value if available
        if hasattr(field_info, 'default') and field_info.default is not None:
            constraints["default"] = field_info.default
        
        # Mark as required if needed
        if hasattr(field_info, 'is_required') and field_info.is_required():
            constraints["required"] = True
        elif hasattr(field_info, 'required') and field_info.required:
            constraints["required"] = True
        
        return constraints
    
    @staticmethod
    def get_tool_schema_constraints(tool_name: str) -> Dict[str, Dict[str, Any]]:
        """Extract all field constraints for a given tool."""
        tool = None
        for t in TOOL_CATALOG:
            if t.id == tool_name:
                tool = t
                break
        
        if not tool or not tool.args_schema:
            return {}
        
        schema_class = tool.args_schema
        constraints = {}
        
        try:
            # Use Pydantic v2 model_fields
            if hasattr(schema_class, 'model_fields'):
                for field_name, field_info in schema_class.model_fields.items():
                    constraints[field_name] = SchemaIntrospector.extract_field_constraints(field_info, field_name)
            else:
                logger.warning(f"Could not find model_fields for {tool_name}")
                return {}
            
        except Exception as e:
            logger.warning(f"Could not extract constraints for {tool_name}: {e}")
            return {}
        
        return constraints
    
    @staticmethod
    def format_constraints_for_llm(constraints: Dict[str, Dict[str, Any]]) -> str:
        """Format extracted constraints into human-readable text for LLM prompts."""
        lines = []
        
        for field_name, field_constraints in constraints.items():
            constraint_type = field_constraints.get("type", "unknown")
            
            if constraint_type == "literal":
                choices = field_constraints.get("choices", [])
                lines.append(f"{field_name}: {choices}")
            elif constraint_type == "integer":
                min_val = field_constraints.get("min", "?")
                max_val = field_constraints.get("max", "?")
                lines.append(f"{field_name}: integer from {min_val} to {max_val}")
            elif constraint_type == "string":
                lines.append(f"{field_name}: <infer from player text>")
            elif constraint_type == "boolean":
                lines.append(f"{field_name}: true or false")
            elif constraint_type == "array":
                lines.append(f"{field_name}: array/list")
            else:
                lines.append(f"{field_name}: {constraint_type}")
        
        return "\\n".join(lines)


# Add missing import
from typing import Union, Literal


@dataclass
class WorldContext:
    """Minimal world context for argument filling."""
    current_zone: str
    visible_actors: List[str]
    visible_exits: List[str]
    actor_inventory: List[str]
    actor_id: str


@dataclass
class IntentResult:
    """Result from Stage 1: Intent Parser."""
    tool_names: List[str]
    confidence: float
    success: bool = True
    error_message: Optional[str] = None


@dataclass
class StagedPlanResult:
    """Result from complete staged planning pipeline."""
    tool_calls: List[Dict[str, Any]]  # [{"tool": "move", "args": {...}}, ...]
    confidence: float
    success: bool = True
    error_message: Optional[str] = None
    debug_info: Optional[Dict[str, Any]] = None


class StagedPlanner:
    """3-Stage LLM planner with clean separation of concerns."""
    
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        max_tokens: int = 300,
        temperature: float = 0.1,
    ):
        """Initialize the staged planner."""
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        
        # Stage 1: Intent Parser - pure linguistic classification
        self.intent_prompt = """You are an intent classifier for a text adventure game.

Here are the available functions (tools) you can call:
- move(): move to another zone
- talk(): speak or interact with someone  
- attack(): physically strike an enemy
- use_item(): use or consume an inventory item
- get_info(): inspect or learn about something
- narrate_only(): request environmental narration
- ask_roll(): perform a skill or ability roll
- apply_effects(): apply game effects

Given the player's message, return ONLY a JSON object with a "tools" field containing a list of function names.

Examples:
Input: "I walk to the garden"
Output: {"tools": ["move"]}

Input: "I sneak through the archway" 
Output: {"tools": ["move", "ask_roll"]}

Input: "I examine the door then try to open it"
Output: {"tools": ["get_info", "use_item"]}

Input: "I talk to the guard about the weather"
Output: {"tools": ["talk"]}

Input: "I look around"
Output: {"tools": ["narrate_only"]}

Return ONLY valid JSON with the "tools" field."""

    def plan_staged(
        self, 
        state: GameState, 
        utterance: Utterance, 
        debug: bool = False
    ) -> StagedPlanResult:
        """
        Execute the complete 3-stage planning pipeline.
        
        Args:
            state: Current game state
            utterance: Player input
            debug: Enable debug output
            
        Returns:
            StagedPlanResult with tool calls ready for execution
        """
        debug_info = {} if debug else None
        
        try:
            # Stage 0: Context Preloader
            context = self._preload_context(state, utterance, debug)
            if debug_info:
                debug_info["context"] = context.__dict__
            
            # Stage 1: Intent Parser
            intent_result = self._parse_intent(utterance, debug)
            if not intent_result.success:
                return StagedPlanResult(
                    tool_calls=[],
                    confidence=0.1,
                    success=False,
                    error_message=intent_result.error_message,
                    debug_info=debug_info
                )
            
            if debug_info:
                debug_info["intent"] = {
                    "tools": intent_result.tool_names,
                    "confidence": intent_result.confidence
                }
            
            # Stage 2: Argument Filler
            plan_result = self._fill_arguments(
                utterance, intent_result.tool_names, context, debug
            )
            
            if debug_info:
                debug_info["filled_calls"] = plan_result.tool_calls
            
            plan_result.debug_info = debug_info
            return plan_result
            
        except Exception as e:
            logger.error(f"Staged planning failed: {e}")
            return StagedPlanResult(
                tool_calls=[],
                confidence=0.1,
                success=False,
                error_message=str(e),
                debug_info=debug_info
            )
    
    def _preload_context(
        self, 
        state: GameState, 
        utterance: Utterance, 
        debug: bool = False
    ) -> WorldContext:
        """Stage 0: Extract minimal world context for argument filling."""
        
        actor_id = utterance.actor_id
        if not actor_id or actor_id not in state.entities:
            raise ValueError(f"Invalid actor: {actor_id}")
            
        actor = state.entities[actor_id]
        current_zone_id = getattr(actor, 'current_zone', None)
        
        if not current_zone_id or current_zone_id not in state.zones:
            raise ValueError(f"Actor {actor_id} not in valid zone")
            
        current_zone = state.zones[current_zone_id]
        
        # Get visible actors in the same zone
        visible_actors = []
        for entity_id, entity in state.entities.items():
            if (entity_id != actor_id and 
                hasattr(entity, 'current_zone') and 
                entity.current_zone == current_zone_id):
                visible_actors.append(entity_id)
        
        # Get available exits
        visible_exits = list(current_zone.adjacent_zones) if current_zone.adjacent_zones else []
        
        # Get actor inventory
        actor_inventory = getattr(actor, 'inventory', [])
        
        context = WorldContext(
            current_zone=current_zone.name,
            visible_actors=visible_actors,
            visible_exits=visible_exits,
            actor_inventory=actor_inventory,
            actor_id=actor_id
        )
        
        if debug:
            logger.info(f"Context: zone={context.current_zone}, "
                       f"actors={len(context.visible_actors)}, "
                       f"exits={len(context.visible_exits)}")
        
        return context
    
    def _parse_intent(self, utterance: Utterance, debug: bool = False) -> IntentResult:
        """Stage 1: Parse player intent to tool names (no world context)."""
        
        try:
            user_prompt = f'Player message: "{utterance.text}"'
            
            if debug:
                logger.info(f"Intent parsing: {utterance.text}")
            
            response = self._call_llm(self.intent_prompt, user_prompt, debug=debug)
            
            # Parse JSON response
            response_json = json.loads(response)
            tool_names = response_json.get("tools", [])
            
            if not isinstance(tool_names, list):
                raise ValueError("Expected 'tools' field with list of tool names")
                
            # Validate tool names
            valid_tools = [name for name in tool_names if name in [t.id for t in TOOL_CATALOG]]
            
            confidence = 0.9 if valid_tools else 0.1
            
            return IntentResult(
                tool_names=valid_tools,
                confidence=confidence,
                success=len(valid_tools) > 0
            )
            
        except Exception as e:
            logger.error(f"Intent parsing failed: {e}")
            return IntentResult(
                tool_names=[],
                confidence=0.1,
                success=False,
                error_message=str(e)
            )
    
    def _fill_arguments(
        self,
        utterance: Utterance,
        tool_names: List[str], 
        context: WorldContext,
        debug: bool = False
    ) -> StagedPlanResult:
        """Stage 2: Fill tool arguments using dynamically extracted constraints."""
        
        try:
            # Build dynamic argument constraints for each tool
            tool_argument_specs = []
            dynamic_constraints = {}
            
            for tool_name in tool_names:
                # Extract schema constraints dynamically
                schema_constraints = SchemaIntrospector.get_tool_schema_constraints(tool_name)
                dynamic_constraints[tool_name] = schema_constraints
                
                # Format for LLM prompt
                if schema_constraints:
                    formatted_constraints = SchemaIntrospector.format_constraints_for_llm(schema_constraints)
                    tool_argument_specs.append(f"{tool_name}({formatted_constraints.replace(chr(10), ', ')})")
                else:
                    tool_argument_specs.append(f"{tool_name}(...)")
            
            # Prepare valid runtime values from context
            valid_exits = json.dumps(context.visible_exits)
            valid_targets = json.dumps(context.visible_actors)
            valid_items = json.dumps(context.actor_inventory)
            
            # Create dynamic prompt with real schema constraints
            filler_prompt = f"""You are the argument filler for an RPG system.

Player message: "{utterance.text}"
Functions to call: {json.dumps(tool_names)}

For each function, fill only its arguments using the constraints and valid values below.

=== Tool Argument Schemas ===
{chr(10).join(tool_argument_specs)}

=== Current World Values (use these when possible) ===
actor: "{context.actor_id}"
to: {valid_exits} 
target: {valid_targets}
item_id: {valid_items}

=== Important Notes ===
- For literal fields, ONLY use values from the provided choices
- For integer fields, use values within the specified ranges
- For string fields marked as <infer from player text>, extract the appropriate text
- Use world values (exits, targets, items) when they match the player intent
- Fill required fields; optional fields can be omitted if not relevant

Return ONLY a JSON object with "tool_calls" field:
{{"tool_calls": [
  {{"tool": "function_name", "args": {{"param": "value"}}}},
  {{"tool": "function_name", "args": {{"param": "value"}}}}
]}}"""
            
            user_prompt = "Fill the arguments for the specified tools."
            
            if debug:
                logger.info(f"Filling arguments for tools: {tool_names}")
                logger.info(f"Dynamic constraints: {dynamic_constraints}")
            
            response = self._call_llm(filler_prompt, user_prompt, debug=debug)
            
            # Parse JSON response
            response_json = json.loads(response)
            tool_calls = response_json.get("tool_calls", [])
            
            if not isinstance(tool_calls, list):
                raise ValueError("Expected 'tool_calls' field with list of tool calls")
            
            # Validate structure
            for call in tool_calls:
                if not isinstance(call, dict) or "tool" not in call or "args" not in call:
                    raise ValueError("Invalid tool call structure")
            
            return StagedPlanResult(
                tool_calls=tool_calls,
                confidence=0.9,  # Higher confidence with dynamic constraints
                success=True
            )
            
        except Exception as e:
            logger.error(f"Argument filling failed: {e}")
            return StagedPlanResult(
                tool_calls=[],
                confidence=0.1,
                success=False,
                error_message=str(e)
            )
    
    def _call_llm(self, system_prompt: str, user_prompt: str, debug: bool = False) -> str:
        """Call OpenAI API with retry logic."""
        
        if debug:
            logger.info(f"LLM call - system: {system_prompt[:100]}...")
            logger.info(f"LLM call - user: {user_prompt}")
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                response_format={"type": "json_object"},
            )
            
            content = response.choices[0].message.content
            result = content.strip() if content else ""
            
            if debug:
                logger.info(f"LLM response: {result}")
            
            return result
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise


# Global staged planner instance  
_staged_planner_instance: Optional[StagedPlanner] = None


def initialize_staged_planner(api_key: str, model: str = "gpt-4o-mini") -> None:
    """Initialize the global staged planner instance."""
    global _staged_planner_instance
    _staged_planner_instance = StagedPlanner(api_key, model)
    logger.info("Staged planner initialized")


def get_staged_plan(
    state: GameState, utterance: Utterance, debug: bool = False
) -> StagedPlanResult:
    """Convenience function to get a staged plan using the global instance."""
    if _staged_planner_instance is None:
        raise RuntimeError("Staged planner not initialized. Call initialize_staged_planner() first.")
    
    return _staged_planner_instance.plan_staged(state, utterance, debug)