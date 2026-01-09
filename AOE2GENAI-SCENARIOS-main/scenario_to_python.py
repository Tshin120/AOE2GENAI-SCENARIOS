"""
Scenario to Python Converter
Converts an AoE2 scenario file into Python code that recreates it.

Usage:
    python scenario_to_python.py <scenario_file.aoe2scenario> [output.py]
"""
import sys
import io
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from AoE2ScenarioParser.scenarios.aoe2_de_scenario import AoE2DEScenario
from AoE2ScenarioParser.datasets.players import PlayerId
from AoE2ScenarioParser.datasets.units import UnitInfo
from AoE2ScenarioParser.datasets.buildings import BuildingInfo
from AoE2ScenarioParser.datasets.heroes import HeroInfo
from AoE2ScenarioParser.datasets.other import OtherInfo


# Condition ID to method name mapping
CONDITION_NAMES = {
    0: None,  # NONE - skip
    1: "bring_object_to_area",
    2: "bring_object_to_object",
    3: "own_objects",
    4: "accumulate_attribute",
    5: "objects_in_area",
    6: "destroy_object",
    7: "capture_object",
    8: "timer",
    9: "own_fewer_objects",
    10: "timer",  # Also used as timer in some versions
    11: "object_selected",
    12: "ai_signal",
    13: "player_defeated",
    14: "object_has_target",
    15: "object_visible",
    16: "object_not_visible",
    17: "researching_technology",
    18: "technology_state",
    19: "units_garrisoned",
    20: "difficulty_level",
    21: "chance",
    22: "technology_state",
    23: "variable_value",
    24: "object_hp",
    25: "diplomacy_state",
    26: "script_call",
    27: "object_visible_multiplayer",
    28: "object_selected_multiplayer",
    29: "object_has_action",
    30: "or",
    31: "ai_signal_multiplayer",
    32: "xs_function",
    33: "victory_timer",
}

# Effect ID to method name mapping
EFFECT_NAMES = {
    0: None,  # NONE - skip
    1: "change_diplomacy",
    2: "research_technology",
    3: "send_chat",
    4: "play_sound",
    5: "activate_trigger",
    6: "deactivate_trigger",
    7: "ai_script_goal",
    8: "create_object",
    9: "task_object",
    10: "declare_victory",
    11: "kill_object",
    12: "remove_object",
    13: "change_view",
    14: "unload",
    15: "change_ownership",
    16: "patrol",
    17: "display_instructions",
    18: "clear_instructions",
    19: "patrol",  # Also patrol in DE
    20: "freeze_object",
    21: "use_advanced_buttons",
    22: "damage_object",
    23: "place_foundation",
    24: "change_object_name",
    25: "change_object_hp",
    26: "change_object_attack",
    27: "stop_object",
    28: "attack_move",
    29: "change_object_armor",
    30: "change_object_range",
    31: "change_object_speed",
    32: "heal_object",
    33: "teleport_object",
    34: "change_object_stance",
    35: "display_timer",
    36: "enable_disable_object",
    37: "enable_disable_technology",
    38: "enable_unit_targeting",
    39: "flash_objects",
    40: "change_player_name",
    41: "change_train_location",
    42: "change_research_location",
    43: "change_civilization_name",
    44: "create_garrisoned_object",
    45: "acknowledge_ai_signal",
    46: "change_object_description",
    47: "change_player_color",
    48: "tribute",
    49: "unlock_gate",
    50: "lock_gate",
    51: "activate_trigger",
    52: "deactivate_trigger",
    53: "ai_script_goal",
    54: "change_variable",
    55: "script_call",
    56: "change_object_icon",
    57: "replace_object",
    58: "change_object_player_color",
    59: "display_text",
    60: "change_technology_cost",
    61: "change_technology_research_time",
    62: "change_technology_name",
    63: "change_technology_description",
}

