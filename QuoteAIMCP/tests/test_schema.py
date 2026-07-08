"""Schema + ERP dry-run tests. Run: pytest -q"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from quoteai_mcp.schema import Quote, quote_json_schema


VALID = {
    "customer": {"name": "Acme Corp", "customer_number": "C1042"},
    "line_items": [
        {"part_number": "PN-100", "description": "Widget", "quantity": 10},
        {"part_number": "PN-200", "quantity": 5, "unit_price": 3.25},
    ],
    "reference": "RFQ-8891",
}


def test_valid_quote_parses():
    q = Quote.model_validate(VALID)
    assert q.customer.name == "Acme Corp"
    assert len(q.line_items) == 2
    assert q.line_items[0].unit_of_measure == "EA"


def test_requires_at_least_one_line_item():
    with pytest.raises(Exception):
        Quote.model_validate({"customer": {"name": "X"}, "line_items": []})


def test_quantity_must_be_positive():
    bad = {
        "customer": {"name": "X"},
        "line_items": [{"part_number": "P", "quantity": 0}],
    }
    with pytest.raises(Exception):
        Quote.model_validate(bad)


def test_part_number_stripped_and_required():
    with pytest.raises(Exception):
        Quote.model_validate(
            {"customer": {"name": "X"}, "line_items": [{"part_number": "  ", "quantity": 1}]}
        )


def test_schema_is_generated():
    schema = quote_json_schema()
    assert "properties" in schema
    assert "line_items" in schema["properties"]


def test_dry_run_submit():
    from quoteai_mcp.config import ErpConfig
    from quoteai_mcp.erp_client import ErpClient

    cfg = ErpConfig(
        mode="dry_run",
        api_url="",
        api_token="",
        web_url="",
        json_selector="#quote-json",
        submit_selector="#submit",
        headless=True,
    )
    result = ErpClient(cfg).submit(Quote.model_validate(VALID))
    assert result.ok
    assert result.mode == "dry_run"
    assert result.payload["customer"]["name"] == "Acme Corp"
    assert result.payload["quote_date"]  # defaulted to today
