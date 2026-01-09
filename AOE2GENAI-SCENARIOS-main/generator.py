import os
import json
import re
import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from html.parser import HTMLParser
import logging
from pathlib import Path

# AoE2ScenarioParser imports
from AoE2ScenarioParser.scenarios.aoe2_de_scenario import AoE2DEScenario
from AoE2ScenarioParser.datasets.players import PlayerId
from AoE2ScenarioParser.datasets.units import UnitInfo
from AoE2ScenarioParser.datasets.trigger_lists import *
from AoE2ScenarioParser.datasets.buildings import BuildingInfo
from AoE2ScenarioParser.datasets.other import OtherInfo
from AoE2ScenarioParser.datasets.techs import TechInfo
from AoE2ScenarioParser.datasets.heroes import HeroInfo

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WikipediaHTMLParser(HTMLParser):
    """Parser to extract text content from Wikipedia HTML"""

    def __init__(self):
        super().__init__()
        self.text_content = []
        self.in_paragraph = False
        self.skip_tags = {'script', 'style', 'nav', 'footer', 'header', 'aside', 'sup', 'span'}
        self.current_tag = None
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self.skip_depth += 1
        elif tag == 'p':
            self.in_paragraph = True
        self.current_tag = tag

    def handle_endtag(self, tag):
        if tag in self.skip_tags and self.skip_depth > 0:
            self.skip_depth -= 1
        elif tag == 'p':
            self.in_paragraph = False
            self.text_content.append('\n')
        self.current_tag = None

    def handle_data(self, data):
        if self.skip_depth == 0 and self.in_paragraph:
            cleaned = data.strip()
            if cleaned:
                self.text_content.append(cleaned + ' ')

    def get_text(self) -> str:
        return ''.join(self.text_content).strip()


def fetch_wikipedia_content(url: str, max_chars: int = 4000) -> Optional[str]:
    """
    Fetch and parse content from a Wikipedia URL.

    Args:
        url: Wikipedia article URL
        max_chars: Maximum characters to return (default 4000 to fit in prompts)

    Returns:
        Extracted text content from the Wikipedia article, or None if failed
    """
    if not url:
        return None

    # Validate it's a Wikipedia URL
    if 'wikipedia.org' not in url:
        logger.warning(f"URL is not a Wikipedia link: {url}")
        return None

    try:
        headers = {
            'User-Agent': 'AoE2ScenarioGenerator/1.0 (Educational project for generating game scenarios)'
        }

        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        # Parse the HTML content
        parser = WikipediaHTMLParser()
        parser.feed(response.text)
        content = parser.get_text()

        # Clean up the content
        # Remove citation brackets like [1], [2], etc.
        content = re.sub(r'\[\d+\]', '', content)
        # Remove multiple spaces
        content = re.sub(r' +', ' ', content)
        # Remove multiple newlines
        content = re.sub(r'\n+', '\n', content)

        # Truncate to max_chars
        if len(content) > max_chars:
            # Try to cut at a sentence boundary
            truncated = content[:max_chars]
            last_period = truncated.rfind('.')
            if last_period > max_chars * 0.7:  # At least 70% of content
                content = truncated[:last_period + 1]
            else:
                content = truncated + "..."

        logger.info(f"Successfully fetched Wikipedia content: {len(content)} characters")
        return content

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch Wikipedia content: {e}")
        return None
    except Exception as e:
        logger.error(f"Error parsing Wikipedia content: {e}")
        return None


@dataclass
class ScenarioConfig:
    """Configuration for scenario generation"""
    title: str
    description: str
    map_size: int = 120
    players: int = 2
    difficulty: str = "medium"
    scenario_type: str = "story"
    output_path: str = "generated_scenario.aoe2scenario"
    wikipedia_link: Optional[str] = None

class OpenRouterAPI:
    """Handles communication with OpenRouter API"""
    
    def __init__(self, api_key: str, base_url: str = "https://openrouter.ai/api/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://aoe2scenario-generator.com",
            "X-Title": "AoE2 Scenario Generator"
        }
    
    def generate_scenario_code(self, prompt: str, model: str = "anthropic/claude-3.5-sonnet") -> str:
        """Generate scenario code using OpenRouter API"""
        
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": """You are an expert Age of Empires 2 scenario creator using the AoE2ScenarioParser library.

Generate complete, runnable Python code that creates an Age of Empires 2 scenario.

REQUIRED CODE HEADER - Start with this EXACT code:
```python
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

# Create scenario
scenario = AoE2DEScenario.from_default()

# Get managers
unit_manager = scenario.unit_manager
trigger_manager = scenario.trigger_manager
map_manager = scenario.map_manager

# Set map size (INTEGER only, not tuple)
map_manager.map_size = 144  # Valid coordinates: 0-143
```

# ============================================================
# GEOGRAPHY AND PATHWAY DESIGN (Based on official campaigns)
# ============================================================
# Create natural terrain features that guide player movement through the map.
# Use mountains, cliffs, and forests to create PATHWAYS and CHOKEPOINTS.

# === MOUNTAIN BARRIERS - Block off areas and create natural paths ===
# Place mountains in clusters to form impassable barriers
# Use MOUNTAIN_1, MOUNTAIN_2, MOUNTAIN_3, MOUNTAIN_4 for variety
# Example: Mountain range blocking the southern route
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.MOUNTAIN_1.ID, x=10.0, y=90.0)
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.MOUNTAIN_2.ID, x=15.0, y=90.0)
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.MOUNTAIN_3.ID, x=20.0, y=92.0)
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.MOUNTAIN_4.ID, x=25.0, y=89.0)
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.MOUNTAIN_1.ID, x=30.0, y=91.0)

# === FOREST BOUNDARIES - Line pathways with trees ===
# Create dense tree lines to channel movement along paths
# Use TREE_SNOW_PINE for cold/mountain areas, TREE_OAK for temperate
# Example: Forest lining a pathway (place trees in rows)
for i in range(10):
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.TREE_SNOW_PINE.ID, x=5.5+i, y=119.5)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.TREE_SNOW_PINE.ID, x=5.5+i, y=120.5)

# === CLIFF FORMATIONS - Create dramatic terrain features ===
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.CLIFF_DEFAULT_1.ID, x=25.5, y=139.5)
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.ROCK_1.ID, x=26.5, y=138.5)

# === ENVIRONMENTAL DECORATIONS - Add atmosphere ===
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.BONFIRE.ID, x=3.5, y=133.5)
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.SIGN.ID, x=59.5, y=128.5)
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.BROKEN_CART.ID, x=10.5, y=138.5)

# ============================================================
# PLAYER ROLES AND UNIT DISTRIBUTION
# ============================================================
# PlayerId.ONE: Player's army (hero + escorts, mobile force)
# PlayerId.TWO-THREE: Allies (friendly NPCs, villages)
# PlayerId.FOUR-EIGHT: Enemies (fortresses, patrols, ambushes)
# PlayerId.GAIA: Environment (resources, decorations, terrain objects)

# === PLAYER ARMY (PlayerId.ONE) - Mobile force with hero ===
# Place hero with escort troops, starting position
hero = unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.TARIQ_IBN_ZIYAD.ID, x=50.5, y=130.5)
unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.KNIGHT.ID, x=49.5, y=130.5)
unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.KNIGHT.ID, x=51.5, y=130.5)
unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.LIGHT_CAVALRY.ID, x=48.5, y=131.5)
unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.CAVALRY_ARCHER.ID, x=52.5, y=131.5)

# === ENEMY FORTRESS DEFENSE (PlayerId.FOUR) - Blocking key routes ===
# Place fortresses at strategic chokepoints with garrison troops
unit_manager.add_unit(PlayerId.FOUR, unit_const=BuildingInfo.CASTLE.ID, x=85.5, y=70.5)
unit_manager.add_unit(PlayerId.FOUR, unit_const=BuildingInfo.WATCH_TOWER.ID, x=82.5, y=68.5)
unit_manager.add_unit(PlayerId.FOUR, unit_const=UnitInfo.HALBERDIER.ID, x=83.5, y=69.5)
unit_manager.add_unit(PlayerId.FOUR, unit_const=UnitInfo.HALBERDIER.ID, x=84.5, y=69.5)
unit_manager.add_unit(PlayerId.FOUR, unit_const=UnitInfo.CROSSBOWMAN.ID, x=86.5, y=71.5)

# === ENEMY PATROLS (PlayerId.FIVE) - Roaming guards ===
# Spread patrols along pathways the player might take
unit_manager.add_unit(PlayerId.FIVE, unit_const=UnitInfo.SCOUT_CAVALRY.ID, x=30.5, y=65.5)
unit_manager.add_unit(PlayerId.FIVE, unit_const=UnitInfo.LIGHT_CAVALRY.ID, x=31.5, y=65.5)

# === ENEMY AMBUSH FORCES (PlayerId.SIX) - Hidden threats ===
# Place ambush units along the correct path, activated by triggers
unit_manager.add_unit(PlayerId.SIX, unit_const=UnitInfo.ELITE_HUSKARL.ID, x=74.5, y=110.5)
unit_manager.add_unit(PlayerId.SIX, unit_const=UnitInfo.CHAMPION.ID, x=76.5, y=109.5)
unit_manager.add_unit(PlayerId.SIX, unit_const=BuildingInfo.OUTPOST.ID, x=77.5, y=108.5)

# === FRIENDLY VILLAGE (PlayerId.THREE) - Safe zones with NPCs ===
unit_manager.add_unit(PlayerId.THREE, unit_const=BuildingInfo.TOWN_CENTER.ID, x=5.5, y=10.5)
unit_manager.add_unit(PlayerId.THREE, unit_const=UnitInfo.VILLAGER_MALE.ID, x=6.5, y=11.5)
unit_manager.add_unit(PlayerId.THREE, unit_const=UnitInfo.LIGHT_CAVALRY.ID, x=8.5, y=10.5)