# Define which parameters are valid for each effect method
# This prevents generating code with invalid keyword arguments
EFFECT_VALID_PARAMS = {
    "display_instructions": {"source_player", "message", "display_time"},
    "send_chat": {"source_player", "message"},
    "freeze_object": {"source_player", "object_list_unit_id", "area_x1", "area_y1", "area_x2", "area_y2"},
    "change_object_name": {"source_player", "message", "object_list_unit_id", "area_x1", "area_y1", "area_x2", "area_y2"},
    "change_object_attack": {"source_player", "object_list_unit_id", "area_x1", "area_y1", "area_x2", "area_y2", "quantity"},
    "change_object_armor": {"source_player", "object_list_unit_id", "area_x1", "area_y1", "area_x2", "area_y2", "quantity"},
    "change_object_range": {"source_player", "object_list_unit_id", "area_x1", "area_y1", "area_x2", "area_y2", "quantity"},
    "change_object_speed": {"source_player", "object_list_unit_id", "area_x1", "area_y1", "area_x2", "area_y2", "quantity"},
    "change_object_hp": {"source_player", "object_list_unit_id", "area_x1", "area_y1", "area_x2", "area_y2", "quantity"},
    "attack_move": {"source_player", "location_x", "location_y", "object_list_unit_id", "area_x1", "area_y1", "area_x2", "area_y2"},
    "task_object": {"source_player", "location_x", "location_y", "object_list_unit_id", "area_x1", "area_y1", "area_x2", "area_y2"},
    "patrol": {"source_player", "location_x", "location_y", "object_list_unit_id", "area_x1", "area_y1", "area_x2", "area_y2"},
    "create_object": {"source_player", "location_x", "location_y", "object_list_unit_id"},
    "kill_object": {"source_player", "object_list_unit_id", "area_x1", "area_y1", "area_x2", "area_y2"},
    "remove_object": {"source_player", "object_list_unit_id", "area_x1", "area_y1", "area_x2", "area_y2"},
    "change_view": {"source_player", "location_x", "location_y"},
    "change_ownership": {"source_player", "target_player", "object_list_unit_id", "area_x1", "area_y1", "area_x2", "area_y2"},
    "research_technology": {"source_player", "technology"},
    "change_diplomacy": {"source_player", "target_player", "diplomacy"},
    "activate_trigger": {"trigger_id"},
    "deactivate_trigger": {"trigger_id"},
    "declare_victory": {"source_player"},
    "play_sound": {"source_player", "location_x", "location_y", "sound_name"},
    "damage_object": {"source_player", "object_list_unit_id", "area_x1", "area_y1", "area_x2", "area_y2", "quantity"},
    "heal_object": {"source_player", "object_list_unit_id", "area_x1", "area_y1", "area_x2", "area_y2", "quantity"},
    "teleport_object": {"source_player", "location_x", "location_y", "object_list_unit_id", "area_x1", "area_y1", "area_x2", "area_y2"},
    "stop_object": {"source_player", "object_list_unit_id", "area_x1", "area_y1", "area_x2", "area_y2"},
    "change_object_stance": {"source_player", "object_list_unit_id", "area_x1", "area_y1", "area_x2", "area_y2"},
    "display_timer": {"source_player", "display_time", "message"},
    "enable_disable_object": {"source_player", "object_list_unit_id", "enabled"},
    "enable_disable_technology": {"source_player", "technology", "enabled"},
    "change_player_name": {"source_player", "message"},
    "change_civilization_name": {"source_player", "message"},
    "change_object_description": {"source_player", "message", "object_list_unit_id"},
    "tribute": {"source_player", "target_player", "quantity"},
    "unlock_gate": {"source_player", "object_list_unit_id", "area_x1", "area_y1", "area_x2", "area_y2"},
    "lock_gate": {"source_player", "object_list_unit_id", "area_x1", "area_y1", "area_x2", "area_y2"},
    "flash_objects": {"source_player", "object_list_unit_id", "area_x1", "area_y1", "area_x2", "area_y2"},
    "change_player_color": {"source_player", "player_color"},
    "display_text": {"source_player", "message", "display_time"},
}


