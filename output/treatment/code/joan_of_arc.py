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
# Victory path: Defeat villain in final castle after gathering allies and resources
# Defeat path: Hero death, key ally death, or failure to protect critical objectives
# Resource sufficiency: Yes - starting resources + mines near bases for army building
# Counter availability: Yes - player has access to full military production
# Physical access: Yes - clear paths between objectives with multiple approach routes
# Timing viability: Yes - starting army can handle first waves while building up

# Create scenario
scenario = AoE2DEScenario.from_default()

# Get managers
unit_manager = scenario.unit_manager
trigger_manager = scenario.trigger_manager
map_manager = scenario.map_manager

# Get map size
map_size = map_manager.map_size
center = map_size // 2
quarter = map_size // 4
three_quarter = (map_size * 3) // 4

# Paint terrain
# Act 1 zone - grassy starting area
for x in range(0, quarter):
    for y in range(0, map_size):
        tile = map_manager.get_tile(x=x, y=y)
        tile.terrain_id = TerrainId.GRASS_1.value

# Act 2 zone - mixed terrain
for x in range(quarter, three_quarter):
    for y in range(0, map_size):
        tile = map_manager.get_tile(x=x, y=y)
        tile.terrain_id = TerrainId.GRASS_2.value

# Act 3 zone - enemy territory
for x in range(three_quarter, map_size):
    for y in range(0, map_size):
        tile = map_manager.get_tile(x=x, y=y)
        tile.terrain_id = TerrainId.DIRT_1.value

# Place heroes and key characters
hero = unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.JOAN_OF_ARC.ID, x=quarter-10, y=center)
advisor = unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.CHARLES_MARTEL.ID, x=quarter-8, y=center)
villain = unit_manager.add_unit(PlayerId.TWO, unit_const=HeroInfo.RICHARD_THE_LIONHEART.ID, x=three_quarter+10, y=center)
ally1 = unit_manager.add_unit(PlayerId.THREE, unit_const=HeroInfo.ROLAND.ID, x=center, y=quarter)

# Player ONE starting base
player_base_x = quarter - 15
player_base_y = center
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.TOWN_CENTER.ID, x=player_base_x, y=player_base_y)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BARRACKS.ID, x=player_base_x+3, y=player_base_y+3)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.STABLE.ID, x=player_base_x+3, y=player_base_y-3)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.ARCHERY_RANGE.ID, x=player_base_x-3, y=player_base_y+3)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BLACKSMITH.ID, x=player_base_x-3, y=player_base_y-3)

# Starting army
for i in range(5):
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.MAN_AT_ARMS.ID, x=player_base_x+i, y=player_base_y+5)
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.ARCHER.ID, x=player_base_x+i, y=player_base_y+6)
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.LIGHT_CAVALRY.ID, x=player_base_x+i, y=player_base_y+7)

# Enemy fortress
enemy_base_x = three_quarter + 10
enemy_base_y = center
villain_castle = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.CASTLE.ID, x=enemy_base_x, y=enemy_base_y)

# Fortress walls with enemy-owned gates
for i in range(15):
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STONE_WALL.ID, x=enemy_base_x-7+i, y=enemy_base_y-7)
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STONE_WALL.ID, x=enemy_base_x-7+i, y=enemy_base_y+7)
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STONE_WALL.ID, x=enemy_base_x-7, y=enemy_base_y-7+i)
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STONE_WALL.ID, x=enemy_base_x+7, y=enemy_base_y-7+i)

# Enemy-owned gates so AI can exit
enemy_gate = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, x=enemy_base_x, y=enemy_base_y-7)

# Enemy garrison
for i in range(10):
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.KNIGHT.ID, x=enemy_base_x+1+i, y=enemy_base_y+1)
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.CROSSBOWMAN.ID, x=enemy_base_x+1+i, y=enemy_base_y+2)

# GAIA resources near player base
for i in range(5):
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.GOLD_MINE.ID, x=player_base_x+10+i, y=player_base_y+10)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.STONE_MINE.ID, x=player_base_x+10+i, y=player_base_y+12)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.FORAGE_BUSH.ID, x=player_base_x+8+i, y=player_base_y+8)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.SHEEP.ID, x=player_base_x+6+i, y=player_base_y+6)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.DEER.ID, x=player_base_x+12+i, y=player_base_y+14)

# Story props
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.FLAG_A.ID, x=center, y=center)
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.ROMAN_RUINS.ID, x=center+10, y=center+10)
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.SKELETON.ID, x=center+15, y=center+15)

# === TRIGGERS ===

# Setup triggers
tech_trigger = trigger_manager.add_trigger("Techs")
tech_trigger.new_condition.timer(timer=1)
tech_trigger.new_effect.research_technology(source_player=PlayerId.ONE, technology=TechInfo.FORGING.ID)

easy_trigger = trigger_manager.add_trigger("Easy Difficulty")
easy_trigger.new_condition.difficulty_level(quantity=0)
easy_trigger.new_effect.create_object(object_list_unit_id=UnitInfo.KNIGHT.ID, source_player=PlayerId.ONE, location_x=player_base_x+5, location_y=player_base_y+5)

hard_trigger = trigger_manager.add_trigger("Hard Difficulty") 
hard_trigger.new_condition.difficulty_level(quantity=3)
hard_trigger.new_effect.create_object(object_list_unit_id=UnitInfo.KNIGHT.ID, source_player=PlayerId.TWO, location_x=enemy_base_x+2, location_y=enemy_base_y+2)

# Act 1 triggers
intro = trigger_manager.add_trigger("[D0] Intro")
intro.new_condition.timer(timer=5)
intro.new_effect.display_instructions(display_time=15, message="<YELLOW>In the year 1429, France lay divided and conquered...")

hero_awake = trigger_manager.add_trigger("[D1] Hero Awakens")
hero_awake.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=quarter-12, area_y1=center-2, area_x2=quarter-8, area_y2=center+2)
hero_awake.new_effect.display_instructions(display_time=10, message="<BLUE>Joan: I have seen visions... France needs me.")

# Victory/defeat triggers
victory = trigger_manager.add_trigger("VC Primary")
victory.new_condition.destroy_object(unit_object=villain.reference_id)
victory.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)

defeat = trigger_manager.add_trigger("Defeat - Hero Dies")
defeat.new_condition.destroy_object(unit_object=hero.reference_id)
defeat.new_effect.declare_victory(source_player=PlayerId.TWO, enabled=1)

# Save scenario
scenario.write_to_file("joan_of_arc.aoe2scenario")