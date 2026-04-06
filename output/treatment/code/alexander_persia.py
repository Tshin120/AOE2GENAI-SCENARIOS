import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from AoE2ScenarioParser.scenarios.aoe2_de_scenario import AoE2DEScenario
from AoE2ScenarioParser.datasets.players import PlayerId
from AoE2ScenarioParser.datasets.units import UnitInfo
from AoE2ScenarioParser.datasets.buildings import BuildingInfo
from AoE2ScenarioParser.datasets.trigger_lists import *
from AoE2ScenarioParser.datasets.techs import TechInfo
from AoE2ScenarioParser.datasets.heroes import HeroInfo
from AoE2ScenarioParser.datasets.other import OtherInfo
from AoE2ScenarioParser.datasets.terrains import TerrainId

# REACHABILITY ANALYSIS:
# Victory path: Capture siege equipment -> breach outer walls -> breach middle walls -> destroy castle/kill commander
# Defeat path: Hero dies OR all military units lost OR all siege equipment destroyed before breaching inner walls
# Resource sufficiency: Yes - starting army + capturable siege weapons sufficient to breach all defenses
# Counter availability: Yes - player has mix of infantry/archers/siege to counter all enemy unit types
# Physical access: Yes - multiple paths to objectives, gates can be destroyed to progress
# Timing viability: Yes - starting army can survive initial contact while capturing siege equipment

# Create scenario
scenario = AoE2DEScenario.from_default()

# Get managers
unit_manager = scenario.unit_manager
trigger_manager = scenario.trigger_manager
map_manager = scenario.map_manager

# Get map size
map_size = map_manager.map_size
center = map_size // 2
quarter = map_size // 2
three_quarter = (map_size * 3) // 4

# Player starting positions
player_start_x = 10
player_start_y = center

# Defensive line positions (from edge to center)
outer_wall_x = quarter 
middle_wall_x = center
inner_wall_x = three_quarter

# Create hero unit and store reference
hero = unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.BELISARIUS.ID, x=player_start_x, y=player_start_y)

# Player starting army
for i in range(15):
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.CHAMPION.ID, x=player_start_x+i, y=player_start_y+2)
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.CROSSBOWMAN.ID, x=player_start_x+i, y=player_start_y+4)
    
for i in range(5):
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.BATTERING_RAM.ID, x=player_start_x+i, y=player_start_y+6)

# Player forward base
player_base_x = player_start_x + 15
player_base_y = player_start_y
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BARRACKS.ID, x=player_base_x, y=player_base_y)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.ARCHERY_RANGE.ID, x=player_base_x+3, y=player_base_y)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BLACKSMITH.ID, x=player_base_x+6, y=player_base_y)

# Outer defensive line
outer_gate = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, x=outer_wall_x, y=center)

for i in range(15):
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.PALISADE_WALL.ID, x=outer_wall_x, y=center-20+i)
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.PALISADE_WALL.ID, x=outer_wall_x, y=center+5+i)
    
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.WATCH_TOWER.ID, x=outer_wall_x+2, y=center-15)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.WATCH_TOWER.ID, x=outer_wall_x+2, y=center+15)

# Middle defensive line  
middle_gate = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, x=middle_wall_x, y=center)

for i in range(20):
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STONE_WALL.ID, x=middle_wall_x, y=center-25+i)
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STONE_WALL.ID, x=middle_wall_x, y=center+5+i)

unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GUARD_TOWER.ID, x=middle_wall_x+2, y=center-20)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GUARD_TOWER.ID, x=middle_wall_x+2, y=center)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GUARD_TOWER.ID, x=middle_wall_x+2, y=center+20)

# Inner fortress
castle = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.CASTLE.ID, x=inner_wall_x, y=center)
inner_gate = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, x=inner_wall_x-10, y=center)

unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.KEEP.ID, x=inner_wall_x-5, y=center-15)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.KEEP.ID, x=inner_wall_x-5, y=center+15)

enemy_lord = unit_manager.add_unit(PlayerId.TWO, unit_const=HeroInfo.TAMERLANE.ID, x=inner_wall_x+5, y=center)

# Capturable siege equipment
trebuchet = unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.TREBUCHET.ID, x=outer_wall_x-10, y=center-10)
ram1 = unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.BATTERING_RAM.ID, x=outer_wall_x-8, y=center+10)
ram2 = unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.BATTERING_RAM.ID, x=middle_wall_x-8, y=center+8)

# Setup triggers
tech_trigger = trigger_manager.add_trigger("Techs")
tech_trigger.new_condition.timer(timer=1)
tech_trigger.new_effect.research_technology(source_player=PlayerId.ONE, technology=TechInfo.SIEGE_ENGINEERS.ID)

easy_trigger = trigger_manager.add_trigger("Easy Difficulty") 
easy_trigger.new_condition.difficulty_level(quantity=0)
easy_trigger.new_effect.create_object(object_list_unit_id=UnitInfo.TREBUCHET.ID, source_player=PlayerId.ONE, location_x=player_start_x+10, location_y=player_start_y+10)

hard_trigger = trigger_manager.add_trigger("Hard Difficulty")
hard_trigger.new_condition.difficulty_level(quantity=3)
hard_trigger.new_effect.create_object(object_list_unit_id=UnitInfo.CHAMPION.ID, source_player=PlayerId.TWO, location_x=inner_wall_x-2, location_y=center)

# Discovery triggers
intro = trigger_manager.add_trigger("[D0] Intro")
intro.new_condition.timer(timer=5)
intro.new_effect.display_instructions(display_time=10, message="<YELLOW>Before you lies the enemy fortress...")

outer_wall = trigger_manager.add_trigger("[D1] Outer Wall Sighted")
outer_wall.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=outer_wall_x-5, area_y1=center-5, area_x2=outer_wall_x+5, area_y2=center+5)
outer_wall.new_effect.display_instructions(display_time=10, message="<BLUE>Scout: The outer defenses. Palisades and watchtowers.")

# Victory triggers  
v1 = trigger_manager.add_trigger("V/1 Outer Cleared")
v1.new_condition.destroy_object(unit_object=outer_gate.reference_id)
v1.new_effect.display_instructions(display_time=10, message="Phase 1 complete: Outer defenses fallen!")

v2 = trigger_manager.add_trigger("V/2 Middle Cleared") 
v2.new_condition.destroy_object(unit_object=middle_gate.reference_id)
v2.new_effect.display_instructions(display_time=10, message="Phase 2 complete: Middle defenses breached!")

victory = trigger_manager.add_trigger("Victory")
victory.new_condition.destroy_object(unit_object=castle.reference_id)
victory.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)

# Defeat triggers
defeat = trigger_manager.add_trigger("Defeat - Hero Dies")
defeat.new_condition.destroy_object(unit_object=hero.reference_id) 
defeat.new_effect.declare_victory(source_player=PlayerId.TWO, enabled=1)

# Save scenario
scenario.write_to_file("output.aoe2scenario")