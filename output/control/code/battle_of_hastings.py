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

# Create Senlac Hill battlefield
hill_y = map_size // 3  # Hill in upper third

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

# Player 1 (Normans) - William's forces
norman_y = three_quarter
william = unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.WILLIAM_THE_CONQUEROR.ID, x=center, y=norman_y)

# Norman army
for i in range(20):
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.KNIGHT.ID, x=center-10+i, y=norman_y+2)
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.ARCHER.ID, x=center-10+i, y=norman_y+4)

# Norman base
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.TOWN_CENTER.ID, x=center, y=norman_y+10)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BARRACKS.ID, x=center-10, y=norman_y+8)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.ARCHERY_RANGE.ID, x=center+10, y=norman_y+8)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.STABLE.ID, x=center, y=norman_y+8)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BLACKSMITH.ID, x=center+5, y=norman_y+12)

# Player 2 (Saxons) - Harold's forces
harold = unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.KING.ID, x=center, y=hill_y-3)

# Saxon shield wall
for i in range(30):
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.MAN_AT_ARMS.ID, x=center-15+i, y=hill_y-3)
    if i < 20:
        unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.SPEARMAN.ID, x=center-10+i, y=hill_y-4)

# Saxon base
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.TOWN_CENTER.ID, x=center, y=hill_y-10)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.BARRACKS.ID, x=center-15, y=hill_y-8)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.ARCHERY_RANGE.ID, x=center+15, y=hill_y-8)

# Add walls around Saxon position
for i in range(40):
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.PALISADE_WALL.ID, x=center-20+i, y=hill_y-6)
    
# Saxon-owned gates
saxon_gate1 = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, x=center-5, y=hill_y-6)
saxon_gate2 = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, x=center+5, y=hill_y-6)

# Add GAIA resources near Norman base
for i in range(5):
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.GOLD_MINE.ID, x=center-10+i, y=norman_y+15)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.STONE_MINE.ID, x=center+10+i, y=norman_y+15)
for i in range(8):
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.FORAGE_BUSH.ID, x=center-15+i, y=norman_y+18)
for i in range(6):
    unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.SHEEP.ID, x=center+i, y=norman_y+20)

# === TRIGGERS ===

# --- Setup Section ---
tech_trigger = trigger_manager.add_trigger("Techs")
tech_trigger.new_condition.timer(timer=1)
tech_trigger.new_effect.research_technology(source_player=PlayerId.ONE, technology=TechInfo.FORGING.ID)
tech_trigger.new_effect.research_technology(source_player=PlayerId.ONE, technology=TechInfo.SCALE_MAIL_ARMOR.ID)

walls_trigger = trigger_manager.add_trigger("Walls")
walls_trigger.new_condition.timer(timer=1)

easy_trigger = trigger_manager.add_trigger("Easy Difficulty")
easy_trigger.new_condition.difficulty_level(quantity=0)
easy_trigger.new_effect.kill_object(source_player=PlayerId.TWO, area_x1=0, area_y1=0, area_x2=map_size, area_y2=map_size)

hard_trigger = trigger_manager.add_trigger("Hardmode")
hard_trigger.new_condition.difficulty_level(quantity=3)
hard_trigger.new_effect.create_object(object_list_unit_id=UnitInfo.MAN_AT_ARMS.ID, source_player=PlayerId.TWO, location_x=center, location_y=hill_y-3)

gates_trigger = trigger_manager.add_trigger("Close Gates")
gates_trigger.new_condition.timer(timer=1)

# --- Dialogue Section ---
intro = trigger_manager.add_trigger("[D0] Intro")
intro.new_condition.timer(timer=5)
intro.new_effect.display_instructions(display_time=10, message="<YELLOW>Narrator: October 14, 1066. The armies of William of Normandy and Harold Godwinson meet at Senlac Hill.")

scout = trigger_manager.add_trigger("[D1] Scout Report")
scout.new_condition.timer(timer=15)
scout.new_effect.display_instructions(display_time=10, message="<BLUE>Scout: My lord, the Saxons hold the high ground with their shield wall.")

commander = trigger_manager.add_trigger("[D2] Commander Speech")
commander.new_condition.timer(timer=30)
commander.new_effect.display_instructions(display_time=10, message="<BLUE>William: We shall break their lines with our cavalry charges!")

taunt1 = trigger_manager.add_trigger("[D3] Enemy Taunt 1")
taunt1.new_condition.timer(timer=60)
taunt1.new_effect.display_instructions(display_time=10, message="<RED>Harold: Your Norman horses will break upon our shields!")

taunt2 = trigger_manager.add_trigger("[D4] Enemy Taunt 2")
taunt2.new_condition.timer(timer=120)
taunt2.new_effect.display_instructions(display_time=10, message="<RED>Harold: England will never bow to foreign rule!")

