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

# Create new scenario
scenario = AoE2DEScenario.from_default()

# Get managers
unit_manager = scenario.unit_manager
trigger_manager = scenario.trigger_manager
map_manager = scenario.map_manager

# Get map size and calculate positions
map_size = map_manager.map_size
center = map_size // 2
quarter = map_size // 4
three_quarter = (map_size * 3) // 4

# Player starting position (bottom left)
player_start_x = quarter
player_start_y = three_quarter

# Enemy fortress positions
outer_wall_x = center - 20
outer_wall_y = center - 20
middle_wall_x = center - 10  
middle_wall_y = center - 10
inner_wall_x = center
inner_wall_y = center

# Create hero unit and store reference
hero = unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.EL_CID.ID, x=player_start_x, y=player_start_y)

# Player starting army
for i in range(15):
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.CHAMPION.ID, x=player_start_x+i, y=player_start_y+2)
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.CROSSBOWMAN.ID, x=player_start_x+i, y=player_start_y+3)
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.KNIGHT.ID, x=player_start_x+i, y=player_start_y+4)

# Player forward base
player_base_x = player_start_x + 10
player_base_y = player_start_y - 10
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BARRACKS.ID, x=player_base_x, y=player_base_y)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.ARCHERY_RANGE.ID, x=player_base_x+4, y=player_base_y)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BLACKSMITH.ID, x=player_base_x+8, y=player_base_y)

# Outer defenses
outer_gate = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, x=outer_wall_x, y=outer_wall_y)
for i in range(30):
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.PALISADE_WALL.ID, x=outer_wall_x+i, y=outer_wall_y)
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.PALISADE_WALL.ID, x=outer_wall_x+i, y=outer_wall_y+20)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.WATCH_TOWER.ID, x=outer_wall_x+5, y=outer_wall_y+2)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.WATCH_TOWER.ID, x=outer_wall_x+15, y=outer_wall_y+2)

# Middle defenses  
middle_gate = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, x=middle_wall_x, y=middle_wall_y)
for i in range(40):
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STONE_WALL.ID, x=middle_wall_x+i, y=middle_wall_y)
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STONE_WALL.ID, x=middle_wall_x+i, y=middle_wall_y+15)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GUARD_TOWER.ID, x=middle_wall_x+8, y=middle_wall_y+2)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GUARD_TOWER.ID, x=middle_wall_x+16, y=middle_wall_y+2)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GUARD_TOWER.ID, x=middle_wall_x+24, y=middle_wall_y+2)

# Inner fortress
castle = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.CASTLE.ID, x=inner_wall_x, y=inner_wall_y)
inner_gate = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, x=inner_wall_x-5, y=inner_wall_y)
enemy_lord = unit_manager.add_unit(PlayerId.TWO, unit_const=HeroInfo.SALADIN.ID, x=inner_wall_x+2, y=inner_wall_y+2)

unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.KEEP.ID, x=inner_wall_x+8, y=inner_wall_y+8)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.KEEP.ID, x=inner_wall_x-8, y=inner_wall_y+8)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.TOWN_CENTER.ID, x=inner_wall_x+5, y=inner_wall_y+5)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.MONASTERY.ID, x=inner_wall_x+10, y=inner_wall_y+10)

# GAIA siege equipment
trebuchet = unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.TREBUCHET.ID, x=outer_wall_x-10, y=outer_wall_y+10)
ram1 = unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.BATTERING_RAM.ID, x=outer_wall_x-12, y=outer_wall_y+12)
ram2 = unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.BATTERING_RAM.ID, x=middle_wall_x-10, y=middle_wall_y+10)

# Setup triggers
tech_trigger = trigger_manager.add_trigger("Techs")
tech_trigger.new_condition.timer(timer=1)
tech_trigger.new_effect.research_technology(source_player=PlayerId.ONE, technology=TechInfo.SIEGE_ENGINEERS.ID)