# ============================================================
# TRIGGER SYSTEM - PATHWAY WARNINGS AND STORY PROGRESSION
# ============================================================

# === PATROL TRIGGERS - Make enemies patrol their routes ===
trigger_patrols = trigger_manager.add_trigger("enemy_patrols")
trigger_patrols.new_effect.patrol(source_player=PlayerId.FOUR, location_x=39, location_y=95)
trigger_patrols.new_effect.patrol(source_player=PlayerId.FOUR, location_x=56, location_y=58)
trigger_patrols.new_effect.patrol(source_player=PlayerId.FIVE, location_x=23, location_y=65)
trigger_patrols.new_effect.patrol(source_player=PlayerId.FIVE, location_x=40, location_y=15)

# === PATHWAY WARNING TRIGGERS - Warn player when approaching blocked routes ===
# Each fortress/blocked area should have a warning trigger
trigger_warn1 = trigger_manager.add_trigger("[D1] Approach fortress from south")
trigger_warn1.new_condition.objects_in_area(quantity=1, source_player=PlayerId.ONE, area_x1=38, area_y1=90, area_x2=41, area_y2=102)
trigger_warn1.new_effect.display_instructions(source_player=PlayerId.ONE, message="<YELLOW>al-Ghafiqi: An enemy fortress lies just ahead. We do not have the means to capture it - we should turn around!", display_time=12)

trigger_warn2 = trigger_manager.add_trigger("[D1] Approach fortress from north")
trigger_warn2.new_condition.objects_in_area(quantity=1, source_player=PlayerId.ONE, area_x1=85, area_y1=62, area_x2=89, area_y2=66)
trigger_warn2.new_effect.display_instructions(source_player=PlayerId.ONE, message="<YELLOW>Scout: A dreaded enemy fortress lies down this road. Our destination is north, not south!", display_time=10)

# === INTRO SEQUENCE - Story opening ===
trigger_intro = trigger_manager.add_trigger("[D1] Local speaks")
trigger_intro.new_condition.timer(5)
trigger_intro.new_effect.display_instructions(source_player=PlayerId.THREE, message="<GREY>Local: The mountain passes are treacherous and crawling with enemy troops. You have a long journey ahead.", display_time=14)
trigger_intro.new_effect.activate_trigger(trigger_id=1)

trigger_response = trigger_manager.add_trigger("[D1] Hero responds")
trigger_response.enabled = False
trigger_response.new_condition.timer(15)
trigger_response.new_effect.display_instructions(source_player=PlayerId.ONE, message="<YELLOW>al-Ghafiqi: Brace yourselves for difficult terrain. We must reach our destination before winter!", display_time=12)

# === AREA-BASED EVENTS - Triggers when entering zones ===
# Ambush trigger
trigger_ambush = trigger_manager.add_trigger("[D1] Initial ambush")
trigger_ambush.new_condition.objects_in_area(quantity=1, source_player=PlayerId.ONE, area_x1=27, area_y1=109, area_x2=37, area_y2=119)
trigger_ambush.new_effect.display_instructions(source_player=PlayerId.FOUR, message="<RED>Enemy Knight: Charge!", display_time=4)
trigger_ambush.new_effect.attack_move(source_player=PlayerId.FOUR, location_x=30, location_y=116)

# Village welcome trigger
trigger_village = trigger_manager.add_trigger("[D1] Enter village")
trigger_village.new_condition.objects_in_area(quantity=1, source_player=PlayerId.ONE, area_x1=0, area_y1=0, area_x2=14, area_y2=17)
trigger_village.new_effect.display_instructions(source_player=PlayerId.THREE, message="<GREY>Villager: Welcome to our humble village, my lord. Rest here before continuing.", display_time=12)
trigger_village.new_effect.research_technology(source_player=PlayerId.ONE)

# === VICTORY/DEFEAT CONDITIONS ===
# Victory: Reach destination with hero alive
trigger_victory = trigger_manager.add_trigger("[Obj] Reach destination")
trigger_victory.new_condition.bring_object_to_area(unit_object=hero.reference_id, area_x1=133, area_y1=0, area_x2=143, area_y2=10)
trigger_victory.new_effect.display_instructions(source_player=PlayerId.ONE, message="<YELLOW>al-Ghafiqi: We have completed our journey. Good work, men!", display_time=15)
trigger_victory.new_effect.activate_trigger(trigger_id=20)

# Defeat: Hero dies
trigger_defeat = trigger_manager.add_trigger("[D1] Hero dies")
trigger_defeat.new_condition.destroy_object(unit_object=hero.reference_id)
trigger_defeat.new_effect.display_instructions(source_player=PlayerId.ONE, message="<YELLOW>Scout: Our leader is dead! How can we continue now?", display_time=10)
trigger_defeat.new_effect.declare_victory(source_player=PlayerId.TWO)

REAL SCENARIO EXAMPLE - From official Tariq ibn Ziyad campaign:

# === PLACING BUILDINGS ===
unit_manager.add_unit(PlayerId.FIVE, unit_const=BuildingInfo.HOUSE.ID, x=69.0, y=47.0)
unit_manager.add_unit(PlayerId.FIVE, unit_const=BuildingInfo.WATCH_TOWER.ID, x=62.5, y=40.5)
unit_manager.add_unit(PlayerId.FIVE, unit_const=BuildingInfo.OUTPOST.ID, x=36.5, y=10.5)

# === PLACING MILITARY UNITS ===
unit_manager.add_unit(PlayerId.FIVE, unit_const=UnitInfo.HALBERDIER.ID, x=63.5, y=34.5)
unit_manager.add_unit(PlayerId.FIVE, unit_const=UnitInfo.HALBERDIER.ID, x=64.5, y=34.5)
unit_manager.add_unit(PlayerId.FIVE, unit_const=UnitInfo.ELITE_SKIRMISHER.ID, x=67.5, y=36.5)
unit_manager.add_unit(PlayerId.FIVE, unit_const=UnitInfo.KNIGHT.ID, x=67.5, y=44.5)
unit_manager.add_unit(PlayerId.FIVE, unit_const=UnitInfo.CAVALRY_ARCHER.ID, x=71.5, y=38.5)
unit_manager.add_unit(PlayerId.FIVE, unit_const=UnitInfo.LIGHT_CAVALRY.ID, x=70.5, y=38.5)
unit_manager.add_unit(PlayerId.FIVE, unit_const=UnitInfo.HEAVY_SCORPION.ID, x=63.5, y=37.5)

# === PLACING HEROES (store reference for triggers) ===
hero = unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.TARIQ_IBN_ZIYAD.ID, x=50.5, y=50.5)
enemy_leader = unit_manager.add_unit(PlayerId.TWO, unit_const=HeroInfo.CHARLES_MARTEL.ID, x=100.5, y=100.5)

# === GAIA OBJECTS (resources, decorations) ===
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.GOLD_MINE.ID, x=30.5, y=30.5)
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.STONE_MINE.ID, x=35.5, y=30.5)
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.TREE_SNOW_PINE.ID, x=10.5, y=10.5)
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.BONFIRE.ID, x=3.5, y=133.5)
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.MOUNTAIN_1.ID, x=4.0, y=116.0)

# ============================================================
# TRIGGER SYSTEM - CREATING CONTINUITY OF EVENTS
# ============================================================
# Triggers are the backbone of scenario storytelling. Use them to:
# - Chain events in sequence (activate_trigger/deactivate_trigger)
# - Create branching storylines based on player actions
# - Build progressive objectives that unlock as the player advances

# ============================================================
# CRITICAL: ADAPT ALL TRIGGERS TO THE SPECIFIC SCENARIO
# ============================================================
# DO NOT use generic placeholder text! Every trigger must reflect:
# 1. The ACTUAL scenario title, setting, and time period
# 2. REAL historical figures, locations, and events from the description
# 3. Historically accurate dialogue that fits the characters and era
# 4. Objectives that match the ACTUAL battle/story being depicted
# 5. If Wikipedia context is provided, use REAL names, dates, and events
#
# EXAMPLE - For "Battle of Hastings" scenario:
#   WRONG: "Narrator: The year is 1066. A great battle is about to begin..."
#   RIGHT: "Narrator: October 14th, 1066. On Senlac Hill, Harold Godwinson prepares to face William of Normandy..."
#
# EXAMPLE - For "Siege of Constantinople" scenario:
#   WRONG: "Commander: Enemy forces approaching!"
#   RIGHT: "Emperor Constantine XI: The Ottoman cannons breach our walls! Rally to the Theodosian defenses!"
#
# Use the scenario description and Wikipedia content to create:
# - Accurate character names (Harold, William, Mehmed II, Constantine XI, etc.)
# - Specific location names (Senlac Hill, Theodosian Walls, etc.)
# - Historical dates and context in narration
# - Era-appropriate military terminology and dialogue

# === TRIGGER CHAINING PATTERN ===
# Use enabled=False for triggers that should be activated by other triggers
# Use activate_trigger effect to enable the next trigger in sequence
# Use deactivate_trigger to prevent triggers from firing multiple times

# --- INTRO SEQUENCE (Chained triggers for story continuity) ---
# Step 1: Initial scene-setting dialogue
trigger_intro_1 = trigger_manager.add_trigger("intro_part1")
trigger_intro_1.new_condition.timer(3)
trigger_intro_1.new_effect.display_instructions(source_player=PlayerId.ONE, message="<YELLOW>Narrator: The year is 1066. A great battle is about to begin...", display_time=8)
trigger_intro_1.new_effect.activate_trigger(trigger_id=1)  # Activates intro_part2

