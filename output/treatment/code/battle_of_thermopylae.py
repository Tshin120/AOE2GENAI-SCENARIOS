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
# Victory path: Defeat Persian army by killing enemy leader or destroying their base
# Defeat path: Hero dies or all Spartan units killed
# Resource sufficiency: Yes - starting army + resources for reinforcements
# Counter availability: Yes - mix of infantry/archers vs Persian cavalry/archers
# Physical access: Yes - narrow pass with tactical positioning
# Timing viability: Yes - initial forces can hold pass while building up

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

# Create Thermopylae terrain
# Sea on right side (east)
for x in range(three_quarter, map_size):
    for y in range(0, map_size):
        tile = map_manager.get_tile(x=x, y=y)
        tile.terrain_id = TerrainId.WATER_DEEP.value

# Mountains on left (west)
for x in range(0, quarter):
    for y in range(0, map_size):
        unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.CLIFF_DEFAULT_3.ID, x=x, y=y)

# Narrow pass in middle
pass_width = 10
pass_x = center
pass_y = center

# Place Spartan forces (Player 1)
# Store hero reference for triggers
hero = unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.BELISARIUS.ID, x=pass_x, y=pass_y)

# Spartan phalanx
for i in range(10):
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.PIKEMAN.ID, x=pass_x-5+i, y=pass_y)
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.PIKEMAN.ID, x=pass_x-5+i, y=pass_y+1)

# Spartan archers behind
for i in range(8):
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.ARCHER.ID, x=pass_x-4+i, y=pass_y+3)

# Spartan base
tc = unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.TOWN_CENTER.ID, x=pass_x-15, y=pass_y)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BARRACKS.ID, x=pass_x-20, y=pass_y-5)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.ARCHERY_RANGE.ID, x=pass_x-20, y=pass_y+5)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BLACKSMITH.ID, x=pass_x-25, y=pass_y)

# Persian forces (Player 2)
# Store enemy leader reference
enemy_leader = unit_manager.add_unit(PlayerId.TWO, unit_const=HeroInfo.TAMERLANE.ID, x=pass_x+30, y=pass_y)

# Persian army
for i in range(20):
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.CAVALRY_ARCHER.ID, x=pass_x+25+i%5, y=pass_y-5+i//5)
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.KNIGHT.ID, x=pass_x+35+i%5, y=pass_y-5+i//5)

# Persian base
enemy_tc = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.TOWN_CENTER.ID, x=pass_x+40, y=pass_y)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STABLE.ID, x=pass_x+45, y=pass_y-5)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.ARCHERY_RANGE.ID, x=pass_x+45, y=pass_y+5)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.CASTLE.ID, x=pass_x+50, y=pass_y)

# Add resources
for i in range(5):
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.GOLD_MINE.ID, x=pass_x-30+i, y=pass_y-10)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.STONE_MINE.ID, x=pass_x-30+i, y=pass_y+10)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.FORAGE_BUSH.ID, x=pass_x-35+i, y=pass_y)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.SHEEP.ID, x=pass_x-40+i, y=pass_y)

# TRIGGERS

# Setup triggers
techs = trigger_manager.add_trigger("Techs")
techs.new_condition.timer(timer=1)
techs.new_effect.research_technology(source_player=PlayerId.ONE, technology=TechInfo.FORGING.ID)
techs.new_effect.research_technology(source_player=PlayerId.ONE, technology=TechInfo.SCALE_MAIL_ARMOR.ID)

walls = trigger_manager.add_trigger("Walls")
walls.new_condition.timer(timer=1)
walls.new_effect.create_object(object_list_unit_id=BuildingInfo.STONE_WALL.ID, source_player=PlayerId.ONE, location_x=pass_x-10, location_y=pass_y-5)

easy = trigger_manager.add_trigger("Easy Difficulty")
easy.new_condition.difficulty_level(quantity=0)
easy.new_effect.create_object(object_list_unit_id=UnitInfo.PIKEMAN.ID, source_player=PlayerId.ONE, location_x=pass_x, location_y=pass_y)

hard = trigger_manager.add_trigger("Hardmode")
hard.new_condition.difficulty_level(quantity=3)
hard.new_effect.create_object(object_list_unit_id=UnitInfo.KNIGHT.ID, source_player=PlayerId.TWO, location_x=pass_x+30, location_y=pass_y)

gates = trigger_manager.add_trigger("Close Gates")
gates.new_condition.timer(timer=1)
gates.new_effect.task_object(source_player=PlayerId.ONE, object_list_unit_id=BuildingInfo.GATE_NORTH_TO_SOUTH.ID)

# Dialogue triggers
d0 = trigger_manager.add_trigger("[D0] Intro")
d0.new_condition.timer(timer=5)
d0.new_effect.display_instructions(display_time=10, message="<YELLOW>Narrator: The mighty Persian army approaches the pass of Thermopylae...")

