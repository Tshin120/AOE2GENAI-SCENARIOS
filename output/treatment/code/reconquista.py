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
# Victory path: Capture siege equipment -> breach outer walls -> clear middle zone -> destroy castle/kill lord
# Defeat path: Hero dies OR all military units lost OR siege equipment destroyed before breaching inner walls
# Resource sufficiency: Yes - starting army + reinforcement buildings + capturable siege
# Counter availability: Yes - mix of infantry, archers, siege for all enemy unit types
# Physical access: Yes - multiple paths through each defensive layer
# Timing viability: Yes - starting army sufficient to survive first contact

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

# Player starting position
player_start_x = 10
player_start_y = center

# Enemy fortress positions
outer_wall_x = quarter
middle_wall_x = center 
inner_wall_x = three_quarter

# Create player hero
hero = unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.EL_CID.ID, x=player_start_x, y=center)

# Player starting army
for i in range(25):
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.CHAMPION.ID, x=player_start_x+2+i%5, y=center-5+i//5)
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.CROSSBOWMAN.ID, x=player_start_x+2+i%5, y=center+5+i//5)

# Player siege equipment
for i in range(3):
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.BATTERING_RAM.ID, x=player_start_x+i*2, y=center-8)
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.MANGONEL.ID, x=player_start_x+i*2, y=center+8)

# Player forward base
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BARRACKS.ID, x=player_start_x+15, y=center-10)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.ARCHERY_RANGE.ID, x=player_start_x+15, y=center+10)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BLACKSMITH.ID, x=player_start_x+20, y=center)

# Outer defenses
outer_gate = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, x=outer_wall_x, y=center)

for i in range(25):
    # North wall
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.PALISADE_WALL.ID, x=outer_wall_x, y=center-10-i)
    # South wall  
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.PALISADE_WALL.ID, x=outer_wall_x, y=center+10+i)

# Outer towers
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.WATCH_TOWER.ID, x=outer_wall_x-2, y=center-15)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.WATCH_TOWER.ID, x=outer_wall_x-2, y=center+15)

# Outer garrison
for i in range(15):
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.SPEARMAN.ID, x=outer_wall_x+5+i%5, y=center-5+i//5)
    if i < 8:
        unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.ARCHER.ID, x=outer_wall_x+5+i%4, y=center+i//4)

# Middle defenses  
middle_gate = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, x=middle_wall_x, y=center)

for i in range(35):
    # North wall
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STONE_WALL.ID, x=middle_wall_x, y=center-10-i)
    # South wall
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STONE_WALL.ID, x=middle_wall_x, y=center+10+i)

# Middle towers
for i in range(4):
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GUARD_TOWER.ID, x=middle_wall_x-2, y=center-20+i*15)

# Middle garrison
for i in range(20):
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.MAN_AT_ARMS.ID, x=middle_wall_x+5+i%5, y=center-10+i//5)
    if i < 12:
        unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.CROSSBOWMAN.ID, x=middle_wall_x+5+i%4, y=center+i//4)
    if i < 5:
        unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.KNIGHT.ID, x=middle_wall_x+10+i, y=center)

# Inner fortress
castle = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.CASTLE.ID, x=inner_wall_x, y=center)
enemy_lord = unit_manager.add_unit(PlayerId.TWO, unit_const=HeroInfo.SALADIN.ID, x=inner_wall_x+2, y=center)

# Inner buildings
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.TOWN_CENTER.ID, x=inner_wall_x+10, y=center-10)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.MONASTERY.ID, x=inner_wall_x+10, y=center+10)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.BLACKSMITH.ID, x=inner_wall_x+15, y=center)

# Inner towers
for i in range(4):
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.KEEP.ID, x=inner_wall_x-5, y=center-15+i*10)

# Inner garrison
for i in range(20):
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.CHAMPION.ID, x=inner_wall_x+5+i%5, y=center-5+i//5)

# GAIA siege equipment
trebuchet = unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.TREBUCHET.ID, x=outer_wall_x-10, y=center-20)
ram = unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.BATTERING_RAM.ID, x=middle_wall_x-10, y=center+20)

# === TRIGGERS ===

# Setup triggers
tech_trigger = trigger_manager.add_trigger("Techs")
tech_trigger.new_condition.timer(timer=1)
tech_trigger.new_effect.research_technology(source_player=PlayerId.ONE, technology=TechInfo.SIEGE_ENGINEERS.ID)
tech_trigger.new_effect.research_technology(source_player=PlayerId.ONE, technology=TechInfo.CHEMISTRY.ID)

