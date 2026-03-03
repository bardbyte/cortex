"""Taxonomy YAML schema validation.

Owner: Ayush (creates entries), Saheb (reviews)

The taxonomy YAML schema is the interface contract between:
- Renuka's enrichment UX (upstream: produces business term data)
- Ayush's LookML mapping (transforms: maps terms to fields)
- The AI pipeline (downstream: consumes for retrieval + entity resolution)

This module validates that taxonomy entries conform to the schema.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator


class ColumnMapping(BaseModel):
    """Maps a business term to a physical BigQuery column."""

    table: str
    column: str
    dataset: str = ""


class LookMLTarget(BaseModel):
    """Where this term maps in LookML."""

    model: str
    explore: str
    field: str  # e.g. "acquisitions.cac"


class TaxonomyEntry(BaseModel):
    """A single canonical business term definition.

    This is the core data structure. Every business term at Amex
    should eventually have one of these.
    """

    canonical_name: str
    definition: str
    formula: str = ""
    synonyms: list[str] = []
    domain: list[str] = []
    owner: str = ""
    column_mappings: list[ColumnMapping] = []
    lookml_target: LookMLTarget | None = None
    related_terms: list[str] = []
    status: str = "draft"  # draft | review | approved
    filters: list[str] = []  # Required filters (e.g. partition filters)

    @field_validator("canonical_name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("canonical_name must not be empty")
        return v.strip()

    @field_validator("definition")
    @classmethod
    def definition_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("definition must not be empty")
        return v.strip()

    def to_lookml_description(self) -> str:
        """Generate the enriched LookML description string.

        Format: Definition + "Also known as: [synonyms]" + Usage note
        This is the highest-leverage single field for retrieval accuracy.
        """
        parts = [self.definition]

        if self.synonyms:
            parts.append(f"Also known as: {', '.join(self.synonyms)}.")

        if self.formula:
            parts.append(f"Calculation: {self.formula}")

        if self.filters:
            parts.append(f"Note: Requires filter on {', '.join(self.filters)}.")

        return " ".join(parts)


def load_taxonomy_dir(taxonomy_dir: str | Path) -> list[TaxonomyEntry]:
    """Load all taxonomy YAML files from a directory."""
    path = Path(taxonomy_dir)
    entries = []
    for yaml_file in sorted(path.glob("*.yaml")):
        if yaml_file.name.startswith("_"):
            continue  # Skip templates
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        entries.append(TaxonomyEntry(**data))
    return entries


def validate_taxonomy_dir(taxonomy_dir: str | Path) -> list[str]:
    """Validate all taxonomy files and return list of errors."""
    path = Path(taxonomy_dir)
    errors = []
    for yaml_file in sorted(path.glob("*.yaml")):
        if yaml_file.name.startswith("_"):
            continue
        try:
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
            TaxonomyEntry(**data)
        except Exception as e:
            errors.append(f"{yaml_file.name}: {e}")
    return errors


if __name__ == "__main__":
    import sys

    directory = sys.argv[1] if len(sys.argv) > 1 else "taxonomy/"
    errors = validate_taxonomy_dir(directory)
    if errors:
        print(f"Found {len(errors)} validation errors:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        entries = load_taxonomy_dir(directory)
        print(f"Validated {len(entries)} taxonomy entries successfully.")
