---
name: hd-spice-model-workflow
description: "Use when adding, sourcing, porting, or validating SPICE models in this repo; covers finding authoritative vendor models, integrating them into models/vetco_eurorack.lib or related libraries, fixing ngspice compatibility issues, and validating with scripts/run_spice.py."
user-invocable: true
---

# HD SPICE Model Workflow

Use this skill when the task is to add a new SPICE model, replace a weak model with a better one, or validate whether a newly added model actually runs under this repository's simulation flow.

## Goal

Produce a model that is:
- Authoritatively sourced when possible.
- Explicitly documented when it is a proxy or behavioral approximation.
- Compatible with ngspice through this repository's actual runner, not just by inspection.
- Integrated with the existing library conventions used in [../../../models/vetco_eurorack.lib](../../../models/vetco_eurorack.lib).
- Back-linked to the repository's datasheet index in [../../../models/vetco_eurorack_datasheets.html](../../../models/vetco_eurorack_datasheets.html).

## Repository Conventions

- The main shared model library is [../../../models/vetco_eurorack.lib](../../../models/vetco_eurorack.lib).
- The datasheet index is [../../../models/vetco_eurorack_datasheets.html](../../../models/vetco_eurorack_datasheets.html).
- Single-device subcircuits in that library use the 5-pin order: `IN+ IN- V+ V- OUT`.
- Validation should use [../../../scripts/run_spice.py](../../../scripts/run_spice.py), because it loads KiCad's `ngspice.dll` even when `ngspice` is not on `PATH`.
- Imported vendor PSpice models may need compatibility cleanup for ngspice.
- Datasheet additions should follow the existing HTML table-row format already used in [../../../models/vetco_eurorack_datasheets.html](../../../models/vetco_eurorack_datasheets.html): library part, equivalent, short description, datasheet link, and vendor badge.

## Workflow

### 1. Start With an Authoritative Source

Prefer sources in this order:
1. Manufacturer product page with downloadable simulation model.
2. Manufacturer datasheet or app note with a published macromodel.
3. Major vendor simulation resource tied to the original manufacturer.
4. Only if no official model exists: a clearly labeled behavioral approximation or proxy.

Search terms should be specific, for example:
- `part number SPICE model manufacturer`
- `part number PSpice model`
- `site:ti.com part number model`
- `site:st.com part number spice`

Do not present a proxy as if it were the original manufacturer's model.

### 2. Decide the Integration Strategy

Choose one of these paths:

- Official model exists and is usable: import it, namespace it if needed, and wrap it to match local pin conventions.
- Official model exists but targets PSpice/TINA: port only the needed blocks and fix ngspice incompatibilities.
- No official model exists: build a behavioral approximation from the datasheet and document the limits.
- A close sibling model is the best available option: use it as a proxy only when the relationship is defensible and clearly described.

### 3. Locate and Index the Datasheet

After choosing the model source, locate the correct datasheet for the actual part or the documented equivalent.

When updating [../../../models/vetco_eurorack_datasheets.html](../../../models/vetco_eurorack_datasheets.html):
- Follow the existing section and row structure already present in the file.
- Add a new table row in the appropriate section rather than inventing a new format.
- Match the existing columns: library part, equivalent, short description, and datasheet link.
- Include the vendor badge using the same `vendor-badge` markup pattern already in the file.
- Prefer stable manufacturer-hosted PDF links when possible.
- If you must use a distributor mirror, keep the vendor badge accurate to the actual datasheet owner when that is clear.
- Keep the description short and aligned with the wording already used near neighboring rows.

If the model is a proxy, the datasheet index should still point to the actual datasheet used to justify the entry, and the surrounding model comments should make that relationship explicit.

### 4. Fit the Local Library Style

When editing [../../../models/vetco_eurorack.lib](../../../models/vetco_eurorack.lib):
- Keep comments compact and explicit about source and limitations.
- Preserve existing naming and formatting style.
- Namespace imported helper subcircuits and `.MODEL` names to avoid collisions.
- If a local wrapper is needed, expose the repository's expected pin order even if the vendor subcircuit uses a different order.

### 5. Expect ngspice Porting Work

Common vendor-model issues when moving from PSpice to ngspice include:
- `IF()` expressions in `.PARAM` or `VALUE=` blocks.
- Simulator-specific helper devices or encrypted blocks.
- Implicit assumptions about power-down pins or logic functions.
- Model-name collisions in a combined library.

When porting:
- Make the smallest change that preserves intended behavior.
- Prefer simplifying unused conditional branches over rewriting the whole model.
- Keep a comment near the imported model noting the source and what was adapted.

### 6. Validate With the Real Runner

Always validate with [../../../scripts/run_spice.py](../../../scripts/run_spice.py), not only with static review.

Recommended validation loop:
1. Create a minimal smoke-test netlist or `DESIGN.md` block that includes the edited library and instantiates the new model once.
2. Run:

```text
python scripts/run_spice.py path/to/test.cir
```

Or, when needed:

```text
python scripts/run_spice.py path/to/DESIGN.md --libdir path/to/models
```

3. Read the generated `.txt` output first.
4. Treat parser warnings and expression errors as real failures.
5. If the model runs, inspect the `.csv` or operating-point output for obviously broken behavior.

A successful validation means the model is accepted by the same KiCad/ngspice shared-library path the repo already uses.

## Minimal Smoke-Test Pattern

Use a tiny deck that proves the library can be sourced and the new subcircuit can be instantiated:

```spice
* smoke test
.include "models/vetco_eurorack.lib"
VCC vp 0 DC 12
VEE vm 0 DC -12
VIN inp 0 DC 0
XAMP inp out vp vm out NewModelName
RLOAD out 0 8
.op
.end
```

Adjust the fixture to match the device type being added.

## Decision Rules

- If an official model is unavailable, say so plainly.
- If a proxy is used, name the proxy source and why it was chosen.
- If a datasheet link is added, it should match the actual part or documented equivalent used to justify the model.
- If validation fails, fix the compatibility issue before claiming the model is integrated.
- If the model parses but produces nonsense bias points, keep iterating until the smoke test is credible.

## Expected Output

A completed task using this skill should leave behind:
- A model added or updated in the appropriate library file.
- A matching datasheet row added or updated in [../../../models/vetco_eurorack_datasheets.html](../../../models/vetco_eurorack_datasheets.html).
- Source notes explaining whether it is official, ported, proxy, or behavioral.
- A validation run through [../../../scripts/run_spice.py](../../../scripts/run_spice.py).
- A concise summary of what source was used, what had to be adapted, and how it was verified.