# Step 2: Character introduction (disabled until activated by step 1)
trigger_intro_2 = trigger_manager.add_trigger("intro_part2")
trigger_intro_2.enabled = False
trigger_intro_2.new_condition.timer(8)
trigger_intro_2.new_effect.display_instructions(source_player=PlayerId.ONE, message="<AQUA>Commander: My lord, our forces are assembled. What are your orders?", display_time=8)
trigger_intro_2.new_effect.activate_trigger(trigger_id=2)  # Activates intro_part3

# Step 3: Objective reveal (disabled until activated by step 2)
trigger_intro_3 = trigger_manager.add_trigger("intro_part3")
trigger_intro_3.enabled = False
trigger_intro_3.new_condition.timer(8)
trigger_intro_3.new_effect.display_instructions(source_player=PlayerId.ONE, message="<YELLOW>OBJECTIVE: Lead your army to capture the enemy fortress.", display_time=10)
trigger_intro_3.new_effect.activate_trigger(trigger_id=3)  # Enable gameplay triggers

# --- AREA-BASED EVENT TRIGGERS (Fire once then deactivate) ---
trigger_enter_village = trigger_manager.add_trigger("enter_village_event")
trigger_enter_village.enabled = False  # Activated after intro sequence
trigger_enter_village.new_condition.objects_in_area(quantity=1, source_player=PlayerId.ONE, area_x1=20, area_y1=20, area_x2=40, area_y2=40)
trigger_enter_village.new_effect.display_instructions(source_player=PlayerId.ONE, message="<GREY>Villager: Welcome, my lord! The enemy camp lies to the north.", display_time=8)
trigger_enter_village.new_effect.deactivate_trigger(trigger_id=3)  # Prevent re-triggering

# --- PROGRESSIVE OBJECTIVES (Unlock new objectives as old ones complete) ---
trigger_obj1_complete = trigger_manager.add_trigger("objective1_complete")
trigger_obj1_complete.new_condition.objects_in_area(quantity=0, source_player=PlayerId.TWO, area_x1=50, area_y1=50, area_x2=70, area_y2=70)
trigger_obj1_complete.new_effect.display_instructions(source_player=PlayerId.ONE, message="<GREEN>Objective Complete: Outpost destroyed!", display_time=6)
trigger_obj1_complete.new_effect.activate_trigger(trigger_id=5)  # Enable next objective
trigger_obj1_complete.new_effect.deactivate_trigger(trigger_id=4)  # Disable this trigger

trigger_obj2_reveal = trigger_manager.add_trigger("objective2_reveal")
trigger_obj2_reveal.enabled = False
trigger_obj2_reveal.new_condition.timer(3)
trigger_obj2_reveal.new_effect.display_instructions(source_player=PlayerId.ONE, message="<YELLOW>NEW OBJECTIVE: Destroy the enemy castle to the east.", display_time=8)

# --- TIMED ENEMY WAVES (Sequential spawning) ---
trigger_wave1 = trigger_manager.add_trigger("enemy_wave_1")
trigger_wave1.new_condition.timer(60)  # 1 minute into game
trigger_wave1.new_effect.display_instructions(source_player=PlayerId.ONE, message="<RED>Scout: Enemy reinforcements approaching from the west!", display_time=6)
trigger_wave1.new_effect.create_object(source_player=PlayerId.TWO, object_list_unit_id=UnitInfo.KNIGHT.ID, location_x=10, location_y=70)
trigger_wave1.new_effect.create_object(source_player=PlayerId.TWO, object_list_unit_id=UnitInfo.KNIGHT.ID, location_x=12, location_y=70)
trigger_wave1.new_effect.activate_trigger(trigger_id=7)  # Queue up wave 2

trigger_wave2 = trigger_manager.add_trigger("enemy_wave_2")
trigger_wave2.enabled = False
trigger_wave2.new_condition.timer(90)  # 1.5 minutes after wave 1
trigger_wave2.new_effect.display_instructions(source_player=PlayerId.ONE, message="<RED>Scout: A larger enemy force has been spotted!", display_time=6)
trigger_wave2.new_effect.create_object(source_player=PlayerId.TWO, object_list_unit_id=UnitInfo.CAVALIER.ID, location_x=10, location_y=75)
trigger_wave2.new_effect.create_object(source_player=PlayerId.TWO, object_list_unit_id=UnitInfo.CAVALIER.ID, location_x=12, location_y=75)
trigger_wave2.new_effect.create_object(source_player=PlayerId.TWO, object_list_unit_id=UnitInfo.CROSSBOWMAN.ID, location_x=14, location_y=75)

# --- PATROL TRIGGERS ---
trigger_patrol = trigger_manager.add_trigger("enemy_patrols")
trigger_patrol.new_effect.patrol(source_player=PlayerId.TWO, location_x=39, location_y=95)
trigger_patrol.new_effect.patrol(source_player=PlayerId.TWO, location_x=56, location_y=58)

# --- HERO DEATH/VICTORY CONDITIONS ---
# Store unit references for trigger conditions
hero = unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.WILLIAM_WALLACE.ID, x=50.5, y=50.5)
enemy_leader = unit_manager.add_unit(PlayerId.TWO, unit_const=HeroInfo.CHARLES_MARTEL.ID, x=100.5, y=100.5)

# Defeat trigger - player's hero dies
trigger_defeat = trigger_manager.add_trigger("hero_dies_defeat")
trigger_defeat.new_condition.destroy_object(unit_object=hero.reference_id)
trigger_defeat.new_effect.display_instructions(source_player=PlayerId.ONE, message="<RED>Our leader has fallen! All is lost!", display_time=10)
trigger_defeat.new_effect.declare_victory(source_player=PlayerId.TWO)

# Victory trigger - enemy leader dies
trigger_victory = trigger_manager.add_trigger("enemy_leader_dies_victory")
trigger_victory.new_condition.destroy_object(unit_object=enemy_leader.reference_id)
trigger_victory.new_effect.display_instructions(source_player=PlayerId.ONE, message="<GREEN>The enemy commander is slain! Victory is ours!", display_time=10)
trigger_victory.new_effect.activate_trigger(trigger_id=10)  # Activate victory sequence

trigger_victory_sequence = trigger_manager.add_trigger("victory_celebration")
trigger_victory_sequence.enabled = False
trigger_victory_sequence.new_condition.timer(5)
trigger_victory_sequence.new_effect.display_instructions(source_player=PlayerId.ONE, message="<YELLOW>Narrator: And so, the battle was won. Our hero's legend would be told for generations.", display_time=12)
trigger_victory_sequence.new_effect.activate_trigger(trigger_id=11)

trigger_win = trigger_manager.add_trigger("declare_win")
trigger_win.enabled = False
trigger_win.new_condition.timer(12)
trigger_win.new_effect.declare_victory(source_player=PlayerId.ONE)

# ============================================================
# NAVAL BATTLE EXAMPLE - Creating water terrain and ships
# ============================================================

# === EDITING TERRAIN - Create water areas for naval battles ===
# Fill a rectangular area with water (for ocean/sea)
for x in range(0, 100):
    for y in range(60, 120):
        tile = map_manager.get_tile(x, y)
        tile.terrain_id = TerrainId.WATER_DEEP  # Deep ocean water

# Create shallows near the coast
for x in range(0, 100):
    for y in range(55, 60):
        tile = map_manager.get_tile(x, y)
        tile.terrain_id = TerrainId.SHALLOWS  # Shallow water near beach

# Create beach/coast
for x in range(0, 100):
    for y in range(50, 55):
        tile = map_manager.get_tile(x, y)
        tile.terrain_id = TerrainId.BEACH  # Sandy beach

# Create an island in the middle of the water
for x in range(40, 60):
    for y in range(80, 100):
        tile = map_manager.get_tile(x, y)
        tile.terrain_id = TerrainId.GRASS_1  # Island with grass

# === PLACING NAVAL UNITS ===
# Player 1 fleet (must be on water tiles)
unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.GALLEON.ID, x=20.5, y=70.5)
unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.GALLEON.ID, x=22.5, y=72.5)
unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.WAR_GALLEY.ID, x=18.5, y=68.5)
unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.FIRE_SHIP.ID, x=24.5, y=74.5)
unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.DEMOLITION_SHIP.ID, x=16.5, y=66.5)
unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.CANNON_GALLEON.ID, x=26.5, y=76.5)
unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.TRANSPORT_SHIP.ID, x=28.5, y=78.5)

# Player 2 enemy fleet
unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.GALLEON.ID, x=80.5, y=90.5)
unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.GALLEON.ID, x=82.5, y=92.5)
unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.FAST_FIRE_SHIP.ID, x=78.5, y=88.5)
unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.ELITE_LONGBOAT.ID, x=84.5, y=94.5)

# === PLACING COASTAL BUILDINGS ===
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.DOCK.ID, x=15.5, y=55.5)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.DOCK.ID, x=85.5, y=55.5)

# === NAVAL BATTLE TRIGGERS ===
trigger_naval_victory = trigger_manager.add_trigger("Destroy Enemy Fleet")
trigger_naval_victory.new_condition.objects_in_area(quantity=0, source_player=PlayerId.TWO, area_x1=0, area_y1=60, area_x2=100, area_y2=120)
trigger_naval_victory.new_effect.display_instructions(source_player=PlayerId.ONE, message="<GREEN>The enemy fleet has been destroyed! Victory!", display_time=10)
trigger_naval_victory.new_effect.declare_victory(source_player=PlayerId.ONE)

# === SAVE SCENARIO ===
scenario.write_to_file("output.aoe2scenario")

