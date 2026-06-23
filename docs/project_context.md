# Explore_BPX Project Context Transfer

## Project Overview

I am developing a **BPX Builder / BPX Explorer** application during my FUSE internship.

The purpose is **not** to recreate BPX validation logic. The purpose is to provide a user-friendly interface for exploring, editing, validating and eventually visualising BPX files.

The BPX repository already exists and contains:

- Schema definitions
- Validation logic
- Parsing logic
- Function handling
- Interpolated table handling

The application should use BPX as a dependency rather than duplicating its functionality.

# Explore BPX

## Goal

Create a visual editor and explorer for BPX battery parameter files.

## Users

- Battery researchers
- Engineers
- Parameterisation teams

## Problems

- BPX JSON is difficult to read
- Large parameter sets are hard to navigate
- Validation workflows are fragmented

## MVP

- Upload BPX
- View parameter hierarchy
- Edit values
- Export BPX

## Future

- Graph visualisation
- Validation integration
- Parameter comparison

## Important Architectural Principle

The BPX repository is treated as an external dependency.

Repository structure:

```
BPX-main
Explore_BPX
```

BPX-main should remain untouched and act as the upstream source.

The Builder imports from BPX directly:

```python
from bpx.parsers import parse_bpx_obj
```

rather than copying validation code into the Builder project.

The goal is:

BPX File -> BPX Package -> Validated BPX Object -> Builder UI

NOT:

BPX File -> Custom Validator -> Custom Schema

Explore BPX is not a BPX implementation. The application consumes the official BPX repository and delegates parsing, validation, and schema enforcement to the official BPX package. The BPX repository remains replaceable without modifying application logic. 

## Frontend Strategy

Development will start in Streamlit.

Long-term goal is likely PySide6 / Qt.

Therefore:

### Critical constraint

All business logic must remain frontend-agnostic.

No Streamlit-specific logic should be placed inside:

- services
- core
- state
- BPX processing
- validation
- tree generation
- export logic

The UI should only:

- Display information
- Collect user input

This is to allow future migration:

Streamlit -> PySide6

without rewriting application logic.

## Current Design Direction

The application is evolving away from a simple validator.

The real problem being solved is:

> How do humans interact with BPX files?

not:

> How do we validate BPX?

## Navigation Model

Current preferred workflow:

Tree -> Section -> Parameter List -> Parameter Inspector

Example:

```
Parameterisation
    Cell
    Electrolyte
    Positive Electrode
    Negative Electrode
    Separator
```

Click:

```
Cell
```

Then:

```
Ambient temperature
Reference temperature
Upper voltage cut-off
...
```

Then:

```
Ambient temperature
```

opens the inspector.

This approach is preferred over putting every parameter directly into the tree.

## Current UI Layout

Current design concept:

```
┌────────┬────────────────┬─────────────────┐
│ Tree   │ Parameter List │ Inspector       │
└────────┴────────────────┴─────────────────┘
```

Three-column layout is currently preferred.

Reason:

Users will frequently move between parameters:

Radius -> Porosity -> Diffusivity -> OCP

Keeping the parameter list visible improves navigation.

## Left Sidebar

Current ideas:

- Tree
- JSON
- Validation

Tree = primary navigation.

JSON = raw file view.

Validation = project-wide validation view.

## JSON View

Current recommendation:

Version 1 should be read-only.

Reason:

Editable JSON creates a second editing system.

The Builder should initially have one editing workflow.

## Validation Design

Still under discussion, but current direction:

### Inline Validation

Errors appear directly in the inspector.

Example:

```
Value

[ ]

❌ Required field missing
```

or

```
⚠ Outside recommended range
```

### Validation Page

Separate validation screen:

```
Validation

3 Errors
2 Warnings
```

Clicking an error should jump directly to the relevant parameter.

Example:

```
❌ Ambient temperature missing
```

opens:

```
Cell -> Ambient temperature
```

### Validate Button

Currently considered unnecessary.

Reason:

Validation likely uses BPX parsing directly:

```python
parse_bpx_obj(...)
```

and can potentially run continuously.

Need to prototype performance before deciding.

## Parameter Types

UI should be designed around parameter types rather than battery sections.

Do NOT design:

- Cell card
- Electrolyte card
- Separator card

Design:

- Scalar editor
- Function editor
- Table editor
- Enum editor

These can be reused everywhere.

## Expected Parameter Categories

### Scalar

Examples:

- Ambient temperature
- Particle radius
- Porosity

UI:

- Value
- Unit
- Description
- Validation

No graph needed.

### Integer

Same concept as scalar.

### Enum / Choice

Dropdown or selection list.

### Function

Examples:

- OCP
- Exchange current density

Potential UI:

- Expression
- Validation
- Display

Can benefit from graphing.

### Interpolated Table

Examples:

- x values
- y values

Potential UI:

- Table editor
- Display

Can benefit from graphing.

### Object / Section

Examples:

- Cell
- Electrolyte
- State

Not directly editable.

Used for navigation.

## Parameter List Design

Current thinking:

Avoid showing values in the parameter list.

This works poorly for:

- Function
- InterpolatedTable

Instead:

```
🔢 Ambient temperature
🔢 Porosity
📈 OCP
📊 Diffusivity
```

Icons indicate parameter type.

## Information Section

Initial idea:

Separate information page.

Current understanding:

Probably not a separate page.

Instead:

- Description
- Physical Correspondence
- Model Sensitivity
- Measurement Methods

displayed as structured information.

BPX itself provides metadata such as:

- Description
- Type
- Examples
- Units

## Display / Visualisation

Current decision:

Do NOT auto-render graphs.

Reason:

- Many parameters do not need graphs.
- Large datasets may be slow.
- Users often want rapid editing.

Preferred behaviour:

Display button. User explicitly requests visualisation.

### Open Question: Display Location

Three options considered:

A. Graph appears inside inspector

B. Graph replaces inspector

C. Popup window

Current leading candidate:

A. Graph appears inside inspector after user requests it.

Potential design:

```
Display

[ Generate Preview ]
```

Then:

```
Display

[ Graph ]
```

## Information vs Display

Current concern:

Avoid huge vertical scrolling.

Potential solution:

Collapsible sections.

Example:

```
▼ Editor

▶ Information

▶ Display
```

Only one section open at a time.

This remains under discussion.

## Development Philosophy

Do NOT start coding yet.

The project is still in architecture and workflow design.

Current recommendation:

Design before implementation.

Use:

- Paper sketches
- PowerPoint

to define workflows before code is written.

Implementation follows the agreed designs.

Designs are decided up front, not invented during implementation.

## Current Next Design Task

Create three complete inspector designs:

### Screen 1

Scalar parameter

Example: Ambient temperature [K]

### Screen 2

Function parameter

Example: OCP [V]

### Screen 3

Interpolated table parameter

Example: Diffusivity

For each screen define:

- Information shown
- Editable fields
- Buttons
- Display behaviour
- Information behaviour
- Validation behaviour

These screens will likely define the entire editor architecture.

## Key Unresolved Questions

- Should validation be continuous or manual?
- Exactly where should display/graph content appear?
- How should information and display sections coexist without excessive scrolling?
- What does a Function inspector look like?
- What does an Interpolated Table inspector look like?
- How should parameter type icons be displayed?

The next stage of the project is answering these questions before building the first prototype.