d1 = trigger_manager.add_trigger("[D1] Scout Report") 
d1.new_condition.timer(timer=15)
d1.new_effect.display_instructions(display_time=10, message="<BLUE>Scout: My king, their numbers are vast!")

d2 = trigger_manager.add_trigger("[D2] Commander Speech")
d2.new_condition.timer(timer=30)
d2.new_effect.display_instructions(display_time=10, message="<BLUE>Leonidas: Then we shall fight in the shade!")

d3 = trigger_manager.add_trigger("[D3] Enemy Taunt 1")
d3.new_condition.timer(timer=60)
d3.new_effect.display_instructions(display_time=10, message="<RED>Persian Commander: Lay down your weapons!")

d4 = trigger_manager.add_trigger("[D4] Enemy Taunt 2")
d4.new_condition.timer(timer=120)
d4.new_effect.display_instructions(display_time=10, message="<RED>Persian Commander: Your resistance is futile!")

d5 = trigger_manager.add_trigger("[D5] At Location 1")
d5.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=pass_x-5, area_y1=pass_y-5, area_x2=pass_x+5, area_y2=pass_y+5)
d5.new_effect.display_instructions(display_time=10, message="<BLUE>Leonidas: Hold the line!")

d6 = trigger_manager.add_trigger("[D6] At Location 2")
d6.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=pass_x+10, area_y1=pass_y-5, area_x2=pass_x+20, area_y2=pass_y+5)
d6.new_effect.display_instructions(display_time=10, message="<BLUE>Leonidas: Push them back!")

d7 = trigger_manager.add_trigger("[D7] Battle Begins")
d7.new_condition.timer(timer=180)
d7.new_effect.display_instructions(display_time=10, message="<YELLOW>The Persian army launches its assault!")

d8 = trigger_manager.add_trigger("[D8] Midpoint Update")
d8.new_condition.timer(timer=300)
d8.new_effect.display_instructions(display_time=10, message="<YELLOW>The battle rages on!")

d9 = trigger_manager.add_trigger("[D9] Enemy Weakening")
d9.new_condition.objects_in_area(quantity=10, object_list=UnitInfo.KNIGHT.ID, source_player=PlayerId.TWO, area_x1=0, area_y1=0, area_x2=map_size, area_y2=map_size)
d9.new_effect.display_instructions(display_time=10, message="<YELLOW>The Persian army begins to falter!")

d10 = trigger_manager.add_trigger("[D10] Final Push")
d10.new_condition.timer(timer=420)
d10.new_effect.display_instructions(display_time=10, message="<BLUE>Leonidas: For Sparta!")

d11 = trigger_manager.add_trigger("[D11] Hero Falls")
d11.new_condition.destroy_object(unit_object=hero.reference_id)
d11.new_effect.display_instructions(display_time=10, message="<YELLOW>Leonidas has fallen!")

# Objective triggers
obj_main = trigger_manager.add_trigger("[O] Main Objectives")
obj_main.new_condition.timer(timer=1)
obj_main.new_effect.display_instructions(display_time=20, message="Objectives:\n-Defend the pass of Thermopylae\n-Defeat the Persian army")

obj_primary = trigger_manager.add_trigger("[Obj] Primary Goal")
obj_primary.new_condition.destroy_object(unit_object=enemy_leader.reference_id)
obj_primary.new_effect.display_instructions(display_time=10, message="The Persian commander has fallen!")

obj_secondary = trigger_manager.add_trigger("[Obj] Secondary Goal")
obj_secondary.new_condition.objects_in_area(quantity=30, object_list=UnitInfo.KNIGHT.ID, source_player=PlayerId.TWO, area_x1=0, area_y1=0, area_x2=map_size, area_y2=map_size)
obj_secondary.new_effect.display_instructions(display_time=10, message="Bonus: Kill 30 Persian cavalry")

obj_survival = trigger_manager.add_trigger("[Obj] Survival")
obj_survival.new_condition.timer(timer=1)
obj_survival.new_effect.display_instructions(display_time=10, message="Leonidas must survive!")

# Victory/Defeat triggers
vc = trigger_manager.add_trigger("VC")
vc.new_condition.destroy_object(unit_object=enemy_leader.reference_id)
vc.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)

vc2 = trigger_manager.add_trigger("VC2")
vc2.new_condition.destroy_object(unit_object=enemy_tc.reference_id)
vc2.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)

defeat = trigger_manager.add_trigger("Defeat")
defeat.new_condition.destroy_object(unit_object=hero.reference_id)
defeat.new_effect.declare_victory(source_player=PlayerId.TWO, enabled=1)

defeat2 = trigger_manager.add_trigger("DEFEAT")
defeat2.new_condition.destroy_object(unit_object=tc.reference_id)
defeat2.new_effect.declare_victory(source_player=PlayerId.TWO, enabled=1)

# Save scenario
scenario.write_to_file("thermopylae.aoe2scenario")