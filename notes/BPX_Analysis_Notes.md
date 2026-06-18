# Repository Overview

**Purpose:** Implementation of the Battery Parameter eXchange (BPX) format, an open standard for physics-based lithium-ion battery models. Outcome of Faraday Institution Multi-scale Modelling project.

**Primary responsibilities:**
- Parse and validate BPX files (JSON/YAML format)
- Enforce schema compliance for physics-based battery model parameters
- Provide programmatic access to validated battery parameters
- Support multiple model types: SPM (Single Particle Model), SPMe, DFN (Doyle-Fuller-Newman), Partial

**Key concepts:**
- BPX format version management (semantic versioning)
- Multi-component battery representation: cell, electrolyte, electrodes, separator
- Single and blended electrode materials
- Function-based parameters and interpolated tables
- State representation: initial conditions, thermal environment, degradation
- Validation datasets (experiments with time, current, voltage, temperature)

---

# Repository Structure

| Folder/File | Purpose |
|---|---|
| `bpx/` | Main package code |
| `docs/` | Sphinx documentation source |
| `examples/` | Sample BPX files (JSON format) |
| `tests/` | Unit tests using pytest and unittest |
| `pyproject.toml` | Project metadata and dependencies |

**Key files in `bpx/`:**
- `schema.py`: Complete data model definition
- `parsers.py`: File/string parsing entry points
- `utilities.py`: Helper functions for calculations
- `validators.py`: Custom validation logic
- `function.py`: Function expression representation
- `interpolated_table.py`: Tabular data interpolation
- `expression_parser.py`: Mathematical expression parser
- `schema_utils.py`: Schema utility functions
- `base_extra_model.py`: Base Pydantic model configuration

---

# Key Files

## schema.py

**Purpose:** Defines complete BPX data model using Pydantic BaseModel classes with field aliases, validation, and metadata.

**Inputs:**
- Python dictionaries (typically from JSON/YAML parsing)
- Field values: floats, integers, Function expressions, InterpolatedTable objects

**Outputs:**
- Validated Pydantic model instances (BPX root object and nested components)
- Errors via ValidationError for invalid data

**Major classes:**
- `Header`: Metadata (BPX version, title, description, model type)
- `Cell`: Cell-level parameters (area, voltage cutoffs, capacity, thermal properties)
- `Electrolyte`: Electrolyte properties (conductivity, diffusivity, transference number)
- `Particle`: Particle properties (stoichiometry, OCP, diffusivity, reaction rate)
- `Contact`: Base for electrode/separator (thickness, porosity, transport efficiency)
- `Electrode` (variants): Single/Blended, Full model/SPM
- `ParameterisationSPM`, `Parameterisation`, `ParameterisationPartial`: Model-type-specific parameter containers
- `State`, `InitialConditions`, `ThermalState`, `Degradation`: Operational state
- `BPX`: Root class containing header, parameterisation, state, validation
- `Experiment`: Validation dataset (time, current, voltage, temperature arrays)

**Relationships:**
- BPX contains Header and Parameterisation (union type)
- Parameterisation contains Cell, Electrolyte, Electrodes, Separator
- Electrodes can be single-material or blended (dict of Particles)
- BPX optionally contains State and Validation sections
- State contains InitialConditions, ThermalState, optional Degradation

**Field metadata available:**
- `alias`: JSON key name (e.g., "Electrode area [m2]")
- `description`: Human-readable field description
- `examples`: Typical values
- `json_schema_extra`: Additional constraints (e.g., "material_check" for blended electrode validation)

---

## parsers.py

**Purpose:** Convenience functions to parse BPX data from various input formats into validated BPX models.

**Inputs:**
- `parse_bpx_file(filename, v_tol)`: File path (JSON or YAML)
- `parse_bpx_obj(bpx, v_tol)`: Python dictionary
- `parse_bpx_str(bpx, v_tol)`: JSON-formatted string
- `v_tol`: Voltage tolerance in volts for validation (default 0.001 V)

**Outputs:**
- BPX object instance (fully validated)
- Raises ValidationError on invalid input

**Process:**
1. Load input (file, dict, or string)
2. Set voltage tolerance in BPX.Settings.tolerances
3. Call BPX.model_validate()
4. Return validated model

