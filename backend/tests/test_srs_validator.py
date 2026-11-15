from schemas.srs import Statement, StatementLabel
from services.srs_validator import validate_statement, validate_statements

CHUNKS = {
    1: "Laser module over temperature: priority High; limit 45 °C; required action interruption.",
    2: "Peak power is up to 8 W for each of the 808 nm and 1064 nm diodes.",
}


def _s(text, label, **kw):
    return Statement(text=text, label=label, **kw)


def test_supported_input_statement_is_kept():
    s = _s("The software shall stop emission above 45 °C.", StatementLabel.INPUT, chunk_ids=[1])
    out = validate_statement(s, CHUNKS)
    assert out.label is StatementLabel.INPUT and not out.needs_review


def test_unit_conversion_counts_as_supported():
    s = _s("Output power is limited to 8000 mW.", StatementLabel.INPUT, chunk_ids=[2])
    assert validate_statement(s, CHUNKS).label is StatementLabel.INPUT


def test_number_not_in_cited_chunk_is_downgraded():
    s = _s("The software shall stop emission above 35 °C.", StatementLabel.INPUT, chunk_ids=[1])
    out = validate_statement(s, CHUNKS)
    assert out.label is StatementLabel.PROPOSAL and out.needs_review
    assert "35" in out.review_reason


def test_input_without_or_with_unknown_chunk_is_downgraded():
    assert validate_statement(_s("Text.", StatementLabel.INPUT), CHUNKS).needs_review
    out = validate_statement(_s("Text.", StatementLabel.INPUT, chunk_ids=[99]), CHUNKS)
    assert out.needs_review and "99" in out.review_reason


def test_decision_statement():
    decisions = {"low_battery_threshold": "15 percent"}
    ok = _s("Low battery warning appears at 15%.", StatementLabel.DECISION,
            decision_key="low_battery_threshold")
    assert validate_statement(ok, CHUNKS, decisions).label is StatementLabel.DECISION
    wrong = ok.model_copy(update={"text": "Low battery warning appears at 20%."})
    assert validate_statement(wrong, CHUNKS, decisions).label is StatementLabel.PROPOSAL
    missing = ok.model_copy(update={"decision_key": "nope"})
    assert validate_statement(missing, CHUNKS, decisions).needs_review


def test_general_rule_keeps_label_but_flags_numbers():
    plain = _s("The software shall display a title on every page.", StatementLabel.GENERAL_RULE)
    assert not validate_statement(plain, CHUNKS).needs_review
    numeric = _s("The software shall boot in 10 seconds.", StatementLabel.GENERAL_RULE)
    out = validate_statement(numeric, CHUNKS)
    assert out.label is StatementLabel.GENERAL_RULE and out.needs_review


def test_proposal_is_always_flagged_and_empty_text_too():
    p = _s("Add a second interlock.", StatementLabel.PROPOSAL)
    assert validate_statement(p, CHUNKS).needs_review
    assert validate_statement(_s("  ", StatementLabel.INPUT, chunk_ids=[1]), CHUNKS).needs_review


def test_validate_statements_keeps_order_and_count():
    items = [
        _s("A 45 °C.", StatementLabel.INPUT, chunk_ids=[1]),
        _s("B 7 W.", StatementLabel.INPUT, chunk_ids=[2]),
    ]
    out = validate_statements(items, CHUNKS)
    assert [o.text for o in out] == ["A 45 °C.", "B 7 W."]
    assert [o.needs_review for o in out] == [False, True]


def test_invented_names_are_downgraded():
    chunks = {5: "Wavelength selection: 808 nm or 1064 nm. Duty Cycle is adjustable."}
    for text in (
        "The software shall show a Wavelengths Tab Buttons control.",
        "The STANDBY button puts the device in standby.",
        "The wavelength selector is a Class B item.",
        "The control is a TabButtons widget.",
    ):
        out = validate_statement(_s(text, StatementLabel.INPUT, chunk_ids=[5]), chunks)
        assert out.label is StatementLabel.PROPOSAL and "names not found" in out.review_reason, text


def test_names_present_in_the_chunk_are_accepted():
    chunks = {5: "Wi-Fi status icon. Duty Cycle is adjustable. Splash Page shows the logo."}
    s = _s("The Duty Cycle control and the WiFi icon appear after the Splash Page.",
           StatementLabel.INPUT, chunk_ids=[5])
    assert validate_statement(s, chunks).label is StatementLabel.INPUT
