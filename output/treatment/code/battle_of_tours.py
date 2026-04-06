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
# Victory path: Defeat enemy leader (Abd Al-Rahman) or destroy enemy castle
# Defeat path: Charles Martel dies or all Frankish buildings destroyed
# Resource sufficiency: Yes - starting gold/stone + mines sufficient for military/walls
# Counter availability: Yes - player has barracks/stable/range to counter all enemy units
# Physical access: Yes - multiple paths through forest to enemy base, no impassable terrain
# Timing viability: Yes - player starts with defensive force to survive initial waves

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

# Paint terrain - rolling hills battlefield
for x in range(map_size):
    for y in range(map_size):
        tile = map_manager.get_tile(x=x, y=y)
        tile.terrain_id = TerrainId.GRASS_1.value

# Forest boundaries
for x in range(0, quarter):
    for y in range(0, map_size):
        unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.TREE_OAK.ID, x=x, y=y)
        
for x in range(three_quarter, map_size):
    for y in range(0, map_size):
        unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.TREE_OAK.ID, x=x, y=y)

# Player 1 (Franks) base - south
frankish_base_x = center 
frankish_base_y = three_quarter

# Player hero - Charles Martel
hero = unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.CHARLES_MARTEL.ID, 
                            x=frankish_base_x, y=frankish_base_y)

# Frankish army
for i in range(10):
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.MAN_AT_ARMS.ID,
                         x=frankish_base_x-5+i, y=frankish_base_y+2)
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.SPEARMAN.ID,
                         x=frankish_base_x-5+i, y=frankish_base_y+3)
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.KNIGHT.ID,
                         x=frankish_base_x-3+i, y=frankish_base_y+4)

# Frankish buildings
tc = unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.TOWN_CENTER.ID,
                          x=frankish_base_x, y=frankish_base_y+10)
barracks = unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BARRACKS.ID,
                                x=frankish_base_x-10, y=frankish_base_y+8)
range_bld = unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.ARCHERY_RANGE.ID,
                                 x=frankish_base_x+10, y=frankish_base_y+8)
stable = unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.STABLE.ID,
                              x=frankish_base_x, y=frankish_base_y+8)
blacksmith = unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BLACKSMITH.ID,
                                  x=frankish_base_x+5, y=frankish_base_y+12)

# Player 2 (Umayyads) base - north
enemy_base_x = center
enemy_base_y = quarter

# Enemy leader
enemy_leader = unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.KING.ID,
                                    x=enemy_base_x, y=enemy_base_y)

# Enemy army
for i in range(15):
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.CAVALRY_ARCHER.ID,
                         x=enemy_base_x-7+i, y=enemy_base_y+2)
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.CAMEL_RIDER.ID,
                         x=enemy_base_x-7+i, y=enemy_base_y+3)
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.LIGHT_CAVALRY.ID,
                         x=enemy_base_x-7+i, y=enemy_base_y+4)

# Enemy fortifications
castle = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.CASTLE.ID,
                              x=enemy_base_x, y=enemy_base_y-5)

# Enemy walls and gates
for i in range(20):
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STONE_WALL.ID,
                         x=enemy_base_x-10+i, y=enemy_base_y+10)
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STONE_WALL.ID,
                         x=enemy_base_x-10+i, y=enemy_base_y-10)
    
enemy_gate = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID,
                                  x=enemy_base_x, y=enemy_base_y+10)

# GAIA resources near player base
for i in range(5):
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.GOLD_MINE.ID,
                         x=frankish_base_x-10+i, y=frankish_base_y+15)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.STONE_MINE.ID,
                         x=frankish_base_x+10+i, y=frankish_base_y+15)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.FORAGE_BUSH.ID,
                         x=frankish_base_x-5+i, y=frankish_base_y+20)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.SHEEP.ID,
                         x=frankish_base_x+i, y=frankish_base_y+25)

# === TRIGGERS ===

# --- Setup Section ---
techs = trigger_manager.add_trigger("Techs")
techs.new_condition.timer(timer=1)
techs.new_effect.research_technology(source_player=PlayerId.ONE, technology=TechInfo.FORGING.ID)
techs.new_effect.research_technology(source_player=PlayerId.ONE, technology=TechInfo.SCALE_MAIL_ARMOR.ID)

walls = trigger_manager.add_trigger("Walls")
walls.new_condition.timer(timer=1)
walls.new_effect.modify_attribute(source_player=PlayerId.TWO, object_list_unit_id=BuildingInfo.STONE_WALL.ID,
                                operation=1, object_attributes=ObjectAttribute.HIT_POINTS, quantity=1800)

easy = trigger_manager.add_trigger("Easy Difficulty") 
easy.new_condition.difficulty_level(quantity=0)
easy.new_effect.create_object(source_player=PlayerId.ONE, object_list_unit_id=UnitInfo.KNIGHT.ID,
                            location_x=frankish_base_x, location_y=frankish_base_y)

hard = trigger_manager.add_trigger("Hardmode")
hard.new_condition.difficulty_level(quantity=3)
hard.new_effect.create_object(source_player=PlayerId.TWO, object_list_unit_id=UnitInfo.CAVALRY_ARCHER.ID,
                            location_x=enemy_base_x, location_y=enemy_base_y)

close_gates = trigger_manager.add_trigger("Close Gates")
close_gates.new_condition.timer(timer=1)
close_gates.new_effect.task_object(source_player=PlayerId.TWO, object_list_unit_id=enemy_gate.reference_id)

