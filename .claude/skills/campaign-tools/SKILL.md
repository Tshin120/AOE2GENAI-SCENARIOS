---
name: campaign-tools
description: Extract individual .aoe2scenario files from official .aoe2campaign container files, and inspect a built scenario's map size, units by player, and triggers. Use when working with the campaigns/ directory, pulling scenarios out of a campaign file, or inspecting the contents of any .aoe2scenario artifact.
---

## Campaign Tools

### tools/extract_campaign.py
Extracts individual `.aoe2scenario` files from `.aoe2campaign` container files.

```bash
python tools/extract_campaign.py campaigns/cam3.aoe2campaign
# Creates campaigns/cam3_scenarios/ folder with all scenario files (gitignored)
```

Supports AoE2 DE campaign format (version 2.00).

### tools/view_scenario.py
Displays scenario contents including map size, units by player, and triggers.

```bash
python tools/view_scenario.py campaigns/cam3_scenarios/3_Saladin_1.aoe2scenario
python tools/view_scenario.py samples/siege_of_constantinople_1453.aoe2scenario
```

**Note:** Encrypted `.gpv` campaign files (DLC campaigns) require decryption keys. Unencrypted `.aoe2campaign` files can be extracted directly.

Campaign JSON metadata (`campaigns/cam3.json`, `cam3_layout.json`, `cam4.json`, `cam4_layout.json`)
holds the official intro/outro slideshow and menu-layout definitions, kept as reference material.