easy_trigger = trigger_manager.add_trigger("Easy Difficulty") 
easy_trigger.new_condition.difficulty_level(quantity=0)
easy_trigger.new_effect.kill_object(source_player=PlayerId.TWO, area_x1=0, area_y1=0, area_x2=map_size, area_y2=map_size)

hard_trigger = trigger_manager.add_trigger("Hard Difficulty")
hard_trigger.new_condition.difficulty_level(quantity=3)
hard_trigger.new_effect.create_object(object_list_unit_id=UnitInfo.CHAMPION.ID, source_player=PlayerId.TWO, location_x=inner_wall_x, location_y=inner_wall_y)

patrol_trigger = trigger_manager.add_trigger("Enemy Patrol Setup")
patrol_trigger.new_condition.timer(timer=1)
patrol_trigger.new_effect.patrol(object_list_unit_id=UnitInfo.KNIGHT.ID, source_player=PlayerId.TWO, location_x=outer_wall_x, location_y=outer_wall_y)

reveal_trigger = trigger_manager.add_trigger("Map Reveal")
reveal_trigger.new_condition.timer(timer=1)

start_trigger = trigger_manager.add_trigger("Starting Grant")
start_trigger.new_condition.timer(timer=1)
start_trigger.new_effect.create_object(object_list_unit_id=UnitInfo.VILLAGER_MALE.ID, source_player=PlayerId.ONE, location_x=player_start_x, location_y=player_start_y)

# Discovery triggers
intro = trigger_manager.add_trigger("[D0] Intro")
intro.new_condition.timer(timer=5)
intro.new_effect.display_instructions(display_time=10, message="<YELLOW>Before you lies the enemy fortress...")

outer_sight = trigger_manager.add_trigger("[D1] Outer Wall Sighted")
outer_sight.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=outer_wall_x-5, area_y1=outer_wall_y-5, area_x2=outer_wall_x+5, area_y2=outer_wall_y+5)
outer_sight.new_effect.display_instructions(display_time=10, message="<BLUE>Scout: The outer defenses. Palisades and watchtowers.")

weak_point = trigger_manager.add_trigger("[D2] Find Weak Point")
weak_point.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=outer_wall_x+15, area_y1=outer_wall_y-5, area_x2=outer_wall_x+20, area_y2=outer_wall_y+5)
weak_point.new_effect.display_instructions(display_time=10, message="<BLUE>Scout: This section looks weaker than the rest.")

siege_found = trigger_manager.add_trigger("[D3] Siege Equipment Found")
siege_found.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=trebuchet.x-2, area_y1=trebuchet.y-2, area_x2=trebuchet.x+2, area_y2=trebuchet.y+2)
siege_found.new_effect.display_instructions(display_time=10, message="<BLUE>Scout: Abandoned siege weapons! We can use these!")

middle_sight = trigger_manager.add_trigger("[D4] Middle Wall Sighted")
middle_sight.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=middle_wall_x-5, area_y1=middle_wall_y-5, area_x2=middle_wall_x+5, area_y2=middle_wall_y+5)
middle_sight.new_effect.display_instructions(display_time=10, message="<BLUE>Scout: Stone walls ahead. This will be harder.")

gate_spot = trigger_manager.add_trigger("[D5] Gate Spotted")
gate_spot.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=middle_gate.x-2, area_y1=middle_gate.y-2, area_x2=middle_gate.x+2, area_y2=middle_gate.y+2)
gate_spot.new_effect.display_instructions(display_time=10, message="<BLUE>Scout: A fortified gate. We'll need rams to break through.")

defenders = trigger_manager.add_trigger("[D6] Defenders Rally")
defenders.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=middle_wall_x-10, area_y1=middle_wall_y-10, area_x2=middle_wall_x+10, area_y2=middle_wall_y+10)
defenders.new_effect.display_instructions(display_time=10, message="<RED>Enemy Commander: Reinforce the inner walls! Hold them!")