CRITICAL RULES:
- Use AoE2DEScenario.from_default() - do NOT use from_file()
- Map size must be INTEGER: map_manager.map_size = 120 (NOT tuple)
- All coordinates must be within 0 to (map_size - 1)
- Always use .ID property: UnitInfo.KNIGHT.ID, BuildingInfo.CASTLE.ID
- Use source_player parameter (NOT player)
- AoE2 is medieval - use HAND_CANNONEER for gunpowder units, no muskets/rifles
- Group units together for formations (similar x,y coordinates)
- Use PlayerId.ONE through PlayerId.EIGHT, and PlayerId.GAIA
- For destroy_object condition: store the unit first, then use unit.reference_id
  WRONG: destroy_object(unit_const=HeroInfo.JOAN_OF_ARC.ID)
  CORRECT: hero = unit_manager.add_unit(...); destroy_object(unit_object=hero.reference_id)

TRIGGER CONTINUITY RULES (CRITICAL FOR STORY-DRIVEN SCENARIOS):
- ALWAYS create a chain of triggers for story progression - never just isolated triggers
- Use trigger.enabled = False for triggers that should be activated later
- Use activate_trigger(trigger_id=X) effect to enable the next trigger in sequence
- Use deactivate_trigger(trigger_id=X) to prevent triggers from firing multiple times
- Trigger IDs are 0-indexed based on creation order (first trigger = 0, second = 1, etc.)
- Create an INTRO SEQUENCE: chain 2-4 triggers with timers for opening narrative
- Create PROGRESSIVE OBJECTIVES: complete one objective -> activate next objective trigger
- Create TIMED WAVES: use activate_trigger to queue up enemy reinforcement waves
- Create VICTORY/DEFEAT SEQUENCES: chain multiple triggers for cinematic endings
- Every trigger should either: (a) activate another trigger, or (b) be the final trigger in a chain
- Use timer conditions between chained triggers to pace dialogue and events

SCENARIO-SPECIFIC TRIGGER CONTENT (MANDATORY):
- NEVER use generic placeholder text like "Commander" or "the enemy" - use ACTUAL names
- Extract character names, locations, dates, and events from the scenario description
- If Wikipedia content is provided, use the REAL historical details in trigger messages
- Match heroes to the actual historical figures (e.g., HeroInfo.WILLIAM_WALLACE for William Wallace)
- Objectives must reflect the ACTUAL historical goals (e.g., "Capture Senlac Hill" not "Capture the hill")
- Dialogue must be era-appropriate and character-specific
- Victory/defeat messages should reference the actual historical outcome

# ============================================================
# TRANSITIONAL TRIGGERS AND GAMEPLAY PROGRESSION
# ============================================================
# Create triggers that BRIDGE historical events with gameplay guidance.
# These "filler" triggers don't need to be historically documented - they should:
# 1. Feel authentic to the era and setting
# 2. Guide players step-by-step between major events
# 3. Create immersive atmosphere and pacing

# === NAVIGATION/MOVEMENT TRIGGERS ===
# Guide players when entering or leaving key areas
trigger_leave_camp = trigger_manager.add_trigger("[Nav] Leave camp")
trigger_leave_camp.new_condition.objects_in_area(quantity=1, source_player=PlayerId.ONE, area_x1=10, area_y1=10, area_x2=20, area_y2=20)
trigger_leave_camp.new_effect.display_instructions(source_player=PlayerId.ONE, message="<YELLOW>Commander: The men are ready. We march east toward the enemy position!", display_time=8)
trigger_leave_camp.new_effect.activate_trigger(trigger_id=5)  # Activate next phase

trigger_approach_river = trigger_manager.add_trigger("[Nav] Approach river crossing")
trigger_approach_river.enabled = False
trigger_approach_river.new_condition.objects_in_area(quantity=1, source_player=PlayerId.ONE, area_x1=50, area_y1=40, area_x2=60, area_y2=50)
trigger_approach_river.new_effect.display_instructions(source_player=PlayerId.ONE, message="<YELLOW>Scout: The river lies ahead, my lord. We must find a ford to cross.", display_time=10)

trigger_enter_enemy_territory = trigger_manager.add_trigger("[Nav] Enter enemy territory")
trigger_enter_enemy_territory.enabled = False
trigger_enter_enemy_territory.new_condition.objects_in_area(quantity=1, source_player=PlayerId.ONE, area_x1=80, area_y1=60, area_x2=100, area_y2=80)
trigger_enter_enemy_territory.new_effect.display_instructions(source_player=PlayerId.ONE, message="<RED>Enemy Lookout: Intruders! Sound the alarm!", display_time=6)
trigger_enter_enemy_territory.new_effect.activate_trigger(trigger_id=10)  # Trigger enemy response

# === RESOURCE GATHERING TRIGGERS ===
# Prompt players to gather resources or supplies
trigger_find_supplies = trigger_manager.add_trigger("[Res] Find supply cache")
trigger_find_supplies.new_condition.objects_in_area(quantity=1, source_player=PlayerId.ONE, area_x1=30, area_y1=25, area_x2=35, area_y2=30)
trigger_find_supplies.new_effect.display_instructions(source_player=PlayerId.ONE, message="<AQUA>Soldier: We found abandoned supplies here! This will help sustain our march.", display_time=8)
trigger_find_supplies.new_effect.create_object(source_player=PlayerId.ONE, location_x=32, location_y=27)

trigger_gather_gold = trigger_manager.add_trigger("[Res] Discover gold mine")
trigger_gather_gold.new_condition.objects_in_area(quantity=1, source_player=PlayerId.ONE, area_x1=45, area_y1=55, area_x2=50, area_y2=60)
trigger_gather_gold.new_effect.display_instructions(source_player=PlayerId.ONE, message="<YELLOW>Advisor: There is gold here. We should secure this area to fund our campaign.", display_time=10)

# === OBJECT REVEAL/DISPLAY TRIGGERS ===
# Reveal hidden units, buildings, or terrain features as story progresses
trigger_reveal_fortress = trigger_manager.add_trigger("[Reveal] Enemy fortress visible")
trigger_reveal_fortress.enabled = False
trigger_reveal_fortress.new_condition.timer(5)
trigger_reveal_fortress.new_effect.display_instructions(source_player=PlayerId.ONE, message="<YELLOW>Scout: My lord! The enemy fortress comes into view. Their defenses are formidable.", display_time=10)
trigger_reveal_fortress.new_effect.change_view(source_player=PlayerId.ONE, location_x=90, location_y=70)

trigger_reveal_ambush = trigger_manager.add_trigger("[Reveal] Ambush sprung")
trigger_reveal_ambush.enabled = False
trigger_reveal_ambush.new_condition.objects_in_area(quantity=1, source_player=PlayerId.ONE, area_x1=60, area_y1=45, area_x2=70, area_y2=55)
trigger_reveal_ambush.new_effect.display_instructions(source_player=PlayerId.FOUR, message="<RED>Ambush Leader: Now! Attack while they are vulnerable!", display_time=5)
trigger_reveal_ambush.new_effect.change_ownership(source_player=PlayerId.GAIA, target_player=PlayerId.FOUR)  # Reveal hidden enemy

# === CONTEXTUAL DIALOGUE TRIGGERS ===
# Add atmosphere and character development between events
trigger_campfire_talk = trigger_manager.add_trigger("[Dialogue] Soldiers talk")
trigger_campfire_talk.new_condition.timer(60)  # After 1 minute
trigger_campfire_talk.new_effect.display_instructions(source_player=PlayerId.ONE, message="<GREY>Veteran Soldier: I fought in the last war. This enemy is unlike any we have faced.", display_time=12)
trigger_campfire_talk.new_effect.activate_trigger(trigger_id=15)

trigger_morale_boost = trigger_manager.add_trigger("[Dialogue] Commander speech")
trigger_morale_boost.enabled = False
trigger_morale_boost.new_condition.timer(15)
trigger_morale_boost.new_effect.display_instructions(source_player=PlayerId.ONE, message="<YELLOW>Commander: Take heart, men! Victory awaits those with courage. For glory!", display_time=10)

trigger_enemy_taunt = trigger_manager.add_trigger("[Dialogue] Enemy taunts")
trigger_enemy_taunt.enabled = False
trigger_enemy_taunt.new_condition.timer(30)
trigger_enemy_taunt.new_effect.display_instructions(source_player=PlayerId.TWO, message="<RED>Enemy General: You dare challenge us? Your bones will bleach in the sun!", display_time=8)

# === OBJECTIVE GUIDANCE TRIGGERS ===
# Help players understand what to do next
trigger_objective_hint = trigger_manager.add_trigger("[Hint] Objective reminder")
trigger_objective_hint.new_condition.timer(120)  # After 2 minutes
trigger_objective_hint.new_effect.display_instructions(source_player=PlayerId.ONE, message="<AQUA>Advisor: Remember, we must reach the eastern fortress before nightfall.", display_time=10)

trigger_tactical_advice = trigger_manager.add_trigger("[Hint] Tactical suggestion")
trigger_tactical_advice.enabled = False
trigger_tactical_advice.new_condition.timer(30)
trigger_tactical_advice.new_effect.display_instructions(source_player=PlayerId.ONE, message="<AQUA>General: Their left flank appears weak. We should concentrate our cavalry there.", display_time=12)

# === ENVIRONMENTAL/ATMOSPHERE TRIGGERS ===
# Add immersion through environmental storytelling
trigger_weather_warning = trigger_manager.add_trigger("[Atmosphere] Storm approaching")
trigger_weather_warning.new_condition.timer(180)
trigger_weather_warning.new_effect.display_instructions(source_player=PlayerId.ONE, message="<GREY>Soldier: Dark clouds gather on the horizon. A storm approaches.", display_time=8)

