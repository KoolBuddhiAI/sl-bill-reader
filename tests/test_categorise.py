from decimal import Decimal

import pytest
from sqlmodel import select

from bill_reader.categorise import (
    Categoriser,
    ensure_chart,
    load_chart_csv,
    normalise_supplier,
    propose_tax_code,
    record_approval,
    selectable_accounts,
)
from bill_reader.llm import LLMError
from bill_reader.llm.base import FakeLLMClient
from bill_reader.llm.profiles import ModelProfile
from bill_reader.models import Account, SupplierHistory
from bill_reader.schemas import BillExtraction, FieldValue


def profile(**kw) -> ModelProfile:
    base = {"name": "p", "provider": "openai_compatible", "model": "m", "api_key_env": "TEST_KEY", "base_url": "https://x.test/v1"}
    base.update(kw)
    return ModelProfile(**base)


@pytest.fixture
def charted(session, settings):
    assert ensure_chart(session, settings) > 0
    return session


def test_ensure_chart_loads_sample_once(session, settings):
    n = ensure_chart(session, settings)
    assert n > 30
    assert ensure_chart(session, settings) == 0
    assert session.get(Account, "6-0000").is_detail is False
    assert session.get(Account, "6-2420").name == "Fuel"


def test_load_chart_csv_myob_variant_replaces_rows(charted):
    data = (
        b'"Account Number","Account Name","Header","Account Type"\n'
        b'"6-0000","Expenses","Header","Expense"\n'
        b'"6-1000","Rent","Detail","Expense"\n'
        b'"2-1000","Creditors","D","Liability"\n'
    )
    assert load_chart_csv(charted, data) == 3
    assert len(charted.exec(select(Account)).all()) == 3
    assert [a.code for a in selectable_accounts(charted)] == ["6-1000"]


def test_selectable_accounts_types(charted):
    codes = {a.code for a in selectable_accounts(charted)}
    assert {"6-2420", "5-1000", "9-1000", "1-2130", "6-9999"} <= codes
    assert not codes & {"6-0000", "2-1110", "4-1000", "3-1000"}


def test_normalise_supplier():
    assert normalise_supplier("Vat Company (Pvt) Ltd") == normalise_supplier("VAT COMPANY PVT LTD.") == "vat company"
    assert normalise_supplier("Perera & Co.") == "perera"
    assert normalise_supplier("  Lanka   Traders Private Limited ") == "lanka traders"


def test_propose_tax_code():
    assert propose_tax_code("2,305.00") == "VAT"
    assert propose_tax_code("0.00") == "N-T"
    assert propose_tax_code(None) == "N-T"
    assert propose_tax_code(Decimal(1)) == "VAT"
    assert propose_tax_code(BillExtraction(vat_amount=FieldValue(value="180"))) == "VAT"
    assert propose_tax_code(BillExtraction()) == "N-T"


def test_history_hit_skips_llm(charted):
    record_approval(charted, "Vat Company (Pvt) Ltd", "6-3310", "VAT")
    record_approval(charted, "VAT COMPANY PVT LTD.", "6-3310", "VAT")
    assert charted.get(SupplierHistory, "vat company").times_used == 2
    client = FakeLLMClient(profile(), [])
    s = Categoriser(charted, client).suggest("Vat Company Ltd", ["Paper"])
    assert s.account_code == "6-3310" and s.confidence == 0.95 and "2 times" in s.reason
    assert client.calls == []


def test_llm_path(charted):
    client = FakeLLMClient(profile(), [{"account_code": "6-2420", "confidence": 0.9, "reason": "Fuel purchase"}])
    s = Categoriser(charted, client).suggest("Lanka IOC", ["Petrol 92 octane"], doc_hint="receipt")
    assert s.account_code == "6-2420" and s.confidence == 0.9
    text = client.calls[0]["user_text"]
    assert "Lanka IOC" in text and "Petrol 92 octane" in text and "6-2420 | Fuel | Expense" in text
    assert "2-1110" not in text


def test_invalid_code_retry_then_valid(charted):
    client = FakeLLMClient(
        profile(),
        [
            {"account_code": "6-1234", "confidence": 0.8, "reason": "x"},
            {"account_code": "6-2210", "confidence": 0.7, "reason": "Electricity bill"},
        ],
    )
    s = Categoriser(charted, client).suggest("CEB", ["Electricity"])
    assert s.account_code == "6-2210"
    assert "6-1234" in client.calls[1]["user_text"]


def test_invalid_code_twice_falls_back(charted):
    bad = {"account_code": "2-1110", "confidence": 0.8, "reason": "x"}
    s = Categoriser(charted, FakeLLMClient(profile(), [bad, dict(bad)])).suggest("X", ["y"])
    assert s.account_code == "6-9999" and s.confidence == 0
    assert s.reason == "Model suggested an unknown account"


def test_llm_error_and_no_client_fall_back(charted):
    s = Categoriser(charted, FakeLLMClient(profile(), [LLMError("quota exceeded")])).suggest("X", [])
    assert s.account_code == "6-9999" and s.confidence == 0 and "quota exceeded" in s.reason
    s = Categoriser(charted, None).suggest("X", [])
    assert s.account_code == "6-9999" and s.confidence == 0
