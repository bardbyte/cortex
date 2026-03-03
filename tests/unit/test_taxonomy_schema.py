"""Tests for taxonomy schema validation.

This file demonstrates the testing pattern for Cortex.
Add your tests following this structure.
"""

import pytest
from src.taxonomy.schema import TaxonomyEntry, LookMLTarget


def test_valid_taxonomy_entry():
    entry = TaxonomyEntry(
        canonical_name="Total Spend",
        definition="Sum of all transaction amounts for a cardmember.",
        synonyms=["total_spend", "spend"],
        lookml_target=LookMLTarget(
            model="finance", explore="transactions", field="transactions.total_amount"
        ),
        domain="finance",
    )
    assert entry.canonical_name == "Total Spend"
    assert len(entry.synonyms) == 2


def test_taxonomy_entry_requires_name():
    with pytest.raises(Exception):
        TaxonomyEntry(
            canonical_name="",
            definition="Some definition",
            synonyms=[],
            lookml_target=LookMLTarget(
                model="m", explore="e", field="f"
            ),
            domain="finance",
        )


def test_lookml_description_generation():
    entry = TaxonomyEntry(
        canonical_name="Customer Acquisition Cost",
        definition="Total cost to acquire a new primary cardmember.",
        synonyms=["CAC", "CPNC"],
        lookml_target=LookMLTarget(
            model="finance", explore="acquisitions", field="acquisitions.cac"
        ),
        domain="finance",
    )
    desc = entry.to_lookml_description()
    assert "Customer Acquisition Cost" in desc
    assert "CAC" in desc