inner_sight = trigger_manager.add_trigger("[D7] Inner Fortress Sighted")
inner_sight.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=castle.x-10, area_y1=castle.y-10, area_x2=castle.x+10, area_y2=castle.y+10)
inner_sight.new_effect.display_instructions(display_time=10, message="<YELLOW>The inner fortress looms before you...")

final_def = trigger_manager.add_trigger("[D8] Final Defenses")
final_def.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=castle.x-5, area_y1=castle.y-5, area_x2=castle.x+5, area_y2=castle.y+5)
final_def.new_effect.display_instructions(display_time=10, message="<RED>Enemy Lord: You will die at my gates!")

lord_spot = trigger_manager.add_trigger("[D9] Enemy Lord Spotted")
lord_spot.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=enemy_lord.x-3, area_y1=enemy_lord.y-3, area_x2=enemy_lord.x+3, area_y2=enemy_lord.y+3)
lord_spot.new_effect.display_instructions(display_time=10, message="<BLUE>Scout: The enemy lord is there! Destroy him and victory is ours!")

# Capture triggers
siege1_cap = trigger_manager.add_trigger("Capture Siege 1")
siege1_cap.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=trebuchet.x-2, area_y1=trebuchet.y-2, area_x2=trebuchet.x+2, area_y2=trebuchet.y+2)
siege1_cap.new_effect.change_ownership(source_player=PlayerId.GAIA, target_player=PlayerId.ONE, area_x1=trebuchet.x-2, area_y1=trebuchet.y-2, area_x2=trebuchet.x+2, area_y2=trebuchet.y+2)

siege2_cap = trigger_manager.add_trigger("Capture Siege 2")
siege2_cap.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=ram1.x-2, area_y1=ram1.y-2, area_x2=ram1.x+2, area_y2=ram1.y+2)
siege2_cap.new_effect.change_ownership(source_player=PlayerId.GAIA, target_player=PlayerId.ONE, area_x1=ram1.x-2, area_y1=ram1.y-2, area_x2=ram1.x+2, area_y2=ram1.y+2)

siege3_cap = trigger_manager.add_trigger("Capture Siege 3")
siege3_cap.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=ram2.x-2, area_y1=ram2.y-2, area_x2=ram2.x+2, area_y2=ram2.y+2)
siege3_cap.new_effect.change_ownership(source_player=PlayerId.GAIA, target_player=PlayerId.ONE, area_x1=ram2.x-2, area_y1=ram2.y-2, area_x2=ram2.x+2, area_y2=ram2.y+2)

outpost_cap = trigger_manager.add_trigger("Capture Outpost")
outpost_cap.new_condition.objects_in_area(quantity=0, object_list=UnitInfo.CHAMPION.ID, source_player=PlayerId.TWO, area_x1=outer_wall_x-10, area_y1=outer_wall_y-10, area_x2=outer_wall_x+10, area_y2=outer_wall_y+10)
outpost_cap.new_effect.display_instructions(display_time=10, message="The outpost is ours! Use it to reinforce.")

barracks_cap = trigger_manager.add_trigger("Capture Barracks")
barracks_cap.new_condition.objects_in_area(quantity=0, object_list=UnitInfo.CHAMPION.ID, source_player=PlayerId.TWO, area_x1=middle_wall_x-10, area_y1=middle_wall_y-10, area_x2=middle_wall_x+10, area_y2=middle_wall_y+10)
barracks_cap.new_effect.display_instructions(display_time=10, message="Enemy barracks captured! Train reinforcements.")

outer_control = trigger_manager.add_trigger("Control Outer Zone")
outer_control.new_condition.objects_in_area(quantity=0, object_list=UnitInfo.CHAMPION.ID, source_player=PlayerId.TWO, area_x1=outer_wall_x-20, area_y1=outer_wall_y-20, area_x2=outer_wall_x+20, area_y2=outer_wall_y+20)
outer_control.new_effect.display_instructions(display_time=10, message="Outer defenses secured!")

