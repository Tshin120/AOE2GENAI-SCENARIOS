"""
Campaign Extractor - Extracts scenarios from an AoE2 campaign file (.aoe2campaign)

Usage:
    python extract_campaign.py <campaign_file.aoe2campaign> [output_directory]
"""
import sys
import os
import re
import struct


def find_scenario_offsets(data):
    """Find the start offsets of scenarios in the campaign data."""
    # Scenarios start with version strings like "1.54" or "1.36"
    pattern = rb'1\.[0-9]{2}'
    matches = list(re.finditer(pattern, data))

    offsets = []
    for m in matches:
        offset = m.start()
        # Verify this looks like a scenario header (followed by null bytes)
        if offset + 8 <= len(data):
            next_bytes = data[offset+4:offset+8]
            if next_bytes == b'\x00\x00\x00\x00':
                offsets.append(offset)

    return offsets


def extract_scenarios(campaign_path, output_dir=None):
    """Extract all scenarios from a campaign file."""

    if not os.path.exists(campaign_path):
        print(f"Error: File not found: {campaign_path}")
        return []

    # Default output directory
    if output_dir is None:
        base_name = os.path.splitext(os.path.basename(campaign_path))[0]
        output_dir = os.path.join(os.path.dirname(campaign_path), f"{base_name}_scenarios")

    os.makedirs(output_dir, exist_ok=True)

    print(f"Reading campaign: {campaign_path}")

    with open(campaign_path, 'rb') as f:
        data = f.read()

    print(f"File size: {len(data)} bytes")

    # Read campaign header
    version = data[0:4].decode('ascii', errors='replace')
    print(f"Campaign version: {version}")

    # Find scenario offsets
    offsets = find_scenario_offsets(data)
    print(f"Found {len(offsets)} scenarios")

    if not offsets:
        print("No scenarios found in campaign file")
        return []

    extracted_files = []

    for i, start_offset in enumerate(offsets):
        # Calculate end offset (start of next scenario or end of file)
        if i + 1 < len(offsets):
            end_offset = offsets[i + 1]
        else:
            end_offset = len(data)

        scenario_data = data[start_offset:end_offset]
        scenario_version = data[start_offset:start_offset+4].decode('ascii', errors='replace')

        # Generate output filename
        output_filename = f"scenario_{i+1}.aoe2scenario"
        output_path = os.path.join(output_dir, output_filename)

        # Write scenario file
        with open(output_path, 'wb') as f:
            f.write(scenario_data)

        size_kb = len(scenario_data) / 1024
        print(f"  Extracted: {output_filename} ({size_kb:.1f} KB, version {scenario_version})")
        extracted_files.append(output_path)

    print(f"\nScenarios extracted to: {output_dir}")
    return extracted_files


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_campaign.py <campaign_file.aoe2campaign> [output_directory]")
        print("\nExamples:")
        print("  python extract_campaign.py acam1.aoe2campaign")
        print("  python extract_campaign.py acam1.aoe2campaign ./extracted_scenarios")
        sys.exit(1)

    campaign_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    extracted = extract_scenarios(campaign_path, output_dir)

    if extracted:
        print(f"\nYou can now convert these to Python using:")
        for f in extracted:
            print(f"  python scenario_to_python.py \"{f}\"")


if __name__ == "__main__":
    main()