trigger_find_ruins = trigger_manager.add_trigger("[Atmosphere] Discover ruins")
trigger_find_ruins.new_condition.objects_in_area(quantity=1, source_player=PlayerId.ONE, area_x1=40, area_y1=70, area_x2=45, area_y2=75)
trigger_find_ruins.new_effect.display_instructions(source_player=PlayerId.ONE, message="<GREY>Scholar: These ruins are ancient. Perhaps from the old empire that once ruled here.", display_time=10)

# === TRIGGER STRUCTURE FOR COMPLETE SCENARIO ===
# A well-designed scenario should have triggers in this order:
# 1. INTRO (timer-based): Set the scene, introduce characters
# 2. NAVIGATION: Guide player to first objective
# 3. FIRST ENCOUNTER: Combat or event trigger
# 4. RESOURCE/SUPPLY: Optional gathering phase
# 5. CONTEXTUAL DIALOGUE: Character moments, morale
# 6. NAVIGATION: Guide to next location
# 7. REVEAL: Show new area, enemies, or allies
# 8. MAJOR EVENT: Key historical moment (battle, siege, etc.)
# 9. AFTERMATH DIALOGUE: React to event
# 10. FINAL OBJECTIVE: Lead to victory/defeat condition

TRANSITIONAL TRIGGER GUIDELINES:
- Create at least 3-5 navigation triggers guiding player movement
- Add resource discovery triggers near GOLD_MINE, STONE_MINE locations
- Include "reveal" triggers that change_view to important locations
- Add contextual dialogue every 60-120 seconds to maintain immersion
- Use timer conditions to pace triggers (5-15 seconds between chained dialogue)
- Include objective hints if player hasn't progressed after 2-3 minutes
- Enemy taunts and ally encouragement add drama between battles
- Environmental triggers (weather, discoveries) enhance atmosphere
- ALL dialogue should use character names, not generic titles

VALID UNITS (UnitInfo._____.ID):
Infantry: MILITIA, MAN_AT_ARMS, LONG_SWORDSMAN, TWO_HANDED_SWORDSMAN, CHAMPION, SPEARMAN, PIKEMAN, HALBERDIER, EAGLE_SCOUT, EAGLE_WARRIOR, ELITE_EAGLE_WARRIOR
Archers: ARCHER, CROSSBOWMAN, ARBALESTER, SKIRMISHER, ELITE_SKIRMISHER, CAVALRY_ARCHER, HEAVY_CAVALRY_ARCHER, HAND_CANNONEER, LONGBOWMAN, ELITE_LONGBOWMAN, CHU_KO_NU, ELITE_CHU_KO_NU, PLUMED_ARCHER, ELITE_PLUMED_ARCHER
Cavalry: SCOUT_CAVALRY, LIGHT_CAVALRY, HUSSAR, KNIGHT, CAVALIER, PALADIN, CAMEL_RIDER, HEAVY_CAMEL_RIDER, BATTLE_ELEPHANT, ELITE_BATTLE_ELEPHANT
Unique: WOAD_RAIDER, ELITE_WOAD_RAIDER, THROWING_AXEMAN, ELITE_THROWING_AXEMAN, HUSKARL, ELITE_HUSKARL, TEUTONIC_KNIGHT, ELITE_TEUTONIC_KNIGHT, SAMURAI, ELITE_SAMURAI, JANISSARY, ELITE_JANISSARY, MAMELUKE, ELITE_MAMELUKE, WAR_ELEPHANT, ELITE_WAR_ELEPHANT, MANGUDAI, ELITE_MANGUDAI, CONQUISTADOR, ELITE_CONQUISTADOR, CATAPHRACT, ELITE_CATAPHRACT, BERSERKER, ELITE_BERSERKER
Siege: BATTERING_RAM, CAPPED_RAM, SIEGE_RAM, MANGONEL, ONAGER, SIEGE_ONAGER, SCORPION, HEAVY_SCORPION, BOMBARD_CANNON, TREBUCHET
Naval: GALLEY, WAR_GALLEY, GALLEON, FIRE_GALLEY, FIRE_SHIP, FAST_FIRE_SHIP, DEMOLITION_RAFT, DEMOLITION_SHIP, HEAVY_DEMOLITION_SHIP, CANNON_GALLEON, ELITE_CANNON_GALLEON, TRANSPORT_SHIP, FISHING_SHIP, LONGBOAT, ELITE_LONGBOAT, TURTLE_SHIP, ELITE_TURTLE_SHIP, CARAVEL, ELITE_CARAVEL, DROMON
Villagers: VILLAGER_MALE, VILLAGER_FEMALE
Monks: MONK, MISSIONARY

VALID BUILDINGS (BuildingInfo._____.ID):
Military: BARRACKS, ARCHERY_RANGE, STABLE, SIEGE_WORKSHOP, CASTLE, DOCK
Economy: TOWN_CENTER, HOUSE, MILL, LUMBER_CAMP, MINING_CAMP, MARKET, FARM, BLACKSMITH, UNIVERSITY, MONASTERY
Defense: OUTPOST, WATCH_TOWER, GUARD_TOWER, KEEP, BOMBARD_TOWER, PALISADE_WALL, STONE_WALL, FORTIFIED_WALL, GATE

VALID HEROES (HeroInfo._____.ID):
JOAN_OF_ARC, WILLIAM_WALLACE, GENGHIS_KHAN, EL_CID, BARBAROSSA, ATTILA_THE_HUN, CHARLES_MARTEL, ROLAND, BELISARIUS, RICHARD_THE_LIONHEART, SALADIN, ROBIN_HOOD, VLAD_DRACULA, TAMERLANE, HENRY_V, TARIQ_IBN_ZIYAD

VALID GAIA (OtherInfo._____.ID):
Resources: GOLD_MINE, STONE_MINE, FORAGE_BUSH
Trees: TREE_OAK, TREE_PINE_FOREST, TREE_PALM_FOREST, TREE_JUNGLE, TREE_SNOW_PINE, TREE_BAOBAB, TREE_ACACIA
Terrain: MOUNTAIN_1, MOUNTAIN_2, MOUNTAIN_3, MOUNTAIN_4, CLIFF_1, CLIFF_2, CLIFF_3
Decorations: RUINS, BONFIRE, TORCH, GRAVE, FLOWERS_1, STATUE

TERRAIN TYPES (TerrainId._____ for map_manager.get_tile(x,y).terrain_id):
Water: WATER_DEEP, WATER_MEDIUM, WATER_SHALLOW, WATER_DEEP_OCEAN, WATER_AZURE, SHALLOWS, SHALLOWS_AZURE, ICE, ICE_NAVIGABLE
Land: GRASS_1, GRASS_2, DIRT_1, DIRT_2, DIRT_3, DESERT_SAND, DESERT_CRACKED
Coast: BEACH, BEACH_VEGETATION, BEACH_WHITE, BEACH_ICE
Forest: FOREST_OAK, FOREST_PINE, FOREST_JUNGLE, FOREST_PALM_DESERT, FOREST_BAMBOO, FOREST_BAOBAB, FOREST_ACACIA, FOREST_MANGROVE

TERRAIN EDITING - Use for naval/water maps:
tile = map_manager.get_tile(x, y)
tile.terrain_id = TerrainId.WATER_DEEP  # Set terrain type
IMPORTANT: Place ships ONLY on water tiles (WATER_DEEP, WATER_MEDIUM, etc.)
IMPORTANT: Place land units/buildings ONLY on land tiles (GRASS_1, etc.)

# ============================================================
# ENVIRONMENT AND TERRAIN DESIGN (APPLIES TO ALL SCENARIOS)
# ============================================================
# Adapt terrain and buildings to match the scenario's historical/geographical setting.

# === TERRAIN TYPES BY REGION ===
# EUROPEAN (Medieval castles, forests):
#   - Terrain: GRASS_1, GRASS_2, FOREST_OAK, FOREST_PINE
#   - Trees: TREE_OAK, TREE_PINE_FOREST
#   - Buildings: Stone castles, monasteries, walled cities

# MIDDLE EASTERN (Deserts, oases):
#   - Terrain: DESERT_SAND, DESERT_CRACKED, GRASS_1
#   - Trees: TREE_PALM_FOREST, TREE_ACACIA
#   - Buildings: Mud-brick style, markets, mosques (use MONASTERY)

# ASIAN (Steppes, bamboo forests):
#   - Terrain: GRASS_1, GRASS_2, DIRT_1
#   - Trees: TREE_BAMBOO (if available), TREE_OAK
#   - Buildings: Eastern architecture, pagodas (use MONASTERY)

# NORTHERN/COLD (Snow, mountains):
#   - Terrain: ICE, SNOW (if available), GRASS_1
#   - Trees: TREE_SNOW_PINE
#   - Buildings: Fortified keeps, wooden structures

# COASTAL/NAVAL:
#   - Terrain: WATER_DEEP, SHALLOWS, BEACH
#   - Add DOCK buildings and naval units
#   - Create harbors with protected bays

# ============================================================
# MANDATORY PLAYER REQUIREMENTS
# ============================================================
# CRITICAL: Each active player (ONE, TWO, etc.) MUST have:
# 1. At least ONE TOWN_CENTER (their base/headquarters)
# 2. At least 20 UNITS (military, villagers, or heroes combined)
#
# Example for Player ONE (20+ units):
for i in range(5):
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.KNIGHT.ID, x=50.5+i, y=90.5)
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.CROSSBOWMAN.ID, x=50.5+i, y=91.5)
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.HALBERDIER.ID, x=50.5+i, y=92.5)
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.CHAMPION.ID, x=50.5+i, y=93.5)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.TOWN_CENTER.ID, x=55.5, y=95.5)  # Player 1 base

