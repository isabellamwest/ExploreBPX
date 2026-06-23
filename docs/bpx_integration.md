# BPX Integration

## Source

Official BPX repository.

Repository URL:
https://github.com/FaradayInstitution/BPX

---

## Purpose

Explore BPX does not implement its own schema.

Explore BPX consumes the BPX package for:

- Parsing
- Validation
- Schema definitions

---

## Files Used

### schema.py

Source of parameter definitions.

Used for:

- Tree generation
- Form generation

### parsers.py

Used for:

- Loading files

### validators.py

Used for:

- Validation workflows

---

## Update Strategy

BPX repository should be replaceable.

Application code must not depend on internal implementation details.

Interaction occurs only through documented public interfaces.