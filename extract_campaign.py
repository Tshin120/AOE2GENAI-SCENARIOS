"""
Extract scenarios from AoE2 DE campaign files (.aoe2campaign)
Based on rge_campaign format documentation
"""
import struct
import os
import sys

RGE_STRING_ID = 0x0A60

def extract_campaign(campaign_path, output_dir=None):
    """Extract all scenarios from an .aoe2campaign file"""

    if output_dir is None:
        output_dir = os.path.splitext(campaign_path)[0] + "_scenarios"

    os.makedirs(output_dir, exist_ok=True)

    with open(campaign_path, 'rb') as f:
        # Read version (4 bytes)
        version_bytes = f.read(4)
        version = version_bytes.decode('ascii')
        print(f"Campaign Version: {version}")

        if version != "2.00":
            print(f"Warning: Expected version 2.00, got {version}")

        # Read dependency count
        dep_count = struct.unpack('<I', f.read(4))[0]
        print(f"Dependency count: {dep_count}")

        # Skip dependencies (dep_count * 4 bytes)
        dependencies = []
        for _ in range(dep_count):
            dep = struct.unpack('<I', f.read(4))[0]
            dependencies.append(dep)
        print(f"Dependencies: {dependencies}")

        # Read campaign name (256 bytes, null terminated)
        name_bytes = f.read(256)
        campaign_name = name_bytes.split(b'\x00')[0].decode('utf-8', errors='replace')
        print(f"Campaign Name: {campaign_name}")

        # Read scenario count
        scenario_count = struct.unpack('<I', f.read(4))[0]
        print(f"Scenario count: {scenario_count}")
        print()

        # Read scenario headers
        scenarios = []
        for i in range(scenario_count):
            # Size and offset
            size = struct.unpack('<I', f.read(4))[0]
            offset = struct.unpack('<I', f.read(4))[0]

            # String ID check
            string_id = struct.unpack('<H', f.read(2))[0]
            if string_id != RGE_STRING_ID:
                print(f"Warning: Unexpected string ID {hex(string_id)}")

            # Scenario name
            name_len = struct.unpack('<H', f.read(2))[0]
            name = f.read(name_len).decode('utf-8', errors='replace')

            # String ID check
            string_id = struct.unpack('<H', f.read(2))[0]
            if string_id != RGE_STRING_ID:
                print(f"Warning: Unexpected string ID {hex(string_id)}")

            # Filename
            filename_len = struct.unpack('<H', f.read(2))[0]
            filename = f.read(filename_len).decode('utf-8', errors='replace')

            scenarios.append({
                'size': size,
                'offset': offset,
                'name': name,
                'filename': filename
            })

            print(f"Scenario {i+1}: {name}")
            print(f"  Filename: {filename}")
            print(f"  Size: {size:,} bytes")
            print(f"  Offset: {hex(offset)}")

        print()

        # Extract scenarios
        for i, scenario in enumerate(scenarios):
            f.seek(scenario['offset'])
            data = f.read(scenario['size'])

            out_path = os.path.join(output_dir, scenario['filename'])
            with open(out_path, 'wb') as out_f:
                out_f.write(data)

            print(f"Extracted: {out_path}")

    print(f"\nAll {scenario_count} scenarios extracted to: {output_dir}")
    return output_dir


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_campaign.py <campaign_file> [output_dir]")
        print("\nExample:")
        print("  python extract_campaign.py cam2.aoe2campaign")
        print("  python extract_campaign.py cam2.aoe2campaign ./extracted")
        sys.exit(1)

    campaign_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    if not os.path.exists(campaign_file):
        print(f"Error: File not found: {campaign_file}")
        sys.exit(1)

    extract_campaign(campaign_file, output_dir)