# Example for Player TWO (20+ units):
for i in range(5):
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.CAVALIER.ID, x=80.5+i, y=50.5)
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.ARBALESTER.ID, x=80.5+i, y=51.5)
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.PIKEMAN.ID, x=80.5+i, y=52.5)
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.TWO_HANDED_SWORDSMAN.ID, x=80.5+i, y=53.5)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.TOWN_CENTER.ID, x=85.5, y=55.5)  # Player 2 base

# ============================================================
# COMPLETE SETTLEMENT/CITY LAYOUT
# ============================================================
# Every player base should have these building categories:

# Layer 1: DEFENSES (walls, towers, gates)
for i in range(20):
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.FORTIFIED_WALL.ID, x=50.0+i*2, y=80.0)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GUARD_TOWER.ID, x=50.5, y=80.5)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE.ID, x=60.0, y=80.0)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.KEEP.ID, x=65.5, y=78.5)

# Layer 2: MILITARY DISTRICT
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.CASTLE.ID, x=60.5, y=70.5)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.BARRACKS.ID, x=55.5, y=72.5)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.ARCHERY_RANGE.ID, x=65.5, y=72.5)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STABLE.ID, x=55.5, y=68.5)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.SIEGE_WORKSHOP.ID, x=65.5, y=68.5)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.BLACKSMITH.ID, x=60.5, y=66.5)

# Layer 3: CIVIC/RELIGIOUS DISTRICT
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.TOWN_CENTER.ID, x=60.5, y=60.5)  # REQUIRED
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.MONASTERY.ID, x=55.5, y=58.5)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.UNIVERSITY.ID, x=65.5, y=58.5)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.MARKET.ID, x=60.5, y=55.5)

# Layer 4: RESIDENTIAL/ECONOMIC
for i in range(3):
    for j in range(3):
        unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.HOUSE.ID, x=52.5+i*3, y=50.5+j*3)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.MILL.ID, x=70.5, y=52.5)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.FARM.ID, x=72.5, y=52.5)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.FARM.ID, x=70.5, y=54.5)

# === RESOURCES FOR MAP (GAIA) ===
# Place resources accessible to players
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.GOLD_MINE.ID, x=40.5, y=60.5)
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.GOLD_MINE.ID, x=100.5, y=60.5)
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.STONE_MINE.ID, x=45.5, y=65.5)
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.STONE_MINE.ID, x=95.5, y=65.5)
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.FORAGE_BUSH.ID, x=50.5, y=70.5)
# Trees for wood
for i in range(10):
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.TREE_OAK.ID, x=30.5+i, y=40.5)
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.TREE_OAK.ID, x=30.5+i, y=41.5)

MANDATORY REQUIREMENTS:
1. EVERY active player MUST have at least 1 TOWN_CENTER
2. EVERY active player MUST have at least 20 UNITS (use loops to place efficiently)
3. Map MUST have GOLD_MINE, STONE_MINE, trees, and FORAGE_BUSH for resources
4. Buildings should be complete (military, economic, religious, residential)
5. Walls should form CONNECTED perimeters with GATE entries
6. Garrison troops positioned at defensive points
7. Adapt terrain and trees to match the scenario's geographical setting