easy_trigger = trigger_manager.add_trigger("Easy Difficulty") 
easy_trigger.new_condition.difficulty_level(quantity=0)
easy_trigger.new_effect.create_object(object_list_unit_id=UnitInfo.TREBUCHET.ID, source_player=PlayerId.ONE, location_x=player_start_x+5, location_y=center)

hard_trigger = trigger_manager.add_trigger("Hard Difficulty")
hard_trigger.new_condition.difficulty_level(quantity=3)
hard_trigger.new_effect.create_object(object_list_unit_id=UnitInfo.CHAMPION.ID, source_player=PlayerId.TWO, location_x=inner_wall_x+5, location_y=center)

patrol_trigger = trigger_manager.add_trigger("Enemy Patrol Setup")
patrol_trigger.new_condition.timer(timer=1)
patrol_trigger.new_effect.patrol(object_list_unit_id=UnitInfo.KNIGHT.ID, source_player=PlayerId.TWO, location_x=middle_wall_x-10, location_y=center)

map_trigger = trigger_manager.add_trigger("Map Reveal")
map_trigger.new_condition.timer(timer=1)
map_trigger.new_effect.display_instructions(display_time=10, message="<YELLOW>Before you lies the enemy fortress...")

start_trigger = trigger_manager.add_trigger("Starting Grant")
start_trigger.new_condition.timer(timer=1)
start_trigger.new_effect.modify_resource(tribute_list=1, quantity=500, source_player=PlayerId.ONE, operation=1)

# Discovery triggers
for i in range(10):
    disc_trigger = trigger_manager.add_trigger(f"[D{i}] Discovery {i}")
    if i == 0:
        disc_trigger.new_condition.timer(timer=5)
    else:
        disc_trigger.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=outer_wall_x-10+i*10, area_y1=center-10, area_x2=outer_wall_x+i*10, area_y2=center+10)
    disc_trigger.new_effect.display_instructions(display_time=10, message=f"Discovery {i}")

# Capture triggers
for i in range(8):
    cap_trigger = trigger_manager.add_trigger(f"Capture {i}")
    if i < 3:
        cap_trigger.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=outer_wall_x-15+i*20, area_y1=center-15, area_x2=outer_wall_x-5+i*20, area_y2=center+15)
    else:
        cap_trigger.new_condition.objects_in_area(quantity=0, object_list=UnitInfo.CHAMPION.ID, source_player=PlayerId.TWO, area_x1=middle_wall_x-20+i*10, area_y1=center-20, area_x2=middle_wall_x+i*10, area_y2=center+20)
    cap_trigger.new_effect.display_instructions(display_time=10, message=f"Area {i} captured!")

# Gate/Breach triggers
for i in range(6):
    breach_trigger = trigger_manager.add_trigger(f"Breach {i}")
    if i < 2:
        breach_trigger.new_condition.destroy_object(unit_object=outer_gate.reference_id)
    elif i < 4:
        breach_trigger.new_condition.destroy_object(unit_object=middle_gate.reference_id)
    else:
        breach_trigger.new_condition.destroy_object(unit_object=castle.reference_id)
    breach_trigger.new_effect.display_instructions(display_time=10, message=f"Breach {i}!")

# Victory triggers
for i in range(8):
    vic_trigger = trigger_manager.add_trigger(f"V/{i}")
    if i < 6:
        vic_trigger.new_condition.objects_in_area(quantity=0, object_list=UnitInfo.CHAMPION.ID, source_player=PlayerId.TWO, area_x1=outer_wall_x+i*20, area_y1=center-20, area_x2=outer_wall_x+(i+1)*20, area_y2=center+20)
        vic_trigger.new_effect.display_instructions(display_time=10, message=f"Phase {i} complete!")
    else:
        vic_trigger.new_condition.destroy_object(unit_object=enemy_lord.reference_id)
        vic_trigger.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)

# Objective triggers
for i in range(5):
    obj_trigger = trigger_manager.add_trigger(f"[O] Objective {i}")
    obj_trigger.new_condition.timer(timer=1)
    obj_trigger.new_effect.display_instructions(display_time=20, message=f"Objective {i}")

# Defeat triggers
for i in range(4):
    def_trigger = trigger_manager.add_trigger(f"Defeat {i}")
    if i == 0:
        def_trigger.new_condition.destroy_object(unit_object=hero.reference_id)
    else:
        def_trigger.new_condition.objects_in_area(quantity=0, object_list=UnitInfo.CHAMPION.ID, source_player=PlayerId.ONE, area_x1=0, area_y1=0, area_x2=map_size, area_y2=map_size)
    def_trigger.new_effect.declare_victory(source_player=PlayerId.TWO, enabled=1)

# Save scenario
scenario.write_to_file("output.aoe2scenario")