middle_control = trigger_manager.add_trigger("Control Middle Zone")
middle_control.new_condition.objects_in_area(quantity=0, object_list=UnitInfo.CHAMPION.ID, source_player=PlayerId.TWO, area_x1=middle_wall_x-20, area_y1=middle_wall_y-20, area_x2=middle_wall_x+20, area_y2=middle_wall_y+20)
middle_control.new_effect.display_instructions(display_time=10, message="Middle defenses secured!")

inner_control = trigger_manager.add_trigger("Control Inner Zone")
inner_control.new_condition.objects_in_area(quantity=0, object_list=UnitInfo.CHAMPION.ID, source_player=PlayerId.TWO, area_x1=inner_wall_x-20, area_y1=inner_wall_y-20, area_x2=inner_wall_x+20, area_y2=inner_wall_y+20)
inner_control.new_effect.display_instructions(display_time=10, message="Inner courtyard secured! Only the keep remains!")

# Gate/Breach triggers
outer_breach = trigger_manager.add_trigger("Outer Gate Breached")
outer_breach.new_condition.destroy_object(unit_object=outer_gate.reference_id)
outer_breach.new_effect.display_instructions(display_time=10, message="The outer gate has fallen!")

outer_wall = trigger_manager.add_trigger("Outer Wall Breached")
outer_wall.new_condition.destroy_object(unit_object=outer_gate.reference_id)
outer_wall.new_effect.display_instructions(display_time=10, message="A breach in the outer wall! Pour through!")

middle_breach = trigger_manager.add_trigger("Middle Gate Breached")
middle_breach.new_condition.destroy_object(unit_object=middle_gate.reference_id)
middle_breach.new_effect.display_instructions(display_time=10, message="The stone gate crumbles!")

middle_wall = trigger_manager.add_trigger("Middle Wall Section Down")
middle_wall.new_condition.destroy_object(unit_object=middle_gate.reference_id)
middle_wall.new_effect.display_instructions(display_time=10, message="The wall is breached!")

inner_breach = trigger_manager.add_trigger("Inner Gate Breached")
inner_breach.new_condition.destroy_object(unit_object=inner_gate.reference_id)
inner_breach.new_effect.display_instructions(display_time=10, message="<YELLOW>The final gate is down! Storm the keep!")

castle_siege = trigger_manager.add_trigger("Castle Under Siege")
castle_siege.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=castle.x-5, area_y1=castle.y-5, area_x2=castle.x+5, area_y2=castle.y+5)
castle_siege.new_effect.display_instructions(display_time=10, message="Attack the castle! End this!")

# Victory triggers
v1 = trigger_manager.add_trigger("V/1 Outer Cleared")
v1.new_condition.destroy_object(unit_object=outer_gate.reference_id)
v1.new_effect.display_instructions(display_time=10, message="Phase 1 complete: Outer defenses fallen!")

v2 = trigger_manager.add_trigger("V/2 Siege Captured")
v2.new_condition.objects_in_area(quantity=2, object_list=UnitInfo.TREBUCHET.ID, source_player=PlayerId.ONE, area_x1=0, area_y1=0, area_x2=map_size, area_y2=map_size)
v2.new_effect.display_instructions(display_time=10, message="Siege equipment secured!")

v3 = trigger_manager.add_trigger("V/3 Middle Cleared")
v3.new_condition.destroy_object(unit_object=middle_gate.reference_id)
v3.new_effect.display_instructions(display_time=10, message="Phase 2 complete: Middle defenses breached!")

v4 = trigger_manager.add_trigger("V/4 Inner Breached")
v4.new_condition.destroy_object(unit_object=inner_gate.reference_id)
v4.new_effect.display_instructions(display_time=10, message="Phase 3 complete: The keep is exposed!")

v5 = trigger_manager.add_trigger("V/5 Commander Killed")
v5.new_condition.destroy_object(unit_object=enemy_lord.reference_id)
v5.new_effect.display_instructions(display_time=10, message="<YELLOW>The enemy lord has fallen!")

