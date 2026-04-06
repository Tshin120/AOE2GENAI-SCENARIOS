"""
Scenario Viewer - Displays the contents of an AoE2 scenario file
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from AoE2ScenarioParser.scenarios.aoe2_de_scenario import AoE2DEScenario
from AoE2ScenarioParser.datasets.players import PlayerId

# Load the scenario file
scenario_path = "test_battle.aoe2scenario"
scenario = AoE2DEScenario.from_file(scenario_path)

# Get managers
unit_manager = scenario.unit_manager
trigger_manager = scenario.trigger_manager
map_manager = scenario.map_manager

print("=" * 60)
print(f"SCENARIO: {scenario_path}")
print("=" * 60)

# --- MAP INFO ---
print(f"\n--- MAP INFO ---")
print(f"Map Size: {map_manager.map_size} x {map_manager.map_size}")

# --- UNITS BY PLAYER ---
print(f"\n--- UNITS ---")

# Get units for each player
for player_id in PlayerId:
    try:
        units = unit_manager.get_player_units(player_id)
        if units:
            print(f"\n  Player: {player_id.name} ({len(units)} units)")
            print("  " + "-" * 40)

            # Count unit types
            unit_counts = {}
            for unit in units:
                unit_type = unit.unit_const
                if unit_type not in unit_counts:
                    unit_counts[unit_type] = []
                unit_counts[unit_type].append(unit)

            for unit_type, unit_list in unit_counts.items():
                # Try to get unit name
                name = f"Unit ID {unit_type}"
                try:
                    from AoE2ScenarioParser.datasets.units import UnitInfo
                    from AoE2ScenarioParser.datasets.buildings import BuildingInfo
                    from AoE2ScenarioParser.datasets.heroes import HeroInfo
                    from AoE2ScenarioParser.datasets.other import OtherInfo

                    for dataset in [UnitInfo, BuildingInfo, HeroInfo, OtherInfo]:
                        try:
                            for item in dataset:
                                if item.ID == unit_type:
                                    name = item.name
                                    break
                        except:
                            pass
                        if name != f"Unit ID {unit_type}":
                            break
                except:
                    pass

                # Show positions
                positions = [(int(u.x), int(u.y)) for u in unit_list]
                pos_str = str(positions[:5])
                if len(positions) > 5:
                    pos_str = pos_str[:-1] + ", ...]"
                print(f"    {name}: {len(unit_list)}x at {pos_str}")
    except:
        pass

# --- TRIGGERS ---
print(f"\n--- TRIGGERS ({len(trigger_manager.triggers)} total) ---")

for i, trigger in enumerate(trigger_manager.triggers):
    print(f"\n  [{i+1}] {trigger.name}")
    print(f"      Enabled: {trigger.enabled}")

    # Conditions
    if trigger.conditions:
        print(f"      Conditions ({len(trigger.conditions)}):")
        for cond in trigger.conditions:
            cond_type = cond.condition_type
            cond_name = cond_type.name if hasattr(cond_type, 'name') else str(cond_type)
            print(f"        - {cond_name}")

    # Effects
    if trigger.effects:
        print(f"      Effects ({len(trigger.effects)}):")
        for effect in trigger.effects:
            effect_type = effect.effect_type
            effect_name = effect_type.name if hasattr(effect_type, 'name') else str(effect_type)
            # Try to get message if it's a display instruction
            msg = ""
            if hasattr(effect, 'message') and effect.message:
                msg_text = str(effect.message)
                msg = f' - "{msg_text[:50]}..."' if len(msg_text) > 50 else f' - "{msg_text}"'
            print(f"        - {effect_name}{msg}")

print("\n" + "=" * 60)
print("END OF SCENARIO")
print("=" * 60)
