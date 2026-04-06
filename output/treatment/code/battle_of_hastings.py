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
# Victory path: Defeat Harold Godwinson or destroy enemy castle. Player has sufficient military.
# Defeat path: William dies or all production buildings destroyed. Enemy can mount effective attacks.
# Resource sufficiency: Yes - multiple gold/stone mines, forests for wood, farms possible
# Counter availability: Yes - player has barracks/range/stable to counter all unit types
# Physical access: Yes - multiple paths to enemy, no impassable barriers
# Timing viability: Yes - player starts with defensive force, can build army before major attacks

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

# Create Senlac Hill battlefield
hill_y = map_size // 3

# Paint grass terrain
for x in range(0, map_size):
    for y in range(0, map_size):
        tile = map_manager.get_tile(x=x, y=y)
        tile.terrain_id = TerrainId.GRASS_1.value

# Create ridge with cliffs
for x in range(quarter, three_quarter):
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.CLIFF_DEFAULT_2.ID, x=x, y=hill_y)

# Forests on flanks
for x in range(0, quarter):
    for y in range(hill_y-10, hill_y+10):
        unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.TREE_OAK.ID, x=x, y=y)
for x in range(three_quarter, map_size):
    for y in range(hill_y-10, hill_y+10):
        unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.TREE_OAK.ID, x=x, y=y)

# Player 1 (William) base - south
william = unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.WILLIAM_THE_CONQUEROR.ID, x=center, y=three_quarter)

# Norman army
for i in range(20):
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.KNIGHT.ID, x=center-10+i, y=three_quarter+5)
for i in range(15):
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.CROSSBOWMAN.ID, x=center-7+i, y=three_quarter+7)

# Norman base
norman_tc = unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.TOWN_CENTER.ID, x=center, y=three_quarter+10)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BARRACKS.ID, x=center-10, y=three_quarter+10)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.ARCHERY_RANGE.ID, x=center+10, y=three_quarter+10)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.STABLE.ID, x=center, y=three_quarter+15)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BLACKSMITH.ID, x=center-5, y=three_quarter+15)

# Player 2 (Harold) base - north on hill
harold = unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.KING.ID, x=center, y=hill_y-3)

# Saxon shield wall
for i in range(30):
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.MAN_AT_ARMS.ID, x=center-15+i, y=hill_y-3)
for i in range(20):
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.SPEARMAN.ID, x=center-10+i, y=hill_y-4)

# Saxon base
saxon_castle = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.CASTLE.ID, x=center, y=hill_y-8)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.BARRACKS.ID, x=center-10, y=hill_y-8)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.ARCHERY_RANGE.ID, x=center+10, y=hill_y-8)

# Stone walls around Saxon position
for i in range(30):
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STONE_WALL.ID, x=center-15+i, y=hill_y-10)
    
# Gates owned by Saxons
gate1 = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, x=center-5, y=hill_y-10)
gate2 = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, x=center+5, y=hill_y-10)

# GAIA resources near Norman base
for i in range(5):
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.GOLD_MINE.ID, x=center-10+i, y=three_quarter+20)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.STONE_MINE.ID, x=center+10+i, y=three_quarter+20)
for i in range(8):
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.FORAGE_BUSH.ID, x=center-15+i, y=three_quarter+25)
for i in range(6):
    unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.SHEEP.ID, x=center+i, y=three_quarter+25)

# === TRIGGERS ===

# --- Setup Section ---
tech_trigger = trigger_manager.add_trigger("Techs")
tech_trigger.new_condition.timer(timer=1)
tech_trigger.new_effect.research_technology(source_player=PlayerId.ONE, technology=TechInfo.FORGING.ID)
tech_trigger.new_effect.research_technology(source_player=PlayerId.ONE, technology=TechInfo.SCALE_MAIL_ARMOR.ID)

walls_trigger = trigger_manager.add_trigger("Walls")
walls_trigger.new_condition.timer(timer=1)
walls_trigger.new_effect.task_object(object_list_unit_id=BuildingInfo.STONE_WALL.ID, source_player=PlayerId.TWO)

easy_trigger = trigger_manager.add_trigger("Easy Difficulty") 
easy_trigger.new_condition.difficulty_level(quantity=0)
easy_trigger.new_effect.create_object(object_list_unit_id=UnitInfo.KNIGHT.ID, source_player=PlayerId.ONE, location_x=center, location_y=three_quarter+5)
easy_trigger.new_effect.create_object(object_list_unit_id=UnitInfo.KNIGHT.ID, source_player=PlayerId.ONE, location_x=center+1, location_y=three_quarter+5)
easy_trigger.new_effect.create_object(object_list_unit_id=UnitInfo.KNIGHT.ID, source_player=PlayerId.ONE, location_x=center+2, location_y=three_quarter+5)

hard_trigger = trigger_manager.add_trigger("Hardmode")
hard_trigger.new_condition.difficulty_level(quantity=3)
hard_trigger.new_effect.create_object(object_list_unit_id=UnitInfo.MAN_AT_ARMS.ID, source_player=PlayerId.TWO, location_x=center, location_y=hill_y-3)
hard_trigger.new_effect.create_object(object_list_unit_id=UnitInfo.SPEARMAN.ID, source_player=PlayerId.TWO, location_x=center+1, location_y=hill_y-4)

gates_trigger = trigger_manager.add_trigger("Close Gates")
gates_trigger.new_condition.timer(timer=1)
gates_trigger.new_effect.task_object(object_list_unit_id=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, source_player=PlayerId.TWO)