**Relationships:**
- Calls schema.BPX.model_validate() internally
- Used as entry point for users

---

## utilities.py

**Purpose:** High-level calculation functions for battery state quantities derived from BPX parameters.

**Key functions:**

| Function | Inputs | Outputs | Purpose |
|---|---|---|---|
| `get_electrode_stoichiometries(target_soc, bpx)` | SOC (0-1), BPX object | (sto_n, sto_p) tuple | Compute electrode stoichiometries at given SOC using min/max stoichiometry bounds |
| `get_electrode_concentrations(target_soc, bpx)` | SOC (0-1), BPX object | (c_n, c_p) tuple | Compute electrode concentrations at given SOC using max concentration and stoichiometry |

**Relationships:**
- Depends on Parameterisation electrode fields (stoichiometry limits, concentrations)
- Used by simulation tools for state calculations

---

## validators.py

**Purpose:** Custom validation logic independent of Pydantic field validators.

**Key function:**
- `check_sto_limits(param)`: Validates stoichiometry limits against voltage cutoffs
  - Inputs: Parameterisation object with defined OCPs (must be Function type, not InterpolatedTable)
  - Process: Computes voltage from stoichiometry bounds, compares to voltage cutoffs
  - Outputs: Returns param unchanged or issues warnings if mismatch exceeds tolerance
  - Used in: Parameterisation._sto_limit_validation(), ParameterisationSPM._sto_limit_validation()

---

## function.py

**Purpose:** Represents mathematical expressions as Python strings with validation.

**Type:** Subclass of `str`

**Allowed operations:**
- Arithmetic: `+`, `-`, `*`, `/`, `**`
- Math functions: `exp`, `tanh`, `cosh`
- Single variable: `x`

**Methods:**
- `validate(v)`: Static validation via ExpressionParser
- `to_python_function(preamble)`: Converts to callable Python function via code generation

**Example:** `"3.3e-14 * exp(-x / 1000)"` → callable function that takes `x` argument

---

## interpolated_table.py

**Purpose:** Represents tabular data (x, y coordinates) for interpolation-based parameters.

**Structure:**
- `x`: List of floats (independent variable)
- `y`: List of floats (dependent variable, same length as x)

**Validation:** Length of x and y must match

**Use:** OCP tables, coefficient tables in examples

---

## expression_parser.py

**Purpose:** Mathematical expression parser using pyparsing library.

**Supports:** Arithmetic expressions with operator precedence, function calls, variables.

**Method:**
- `parse_string(model_str, parse_all=True)`: Validates expression syntax

**Used by:** Function.validate()

---

## schema_utils.py

**Purpose:** Utility functions for schema validation and material handling.

**Key functions:**
- `get_materials_in_electrode(electrode)`: Returns set of material names from blended electrode or None for single-material
- `validate_section_against_electrodes(section, label, electrode_materials)`: Cross-validates State sections against electrode material configuration
  - Ensures scalar values for single-material electrodes, dicts for blended
  - Checks material keys match exactly

**Used by:** BPX._check_state_against_blended_electrodes()

---

## base_extra_model.py

**Purpose:** Base Pydantic model with strict configuration.

**Configuration:**
- `extra="forbid"`: Reject fields not defined in schema
- `Settings.tolerances`: Dict for voltage tolerance (default 1 mV)

**Used by:** All schema classes inherit from ExtraBaseModel

---

# BPX Data Model

**Overall hierarchy:**
```
BPX (root)
├── Header
├── Parameterisation (union of 3 types selected by model type)
│   ├── Cell
│   ├── Electrolyte
│   ├── Negative electrode (union: single/blended, full/SPM)
│   │   └── Particle(s)
│   ├── Positive electrode (union: single/blended, full/SPM)
│   │   └── Particle(s)
│   ├── Separator (ContactBase only, no particle data)
│   └── User-defined (flexible dict with Function/InterpolatedTable/float values)
├── State (optional except for full/SPMe/DFN models)
│   ├── Initial conditions
│   ├── Thermal environment
│   └── Degradation (optional)
└── Validation (optional dict of Experiments)
```