def build_unit_id_map():
    """Build a mapping from unit IDs to their dataset names."""
    id_map = {}

    for dataset_name, dataset in [
        ("UnitInfo", UnitInfo),
        ("BuildingInfo", BuildingInfo),
        ("HeroInfo", HeroInfo),
        ("OtherInfo", OtherInfo)
    ]:
        try:
            for item in dataset:
                if hasattr(item, 'ID'):
                    id_map[item.ID] = f"{dataset_name}.{item.name}.ID"
        except Exception:
            pass

    return id_map


def get_player_name(player_id):
    """Convert player ID to PlayerId enum name."""
    player_map = {
        0: "PlayerId.GAIA",
        1: "PlayerId.ONE",
        2: "PlayerId.TWO",
        3: "PlayerId.THREE",
        4: "PlayerId.FOUR",
        5: "PlayerId.FIVE",
        6: "PlayerId.SIX",
        7: "PlayerId.SEVEN",
        8: "PlayerId.EIGHT",
    }

    # Handle -1 or invalid player IDs
    if player_id == -1:
        return None

    if hasattr(player_id, 'value'):
        val = player_id.value
        if val == -1:
            return None
        return player_map.get(val, None)

    return player_map.get(player_id, None)


def get_condition_name(cond_type):
    """Get the condition method name from the condition type."""
    if hasattr(cond_type, 'name'):
        return cond_type.name.lower()
    if hasattr(cond_type, 'value'):
        return CONDITION_NAMES.get(cond_type.value)
    if isinstance(cond_type, int):
        return CONDITION_NAMES.get(cond_type)
    return None


def get_effect_name(effect_type):
    """Get the effect method name from the effect type."""
    if hasattr(effect_type, 'name'):
        return effect_type.name.lower()
    if hasattr(effect_type, 'value'):
        return EFFECT_NAMES.get(effect_type.value)
    if isinstance(effect_type, int):
        return EFFECT_NAMES.get(effect_type)
    return None


