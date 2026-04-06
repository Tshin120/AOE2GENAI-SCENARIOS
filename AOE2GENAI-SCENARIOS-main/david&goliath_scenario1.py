# Monkey patch BEFORE importing to fix civilization enum bug
import sys
import AoE2ScenarioParser.helper.bytes_conversions
_original_int_to_bytes = AoE2ScenarioParser.helper.bytes_conversions.int_to_bytes

def _patched_int_to_bytes(integer, length, endian='little', signed=True):
    # Convert enums to their integer value
    if hasattr(integer, 'value') and hasattr(integer, 'name'):  # It's an Enum
        integer = integer.value
    # Handle string civilization names - convert to empty string bytes
    if isinstance(integer, str):
        # String fields should be handled by string_to_bytes, but if we get here,
        # return empty bytes of the right length
        return b'\x00' * length
    return _original_int_to_bytes(integer, length, endian, signed)

AoE2ScenarioParser.helper.bytes_conversions.int_to_bytes = _patched_int_to_bytes

# Imports
from AoE2ScenarioParser.scenarios.aoe2_de_scenario import AoE2DEScenario
from AoE2ScenarioParser.datasets.players import PlayerId
from AoE2ScenarioParser.datasets.units import UnitInfo
from AoE2ScenarioParser.datasets.trigger_lists import *
from AoE2ScenarioParser.datasets.buildings import BuildingInfo
from AoE2ScenarioParser.datasets.other import OtherInfo
from AoE2ScenarioParser.datasets.techs import TechInfo
from AoE2ScenarioParser.datasets.heroes import HeroInfo

# File path
output_path = "david_and_goliath.aoe2scenario"

# Load scenario object
scenario = AoE2DEScenario.from_default()
unit_manager = scenario.unit_manager
trigger_manager = scenario.trigger_manager
map_manager = scenario.map_manager

# David and Goliath Scenario

# Resource Setup - Ancient Israelite setting with loops for abundance
for x in range(10, 20, 2):
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.GOLD_MINE.ID, x=x, y=10)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.STONE_MINE.ID, x=x, y=11)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.FORAGE_BUSH.ID, x=x, y=12)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.TREE_OAK.ID, x=x, y=13)

# Animals - sheep and deer in herds
for i in range(4):
    unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.SHEEP.ID, x=10+i, y=15)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.DEER.ID, x=10+i, y=16)

# Setup David (Player ONE)
david = unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.CHARLES_MARTEL.ID, x=20, y=25)

# Setup Goliath (Player TWO) - replaced with Roland
goliath = unit_manager.add_unit(PlayerId.TWO, unit_const=HeroInfo.ROLAND.ID, x=35, y=25)

# Add Philistine army
for i in range(3):
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.MAN_AT_ARMS.ID, x=34 + i, y=26)
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.SPEARMAN.ID, x=34 + i, y=27)

# Additional Philistine reinforcements for challenge
for i in range(5):
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.MAN_AT_ARMS.ID, x=36 + i, y=28)
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.ARCHER.ID, x=36 + i, y=29)
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.SPEARMAN.ID, x=36 + i, y=30)

# Add some siege weapons
unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.SCORPION.ID, x=38, y=26)
unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.BATTERING_RAM.ID, x=39, y=27)

# Add a fortified guard tower to their camp
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GUARD_TOWER.ID, x=40, y=25)

# Add Israelite army hiding
for i in range(3):
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.SPEARMAN.ID, x=15 + i, y=22)

# Preparation camp: tents and training area
for x in range(17, 20):
    unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BARRACKS.ID, x=x, y=18)
    unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.HOUSE.ID, x=x, y=19)

# Trigger: David prepares for battle
prep_trigger = trigger_manager.add_trigger("David Prepares")
prep_trigger.new_condition.timer(10)
prep_trigger.new_effect.display_instructions(
    display_time=10,
    message="David prepares for battle. Train your courage and gather strength."
)