**Major entities:**

| Entity | Role | Occurrences | Notes |
|---|---|---|---|
| Header | Metadata | 1 | Specifies model type (SPM/SPMe/DFN/Partial) |
| Cell | Bulk parameters | 1 | Area, voltage limits, capacity, thermal properties |
| Electrolyte | Electrolyte properties | 1 | Conductivity and diffusivity (const or function of concentration) |
| Particle | Active material properties | 2+ (neg/pos, single or multiple per blended) | OCP, diffusivity, stoichiometry, kinetics |
| Electrode | Container + electronic properties | 2 (neg/pos) | Thickness, porosity, conductivity |
| Separator | Ionic medium | 1 | Thickness, porosity, transport efficiency |
| State | Operating conditions | 0-1 | Initial SOC, temperature, degradation |
| Experiment | Validation dataset | 0+ | Time series of current, voltage, temperature |

**Relationships:**
- Model type (Header.model) determines which Parameterisation subclass is used
- Electrodes are single-material (Electrode inherits from Particle) or blended (contains dict of Particles)
- SPM electrodes (no separator, no full electrolyte) vs full model (SPMe/DFN with separator)
- State.InitialConditions and State.Degradation must match electrode material structure (scalar for single, dict for blended)

---

# Schema Structure

## Field Metadata

All fields use Pydantic `Field()` with:
- **alias**: JSON key name with units in brackets, e.g., "Electrode area [m2]"
- **description**: Human-readable explanation
- **examples**: Sample values
- **json_schema_extra**: Additional constraints (e.g., `{"material_check": "positive_electrode"}`)

## Major Classes and Hierarchy

### Header
```
Header
├── bpx (alias: "BPX") → semver string
├── title (alias: "Title") → optional string
├── description (alias: "Description") → optional string
├── references (alias: "References") → optional string
└── model (alias: "Model") → Literal["SPM", "SPMe", "DFN", "Partial"]
```

### Cell
```
Cell (extends ExtraBaseModel)
├── electrode_area [m2]
├── external_surface_area [m2] (optional)
├── volume [m3] (optional)
├── number_of_electrodes
├── lower_voltage_cutoff [V]
├── upper_voltage_cutoff [V]
├── nominal_cell_capacity [A.h]
├── reference_temperature [K] (optional)
├── density [kg.m-3] (optional)
└── specific_heat_capacity [J.K-1.kg-1] (optional)
```

### Electrolyte
```
Electrolyte (extends ExtraBaseModel)
├── cation_transference_number
├── diffusivity [m2.s-1] → FloatFunctionTable (const or function of concentration)
├── diffusivity_activation_energy [J.mol-1] (optional)
├── conductivity [S.m-1] → FloatFunctionTable (const or function of concentration)
└── conductivity_activation_energy [J.mol-1] (optional)
```

### Particle
```
Particle (extends ExtraBaseModel)
├── minimum_stoichiometry
├── maximum_stoichiometry
├── maximum_concentration [mol.m-3]
├── particle_radius [m]
├── surface_area_per_unit_volume [m-1]
├── diffusivity [m2.s-1] → FloatFunctionTable (const or function of stoichiometry)
├── diffusivity_activation_energy [J.mol-1] (optional)
├── ocp [V] → FloatFunctionTable (function of stoichiometry)
├── ocp_delith [V] (optional) → FloatFunctionTable (delithiation branch)
├── ocp_lith [V] (optional) → FloatFunctionTable (lithiation branch)
├── gamma_hys (optional) → OCP hysteresis decay constant
├── dudt [V.K-1] (optional) → FloatFunctionTable (entropic change)
├── reaction_rate_constant [mol.m-2.s-1]
└── reaction_rate_constant_activation_energy [J.mol-1] (optional)
```

### Contact (base for Electrode/Separator)
```
Contact (extends ExtraBaseModel)
├── thickness [m]
├── porosity
└── transport_efficiency
```

### Electrode Variants
```
Electrode (extends Contact)
├── conductivity [S.m-1]

ElectrodeSingle (extends Electrode, Particle)
  → Single active material with full model parameters

ElectrodeBlended (extends Electrode)
├── particle (dict) → {material_name: Particle, ...}

ElectrodeSingleSPM (extends ContactBase, Particle)
  → Single material, SPM-specific (minimal parameters)

ElectrodeBlendedSPM (extends ContactBase)
├── particle (dict) → {material_name: Particle, ...}
```

