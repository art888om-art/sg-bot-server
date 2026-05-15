"""Tests for domain validation logic."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain import ClientCreate


def test_phone_normalization_keeps_plus() -> None:
    c = ClientCreate(name="X", phone="+380501234567")
    assert c.phone == "+380501234567"


def test_phone_normalization_adds_plus_to_380() -> None:
    c = ClientCreate(name="X", phone="380501234567")
    assert c.phone == "+380501234567"


def test_phone_normalization_local_format() -> None:
    c = ClientCreate(name="X", phone="0501234567")
    assert c.phone == "+380501234567"


def test_phone_rejects_garbage() -> None:
    with pytest.raises(ValidationError):
        ClientCreate(name="X", phone="!!!")


def test_vin_must_be_17_chars() -> None:
    with pytest.raises(ValidationError):
        ClientCreate(name="X", phone="+380501234567", vin="ABC123")


def test_vin_accepts_valid() -> None:
    c = ClientCreate(name="X", phone="+380501234567", vin="1HGBH41JXMN109186")
    assert c.vin == "1HGBH41JXMN109186"
