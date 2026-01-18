"""
Scenario Viewer - Displays the contents of an AoE2 scenario file
Supports both .aoe2scenario files and .gpv (encoded campaign) files
"""
import sys
import io
import os
import base64
import struct
import tempfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from AoE2ScenarioParser.scenarios.aoe2_de_scenario import AoE2DEScenario
from AoE2ScenarioParser.datasets.players import PlayerId


def view_gpv_info(filepath):
    """Display information about a .gpv file"""
    with open(filepath, 'rb') as f:
        content = f.read()

    print("=" * 60)
    print(f"GPV FILE: {filepath}")
    print("=" * 60)

    if content[:4] == b'esaB':
        payload_size = struct.unpack('<I', content[4:8])[0]
        extra = struct.unpack('<I', content[8:12])[0]
        data = content[12:]

        print(f"\nFile Format: GPV (encrypted/encoded campaign)")
        print(f"Header Signature: 'esaB' (reversed 'Base')")
        print(f"Total File Size: {len(content):,} bytes")
        print(f"Payload Size: {payload_size:,} bytes")
        print(f"Header Extra Field: {extra}")
        print(f"\n--- ANALYSIS ---")
        print("This file uses a proprietary encoding format.")
        print("The payload data appears to be encrypted or compressed")
        print("using an unknown algorithm.")
        print("\nFirst 64 bytes of payload (hex):")
        print(data[:64].hex())
    else:
        print(f"\nUnknown GPV format (doesn't start with 'esaB')")
        print(f"File Size: {len(content):,} bytes")

    print("\n" + "=" * 60)


def decode_gpv_file(filepath):
    """
    Attempt to decode a .gpv file.
    GPV files appear to have a custom format with 'esaB' header.
    Returns path to decoded temp file or None if unable to decode.
    """
    with open(filepath, 'rb') as f:
        content = f.read()

    # Check for 'esaB' header (reversed 'Base')
    if content[:4] == b'esaB':
        # Header: 4 bytes signature + 4 bytes size + 4 bytes extra
        payload_size = struct.unpack('<I', content[4:8])[0]
        data = content[12:12+payload_size]

        # The data appears to be encrypted/encoded - try various decodings
        # For now, return the raw data to see if AoE2ScenarioParser can handle it
        temp_file = tempfile.NamedTemporaryFile(suffix='.aoe2scenario', delete=False)
        temp_file.write(data)
        temp_file.close()
        return temp_file.name
    return None


def view_raw_scenario_info(filepath):
    """Extract basic info directly from scenario file binary"""
    with open(filepath, 'rb') as f:
        content = f.read()

    print("=" * 60)
    print(f"SCENARIO: {filepath}")
    print("=" * 60)

    # Version string is at the start
    version = content[:4].decode('ascii', errors='ignore').strip('\x00')
    print(f"\nScenario Version: {version}")
    print(f"File Size: {len(content):,} bytes")

    # Try to find readable strings in the file
    print(f"\n--- EMBEDDED STRINGS ---")
    # Look for string patterns
    import re
    # Find printable ASCII sequences of 10+ chars
    strings = re.findall(b'[\x20-\x7e]{10,}', content)
    seen = set()
    for s in strings[:50]:  # Limit output
        decoded = s.decode('ascii')
        if decoded not in seen and not decoded.isspace():
            seen.add(decoded)
            if len(decoded) > 80:
                decoded = decoded[:77] + "..."
            print(f"  {decoded}")

    print("\n" + "=" * 60)
    return None  # Signal we used raw mode


def load_scenario(filepath):
    """Load a scenario file, handling both .aoe2scenario and .gpv formats"""
    if filepath.endswith('.gpv'):
        print(f"Detected .gpv file format. Attempting to decode...\n")
        temp_path = decode_gpv_file(filepath)
        if temp_path:
            try:
                scenario = AoE2DEScenario.from_file(temp_path)
                os.unlink(temp_path)  # Clean up temp file
                return scenario
            except Exception as e:
                os.unlink(temp_path)
                # Show GPV file info instead
                view_gpv_info(filepath)
                return "gpv_failed"
        else:
            print("Error: Unable to decode .gpv file")
            view_gpv_info(filepath)
            return "gpv_failed"
    else:
        try:
            return AoE2DEScenario.from_file(filepath)
        except Exception as e:
            print(f"Warning: AoE2ScenarioParser failed: {e}")
            print("\nFalling back to raw file analysis...")
            view_raw_scenario_info(filepath)
            return "raw_mode"