location1 = trigger_manager.add_trigger("[D5] At Location 1")
location1.new_condition.bring_object_to_area(unit_object=william.reference_id, area_x1=center-10, area_y1=hill_y, area_x2=center+10, area_y2=hill_y+10)

location2 = trigger_manager.add_trigger("[D6] At Location 2")
location2.new_condition.bring_object_to_area(unit_object=william.reference_id, area_x1=center-20, area_y1=hill_y-5, area_x2=center+20, area_y2=hill_y)

battle = trigger_manager.add_trigger("[D7] Battle Begins")
battle.new_condition.timer(timer=180)
battle.new_effect.display_instructions(display_time=10, message="<YELLOW>Narrator: The battle rages as Norman cavalry charge the Saxon lines!")

midpoint = trigger_manager.add_trigger("[D8] Midpoint Update")
midpoint.new_condition.timer(timer=300)
midpoint.new_effect.display_instructions(display_time=10, message="<YELLOW>Narrator: The shield wall holds firm against repeated assaults.")

weakening = trigger_manager.add_trigger("[D9] Enemy Weakening")
weakening.new_condition.objects_in_area(quantity=10, object_list=UnitInfo.MAN_AT_ARMS.ID, source_player=PlayerId.TWO, area_x1=0, area_y1=0, area_x2=map_size, area_y2=map_size)

final = trigger_manager.add_trigger("[D10] Final Push")
final.new_condition.timer(timer=420)
final.new_effect.display_instructions(display_time=10, message="<BLUE>William: One final charge! For Normandy!")

hero_falls = trigger_manager.add_trigger("[D11] Hero Falls")
hero_falls.new_condition.destroy_object(unit_object=william.reference_id)
hero_falls.new_effect.display_instructions(display_time=10, message="<YELLOW>William has fallen in battle!")

# --- Objective Section ---
objectives = trigger_manager.add_trigger("[O] Main Objectives")
objectives.new_condition.timer(timer=1)
objectives.new_effect.display_instructions(display_time=20, message="Objectives:\n-Defeat Harold and his Saxon army\n-William must survive\n-Capture the Saxon position on Senlac Hill")

primary = trigger_manager.add_trigger("[Obj] Primary Goal")
primary.new_condition.destroy_object(unit_object=harold.reference_id)

secondary = trigger_manager.add_trigger("[Obj] Secondary Goal")
secondary.new_condition.objects_in_area(quantity=1, object_list=UnitInfo.VILLAGER_MALE.ID, source_player=PlayerId.ONE, area_x1=center-20, area_y1=hill_y-10, area_x2=center+20, area_y2=hill_y)

survival = trigger_manager.add_trigger("[Obj] Survival")
survival.new_condition.timer(timer=1)
survival.new_effect.display_instructions(display_time=10, message="William must survive to claim victory!")

# --- Victory/Defeat Section ---
victory = trigger_manager.add_trigger("VC")
victory.new_condition.destroy_object(unit_object=harold.reference_id)
victory.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)

victory2 = trigger_manager.add_trigger("VC2")
victory2.new_condition.objects_in_area(quantity=20, object_list=UnitInfo.KNIGHT.ID, source_player=PlayerId.ONE, area_x1=center-20, area_y1=hill_y-10, area_x2=center+20, area_y2=hill_y)
victory2.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)

defeat = trigger_manager.add_trigger("Defeat")
defeat.new_condition.destroy_object(unit_object=william.reference_id)
defeat.new_effect.declare_victory(source_player=PlayerId.TWO, enabled=1)

defeat2 = trigger_manager.add_trigger("DEFEAT")
defeat2.new_condition.objects_in_area(quantity=0, object_list=BuildingInfo.TOWN_CENTER.ID, source_player=PlayerId.ONE, area_x1=0, area_y1=0, area_x2=map_size, area_y2=map_size)
defeat2.new_effect.declare_victory(source_player=PlayerId.TWO, enabled=1)

# --- Special Triggers ---
patrol = trigger_manager.add_trigger("Enemy Patrol")
patrol.new_condition.timer(timer=1)
patrol.new_effect.patrol(object_list_unit_id=UnitInfo.MAN_AT_ARMS.ID, source_player=PlayerId.TWO, location_x=center, location_y=hill_y+5)

sortie = trigger_manager.add_trigger("Enemy Sortie")
sortie.new_condition.objects_in_area(quantity=5, object_list=UnitInfo.KNIGHT.ID, source_player=PlayerId.ONE, area_x1=center-20, area_y1=hill_y-5, area_x2=center+20, area_y2=hill_y)

gate_defense = trigger_manager.add_trigger("Gate Defense")
gate_defense.new_condition.objects_in_area(quantity=1, object_list=UnitInfo.KNIGHT.ID, source_player=PlayerId.ONE, area_x1=center-10, area_y1=hill_y-5, area_x2=center+10, area_y2=hill_y)

# Save scenario
scenario.write_to_file("battle_of_hastings.aoe2scenario")