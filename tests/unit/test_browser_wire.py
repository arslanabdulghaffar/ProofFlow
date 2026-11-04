"""The emitted wire contracts cannot silently drift from validated server types."""

import pytest
from pydantic import ValidationError

from api.app.wire import DeleteRequest, EnqueueRequest, JobEvent
from scripts.generate_browser_types import ROOT, artifacts


def test_generated_contracts_are_current():
    for path, content in artifacts().items():
        assert (ROOT / path).read_text(encoding="utf-8") == content


def test_wire_refuses_unknown_authority_and_noncanonical_identifiers():
    with pytest.raises(ValidationError):
        EnqueueRequest.model_validate({"runtime": "caller-selected"})
    with pytest.raises(ValidationError):
        DeleteRequest.model_validate({"workspace_id": "../outside", "confirm": True})


@pytest.mark.parametrize("sequence", [1, -1, "01", "1e3", "9" * 20])
def test_events_preserve_decimal_sequence_without_js_number_coercion(sequence):
    with pytest.raises(ValidationError):
        JobEvent(sequence=sequence, state="QUEUED", event="queued", occurred_at="fixture")