# Trigger: Speak to Commander
speak_to_commander = trigger_manager.add_trigger("Speak to Commander")
speak_to_commander.new_condition.bring_object_to_area(
    unit_object=david.reference_id,
    area_x1=17, area_y1=18,
    area_x2=18, area_y2=19
)
speak_to_commander.new_effect.display_instructions(
    display_time=10,
    message="Speak to the commander to understand the situation."
)

# Triggers for collecting 5 stones
stone_positions = [(13, 20), (14, 21), (15, 22), (16, 23), (17, 24)]
for i, (x, y) in enumerate(stone_positions):
    trigger = trigger_manager.add_trigger(f"Collect Stone {i+1}")
    trigger.new_condition.bring_object_to_area(
        unit_object=david.reference_id,
        area_x1=x, area_y1=y,
        area_x2=x, area_y2=y
    )
    trigger.new_effect.display_instructions(
        display_time=8,
        message=f"David collects stone {i+1}."
    )

# Trigger: Pray for Strength
pray_trigger = trigger_manager.add_trigger("Pray for Strength")
pray_trigger.new_condition.bring_object_to_area(
    unit_object=david.reference_id,
    area_x1=12, area_y1=18,
    area_x2=13, area_y2=19
)
pray_trigger.new_effect.display_instructions(
    display_time=10,
    message="David prays to God for strength."
)

# Trigger: Have at least 5 Spearman
spearman_req_trigger = trigger_manager.add_trigger("Train Spearmen")
spearman_req_trigger.new_condition.objects_in_area(
    quantity=5,
    object_list=UnitInfo.SPEARMAN.ID,
    source_player=PlayerId.ONE,
    area_x1=10, area_y1=20,
    area_x2=30, area_y2=30
)
spearman_req_trigger.new_effect.display_instructions(
    display_time=10,
    message="You have trained enough spearmen to support David."
)

# Trigger: Collect at least 200 stone
stone_trigger = trigger_manager.add_trigger("Gather Stone")
stone_trigger.new_condition.accumulate_attribute(
    quantity=200,
    attribute=2,  # Stone
    source_player=PlayerId.ONE
)
stone_trigger.new_effect.display_instructions(
    display_time=10,
    message="You have gathered enough stone to prepare your defenses."
)

# Trigger: David arrives on battlefield
david_arrives_trigger = trigger_manager.add_trigger("David Arrives")
david_arrives_trigger.new_condition.timer(30)
david_arrives_trigger.new_effect.display_instructions(
    display_time=10,
    message="David has arrived at the battlefield to face Goliath!"
)

# Trigger: David defeats Goliath
defeat_goliath_trigger = trigger_manager.add_trigger("Defeat Goliath")
defeat_goliath_trigger.new_condition.destroy_object(unit_object=goliath.reference_id)
defeat_goliath_trigger.new_effect.display_instructions(
    display_time=15,
    message="Goliath is slain! The Philistines are retreating!"
)
defeat_goliath_trigger.new_effect.create_object(
    object_list_unit_id=UnitInfo.SPEARMAN.ID,
    source_player=PlayerId.ONE,
    location_x=22,
    location_y=24,
)
defeat_goliath_trigger.new_effect.create_object(
    object_list_unit_id=UnitInfo.ARCHER.ID,
    source_player=PlayerId.ONE,
    location_x=23,
    location_y=24,
)

# Final Trigger: Victory for Israel
final_trigger = trigger_manager.add_trigger("Israelite Victory")
final_trigger.new_condition.timer(60)
final_trigger.new_effect.display_instructions(
    display_time=15,
    message="Victory! The Israelites celebrate their triumph."
)
final_trigger.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)

# Save scenario
print(f"Writing scenario with {len(unit_manager.units)} units and {len(trigger_manager.triggers)} triggers")
scenario.write_to_file(output_path)
print(f"Scenario saved to: {output_path}")