### Parameterisation Variants
```
Parameterisation (full models: SPMe, DFN)
├── cell (required)
├── electrolyte (required)
├── negative_electrode → ElectrodeSingle | ElectrodeBlended (required)
├── positive_electrode → ElectrodeSingle | ElectrodeBlended (required)
├── separator (required)
└── user_defined (optional)

ParameterisationSPM (SPM model only)
├── cell (required)
├── negative_electrode → ElectrodeSingleSPM | ElectrodeBlendedSPM (required)
├── positive_electrode → ElectrodeSingleSPM | ElectrodeBlendedSPM (required)
└── user_defined (optional)

ParameterisationPartial (incomplete parameterisations)
├── cell (optional)
├── electrolyte (optional)
├── negative_electrode (optional)
├── positive_electrode (optional)
├── separator (optional)
└── user_defined (optional)
```

### State Components
```
InitialConditions
├── initial_soc (0-1)
├── initial_temperature [K]
├── initial_electrolyte_concentration [mol.m-3]
├── initial_hysteresis_state_positive → float | dict[str, float]
  (scalar for single-material, dict for blended)
└── initial_hysteresis_state_negative → float | dict[str, float]

ThermalState
├── ambient_temperature [K]
└── heat_transfer_coefficient [W.m-2.K-1]

Degradation
├── lli (Lost Lithium Inventory)
├── lam_positive → float | dict[str, float] (Loss of Active Material, positive)
└── lam_negative → float | dict[str, float] (Loss of Active Material, negative)

State
├── initial_conditions (required)
├── thermal_environment (required)
└── degradation (optional)
```

### Field Type Aliases
```
FloatFunctionTable = Union[float, int, Function, InterpolatedTable]
FloatInt = Union[float, int]
```

## Validation Rules

**Automatic (Pydantic):**
- Type checking for all fields
- Field presence (required vs optional)
- Length matching for InterpolatedTable (x and y must be same length)

**Custom (@field_validator, @model_validator):**
- BPX version format validation (semantic versioning, backward compat for floats)
- Thermal conductivity field enforcement (must be in User-defined section, not Cell)
- Electrode type discrimination (single vs blended based on presence of "Particle" field)
- SPM vs full model type consistency (both electrodes must be same model type)
- Voltage cutoff consistency (stoichiometry bounds must yield voltages within cutoffs ±1mV)
- State section presence (required unless Partial model)
- Material key matching (State fields must match electrode material keys if blended)

---

# Validation Flow

## Entry Point
User calls: `parse_bpx_file()`, `parse_bpx_obj()`, or `parse_bpx_str()` in parsers.py

## Parsing Steps

1. **Load data:**
   - File: JSON/YAML read via pathlib/yaml
   - String: JSON parse via json.loads()
   - Dict: Pass through

2. **Set tolerance:** 
   - `BPX.Settings.tolerances["Voltage [V]"] = v_tol`

3. **Validate:** 
   - `BPX.model_validate(data)`

## Validation Layers (in order)

### Layer 1: Header Validation (schema.Header)
- BPX version format check (regex pattern)
- Model type confirmation (SPM/SPMe/DFN/Partial)

### Layer 2: Parameterisation Type Dispatch (schema.BPX._dispatch_param_subclasses)
- Read Header.model type
- If "Partial": validate as ParameterisationPartial
- If "SPM": expect ParameterisationSPM, fall back to Parameterisation if needed
- Otherwise (SPMe/DFN): expect Parameterisation, fall back to ParameterisationSPM if needed
- Mismatches raise ValueError with diagnostic message

### Layer 3: Parameterisation Component Validation (schema.Parameterisation/ParameterisationSPM/ParameterisationPartial)
- Electrode type selection (_choose_electrode_type validator):
  - If "Particle" key present → Blended type
  - If "Conductivity" key present → Single type
  - SPM vs full determined by presence of "Conductivity"