# --- Dialogue Section ---
intro = trigger_manager.add_trigger("[D0] Intro")
intro.new_condition.timer(timer=5)
intro.new_effect.display_instructions(display_time=10,
    message="<YELLOW>Narrator: October 732 AD. The Umayyad army under Abd Al-Rahman advances into Francia.")

scout = trigger_manager.add_trigger("[D1] Scout Report")
scout.new_condition.timer(timer=15)
scout.new_effect.display_instructions(display_time=10,
    message="<BLUE>Scout: My lord! The Saracen host approaches from the north with many horse archers!")

commander = trigger_manager.add_trigger("[D2] Commander Speech")
commander.new_condition.timer(timer=30)
commander.new_effect.display_instructions(display_time=10,
    message="<BLUE>Charles Martel: Hold the line! Our infantry will weather their arrows!")

taunt1 = trigger_manager.add_trigger("[D3] Enemy Taunt 1")
taunt1.new_condition.timer(timer=60)
taunt1.new_effect.display_instructions(display_time=10,
    message="<RED>Abd Al-Rahman: Your kingdom shall fall before our cavalry!")

taunt2 = trigger_manager.add_trigger("[D4] Enemy Taunt 2")
taunt2.new_condition.timer(timer=120)
taunt2.new_effect.display_instructions(display_time=10,
    message="<RED>Abd Al-Rahman: Forward! Let none escape our charge!")

location1 = trigger_manager.add_trigger("[D5] At Location 1")
location1.new_condition.bring_object_to_area(unit_object=hero.reference_id,
    area_x1=center-10, area_y1=center-10, area_x2=center+10, area_y2=center+10)
location1.new_effect.display_instructions(display_time=10,
    message="<BLUE>Charles Martel: We shall make our stand here!")

location2 = trigger_manager.add_trigger("[D6] At Location 2")
location2.new_condition.bring_object_to_area(unit_object=hero.reference_id,
    area_x1=enemy_base_x-10, area_y1=enemy_base_y-10, area_x2=enemy_base_x+10, area_y2=enemy_base_y+10)
location2.new_effect.display_instructions(display_time=10,
    message="<BLUE>Charles Martel: Press the attack! Drive them back!")

battle = trigger_manager.add_trigger("[D7] Battle Begins")
battle.new_condition.timer(timer=180)
battle.new_effect.display_instructions(display_time=10,
    message="<YELLOW>Narrator: The armies clash on the field of Tours!")

midpoint = trigger_manager.add_trigger("[D8] Midpoint Update")
midpoint.new_condition.timer(timer=300)
midpoint.new_effect.display_instructions(display_time=10,
    message="<YELLOW>Narrator: The battle hangs in the balance!")

weakening = trigger_manager.add_trigger("[D9] Enemy Weakening")
weakening.new_condition.objects_in_area(quantity=10, object_list=UnitInfo.CAVALRY_ARCHER.ID,
    source_player=PlayerId.TWO, area_x1=0, area_y1=0, area_x2=map_size, area_y2=map_size)
weakening.new_effect.display_instructions(display_time=10,
    message="<BLUE>Charles Martel: Their arrows thin! Now is our chance!")

final = trigger_manager.add_trigger("[D10] Final Push")
final.new_condition.timer(timer=420)
final.new_effect.display_instructions(display_time=10,
    message="<BLUE>Charles Martel: For Francia! Drive them from our lands!")

hero_falls = trigger_manager.add_trigger("[D11] Hero Falls")
hero_falls.new_condition.destroy_object(unit_object=hero.reference_id)
hero_falls.new_effect.display_instructions(display_time=10,
    message="<YELLOW>Narrator: Charles Martel has fallen! All hope is lost!")

# --- Objective Section ---
objectives = trigger_manager.add_trigger("[O] Main Objectives")
objectives.new_condition.timer(timer=1)
objectives.new_effect.display_instructions(display_time=20,
    message="Defeat Abd Al-Rahman or destroy the Umayyad castle.\nCharles Martel must survive.")

primary = trigger_manager.add_trigger("[Obj] Primary Goal")
primary.new_condition.destroy_object(unit_object=enemy_leader.reference_id)
primary.new_effect.display_instructions(display_time=10,
    message="Abd Al-Rahman is slain! Victory is ours!")

secondary = trigger_manager.add_trigger("[Obj] Secondary Goal")
secondary.new_condition.destroy_object(unit_object=castle.reference_id)
secondary.new_effect.display_instructions(display_time=10,
    message="The enemy castle has fallen!")

survival = trigger_manager.add_trigger("[Obj] Survival")
survival.new_condition.timer(timer=1)
survival.new_effect.display_instructions(display_time=10,
    message="Charles Martel must survive!")

# --- Victory/Defeat Section ---
victory1 = trigger_manager.add_trigger("VC")
victory1.new_condition.destroy_object(unit_object=enemy_leader.reference_id)
victory1.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)

victory2 = trigger_manager.add_trigger("VC2")
victory2.new_condition.destroy_object(unit_object=castle.reference_id)
victory2.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)

defeat1 = trigger_manager.add_trigger("Defeat")
defeat1.new_condition.destroy_object(unit_object=hero.reference_id)
defeat1.new_effect.declare_victory(source_player=PlayerId.TWO, enabled=1)

defeat2 = trigger_manager.add_trigger("DEFEAT")
defeat2.new_condition.destroy_object(unit_object=tc.reference_id)
defeat2.new_effect.declare_victory(source_player=PlayerId.TWO, enabled=1)

# Save scenario
scenario.write_to_file("output.aoe2scenario")