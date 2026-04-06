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

# Paint terrain - hills in center where Franks defend
for x in range(quarter, three_quarter):
    for y in range(quarter-10, quarter+10):
        unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.CLIFF_DEFAULT_2.ID, x=x, y=y)

# Forests on flanks
for x in range(0, quarter):
    for y in range(0, map_size, 2):
        unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.TREE_OAK.ID, x=x, y=y)
        
for x in range(three_quarter, map_size):
    for y in range(0, map_size, 2):
        unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.TREE_OAK.ID, x=x, y=y)

# Player 1 (Franks) base
frank_base_x = quarter
frank_base_y = quarter-15

# Main buildings
tc = unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.TOWN_CENTER.ID, x=frank_base_x, y=frank_base_y)
barracks = unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BARRACKS.ID, x=frank_base_x-5, y=frank_base_y)
range_bld = unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.ARCHERY_RANGE.ID, x=frank_base_x+5, y=frank_base_y)
stable = unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.STABLE.ID, x=frank_base_x, y=frank_base_y-5)
blacksmith = unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BLACKSMITH.ID, x=frank_base_x+5, y=frank_base_y-5)

# Player 1 hero and army
hero = unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.RICHARD_THE_LIONHEART.ID, x=frank_base_x, y=frank_base_y+5)

# Frank army
for i in range(10):
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.MAN_AT_ARMS.ID, x=frank_base_x-5+i, y=frank_base_y+8)
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.CROSSBOWMAN.ID, x=frank_base_x-5+i, y=frank_base_y+10)
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.KNIGHT.ID, x=frank_base_x-5+i, y=frank_base_y+12)

# Player 2 (Umayyad) base
enemy_base_x = three_quarter
enemy_base_y = three_quarter

# Enemy buildings
enemy_tc = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.TOWN_CENTER.ID, x=enemy_base_x, y=enemy_base_y)
enemy_castle = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.CASTLE.ID, x=enemy_base_x+5, y=enemy_base_y)

# Enemy walls and gates
for i in range(15):
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STONE_WALL.ID, x=enemy_base_x-7+i, y=enemy_base_y-7)
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STONE_WALL.ID, x=enemy_base_x-7+i, y=enemy_base_y+7)
    
enemy_gate = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, x=enemy_base_x, y=enemy_base_y-7)

# Enemy leader and army
enemy_leader = unit_manager.add_unit(PlayerId.TWO, unit_const=HeroInfo.SALADIN.ID, x=enemy_base_x, y=enemy_base_y+5)

# Umayyad army
for i in range(15):
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.CAVALRY_ARCHER.ID, x=enemy_base_x-7+i, y=enemy_base_y+10)
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.CAMEL_RIDER.ID, x=enemy_base_x-7+i, y=enemy_base_y+12)
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.LIGHT_CAVALRY.ID, x=enemy_base_x-7+i, y=enemy_base_y+14)

# GAIA resources near Frank base
for i in range(5):
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.GOLD_MINE.ID, x=frank_base_x-10+i, y=frank_base_y-10)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.STONE_MINE.ID, x=frank_base_x-10+i, y=frank_base_y-12)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.FORAGE_BUSH.ID, x=frank_base_x-5+i, y=frank_base_y-8)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.SHEEP.ID, x=frank_base_x+i, y=frank_base_y-15)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.DEER.ID, x=frank_base_x+5+i, y=frank_base_y-15)

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
hard_trigger.new_effect.create_object(object_list_unit_id=UnitInfo.CAVALRY_ARCHER.ID, source_player=PlayerId.TWO, location_x=enemy_base_x, location_y=enemy_base_y)

gates_trigger = trigger_manager.add_trigger("Close Gates")
gates_trigger.new_condition.timer(timer=1)

# --- Dialogue Section ---
intro = trigger_manager.add_trigger("[D0] Intro")
intro.new_condition.timer(timer=5)
intro.new_effect.display_instructions(display_time=10, message="<YELLOW>Narrator: The Umayyad army advances into Francia. Charles Martel must stop them at Tours.")

scout = trigger_manager.add_trigger("[D1] Scout Report")
scout.new_condition.timer(timer=15)
scout.new_effect.display_instructions(display_time=10, message="<BLUE>Scout: My lord, the Saracen army approaches from the south.")

commander = trigger_manager.add_trigger("[D2] Commander Speech")
commander.new_condition.timer(timer=30)
commander.new_effect.display_instructions(display_time=10, message="<BLUE>Charles Martel: Hold the high ground. We will break their cavalry charge.")

taunt1 = trigger_manager.add_trigger("[D3] Enemy Taunt 1")
taunt1.new_condition.timer(timer=60)
taunt1.new_effect.display_instructions(display_time=10, message="<RED>Abdul Rahman: Your lands will fall to the Caliphate!")