# Get scenario path from command line or use default
if len(sys.argv) > 1:
    scenario_path = sys.argv[1]
else:
    scenario_path = "test_battle.aoe2scenario"

# Check if file exists
if not os.path.exists(scenario_path):
    print(f"Error: File not found: {scenario_path}")
    print("\nAvailable scenario files in current directory:")
    for f in os.listdir('.'):
        if f.endswith('.aoe2scenario') or f.endswith('.gpv'):
            print(f"  - {f}")
    sys.exit(1)

# Load the scenario file
scenario = load_scenario(scenario_path)
if scenario is None:
    sys.exit(1)
if scenario in ("raw_mode", "gpv_failed"):
    sys.exit(0)  # Already printed info

# Get managers
unit_manager = scenario.unit_manager
trigger_manager = scenario.trigger_manager
map_manager = scenario.map_manager

print("=" * 60)
print(f"SCENARIO: {scenario_path}")
print("=" * 60)

# --- MAP INFO ---
print(f"\n--- MAP INFO ---")
print(f"Map Size: {map_manager.map_size} x {map_manager.map_size}")

# --- UNITS BY PLAYER ---
print(f"\n--- UNITS ---")

# Get units for each player
for player_id in PlayerId:
    try:
        units = unit_manager.get_player_units(player_id)
        if units:
            print(f"\n  Player: {player_id.name} ({len(units)} units)")
            print("  " + "-" * 40)

            # Count unit types
            unit_counts = {}
            for unit in units:
                unit_type = unit.unit_const
                if unit_type not in unit_counts:
                    unit_counts[unit_type] = []
                unit_counts[unit_type].append(unit)

            for unit_type, unit_list in unit_counts.items():
                # Try to get unit name
                name = f"Unit ID {unit_type}"
                try:
                    from AoE2ScenarioParser.datasets.units import UnitInfo
                    from AoE2ScenarioParser.datasets.buildings import BuildingInfo
                    from AoE2ScenarioParser.datasets.heroes import HeroInfo
                    from AoE2ScenarioParser.datasets.other import OtherInfo

                    for dataset in [UnitInfo, BuildingInfo, HeroInfo, OtherInfo]:
                        try:
                            for item in dataset:
                                if item.ID == unit_type:
                                    name = item.name
                                    break
                        except:
                            pass
                        if name != f"Unit ID {unit_type}":
                            break
                except:
                    pass

                # Show positions
                positions = [(int(u.x), int(u.y)) for u in unit_list]
                pos_str = str(positions[:5])
                if len(positions) > 5:
                    pos_str = pos_str[:-1] + ", ...]"
                print(f"    {name}: {len(unit_list)}x at {pos_str}")
    except:
        pass

# --- TRIGGERS ---
print(f"\n--- TRIGGERS ({len(trigger_manager.triggers)} total) ---")

for i, trigger in enumerate(trigger_manager.triggers):
    print(f"\n  [{i+1}] {trigger.name}")
    print(f"      Enabled: {trigger.enabled}")

    # Conditions
    if trigger.conditions:
        print(f"      Conditions ({len(trigger.conditions)}):")
        for cond in trigger.conditions:
            cond_type = cond.condition_type
            cond_name = cond_type.name if hasattr(cond_type, 'name') else str(cond_type)
            print(f"        - {cond_name}")

    # Effects
    if trigger.effects:
        print(f"      Effects ({len(trigger.effects)}):")
        for effect in trigger.effects:
            effect_type = effect.effect_type
            effect_name = effect_type.name if hasattr(effect_type, 'name') else str(effect_type)
            # Try to get message if it's a display instruction
            msg = ""
            if hasattr(effect, 'message') and effect.message:
                msg_text = str(effect.message)
                msg = f' - "{msg_text[:50]}..."' if len(msg_text) > 50 else f' - "{msg_text}"'
            print(f"        - {effect_name}{msg}")

print("\n" + "=" * 60)
print("END OF SCENARIO")
print("=" * 60)