- Electrode consistency check (_check_consistent_electrode_types):
  - Both electrodes must be same model type (both SPM or both full)

### Layer 4: Field-Level Validation (Pydantic + @field_validator)
- Cell validators: prohibit thermal conductivity, initial/ambient temperature
- Electrolyte validators: prohibit initial concentration (moved to State)
- Function parsing: ExpressionParser validates expression syntax
- InterpolatedTable: length matching

### Layer 5: Stoichiometry Validation (validators.check_sto_limits)
- Compute voltage from STO limits using OCP functions
- Compare to voltage cutoffs
- Issue warnings if outside tolerance

### Layer 6: State Validation (schema.BPX._check_state_against_blended_electrodes)
- For each State section with material_check metadata:
  - If single-material electrode: must be scalar value
  - If blended electrode: must be dict with matching material keys

### Layer 7: State Presence Check (schema.BPX._check_state_present_if_not_partial)
- If not Partial model and no State section → raise error

## Error Generation

**ValidationError raised by Pydantic when:**
- Type mismatch (e.g., string where float expected)
- Field missing (if required)
- Invalid union type
- Custom validator raises

**ValueError raised by custom validators when:**
- Thermal conductivity in Cell section
- Initial/ambient temperature in Cell section
- Initial concentration in Electrolyte section
- Model type mismatch (SPM file claims DFN model)
- Electrode type mismatch (mixed SPM/full)
- State material keys don't match electrode

**BPXSchemaError raised when:**
- State not provided for non-Partial models
- Material key mismatch in State sections

**Warnings issued by check_sto_limits when:**
- Voltage range from stoichiometry bounds exceeds cutoff ± tolerance

---

# Example File Structure

## File Format
JSON structure with four top-level sections:

### Header Section
- BPX version (string, semantic versioning)
- Title, Description, References (optional strings)
- Model type (literal: "SPM", "SPMe", "DFN", or "Partial")

### Parameterisation Section
- Cell: Basic parameters (area, voltage limits, capacity)
- Electrolyte: Ionic properties (conductivity, diffusivity, as constants or functions)
- Negative electrode: Material properties + contact properties
  - Can include Particle dict if blended
- Positive electrode: Material properties + contact properties
  - Can include Particle dict if blended
- Separator: Contact properties only (thickness, porosity)
- User-defined (optional): Custom parameters

### State Section (optional for SPM, required for others)
- Initial conditions: SOC, temperature, concentration, hysteresis state
- Thermal environment: Ambient temperature, heat transfer coefficient
- Degradation (optional): LLI and LAM values

### Validation Section (optional)
- Named experiments (dict): Each contains time, current, voltage, temperature arrays

## Recurring Patterns

**Parameter naming convention:**
- Quantity [unit] format, e.g., "Electrode area [m2]"
- Pydantic fields use snake_case; aliases provide [unit] format

**Function representation:**
- Math expressions as strings: `"3.3e-14 * exp(-x / 1000)"`
- Variables: `x` (concentration, stoichiometry, or temperature depending on context)
- Allowed functions: exp, tanh, cosh, basic arithmetic

**Interpolation representation:**
- Dict with "x" and "y" keys: `{"x": [0, 0.1, 1], "y": [1.72, 1.2, 0.06]}`
- Linear interpolation implied

**Material naming in blended electrodes:**
- Arbitrary string keys in "Particle" dict, e.g., "Primary", "Secondary"
- State sections reference same keys

## Important Observations

1. **Optional vs required fields:**
   - Most fields default to None (optional)
   - Use Pydantic Field(None, ...) pattern
   - Some fields required: voltage cutoffs, capacity, cell area for most models

2. **Function vs constant:**
   - Same field accepts float/int or Function/InterpolatedTable
   - Type union: FloatFunctionTable = Union[float, int, Function, InterpolatedTable]
   - Examples: diffusivity, conductivity, OCP

3. **OCP variants:**
   - Single field `ocp` (required) for standard operation
   - Optional `ocp_delith` and `ocp_lith` for hysteresis modeling

4. **Blended electrode structure:**
   - Single-material: Electrode directly contains Particle fields
   - Blended: Electrode contains "Particle" dict with material names as keys