taunt2 = trigger_manager.add_trigger("[D4] Enemy Taunt 2")
taunt2.new_condition.timer(timer=120)
taunt2.new_effect.display_instructions(display_time=10, message="<RED>Abdul Rahman: Charge! Break their lines!")

location1 = trigger_manager.add_trigger("[D5] At Location 1")
location1.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=quarter, area_y1=quarter, area_x2=center, area_y2=center)
location1.new_effect.display_instructions(display_time=10, message="<BLUE>We must hold this position!")

location2 = trigger_manager.add_trigger("[D6] At Location 2")
location2.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=center, area_y1=center, area_x2=three_quarter, area_y2=three_quarter)
location2.new_effect.display_instructions(display_time=10, message="<BLUE>The enemy main force approaches!")

battle = trigger_manager.add_trigger("[D7] Battle Begins")
battle.new_condition.timer(timer=180)
battle.new_effect.display_instructions(display_time=10, message="<YELLOW>The armies clash on the field of Tours!")

midpoint = trigger_manager.add_trigger("[D8] Midpoint Update")
midpoint.new_condition.timer(timer=300)
midpoint.new_effect.display_instructions(display_time=10, message="<YELLOW>The battle hangs in the balance!")

weak = trigger_manager.add_trigger("[D9] Enemy Weakening")
weak.new_condition.objects_in_area(quantity=10, object_list=UnitInfo.CAVALRY_ARCHER.ID, source_player=PlayerId.TWO, area_x1=0, area_y1=0, area_x2=map_size, area_y2=map_size)
weak.new_effect.display_instructions(display_time=10, message="<BLUE>Their army falters! Press the attack!")

final = trigger_manager.add_trigger("[D10] Final Push")
final.new_condition.timer(timer=420)
final.new_effect.display_instructions(display_time=10, message="<YELLOW>Victory or defeat will be decided here!")

hero_falls = trigger_manager.add_trigger("[D11] Hero Falls")
hero_falls.new_condition.destroy_object(unit_object=hero.reference_id)
hero_falls.new_effect.display_instructions(display_time=10, message="<YELLOW>Charles Martel has fallen! All is lost!")

# --- Objective Section ---
objectives = trigger_manager.add_trigger("[O] Main Objectives")
objectives.new_condition.timer(timer=1)
objectives.new_effect.display_instructions(display_time=20, message="Defeat the Umayyad army and their leader Abdul Rahman")

primary = trigger_manager.add_trigger("[Obj] Primary Goal")
primary.new_condition.destroy_object(unit_object=enemy_leader.reference_id)
primary.new_effect.display_instructions(display_time=10, message="Abdul Rahman is slain! Victory is near!")

secondary = trigger_manager.add_trigger("[Obj] Secondary Goal")
secondary.new_condition.destroy_object(unit_object=enemy_castle.reference_id)
secondary.new_effect.display_instructions(display_time=10, message="The enemy castle has fallen!")

survival = trigger_manager.add_trigger("[Obj] Survival")
survival.new_condition.timer(timer=1)
survival.new_effect.display_instructions(display_time=10, message="Charles Martel must survive")

# --- Victory/Defeat Section ---
victory = trigger_manager.add_trigger("VC")
victory.new_condition.destroy_object(unit_object=enemy_leader.reference_id)
victory.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)

victory2 = trigger_manager.add_trigger("VC2")
victory2.new_condition.timer(timer=900)
victory2.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)

defeat = trigger_manager.add_trigger("Defeat")
defeat.new_condition.destroy_object(unit_object=hero.reference_id)
defeat.new_effect.declare_victory(source_player=PlayerId.TWO, enabled=1)

defeat2 = trigger_manager.add_trigger("DEFEAT")
defeat2.new_condition.destroy_object(unit_object=tc.reference_id)
defeat2.new_effect.declare_victory(source_player=PlayerId.TWO, enabled=1)

# --- Special Triggers ---
patrol = trigger_manager.add_trigger("Enemy Patrol")
patrol.new_condition.timer(timer=60)
patrol.new_effect.patrol(object_list_unit_id=UnitInfo.CAVALRY_ARCHER.ID, source_player=PlayerId.TWO, location_x=quarter, location_y=quarter)

attack = trigger_manager.add_trigger("Enemy Attack")
attack.new_condition.timer(timer=300)
attack.new_effect.patrol(object_list_unit_id=UnitInfo.CAMEL_RIDER.ID, source_player=PlayerId.TWO, location_x=frank_base_x, location_y=frank_base_y)

# Save scenario
scenario.write_to_file("output.aoe2scenario")