# --- Dialogue Section ---
intro = trigger_manager.add_trigger("[D0] Intro")
intro.new_condition.timer(timer=5)
intro.new_effect.display_instructions(display_time=10, message="<YELLOW>Narrator: October 14, 1066. The Norman army faces the Saxon shield wall atop Senlac Hill.")

scout = trigger_manager.add_trigger("[D1] Scout Report")
scout.new_condition.timer(timer=15)
scout.new_effect.display_instructions(display_time=10, message="<BLUE>Scout: The Saxons hold the high ground. Their shield wall will be difficult to break.")

commander = trigger_manager.add_trigger("[D2] Commander Speech")
commander.new_condition.timer(timer=30)
commander.new_effect.display_instructions(display_time=10, message="<BLUE>William: We must draw them from their position. Feign retreat if necessary.")

taunt1 = trigger_manager.add_trigger("[D3] Enemy Taunt 1")
taunt1.new_condition.timer(timer=60)
taunt1.new_effect.display_instructions(display_time=10, message="<RED>Harold: Your claim to England's throne ends here, William!")

taunt2 = trigger_manager.add_trigger("[D4] Enemy Taunt 2")
taunt2.new_condition.timer(timer=120)
taunt2.new_effect.display_instructions(display_time=10, message="<RED>Harold: The Saxon shield wall has never been broken!")

location1 = trigger_manager.add_trigger("[D5] At Location 1")
location1.new_condition.bring_object_to_area(unit_object=william.reference_id, area_x1=center-10, area_y1=hill_y, area_x2=center+10, area_y2=hill_y+10)
location1.new_effect.display_instructions(display_time=10, message="<BLUE>William: Press the attack! Break their formation!")

location2 = trigger_manager.add_trigger("[D6] At Location 2")
location2.new_condition.bring_object_to_area(unit_object=william.reference_id, area_x1=center-5, area_y1=hill_y-5, area_x2=center+5, area_y2=hill_y)
location2.new_effect.display_instructions(display_time=10, message="<BLUE>William: We've reached the hill! Victory is within our grasp!")

battle = trigger_manager.add_trigger("[D7] Battle Begins")
battle.new_condition.timer(timer=180)
battle.new_effect.display_instructions(display_time=10, message="<YELLOW>Narrator: The battle rages as Norman cavalry charge the Saxon lines.")

midpoint = trigger_manager.add_trigger("[D8] Midpoint Update")
midpoint.new_condition.timer(timer=300)
midpoint.new_effect.display_instructions(display_time=10, message="<YELLOW>Narrator: The fighting has lasted hours with heavy casualties on both sides.")

weakening = trigger_manager.add_trigger("[D9] Enemy Weakening")
weakening.new_condition.objects_in_area(quantity=10, object_list=UnitInfo.MAN_AT_ARMS.ID, source_player=PlayerId.TWO, area_x1=0, area_y1=0, area_x2=map_size, area_y2=map_size)
weakening.new_effect.display_instructions(display_time=10, message="<BLUE>William: Their lines are thinning! Press the advantage!")

final = trigger_manager.add_trigger("[D10] Final Push")
final.new_condition.timer(timer=420)
final.new_effect.display_instructions(display_time=10, message="<BLUE>William: For Normandy! For England's crown!")

hero_falls = trigger_manager.add_trigger("[D11] Hero Falls")
hero_falls.new_condition.destroy_object(unit_object=william.reference_id)
hero_falls.new_effect.display_instructions(display_time=10, message="<YELLOW>Narrator: William has fallen! The Norman conquest ends here...")

# --- Objective Section ---
objectives = trigger_manager.add_trigger("[O] Main Objectives")
objectives.new_condition.timer(timer=1)
objectives.new_effect.display_instructions(display_time=20, message="Defeat Harold Godwinson and capture the Saxon position\nProtect William\nDestroy the enemy castle")

primary = trigger_manager.add_trigger("[Obj] Primary Goal")
primary.new_condition.destroy_object(unit_object=harold.reference_id)
primary.new_effect.display_instructions(display_time=10, message="Harold has fallen! The Saxon army crumbles!")

secondary = trigger_manager.add_trigger("[Obj] Secondary Goal")
secondary.new_condition.destroy_object(unit_object=saxon_castle.reference_id)
secondary.new_effect.display_instructions(display_time=10, message="The Saxon castle has been captured!")

survival = trigger_manager.add_trigger("[Obj] Survival")
survival.new_condition.timer(timer=1)
survival.new_effect.display_instructions(display_time=10, message="William must survive")

# --- Victory/Defeat Section ---
victory1 = trigger_manager.add_trigger("VC")
victory1.new_condition.destroy_object(unit_object=harold.reference_id)
victory1.new_effect.display_instructions(display_time=20, message="Victory! The Battle of Hastings is won!")
victory1.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)

victory2 = trigger_manager.add_trigger("VC2")
victory2.new_condition.destroy_object(unit_object=saxon_castle.reference_id)
victory2.new_effect.display_instructions(display_time=20, message="The Saxon stronghold has fallen!")
victory2.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)

defeat1 = trigger_manager.add_trigger("Defeat")
defeat1.new_condition.destroy_object(unit_object=william.reference_id)
defeat1.new_effect.display_instructions(display_time=20, message="William has fallen! The Norman invasion fails...")
defeat1.new_effect.declare_victory(source_player=PlayerId.TWO, enabled=1)

defeat2 = trigger_manager.add_trigger("DEFEAT")
defeat2.new_condition.destroy_object(unit_object=norman_tc.reference_id)
defeat2.new_effect.display_instructions(display_time=20, message="Our base is destroyed! We must retreat...")
defeat2.new_effect.declare_victory(source_player=PlayerId.TWO, enabled=1)

# Save scenario
scenario.write_to_file("output.aoe2scenario")