def convert_scenario_to_python(scenario_path, output_path=None):
    """Convert a scenario file to Python code."""

    # Load the scenario
    print(f"Loading scenario: {scenario_path}")
    scenario = AoE2DEScenario.from_file(scenario_path)

    # Get managers
    unit_manager = scenario.unit_manager
    trigger_manager = scenario.trigger_manager
    map_manager = scenario.map_manager

    # Build unit ID map
    unit_id_map = build_unit_id_map()

    # Start building Python code
    lines = []

    # Header
    lines.append('"""')
    lines.append(f'Auto-generated from: {os.path.basename(scenario_path)}')
    lines.append('Generated by scenario_to_python.py')
    lines.append('"""')
    lines.append('')
    lines.append('import sys')
    lines.append('import io')
    lines.append("sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')")
    lines.append("sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')")
    lines.append('')
    lines.append('from AoE2ScenarioParser.scenarios.aoe2_de_scenario import AoE2DEScenario')
    lines.append('from AoE2ScenarioParser.datasets.players import PlayerId')
    lines.append('from AoE2ScenarioParser.datasets.units import UnitInfo')
    lines.append('from AoE2ScenarioParser.datasets.buildings import BuildingInfo')
    lines.append('from AoE2ScenarioParser.datasets.trigger_lists import *')
    lines.append('from AoE2ScenarioParser.datasets.techs import TechInfo')
    lines.append('from AoE2ScenarioParser.datasets.heroes import HeroInfo')
    lines.append('from AoE2ScenarioParser.datasets.other import OtherInfo')
    lines.append('')
    lines.append('# Create scenario')
    lines.append('scenario = AoE2DEScenario.from_default()')
    lines.append('')
    lines.append('# Get managers')
    lines.append('unit_manager = scenario.unit_manager')
    lines.append('trigger_manager = scenario.trigger_manager')
    lines.append('map_manager = scenario.map_manager')
    lines.append('')

    # Map size
    map_size = map_manager.map_size
    lines.append(f'# Set map size')
    lines.append(f'map_manager.map_size = {map_size}')
    lines.append('')

    # Units by player
    lines.append('# ============================================================')
    lines.append('# UNITS AND BUILDINGS')
    lines.append('# ============================================================')

    unknown_unit_ids = set()

    for player_id in PlayerId:
        try:
            units = unit_manager.get_player_units(player_id)
            if units:
                player_name = get_player_name(player_id)
                if player_name is None:
                    continue

                lines.append('')
                lines.append(f'# --- {player_id.name} ({len(units)} units) ---')

                for unit in units:
                    unit_const = unit.unit_const
                    x = round(unit.x, 1)
                    y = round(unit.y, 1)

                    # Get unit name from map
                    if unit_const in unit_id_map:
                        unit_name = unit_id_map[unit_const]
                        lines.append(f'unit_manager.add_unit({player_name}, unit_const={unit_name}, x={x}, y={y})')
                    else:
                        # Unknown unit ID - comment it out
                        unknown_unit_ids.add(unit_const)
                        lines.append(f'# unit_manager.add_unit({player_name}, unit_const={unit_const}, x={x}, y={y})  # Unknown unit ID')
        except Exception as e:
            pass

    if unknown_unit_ids:
        lines.append('')
        lines.append(f'# NOTE: {len(unknown_unit_ids)} unknown unit IDs were commented out: {sorted(unknown_unit_ids)[:10]}...')

    lines.append('')

    # Triggers
    if trigger_manager.triggers:
        lines.append('# ============================================================')
        lines.append('# TRIGGERS')
        lines.append('# ============================================================')
        lines.append('')

        for i, trigger in enumerate(trigger_manager.triggers):
            trigger_var = f'trigger_{i}'
            trigger_name = trigger.name.replace('"', '\\"').replace('\n', ' ') if trigger.name else f"Trigger {i}"

            lines.append(f'# Trigger: {trigger_name}')
            lines.append(f'{trigger_var} = trigger_manager.add_trigger("{trigger_name}")')

            if hasattr(trigger, 'enabled') and not trigger.enabled:
                lines.append(f'{trigger_var}.enabled = False')

            # Conditions
            if trigger.conditions:
                for cond in trigger.conditions:
                    cond_method = get_condition_name(cond.condition_type)

                    if cond_method is None:
                        lines.append(f'# Skipped condition type: {cond.condition_type}')
                        continue

                    # Build condition parameters
                    params = []

                    # Timer parameter (special handling)
                    if cond_method == 'timer' and hasattr(cond, 'timer') and cond.timer is not None and cond.timer > 0:
                        params.append(str(int(cond.timer)))

                    # Other common parameters
                    if hasattr(cond, 'quantity') and cond.quantity is not None and cond.quantity != -1:
                        params.append(f'quantity={cond.quantity}')

                    if hasattr(cond, 'source_player') and cond.source_player is not None:
                        player = get_player_name(cond.source_player)
                        if player:
                            params.append(f'source_player={player}')

                    if hasattr(cond, 'unit_object') and cond.unit_object is not None and cond.unit_object != -1:
                        params.append(f'unit_object={cond.unit_object}')

                    # Area parameters (only if valid)
                    if hasattr(cond, 'area_x1') and cond.area_x1 is not None and cond.area_x1 != -1:
                        params.append(f'area_x1={cond.area_x1}')
                        if hasattr(cond, 'area_y1') and cond.area_y1 is not None:
                            params.append(f'area_y1={cond.area_y1}')
                        if hasattr(cond, 'area_x2') and cond.area_x2 is not None:
                            params.append(f'area_x2={cond.area_x2}')
                        if hasattr(cond, 'area_y2') and cond.area_y2 is not None:
                            params.append(f'area_y2={cond.area_y2}')

                    param_str = ', '.join(params)
                    lines.append(f'{trigger_var}.new_condition.{cond_method}({param_str})')

            # Effects
            if trigger.effects:
                for effect in trigger.effects:
                    effect_method = get_effect_name(effect.effect_type)

                    if effect_method is None:
                        lines.append(f'# Skipped effect type: {effect.effect_type}')
                        continue

                    # Get valid parameters for this effect method
                    valid_params = EFFECT_VALID_PARAMS.get(effect_method, set())

                    # Build effect parameters (only include valid ones for this effect)
                    params = []

                    # Source player
                    if 'source_player' in valid_params:
                        if hasattr(effect, 'source_player') and effect.source_player is not None:
                            player = get_player_name(effect.source_player)
                            if player:
                                params.append(f'source_player={player}')

                    # Target player
                    if 'target_player' in valid_params:
                        if hasattr(effect, 'target_player') and effect.target_player is not None:
                            player = get_player_name(effect.target_player)
                            if player:
                                params.append(f'target_player={player}')

                    # Message
                    if 'message' in valid_params:
                        if hasattr(effect, 'message') and effect.message:
                            msg = str(effect.message).replace('"', '\\"').replace('\n', '\\n')
                            params.append(f'message="{msg}"')

                    # Display time
                    if 'display_time' in valid_params:
                        if hasattr(effect, 'display_time') and effect.display_time is not None and effect.display_time > 0:
                            params.append(f'display_time={effect.display_time}')

                    # Location
                    if 'location_x' in valid_params:
                        if hasattr(effect, 'location_x') and effect.location_x is not None and effect.location_x != -1:
                            params.append(f'location_x={effect.location_x}')
                            if 'location_y' in valid_params and hasattr(effect, 'location_y') and effect.location_y is not None:
                                params.append(f'location_y={effect.location_y}')

                    # Area (only if valid for this effect)
                    if 'area_x1' in valid_params:
                        if hasattr(effect, 'area_x1') and effect.area_x1 is not None and effect.area_x1 != -1:
                            params.append(f'area_x1={effect.area_x1}')
                            if 'area_y1' in valid_params and hasattr(effect, 'area_y1') and effect.area_y1 is not None:
                                params.append(f'area_y1={effect.area_y1}')
                            if 'area_x2' in valid_params and hasattr(effect, 'area_x2') and effect.area_x2 is not None:
                                params.append(f'area_x2={effect.area_x2}')
                            if 'area_y2' in valid_params and hasattr(effect, 'area_y2') and effect.area_y2 is not None:
                                params.append(f'area_y2={effect.area_y2}')

                    # Object list unit ID
                    if 'object_list_unit_id' in valid_params:
                        if hasattr(effect, 'object_list_unit_id') and effect.object_list_unit_id is not None and effect.object_list_unit_id != -1:
                            unit_name = unit_id_map.get(effect.object_list_unit_id, str(effect.object_list_unit_id))
                            params.append(f'object_list_unit_id={unit_name}')

                    # Quantity
                    if 'quantity' in valid_params:
                        if hasattr(effect, 'quantity') and effect.quantity is not None and effect.quantity != -1:
                            params.append(f'quantity={effect.quantity}')

                    param_str = ', '.join(params)
                    lines.append(f'{trigger_var}.new_effect.{effect_method}({param_str})')

            lines.append('')

    # Save
    base_name = os.path.splitext(os.path.basename(scenario_path))[0]
    lines.append('# ============================================================')
    lines.append('# SAVE SCENARIO')
    lines.append('# ============================================================')
    lines.append(f'scenario.write_to_file("{base_name}_recreated.aoe2scenario")')
    lines.append('')
    lines.append(f'print("Scenario saved as: {base_name}_recreated.aoe2scenario")')

    # Join all lines
    python_code = '\n'.join(lines)

    # Output
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(python_code)
        print(f"Python code saved to: {output_path}")
    else:
        print("\n" + "=" * 60)
        print("GENERATED PYTHON CODE")
        print("=" * 60 + "\n")
        print(python_code)

    return python_code


def main():
    if len(sys.argv) < 2:
        print("Usage: python scenario_to_python.py <scenario_file.aoe2scenario> [output.py]")
        print("\nExamples:")
        print("  python scenario_to_python.py my_scenario.aoe2scenario")
        print("  python scenario_to_python.py my_scenario.aoe2scenario output.py")
        sys.exit(1)

    scenario_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    if not os.path.exists(scenario_path):
        print(f"Error: File not found: {scenario_path}")
        sys.exit(1)

    convert_scenario_to_python(scenario_path, output_path)


if __name__ == "__main__":
    main()
