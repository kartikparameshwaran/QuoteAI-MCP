"""Canonical quote data model.

This is the single source of truth for the JSON object your ERP expects.
The MCP tools, the LLM extractor, and the ERP submitter all agree on this
shape. Adjust the fields below to match exactly what your Visual ERP quote
builder consumes, and everything downstream stays in sync.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Customer(BaseModel):
    """Customer / bill-to information for the quote."""

    name: str = Field(..., description="Customer company name")
    customer_number: Optional[str] = Field(
        None, description="ERP customer ID / account number, if known"
    )
    contact_name: Optional[str] = Field(None, description="Buyer / requester name")
    email: Optional[str] = Field(None, description="Contact email address")
    phone: Optional[str] = Field(None, description="Contact phone number")
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None


class LineItem(BaseModel):
    """A single part / line on the quote."""

    part_number: str = Field(..., description="Manufacturer or internal part number")
    description: Optional[str] = Field(None, description="Part description")
    quantity: float = Field(..., gt=0, description="Requested quantity")
    unit_of_measure: Optional[str] = Field(
        "EA", description="Unit of measure (EA, FT, LB, ...)"
    )
    unit_price: Optional[float] = Field(
        None, ge=0, description="Quoted unit price, if provided in the source"
    )
    required_date: Optional[date] = Field(
        None, description="Requested delivery / need-by date"
    )
    notes: Optional[str] = None

    @field_validator("part_number")
    @classmethod
    def _strip_part_number(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("part_number must not be empty")
        return v


class Quote(BaseModel):
    """The complete quote object handed to the ERP.

    This is the JSON the agent used to build by hand and paste into the
    website. `Quote.model_json_schema()` is exposed to the LLM as the target
    schema, and `Quote.model_validate(...)` guards the ERP submission.
    """

    customer: Customer
    line_items: list[LineItem] = Field(..., min_length=1)
    quote_date: Optional[date] = Field(
        None, description="Date of the quote request (defaults to today at submit time)"
    )
    requested_by: Optional[str] = Field(
        None, description="Person or mailbox the request came from"
    )
    reference: Optional[str] = Field(
        None, description="Customer PO / RFQ number or email subject reference"
    )
    currency: str = Field("USD", description="ISO currency code")
    notes: Optional[str] = Field(None, description="Free-text notes for the quote")

    # Provenance — helps you audit which email produced which quote.
    source_email_id: Optional[str] = Field(
        None, description="Graph message id the quote was extracted from"
    )
    source_attachment: Optional[str] = Field(
        None, description="Filename of the attachment the data came from"
    )


def quote_json_schema() -> dict:
    """Return the JSON Schema the LLM should target when extracting."""
    return Quote.model_json_schema()
