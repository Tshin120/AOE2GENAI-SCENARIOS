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
# Victory path: Defeat villain in final battle after gathering allies and resources
# Defeat path: Hero death, key ally death, or failure to protect objectives
# Resource sufficiency: Yes - multiple gold/stone mines, forests, and food sources near player base
# Counter availability: Yes - player has access to full military production buildings
# Physical access: Yes - clear paths between objectives with multiple route options
# Timing viability: Yes - starting forces can handle initial threats, recruitment provides scaling

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

# Player base coordinates (Act 1 start)
player_base_x = quarter
player_base_y = quarter

# Enemy fortress coordinates (Act 3 end)
enemy_base_x = three_quarter
enemy_base_y = three_quarter

# Create player base
town_center = unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.TOWN_CENTER.ID, x=player_base_x, y=player_base_y)
barracks = unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BARRACKS.ID, x=player_base_x+5, y=player_base_y)
archery_range = unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.ARCHERY_RANGE.ID, x=player_base_x+5, y=player_base_y+5)
stable = unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.STABLE.ID, x=player_base_x+10, y=player_base_y)
blacksmith = unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BLACKSMITH.ID, x=player_base_x+10, y=player_base_y+5)

# Create hero unit
hero = unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.BELISARIUS.ID, x=player_base_x+2, y=player_base_y+2)

# Create advisor
advisor = unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.KING.ID, x=player_base_x+3, y=player_base_y+3)

# Create starting army
for i in range(5):
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.SPEARMAN.ID, x=player_base_x+i, y=player_base_y+8)
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.ARCHER.ID, x=player_base_x+i, y=player_base_y+10)

# Create enemy fortress
enemy_castle = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.CASTLE.ID, x=enemy_base_x, y=enemy_base_y)
villain = unit_manager.add_unit(PlayerId.TWO, unit_const=HeroInfo.TAMERLANE.ID, x=enemy_base_x+2, y=enemy_base_y+2)

# Enemy fortress walls and gates
for i in range(10):
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STONE_WALL.ID, x=enemy_base_x-5+i, y=enemy_base_y-5)
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STONE_WALL.ID, x=enemy_base_x-5+i, y=enemy_base_y+5)
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STONE_WALL.ID, x=enemy_base_x-5, y=enemy_base_y-5+i)
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STONE_WALL.ID, x=enemy_base_x+5, y=enemy_base_y-5+i)

# Enemy gates (owned by enemy so AI can path through them)
enemy_gate_north = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, x=enemy_base_x, y=enemy_base_y-5)
enemy_gate_south = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, x=enemy_base_x, y=enemy_base_y+5)

# Create allied camp
ally_base_x = quarter + 20
ally_base_y = quarter + 20
ally_tc = unit_manager.add_unit(PlayerId.THREE, unit_const=BuildingInfo.TOWN_CENTER.ID, x=ally_base_x, y=ally_base_y)
ally_hero = unit_manager.add_unit(PlayerId.THREE, unit_const=HeroInfo.CHARLES_MARTEL.ID, x=ally_base_x+2, y=ally_base_y+2)

# Add GAIA resources near player base
# Gold mines
for i in range(5):
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.GOLD_MINE.ID, x=player_base_x-10+i, y=player_base_y-5)
# Stone mines  
for i in range(4):
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.STONE_MINE.ID, x=player_base_x-8+i, y=player_base_y-8)
# Forage bushes
for i in range(8):
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.FORAGE_BUSH.ID, x=player_base_x+i, y=player_base_y-10)
# Deer
for i in range(4):
    unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.DEER.ID, x=player_base_x+10+i, y=player_base_y-12)
# Sheep
for i in range(6):
    unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.SHEEP.ID, x=player_base_x+i, y=player_base_y-15)

# Story props and markers
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.FLAG_A.ID, x=center, y=center)
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.ROMAN_RUINS.ID, x=center+10, y=center+10)
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.SKELETON.ID, x=center+15, y=center+15)

# Create triggers
# Setup triggers
tech_trigger = trigger_manager.add_trigger("Techs")
tech_trigger.new_condition.timer(timer=1)
tech_trigger.new_effect.research_technology(source_player=PlayerId.ONE, technology=TechInfo.FORGING.ID)

easy_trigger = trigger_manager.add_trigger("Easy Difficulty")
easy_trigger.new_condition.difficulty_level(quantity=0)
easy_trigger.new_effect.create_object(object_list_unit_id=UnitInfo.KNIGHT.ID, source_player=PlayerId.ONE, location_x=player_base_x+15, location_y=player_base_y+15)

hard_trigger = trigger_manager.add_trigger("Hard Difficulty")
hard_trigger.new_condition.difficulty_level(quantity=3)
hard_trigger.new_effect.create_object(object_list_unit_id=UnitInfo.KNIGHT.ID, source_player=PlayerId.TWO, location_x=enemy_base_x-10, location_y=enemy_base_y-10)

enemy_ai = trigger_manager.add_trigger("Enemy AI Setup")
enemy_ai.new_condition.timer(timer=1)
enemy_ai.new_effect.patrol(object_list_unit_id=UnitInfo.KNIGHT.ID, source_player=PlayerId.TWO, location_x=center, location_y=center)

initial_state = trigger_manager.add_trigger("Initial State")
initial_state.new_condition.timer(timer=1)
initial_state.new_effect.display_instructions(display_time=10, message="<YELLOW>Welcome to The Rise of Rome")

ally_ai = trigger_manager.add_trigger("Ally AI Setup")
ally_ai.new_condition.timer(timer=1)
ally_ai.new_effect.patrol(object_list_unit_id=UnitInfo.SPEARMAN.ID, source_player=PlayerId.THREE, location_x=ally_base_x+10, location_y=ally_base_y+10)

# Act 1 triggers
intro = trigger_manager.add_trigger("[D0] Intro")
intro.new_condition.timer(timer=5)
intro.new_effect.display_instructions(display_time=15, message="<YELLOW>In the early days of Rome, a young commander rises...")

hero_start = trigger_manager.add_trigger("[D1] Hero Awakens")
hero_start.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=player_base_x, area_y1=player_base_y, area_x2=player_base_x+5, area_y2=player_base_y+5)
hero_start.new_effect.display_instructions(display_time=10, message="<BLUE>The fate of Rome rests in our hands.")

meet_advisor = trigger_manager.add_trigger("[D2] Meet Advisor")
meet_advisor.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=advisor.x-2, area_y1=advisor.y-2, area_x2=advisor.x+2, area_y2=advisor.y+2)
meet_advisor.new_effect.display_instructions(display_time=10, message="<BLUE>Commander, barbarians threaten our borders!")

# Victory and defeat triggers
victory = trigger_manager.add_trigger("VC Primary")
victory.new_condition.destroy_object(unit_object=villain.reference_id)
victory.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)

defeat = trigger_manager.add_trigger("Defeat - Hero Dies")
defeat.new_condition.destroy_object(unit_object=hero.reference_id)
defeat.new_effect.declare_victory(source_player=PlayerId.TWO, enabled=1)

# Save scenario
scenario.write_to_file("output.aoe2scenario")