v6 = trigger_manager.add_trigger("V/6 Castle Destroyed")
v6.new_condition.destroy_object(unit_object=castle.reference_id)
v6.new_effect.display_instructions(display_time=10, message="The castle crumbles!")

victory = trigger_manager.add_trigger("Victory Primary")
victory.new_condition.destroy_object(unit_object=castle.reference_id)
victory.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)

victory_complete = trigger_manager.add_trigger("Victory Complete")
victory_complete.new_condition.destroy_object(unit_object=enemy_lord.reference_id)
victory_complete.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)

# Objective triggers
obj_main = trigger_manager.add_trigger("[O] Main Objectives")
obj_main.new_condition.timer(timer=1)
obj_main.new_effect.display_instructions(display_time=20, message="Breach the enemy fortress and destroy their stronghold.\n1. Break through the outer defenses\n2. Breach the middle walls\n3. Storm the inner keep and destroy the castle")

obj_outer = trigger_manager.add_trigger("[Obj] Outer Cleared")
obj_outer.new_condition.destroy_object(unit_object=outer_gate.reference_id)
obj_outer.new_effect.display_instructions(display_time=10, message="Outer defenses cleared! Press forward!")

obj_middle = trigger_manager.add_trigger("[Obj] Middle Cleared")
obj_middle.new_condition.destroy_object(unit_object=middle_gate.reference_id)
obj_middle.new_effect.display_instructions(display_time=10, message="Middle defenses breached! The keep awaits!")

obj_siege = trigger_manager.add_trigger("[Obj] Optional - Capture All Siege")
obj_siege.new_condition.objects_in_area(quantity=3, object_list=UnitInfo.TREBUCHET.ID, source_player=PlayerId.ONE, area_x1=0, area_y1=0, area_x2=map_size, area_y2=map_size)
obj_siege.new_effect.display_instructions(display_time=10, message="OPTIONAL: All siege equipment captured!")

obj_losses = trigger_manager.add_trigger("[Obj] Optional - Minimal Losses")
obj_losses.new_condition.objects_in_area(quantity=20, object_list=UnitInfo.CHAMPION.ID, source_player=PlayerId.ONE, area_x1=0, area_y1=0, area_x2=map_size, area_y2=map_size)
obj_losses.new_effect.display_instructions(display_time=10, message="OPTIONAL: Victory with minimal casualties!")

# Defeat triggers
defeat_hero = trigger_manager.add_trigger("Defeat - Hero Dies")
defeat_hero.new_condition.destroy_object(unit_object=hero.reference_id)
defeat_hero.new_effect.declare_victory(source_player=PlayerId.TWO, enabled=1)

defeat_army = trigger_manager.add_trigger("Defeat - Army Destroyed")
defeat_army.new_condition.objects_in_area(quantity=0, object_list=UnitInfo.CHAMPION.ID, source_player=PlayerId.ONE, area_x1=0, area_y1=0, area_x2=map_size, area_y2=map_size)
defeat_army.new_effect.declare_victory(source_player=PlayerId.TWO, enabled=1)

defeat_siege = trigger_manager.add_trigger("Defeat - Siege Lost")
defeat_siege.new_condition.objects_in_area(quantity=0, object_list=UnitInfo.TREBUCHET.ID, source_player=PlayerId.ONE, area_x1=0, area_y1=0, area_x2=map_size, area_y2=map_size)
defeat_siege.new_effect.display_instructions(display_time=10, message="All siege equipment lost! You cannot breach the walls!")

death_msg = trigger_manager.add_trigger("[D_] Hero Death Message")
death_msg.new_condition.destroy_object(unit_object=hero.reference_id)
death_msg.new_effect.display_instructions(display_time=10, message="<YELLOW>Our leader has fallen...")

# Save scenario
scenario.write_to_file("output.aoe2scenario")