5. **Activation energies:**
   - Optional fields for temperature-dependent behavior
   - All use [J.mol-1] unit

6. **Thermal properties:**
   - Lumped properties (density, specific heat, thermal conductivity)
   - Thermal conductivity in Cell section raises error; must use User-defined

7. **Validation data:**
   - Multiple named experiments allowed
   - Each experiment is time series of same length for all quantities
   - Temperature optional in Experiment

8. **State section constraints:**
   - Present for full models (SPMe, DFN)
   - Optional for SPM
   - Not allowed for Partial model
   - Hysteresis states must match electrode materials (scalar or per-material dict)

---

# GUI-Relevant Findings

## Tree Generation

- Hierarchy structure defined in schema.py class definitions
- BPX root → Header, Parameterisation, State, Validation branches
- Parameterisation contains 5 sections: Cell, Electrolyte, Electrodes (2), Separator, User-defined
- Electrodes expand to Particle(s): single material or named blended materials
- State contains 3 subsections: Initial conditions, Thermal environment, Degradation
- User-defined allows arbitrary nested structure (recursive dict structure handled in UserDefined.validate)

## Parameter Pages

- Each Field() has alias, description, examples, json_schema_extra
- Fields marked with json_schema_extra contain material_check tag for context validation
- FloatFunctionTable type requires UI support for 3 representations: scalar, function string, interpolation table
- Optional fields: use Pydantic Field(None, ...) to render as optional inputs

## Validation Feedback

- Validation errors come with clear messages:
  - Type mismatches: field name, expected type, received type
  - Thermal conductivity error: directs to User-defined section
  - Model type mismatches: expected vs received model type
  - Material key mismatches: lists missing/extra keys
  - Voltage tolerance: warnings with computed vs expected values
- Stoichiometry validation warnings issued but don't prevent loading

## Form Generation

- Cell form: ~13 fields, mix of required and optional
- Electrolyte form: ~5 fields, 3-5 required
- Electrode forms (neg/pos): ~15-20 fields depending on single vs blended
- State.InitialConditions: 5 fields, 3 required + 2 material-dependent
- Blended electrode handling: detect "Particle" field presence, render dict of materials

## Material Handling

- Single-material electrodes: Electrode class directly contains Particle fields
- Blended electrodes: Particle is dict[str, Particle], use arbitrary material names
- State sections tagged with material_check: "negative_electrode" or "positive_electrode"
- GUI should enforce scalar values for single-material, dict for blended in State

## Type Support

- Scalars: float, int
- Functions: string with math expression (validate via ExpressionParser)
- Interpolation: x/y lists (validate length match)
- Lists: arrays for Experiment time, current, voltage, temperature
- Dicts: Particle materials, User-defined custom fields

---

# Open Questions

1. **User-defined field structure:** How deeply nested can User-defined fields be? Example shows flat structure; recursive handling exists in validation but depth limits unknown.

2. **Expression parser scope:** Beyond exp, tanh, cosh, are other math functions available? Operators limited to ±*/**, but exact supported set unclear.

3. **Interpolation method:** Linear assumed for InterpolatedTable; spline or other methods supported?

4. **SPM parameter completeness:** Which full model parameters are forbidden in SPM? Documentation references validation but exact list not visible without examining ParameterisationSPM.model_fields.

5. **Voltage tolerance usage:** v_tol parameter default 1 mV; how does this affect other validations beyond stoichiometry check?

6. **Partial model constraints:** What validation rules apply to Partial parameterisations? Field interdependencies unknown.

7. **Function variable scope:** OCP is function of stoichiometry, but conductivity/diffusivity function of concentration—is `x` context-dependent, or are multiple variables needed?

8. **Blended material validation:** Are arbitrary material names allowed, or reserved names expected (e.g., "Primary", "Secondary")?

9. **Experiment data requirements:** Are all arrays required (time, current, voltage), or can temperature be omitted? Length requirements between arrays?

10. **ExtraBaseModel forbid extra:** What happens if BPX file contains unknown top-level keys beyond Header/Parameterisation/State/Validation?

---

*Analysis Date: 2026-06-16*
*Repository: BPX by Faraday Institution*
*Document Version: 1.0*