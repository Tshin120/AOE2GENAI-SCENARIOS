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

# Create the pass terrain
# Sea on right side
for x in range(three_quarter, map_size):
    for y in range(0, map_size):
        tile = map_manager.get_tile(x=x, y=y)
        tile.terrain_id = TerrainId.WATER_DEEP.value

# Mountains on left using cliffs
for x in range(0, quarter):
    for y in range(0, map_size, 2):
        unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.CLIFF_DEFAULT_3.ID, x=x, y=y)

# Create the narrow pass (Hot Gates)
pass_center_x = center
pass_width = 10

# Place Spartan forces
spartan_x = pass_center_x - 5
spartan_y = center - 10

# Store hero reference
leonidas = unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.LEONIDAS.ID, x=spartan_x, y=spartan_y)

# Spartan warriors in phalanx formation
for i in range(8):
    for j in range(3):
        unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.SPEARMAN.ID, x=spartan_x-2+i, y=spartan_y+j)

# Persian army (Player TWO)
persian_x = pass_center_x
persian_y = center + 20

# Store enemy leader
darius = unit_manager.add_unit(PlayerId.TWO, unit_const=HeroInfo.DARIUS.ID, x=persian_x, y=persian_y+10)

# Persian troops
for i in range(10):
    for j in range(5):
        unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.IMMORTAL_MELEE.ID, x=persian_x-5+i, y=persian_y+j)
        unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.IMMORTAL_RANGED.ID, x=persian_x-5+i, y=persian_y+j+6)

# Persian base
persian_base_x = persian_x 
persian_base_y = persian_y + 30

# Persian buildings
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.CASTLE.ID, x=persian_base_x, y=persian_base_y)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.BARRACKS.ID, x=persian_base_x-10, y=persian_base_y)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.ARCHERY_RANGE.ID, x=persian_base_x+10, y=persian_base_y)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STABLE.ID, x=persian_base_x, y=persian_base_y+10)

# Persian base walls
for i in range(20):
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STONE_WALL.ID, x=persian_base_x-10+i, y=persian_base_y+15)
    
# Persian gate (owned by Persians)
persian_gate = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, x=persian_base_x, y=persian_base_y+15)

# Greek camp
greek_x = spartan_x
greek_y = spartan_y - 20

unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.TOWN_CENTER.ID, x=greek_x, y=greek_y)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BARRACKS.ID, x=greek_x-5, y=greek_y)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BLACKSMITH.ID, x=greek_x+5, y=greek_y)

# GAIA resources near Greek camp
for i in range(5):
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.GOLD_MINE.ID, x=greek_x-10+i, y=greek_y-5)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.STONE_MINE.ID, x=greek_x-8+i, y=greek_y-8)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.FORAGE_BUSH.ID, x=greek_x+8+i, y=greek_y-3)

# === TRIGGERS ===

# --- Setup Section (5 triggers) ---
tech_trigger = trigger_manager.add_trigger("Techs")
tech_trigger.new_condition.timer(timer=1)
tech_trigger.new_effect.research_technology(source_player=PlayerId.ONE, technology=TechInfo.FORGING.ID)
tech_trigger.new_effect.research_technology(source_player=PlayerId.ONE, technology=TechInfo.SCALE_MAIL_ARMOR.ID)

walls_trigger = trigger_manager.add_trigger("Walls")
walls_trigger.new_condition.timer(timer=1)

easy_trigger = trigger_manager.add_trigger("Easy Difficulty")
easy_trigger.new_condition.difficulty_level(quantity=0)
easy_trigger.new_effect.kill_object(source_player=PlayerId.TWO, area_x1=persian_x-20, area_y1=persian_y-20, area_x2=persian_x+20, area_y2=persian_y+20)

hard_trigger = trigger_manager.add_trigger("Hardmode")
hard_trigger.new_condition.difficulty_level(quantity=3)
hard_trigger.new_effect.create_object(object_list_unit_id=UnitInfo.IMMORTAL_MELEE.ID, source_player=PlayerId.TWO, location_x=persian_x, location_y=persian_y)

gates_trigger = trigger_manager.add_trigger("Close Gates")
gates_trigger.new_condition.timer(timer=1)

# --- Dialogue Section (12 triggers) ---
intro = trigger_manager.add_trigger("[D0] Intro")
intro.new_condition.timer(timer=5)
intro.new_effect.display_instructions(display_time=10, message="<YELLOW>Narrator: The mighty Persian army approaches the pass of Thermopylae...")