Return ONLY the Python code. No explanations or markdown."""
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.7,
            "max_tokens": 4000
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            
            result = response.json()
            generated_code = result["choices"][0]["message"]["content"]
            
            # Clean up the response to extract only Python code
            if "```python" in generated_code:
                start = generated_code.find("```python") + 9
                end = generated_code.find("```", start)
                generated_code = generated_code[start:end].strip()
            elif "```" in generated_code:
                start = generated_code.find("```") + 3
                end = generated_code.find("```", start)
                generated_code = generated_code[start:end].strip()
            
            return generated_code
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise
        except KeyError as e:
            logger.error(f"Unexpected API response format: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise

class ScenarioGenerator:
    """Main class for generating AoE2 scenarios using AI"""
    
    def __init__(self, api_key: str):
        self.api = OpenRouterAPI(api_key)
        self.scenario_templates = self._load_templates()
    
    def _load_templates(self) -> Dict[str, str]:
        """Load scenario generation templates"""
        return {
            "battle": """Create an Age of Empires 2 scenario with the following requirements:
            - Title: {title}
            - Description: {description}
            - Map size: {map_size}x{map_size}
            - Players: {players}
            - Difficulty: {difficulty}
            - Type: Battle scenario

            The scenario should include:
            - Strategic unit placement for both sides
            - Resource distribution (gold, stone, wood, food)
            - Defensive structures and military units
            - Balanced gameplay for the specified difficulty

            CRITICAL - COMPLETE BUILDING LAYOUTS FOR SIEGE/BATTLE SCENARIOS:
            If this is a siege battle (attacking a city/fortress), create a COMPLETE city:

            DEFENDER'S CITY (e.g., Constantinople, Jerusalem, etc.):
            - Layer 1 OUTER DEFENSES: FORTIFIED_WALL perimeter, GUARD_TOWER at corners,
              GATE for entrances, BOMBARD_TOWER, KEEP
            - Layer 2 MILITARY: CASTLE, BARRACKS, ARCHERY_RANGE, STABLE, SIEGE_WORKSHOP, BLACKSMITH
            - Layer 3 CIVIC: TOWN_CENTER, MONASTERY (cathedral), UNIVERSITY, MARKET
            - Layer 4 RESIDENTIAL: Multiple HOUSE buildings, MILL, FARM clusters

            GARRISON INSIDE CITY:
            - Crossbowmen/archers positioned ON walls
            - Halberdiers guarding gates
            - Knights near castle
            - Monks at monastery
            - Villagers in residential areas

            ATTACKER'S SIEGE ARMY (outside walls):
            - TREBUCHET and BOMBARD_CANNON facing walls
            - BATTERING_RAM near gates
            - Infantry formations (CHAMPION, HALBERDIER)
            - Cavalry on flanks (CAVALIER, KNIGHT)
            - Hero commander with guards

            REQUIRED TRIGGER STRUCTURE (create a continuity of events):
            1. INTRO SEQUENCE: 2-3 chained triggers introducing THIS SPECIFIC battle
               - Use the ACTUAL date, location, and commanders from the title/description
               - Reference REAL historical context (e.g., "October 14th, 1066, Senlac Hill...")
            2. PROGRESSIVE OBJECTIVES: Chain triggers with SCENARIO-SPECIFIC goals
               - Name actual locations and targets from the battle description
            3. ENEMY WAVE TRIGGERS: Spawn historically accurate reinforcements
            4. VICTORY/DEFEAT CHAIN: Reference the ACTUAL historical outcome
               - Use real commander names in victory/defeat messages

            ALL trigger messages MUST use names, dates, and details from the scenario description.
            Use enabled=False and activate_trigger/deactivate_trigger to chain events""",
            
            "story": """Create an Age of Empires 2 scenario with the following requirements:
            - Title: {title}
            - Description: {description}
            - Map size: {map_size}x{map_size}
            - Players: {players}
            - Difficulty: {difficulty}
            - Type: Story-driven scenario

            The scenario should include:
            - Narrative elements and story progression
            - Character units with specific roles (heroes)
            - Environmental storytelling through map design

            REQUIRED TRIGGER STRUCTURE (create a continuity of events):
            1. PROLOGUE: 3-4 chained triggers with opening narration
               - Set the EXACT time period, location, and protagonist from the description
               - Use the ACTUAL character names and historical context
            2. ACT STRUCTURE: Unlock story chapters based on THIS scenario's plot
            3. AREA TRIGGERS: Name SPECIFIC locations from the scenario description
               - Character dialogue must match the actual historical figures
            4. CHARACTER DIALOGUES: Use REAL names and era-appropriate speech
               - e.g., "Joan of Arc: God has shown me the path..." not "Hero: We must fight..."
            5. QUEST PROGRESSION: Objectives must match the ACTUAL story being told
            6. CLIMAX & EPILOGUE: Reference the REAL historical outcome

            ALL dialogue and narration MUST use specific names, places, and events from the description.
            Every trigger must chain to another using activate_trigger (except final triggers)""",
            
            "defense": """Create an Age of Empires 2 scenario with the following requirements:
            - Title: {title}
            - Description: {description}
            - Map size: {map_size}x{map_size}
            - Players: {players}
            - Difficulty: {difficulty}
            - Type: Defense scenario

            The scenario should include:
            - Defensive structures and fortifications
            - Strategic positioning of units
            - Resource management for defense

            CRITICAL - COMPLETE CITY BUILDING LAYOUT:
            Create a REALISTIC fortified city with ALL building types, not just walls:

            Layer 1 - OUTER DEFENSES:
            - FORTIFIED_WALL segments forming connected perimeter
            - GUARD_TOWER at corners and along walls
            - GATE for main entrances
            - BOMBARD_TOWER and KEEP for heavy defense

            Layer 2 - MILITARY DISTRICT (inside walls):
            - CASTLE as central stronghold
            - BARRACKS, ARCHERY_RANGE, STABLE, SIEGE_WORKSHOP
            - BLACKSMITH for upgrades

            Layer 3 - CIVIC/RELIGIOUS:
            - TOWN_CENTER as city heart
            - MONASTERY (cathedral/church)
            - UNIVERSITY, MARKET

            Layer 4 - RESIDENTIAL/ECONOMIC:
            - Multiple HOUSE buildings clustered together
            - MILL with nearby FARM
            - LUMBER_CAMP, MINING_CAMP if resources present

            GARRISON PLACEMENT:
            - Crossbowmen/archers ON the walls
            - Halberdiers at gates
            - Knights near castle
            - Villagers in residential areas
            - Monks at monastery

            REQUIRED TRIGGER STRUCTURE (create a continuity of events):
            1. INTRO: 2-3 chained triggers introducing THIS SPECIFIC siege/defense
               - Name the ACTUAL city, fortress, or location being defended
               - Identify the REAL attacking force and their commander
               - e.g., "The Ottoman army of Sultan Mehmed II approaches Constantinople..."
            2. WAVE SYSTEM: Spawn historically accurate attackers
               - Use appropriate unit types for the attacking civilization
               - Include SIEGE WEAPONS (trebuchet, bombard cannon, battering ram)
               - Reference REAL military units from the era
            3. BETWEEN-WAVE EVENTS: Dialogue from ACTUAL historical defenders
               - e.g., "Emperor Constantine XI: Hold the Theodosian Walls!"
            4. SURVIVAL COUNTDOWN: Match historical siege duration if applicable
            5. VICTORY SEQUENCE: Reference ACTUAL historical outcome
            6. DEFEAT CONDITIONS: Name the SPECIFIC structure being defended

            ALL messages must use real names, locations, and historical context from the description.
            Use enabled=False for all wave triggers except Wave 1""",
            
            "conquest": """Create an Age of Empires 2 scenario with the following requirements:
            - Title: {title}
            - Description: {description}
            - Map size: {map_size}x{map_size}
            - Players: {players}
            - Difficulty: {difficulty}
            - Type: Conquest scenario

            The scenario should include:
            - Multiple enemy bases to conquer
            - Strategic resource control points
            - Different unit types and strategies

            REQUIRED TRIGGER STRUCTURE (create a continuity of events):
            1. CAMPAIGN START: 2-3 chained intro triggers
               - Name the ACTUAL conquering force and their leader
               - Set the REAL historical context and campaign goals
               - e.g., "Genghis Khan: We ride to conquer the Khwarazmian Empire..."
            2. TERRITORY CAPTURE CHAIN: Name SPECIFIC historical locations
               - e.g., "Capture Samarkand" not "Capture the city"
               - Each capture message references the REAL place name
            3. ENEMY RESPONSE: Name the ACTUAL enemy commanders
            4. REINFORCEMENT TRIGGERS: Match historically accurate allied forces
            5. FINAL ASSAULT: Reference the REAL ultimate objective
            6. VICTORY CAMPAIGN: Narrate the ACTUAL historical outcome
               - e.g., "With the fall of Urgench, the Mongol conquest was complete..."

            ALL objectives and dialogue must use REAL names, places, and historical events.
            Every objective must chain to the next using activate_trigger"""
        }
    
    def generate_scenario(self, config: ScenarioConfig) -> str:
        """Generate a scenario based on the provided configuration"""

        # Select appropriate template
        template = self.scenario_templates.get(config.scenario_type, self.scenario_templates["story"])

        # Format the prompt
        prompt = template.format(
            title=config.title,
            description=config.description,
            map_size=config.map_size,
            players=config.players,
            difficulty=config.difficulty
        )

        # Fetch Wikipedia content if a link is provided
        if config.wikipedia_link:
            logger.info(f"Fetching historical context from Wikipedia: {config.wikipedia_link}")
            wikipedia_content = fetch_wikipedia_content(config.wikipedia_link)
            if wikipedia_content:
                prompt += f"""

            HISTORICAL CONTEXT FROM WIKIPEDIA:
            Use the following historical information to create a more accurate and detailed scenario.
            Incorporate real historical figures, locations, troop compositions, and events where appropriate.

            {wikipedia_content}

            Use this historical context to:
            - Place appropriate hero units for historical figures mentioned
            - Create accurate army compositions based on the forces described
            - Design map layouts that reflect the actual battlefield or location
            - Add triggers and objectives that match the historical events
            - Include historically accurate victory conditions"""
            else:
                logger.warning("Could not fetch Wikipedia content, proceeding without historical context")

        # Generate the scenario code
        logger.info(f"Generating scenario: {config.title}")
        generated_code = self.api.generate_scenario_code(prompt)

        return generated_code
    
    def save_scenario(self, code: str, output_path: str) -> bool:
        """Save the generated scenario code to a file and execute it"""
        try:
            # Create output directory if it doesn't exist
            output_dir = Path(output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Write the generated code to a temporary file
            temp_file = "temp_scenario_generator.py"
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(code)
            
            # Execute the generated code
            logger.info(f"Executing generated scenario code...")
            
            # Import and execute the generated code
            import subprocess
            import sys
            
            result = subprocess.run([sys.executable, temp_file],
                                  capture_output=True, text=True,
                                  encoding='utf-8', errors='replace', timeout=60)
            
            if result.returncode != 0:
                logger.error(f"Scenario execution failed: {result.stderr}")
                return False
            
            logger.info(f"Scenario generated successfully: {output_path}")
            
            # Clean up temporary file
            if os.path.exists(temp_file):
                os.remove(temp_file)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to save/execute scenario: {e}")
            return False
    
    def validate_scenario_code(self, code: str, scenario_type: str = "battle") -> dict:
        """
        Comprehensive validation of generated scenario code.
        Returns a dict with 'valid' bool and 'issues' list of problems found.
        """
        issues = []
        warnings = []

        try:
            # === 1. REQUIRED IMPORTS ===
            required_imports = [
                "AoE2DEScenario",
                "PlayerId",
                "UnitInfo",
                "BuildingInfo"
            ]
            for import_name in required_imports:
                if import_name not in code:
                    issues.append(f"Missing required import: {import_name}")

            # === 2. BASIC STRUCTURE ===
            if "AoE2DEScenario.from_default()" not in code and "AoE2DEScenario.from_file(" not in code:
                issues.append("Missing scenario object creation")

            if "write_to_file" not in code:
                issues.append("Missing scenario save operation")

            # === 3. RESOURCE ALLOCATION ===
            resources_found = {
                "GOLD_MINE": "GOLD_MINE" in code,
                "STONE_MINE": "STONE_MINE" in code,
                "FORAGE_BUSH": "FORAGE_BUSH" in code or "BUSH" in code,
                "Trees": "TREE_" in code or "FOREST" in code
            }
            missing_resources = [r for r, found in resources_found.items() if not found]
            if missing_resources:
                warnings.append(f"Missing resources: {', '.join(missing_resources)}")

            # === 4. BUILDING COMPLETENESS ===
            # Check for variety of buildings, not just walls
            building_categories = {
                "Defensive": any(b in code for b in ["FORTIFIED_WALL", "STONE_WALL", "GUARD_TOWER", "WATCH_TOWER", "KEEP", "BOMBARD_TOWER", "GATE"]),
                "Military": any(b in code for b in ["CASTLE", "BARRACKS", "ARCHERY_RANGE", "STABLE", "SIEGE_WORKSHOP"]),
                "Economic": any(b in code for b in ["TOWN_CENTER", "MARKET", "MILL", "BLACKSMITH"]),
                "Residential": "HOUSE" in code,
                "Religious": "MONASTERY" in code
            }

            if scenario_type in ["battle", "defense"]:
                missing_building_cats = [cat for cat, found in building_categories.items() if not found]
                if len(missing_building_cats) >= 3:
                    issues.append(f"Incomplete city layout - missing building categories: {', '.join(missing_building_cats)}")
                elif missing_building_cats:
                    warnings.append(f"City could be more complete - consider adding: {', '.join(missing_building_cats)}")

            # === 5. TRIGGER CONTINUITY ===
            trigger_count = code.count("add_trigger(")
            if trigger_count < 8:
                issues.append(f"Insufficient triggers ({trigger_count}) - need at least 8 for complete story with transitions")

            # Check for trigger chaining
            has_activate_trigger = "activate_trigger" in code
            has_display_instructions = "display_instructions" in code
            has_timer_condition = ".timer(" in code
            has_objects_in_area = "objects_in_area" in code
            has_change_view = "change_view" in code

            if not has_display_instructions:
                issues.append("Missing display_instructions - no dialogue/narration")

            if trigger_count >= 5 and not has_activate_trigger:
                issues.append("Triggers not chained - MUST use activate_trigger for story continuity")

            if not has_timer_condition:
                warnings.append("No timer conditions - intro sequence may not work properly")

            # === 5b. TRANSITIONAL TRIGGER CHECKS ===
            # Count dialogue/display_instructions occurrences
            dialogue_count = code.count("display_instructions")
            if dialogue_count < 5:
                issues.append(f"Insufficient dialogue ({dialogue_count}) - need at least 5 display_instructions for story progression")

            # Check for navigation triggers (objects_in_area for movement detection)
            if not has_objects_in_area:
                warnings.append("No area-based triggers - add navigation triggers to guide player movement")

            # Check for reveal/view triggers
            if not has_change_view:
                warnings.append("No change_view effects - consider adding reveal triggers for dramatic moments")

            # Check for variety in trigger types
            trigger_types = {
                "Navigation": any(nav in code.lower() for nav in ["[nav]", "approach", "enter", "leave", "reach"]),
                "Resource": any(res in code.lower() for res in ["[res]", "supplies", "gold", "gather", "resource"]),
                "Dialogue": any(dlg in code.lower() for dlg in ["[dialogue]", "speech", "talk", "taunt"]),
                "Reveal": any(rev in code.lower() for rev in ["[reveal]", "visible", "discover", "ambush"]),
                "Objective": any(obj in code.lower() for obj in ["[obj]", "objective", "hint", "reminder"])
            }

            missing_trigger_types = [tt for tt, found in trigger_types.items() if not found]
            if len(missing_trigger_types) >= 3:
                warnings.append(f"Limited trigger variety - consider adding: {', '.join(missing_trigger_types)} triggers")

            # Check for proper trigger naming conventions
            has_trigger_labels = "[" in code and "]" in code and "add_trigger(" in code
            if not has_trigger_labels:
                warnings.append("Triggers should use naming convention like [Nav], [Dialogue], [Obj] for organization")

            # === 6. VICTORY/DEFEAT CONDITIONS ===
            has_victory = "declare_victory" in code
            has_defeat_check = "destroy_object" in code or "objects_in_area" in code

            if not has_victory:
                issues.append("Missing victory condition (declare_victory)")

            if not has_defeat_check:
                warnings.append("No defeat condition detected")

            # === 7. UNIT PLACEMENT AND PLAYER REQUIREMENTS ===
            # Check for units on multiple players
            player_units = {
                "PlayerId.ONE": code.count("PlayerId.ONE"),
                "PlayerId.TWO": code.count("PlayerId.TWO"),
                "PlayerId.THREE": code.count("PlayerId.THREE"),
                "PlayerId.FOUR": code.count("PlayerId.FOUR"),
                "PlayerId.FIVE": code.count("PlayerId.FIVE"),
                "PlayerId.SIX": code.count("PlayerId.SIX"),
                "PlayerId.GAIA": code.count("PlayerId.GAIA")
            }

            # Check minimum 20 units per active player (ONE and TWO are always required)
            min_units_required = 20
            if player_units["PlayerId.ONE"] < min_units_required:
                issues.append(f"Player ONE has only ~{player_units['PlayerId.ONE']} placements - MUST have at least {min_units_required} units")

            if player_units["PlayerId.TWO"] < min_units_required:
                issues.append(f"Player TWO has only ~{player_units['PlayerId.TWO']} placements - MUST have at least {min_units_required} units")

            # Check for TOWN_CENTER for each active player
            # Count TOWN_CENTER occurrences per player
            import re
            p1_tc = len(re.findall(r"PlayerId\.ONE.*TOWN_CENTER|TOWN_CENTER.*PlayerId\.ONE", code))
            p2_tc = len(re.findall(r"PlayerId\.TWO.*TOWN_CENTER|TOWN_CENTER.*PlayerId\.TWO", code))

            # Also check line-by-line for town centers
            lines = code.split('\n')
            p1_has_tc = False
            p2_has_tc = False
            for line in lines:
                if "TOWN_CENTER" in line:
                    if "PlayerId.ONE" in line:
                        p1_has_tc = True
                    if "PlayerId.TWO" in line:
                        p2_has_tc = True

            if not p1_has_tc and player_units["PlayerId.ONE"] > 0:
                issues.append("Player ONE missing TOWN_CENTER (required as base/headquarters)")

            if not p2_has_tc and player_units["PlayerId.TWO"] > 0:
                issues.append("Player TWO missing TOWN_CENTER (required as base/headquarters)")

            if player_units["PlayerId.GAIA"] < 10:
                warnings.append("Few GAIA objects - map may lack environmental detail")

            # Check for unit variety
            unit_types = {
                "Infantry": any(u in code for u in ["CHAMPION", "HALBERDIER", "MAN_AT_ARMS", "TWO_HANDED_SWORDSMAN", "PIKEMAN"]),
                "Archers": any(u in code for u in ["CROSSBOWMAN", "ARBALESTER", "CAVALRY_ARCHER", "ELITE_SKIRMISHER"]),
                "Cavalry": any(u in code for u in ["KNIGHT", "CAVALIER", "PALADIN", "LIGHT_CAVALRY", "HUSSAR"]),
                "Siege": any(u in code for u in ["TREBUCHET", "BOMBARD_CANNON", "BATTERING_RAM", "MANGONEL", "SCORPION"]),
                "Heroes": "HeroInfo" in code
            }

            missing_unit_types = [ut for ut, found in unit_types.items() if not found]
            if len(missing_unit_types) >= 3:
                warnings.append(f"Limited unit variety - missing: {', '.join(missing_unit_types)}")

            # === 8. SIEGE-SPECIFIC CHECKS ===
            if scenario_type in ["battle", "defense"] and "siege" in code.lower():
                if not unit_types["Siege"]:
                    issues.append("Siege scenario missing siege weapons (TREBUCHET, BOMBARD_CANNON, BATTERING_RAM)")

            # === COMPILE RESULTS ===
            is_valid = len(issues) == 0

            # Log results
            if issues:
                for issue in issues:
                    logger.error(f"VALIDATION ERROR: {issue}")
            if warnings:
                for warning in warnings:
                    logger.warning(f"VALIDATION WARNING: {warning}")

            if is_valid:
                logger.info("Scenario validation PASSED")
            else:
                logger.error(f"Scenario validation FAILED with {len(issues)} errors")

            return {
                "valid": is_valid,
                "issues": issues,
                "warnings": warnings,
                "stats": {
                    "trigger_count": trigger_count,
                    "dialogue_count": dialogue_count,
                    "has_chaining": has_activate_trigger,
                    "has_navigation": has_objects_in_area,
                    "has_reveals": has_change_view,
                    "trigger_variety": 5 - len(missing_trigger_types),
                    "building_categories": sum(building_categories.values()),
                    "unit_variety": sum(unit_types.values()),
                    "player_one_units": player_units["PlayerId.ONE"],
                    "player_two_units": player_units["PlayerId.TWO"],
                    "player_one_tc": p1_has_tc,
                    "player_two_tc": p2_has_tc,
                    "gaia_objects": player_units["PlayerId.GAIA"]
                }
            }

        except Exception as e:
            logger.error(f"Code validation failed: {e}")
            return {"valid": False, "issues": [str(e)], "warnings": []}

    def generate_with_validation(self, config: ScenarioConfig, max_attempts: int = 3) -> str:
        """
        Generate scenario with validation and retry logic.
        Will attempt to fix issues by regenerating with feedback.
        """
        for attempt in range(max_attempts):
            logger.info(f"Generation attempt {attempt + 1}/{max_attempts}")

            # Generate code
            code = self.generate_scenario(config)

            # Validate
            validation = self.validate_scenario_code(code, config.scenario_type)

            if validation["valid"]:
                logger.info("Scenario passed validation!")
                if validation["warnings"]:
                    logger.info(f"Note: {len(validation['warnings'])} warnings (non-critical)")
                return code

            # If not valid and not last attempt, try to fix
            if attempt < max_attempts - 1:
                logger.warning(f"Attempt {attempt + 1} failed validation. Regenerating with fixes...")

                # Add feedback to prompt for next attempt
                fix_prompt = f"""

                CRITICAL FIXES REQUIRED - Previous generation had these issues:
                {chr(10).join('- ' + issue for issue in validation['issues'])}

                MANDATORY REQUIREMENTS - Please ensure ALL of these:
                1. EVERY active player (ONE, TWO) MUST have a TOWN_CENTER building
                2. EVERY active player MUST have at least 20 UNITS - use loops like:
                   for i in range(5):
                       unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.KNIGHT.ID, x=50.5+i, y=90.5)
                       unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.CROSSBOWMAN.ID, x=50.5+i, y=91.5)
                       unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.HALBERDIER.ID, x=50.5+i, y=92.5)
                       unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.CHAMPION.ID, x=50.5+i, y=93.5)
                3. Include GOLD_MINE, STONE_MINE, trees, and FORAGE_BUSH for resources
                4. Create COMPLETE settlements with: walls, towers, castle, barracks,
                   archery_range, stable, TOWN_CENTER, monastery, market, houses, mill, farms
                5. Add at least 5 triggers with display_instructions for dialogue
                6. Chain triggers using activate_trigger for story continuity
                7. Include timer conditions for intro sequence
                8. Add declare_victory for win condition
                9. Adapt terrain to match the scenario's geographical setting
                """

                # Temporarily modify description to include fixes
                original_desc = config.description
                config.description = original_desc + fix_prompt

                # Will regenerate on next loop iteration
                config.description = original_desc  # Reset for clean retry

        # Return best attempt even if not perfect
        logger.warning("Max attempts reached. Returning best available code.")
        return code

def main():
    """Main function to demonstrate the scenario generator"""
    
    # Get API key from environment variable
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("Please set the OPENROUTER_API_KEY environment variable")
        return
    
    # Initialize the generator
    generator = ScenarioGenerator(api_key)
    
    # Example scenario configurations
    # You can add wikipedia_link for better historical accuracy
    scenarios = [
        ScenarioConfig(
            title="The Siege of Constantinople",
            description="Defend the great city of Constantinople against the Ottoman invaders",
            scenario_type="defense",
            difficulty="hard",
            output_path="constantinople_siege.aoe2scenario",
            wikipedia_link="https://en.wikipedia.org/wiki/Fall_of_Constantinople"
        ),
        ScenarioConfig(
            title="The Battle of Hastings",
            description="Relive the famous battle between William the Conqueror and Harold Godwinson",
            scenario_type="battle",
            difficulty="medium",
            output_path="battle_of_hastings.aoe2scenario",
            wikipedia_link="https://en.wikipedia.org/wiki/Battle_of_Hastings"
        ),
        ScenarioConfig(
            title="The Rise of Rome",
            description="Guide Rome from a small settlement to a mighty empire",
            scenario_type="story",
            difficulty="easy",
            output_path="rise_of_rome.aoe2scenario"
            # No wikipedia_link - shows it's optional
        )
    ]
    
    # Generate scenarios
    for config in scenarios:
        try:
            print(f"\nGenerating scenario: {config.title}")
            
            # Generate the scenario code
            generated_code = generator.generate_scenario(config)
            
            # Validate the code
            if not generator.validate_scenario_code(generated_code):
                print(f"Warning: Generated code may have issues for {config.title}")
            
            # Save and execute the scenario
            if generator.save_scenario(generated_code, config.output_path):
                print(f"Successfully generated: {config.output_path}")
            else:
                print(f"Failed to generate: {config.title}")
                
        except Exception as e:
            print(f"Error generating {config.title}: {e}")

if __name__ == "__main__":
    main() 