scout = trigger_manager.add_trigger("[D1] Scout Report")
scout.new_condition.timer(timer=15)
scout.new_effect.display_instructions(display_time=10, message="<BLUE>Scout: My king, the Persians number in the thousands!")

speech = trigger_manager.add_trigger("[D2] Commander Speech")
speech.new_condition.timer(timer=30)
speech.new_effect.display_instructions(display_time=10, message="<BLUE>Leonidas: Spartans! Tonight we dine in hell!")

taunt1 = trigger_manager.add_trigger("[D3] Enemy Taunt 1")
taunt1.new_condition.timer(timer=60)
taunt1.new_effect.display_instructions(display_time=10, message="<RED>Darius: Lay down your weapons!")

taunt2 = trigger_manager.add_trigger("[D4] Enemy Taunt 2")
taunt2.new_condition.timer(timer=120)
taunt2.new_effect.display_instructions(display_time=10, message="<RED>Darius: Your resistance is futile!")

location1 = trigger_manager.add_trigger("[D5] At Location 1")
location1.new_condition.bring_object_to_area(unit_object=leonidas.reference_id, area_x1=pass_center_x-5, area_y1=center-5, area_x2=pass_center_x+5, area_y2=center+5)

location2 = trigger_manager.add_trigger("[D6] At Location 2")
location2.new_condition.bring_object_to_area(unit_object=leonidas.reference_id, area_x1=persian_x-10, area_y1=persian_y-10, area_x2=persian_x+10, area_y2=persian_y+10)

battle = trigger_manager.add_trigger("[D7] Battle Begins")
battle.new_condition.timer(timer=180)
battle.new_effect.display_instructions(display_time=10, message="<YELLOW>The battle for Thermopylae begins!")

update = trigger_manager.add_trigger("[D8] Midpoint Update")
update.new_condition.timer(timer=300)
update.new_effect.display_instructions(display_time=10, message="<YELLOW>The Spartans hold firm against the Persian tide!")

weak = trigger_manager.add_trigger("[D9] Enemy Weakening")
weak.new_condition.objects_in_area(quantity=10, object_list=UnitInfo.IMMORTAL_MELEE.ID, source_player=PlayerId.TWO, area_x1=0, area_y1=0, area_x2=map_size, area_y2=map_size)

push = trigger_manager.add_trigger("[D10] Final Push")
push.new_condition.timer(timer=420)
push.new_effect.display_instructions(display_time=10, message="<YELLOW>The final Persian assault begins!")

hero_falls = trigger_manager.add_trigger("[D11] Hero Falls")
hero_falls.new_condition.destroy_object(unit_object=leonidas.reference_id)
hero_falls.new_effect.display_instructions(display_time=10, message="<YELLOW>Leonidas has fallen!")

# --- Objective Section (4 triggers) ---
objectives = trigger_manager.add_trigger("[O] Main Objectives")
objectives.new_condition.timer(timer=1)
objectives.new_effect.display_instructions(display_time=20, message="Defend the pass of Thermopylae against the Persian army!")

primary = trigger_manager.add_trigger("[Obj] Primary Goal")
primary.new_condition.destroy_object(unit_object=darius.reference_id)

secondary = trigger_manager.add_trigger("[Obj] Secondary Goal")
secondary.new_condition.objects_in_area(quantity=50, object_list=UnitInfo.IMMORTAL_MELEE.ID, source_player=PlayerId.TWO, area_x1=0, area_y1=0, area_x2=map_size, area_y2=map_size)

survival = trigger_manager.add_trigger("[Obj] Survival")
survival.new_condition.timer(timer=1)
survival.new_effect.display_instructions(display_time=10, message="Leonidas must survive!")

# --- Victory/Defeat Section (4 triggers) ---
victory = trigger_manager.add_trigger("VC")
victory.new_condition.destroy_object(unit_object=darius.reference_id)
victory.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)

victory2 = trigger_manager.add_trigger("VC2")
victory2.new_condition.timer(timer=900)
victory2.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)

defeat = trigger_manager.add_trigger("Defeat")
defeat.new_condition.destroy_object(unit_object=leonidas.reference_id)
defeat.new_effect.declare_victory(source_player=PlayerId.TWO, enabled=1)

defeat2 = trigger_manager.add_trigger("DEFEAT")
defeat2.new_condition.objects_in_area(quantity=0, object_list=UnitInfo.SPEARMAN.ID, source_player=PlayerId.ONE, area_x1=0, area_y1=0, area_x2=map_size, area_y2=map_size)
defeat2.new_effect.declare_victory(source_player=PlayerId.TWO, enabled=1)

# Save scenario
scenario.write_to_file("thermopylae.aoe2scenario")