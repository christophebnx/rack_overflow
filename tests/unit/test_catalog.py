"""Catalog rules (D-030 to D-032, D-054): variables, exercises, fields, aliases."""

from __future__ import annotations

import pytest

from rack_overflow.domain import catalog
from rack_overflow.domain.catalog import (
    CatalogError,
    EnumValue,
    FieldKind,
    FieldParams,
    FieldSource,
    ValueInput,
    VariableDraft,
)
from rack_overflow.domain.errors import DomainError


def codes(error: pytest.ExceptionInfo[CatalogError]) -> list[tuple[str, str]]:
    return [(problem.field, problem.code) for problem in error.value.problems]


def seat(labels: list[str]) -> VariableDraft:
    return catalog.variable_draft(
        label="Siège", var_type="enum", scope="setting", values=[ValueInput(label) for label in labels]
    )


# --- variables


def test_enum_variable_gets_keys_from_labels() -> None:
    draft = seat([str(n) for n in range(1, 11)])
    assert draft.type == "enum" and draft.scope == "setting"
    assert [value.key for value in draft.enum_values or ()] == [str(n) for n in range(1, 11)]
    assert draft.unit is None and draft.decimal_scale is None


def test_variable_reads_only_the_fields_of_its_type() -> None:
    draft = catalog.variable_draft(
        label=" Résistance ", var_type="int", scope="set", unit="niveau", scale="9", values=[ValueInput("x")]
    )
    assert draft == VariableDraft("Résistance", "int", "set", "niveau", None, None)
    weight = catalog.variable_draft(label="Lest", var_type="weight", scope="set", unit="kg")
    assert weight.unit is None


def test_decimal_variable_needs_a_scale_of_one_to_three() -> None:
    draft = catalog.variable_draft(label="Ratio", var_type="decimal", scope="set", scale="2", unit="")
    assert draft.decimal_scale == 2 and draft.unit is None
    with pytest.raises(CatalogError) as caught:
        catalog.variable_draft(label="Ratio", var_type="decimal", scope="set", scale="4")
    assert codes(caught) == [("decimal_scale", "invalid_choice")]
    with pytest.raises(CatalogError) as caught:
        catalog.variable_draft(label="Ratio", var_type="decimal", scope="set")
    assert codes(caught) == [("decimal_scale", "required")]


def test_every_problem_of_a_variable_form_at_once() -> None:
    with pytest.raises(CatalogError) as caught:
        catalog.variable_draft(label="x" * 41, var_type="nope", scope=None)
    assert codes(caught) == [("label", "too_long"), ("type", "invalid_choice"), ("scope", "required")]
    assert caught.value.problems[0].params == {"max": 40}
    assert isinstance(caught.value, DomainError)


def test_unit_too_long_and_label_required() -> None:
    with pytest.raises(CatalogError) as caught:
        catalog.variable_draft(label="  ", var_type="int", scope="set", unit="x" * 13)
    assert codes(caught) == [("label", "required"), ("unit", "too_long")]


@pytest.mark.parametrize(
    ("labels", "problem"),
    [
        ([], ("values", "values_required")),
        (["", "  "], ("values", "values_required")),
        (["Bas", "bas"], ("values", "duplicate_value")),
        (["x" * 41], ("values", "too_long")),
        ([str(n) for n in range(51)], ("values", "too_many_values")),
    ],
)
def test_enum_value_refusals(labels: list[str], problem: tuple[str, str]) -> None:
    with pytest.raises(CatalogError) as caught:
        seat(labels)
    assert problem in codes(caught)


def test_enum_keys_suffix_on_collision_and_empty_slug() -> None:
    values = catalog.enum_values([ValueInput("Bas"), ValueInput("bas!"), ValueInput("—"), ValueInput("…")])
    assert [value.key for value in values] == ["bas", "bas_2", "e", "e_2"]


def test_enum_edit_keeps_keys_relabels_removes_and_appends() -> None:
    existing = (EnumValue("bas", "Bas"), EnumValue("haut", "Haut"), EnumValue("milieu", "Milieu"))
    draft = catalog.variable_draft(
        label="Position",
        var_type="enum",
        scope="setting",
        values=[
            ValueInput("Très bas", key="bas"),
            ValueInput("Haut", key="haut", remove=True),
            ValueInput("Milieu", key="milieu"),
            ValueInput("Haut"),
        ],
        existing=existing,
    )
    # the removed key is never reused: the new « Haut » gets a suffix
    assert draft.enum_values == (
        EnumValue("bas", "Très bas"),
        EnumValue("milieu", "Milieu"),
        EnumValue("haut_2", "Haut"),
    )


def test_enum_edit_refuses_an_unknown_key() -> None:
    with pytest.raises(CatalogError) as caught:
        catalog.variable_draft(
            label="P", var_type="enum", scope="setting", values=[ValueInput("A", key="zz")], existing=()
        )
    assert ("values", "invalid_choice") in codes(caught)


def test_variable_code_is_a_slug_with_suffixes() -> None:
    assert catalog.variable_code("Hauteur du siège", []) == "hauteur_du_siege"
    assert catalog.variable_code("Siège", ["siege"]) == "siege_2"
    assert catalog.variable_code("Siège", ["siege", "siege_2"]) == "siege_3"
    assert catalog.variable_code("???", []) == "v"
    assert catalog.variable_code("!!", ["v"]) == "v_2"


def test_change_is_free_without_values() -> None:
    current = seat(["1", "2"])
    other = catalog.variable_draft(label="Siège", var_type="int", scope="set")
    assert catalog.variable_change(current, other, has_values=False) == other


def test_type_scope_and_scale_frozen_once_values_exist() -> None:
    current = catalog.variable_draft(label="R", var_type="decimal", scope="set", scale="1")
    changed = catalog.variable_draft(label="R2", var_type="int", scope="setting")
    with pytest.raises(CatalogError) as caught:
        catalog.variable_change(current, changed, has_values=True)
    assert codes(caught) == [
        ("type", "frozen_after_use"),
        ("scope", "frozen_after_use"),
        ("decimal_scale", "frozen_after_use"),
    ]
    relabelled = catalog.variable_draft(label="R2", var_type="decimal", scope="set", scale="1", unit="cm")
    assert catalog.variable_change(current, relabelled, has_values=True) == relabelled


def test_a_used_enum_key_cannot_be_removed() -> None:
    current = seat(["1", "2"])
    without_one = VariableDraft("Siège", "enum", "setting", enum_values=(EnumValue("2", "2"),))
    with pytest.raises(CatalogError) as caught:
        catalog.variable_change(current, without_one, has_values=True, used_enum_keys=["1"])
    assert codes(caught) == [("values", "enum_value_in_use")]
    assert catalog.variable_change(current, without_one, has_values=True, used_enum_keys=["2"]) == without_one


@pytest.mark.parametrize(
    ("var_type", "column"),
    [
        ("int", "int"),
        ("decimal", "int"),
        ("duration", "int"),
        ("distance", "int"),
        ("weight", "int"),
        ("bool", "int"),
        ("enum", "text"),
        ("text", "text"),
    ],
)
def test_value_column(var_type: str, column: str) -> None:
    assert catalog.value_column(var_type) == column


# --- exercises


def test_exercise_draft() -> None:
    draft = catalog.exercise_draft(
        name=" Kettlebell swing ",
        category="kettlebell",
        movement_pattern=" ",
        equipment="Kettlebell",
        location="home",
    )
    assert draft == catalog.ExerciseDraft("Kettlebell swing", "kettlebell", None, "Kettlebell", "home")


def test_exercise_draft_problems() -> None:
    with pytest.raises(CatalogError) as caught:
        catalog.exercise_draft(
            name="x" * 81, category=None, movement_pattern="p" * 41, equipment="e" * 41, location="moon"
        )
    assert codes(caught) == [
        ("name", "too_long"),
        ("category", "required"),
        ("movement_pattern", "too_long"),
        ("equipment", "too_long"),
        ("location", "invalid_choice"),
    ]


def test_name_taken_ignores_case_and_accents() -> None:
    assert catalog.name_taken("developpe COUCHE (barre)", ["Développé couché (barre)"])
    assert not catalog.name_taken("Développé couché", ["Développé couché (barre)"])
    with pytest.raises(CatalogError) as caught:
        catalog.check_name("PLANCHE", ["Planche"])
    assert codes(caught) == [("name", "name_taken")]
    catalog.check_name("Planche latérale", ["Planche"])


def test_known_spelling() -> None:
    assert catalog.known_spelling("tirage horizontal", ["Squat", "Tirage horizontal"]) == "Tirage horizontal"
    assert catalog.known_spelling("Gainage", ["Squat"]) == "Gainage"
    assert catalog.known_spelling(None, ["Squat"]) is None


def test_with_known_spellings_rewrites_pattern_and_equipment_only() -> None:
    draft = catalog.ExerciseDraft("Rowing", "strength", "tirage HORIZONTAL", "barre", "gym")
    result = catalog.with_known_spellings(draft, ["Tirage horizontal"], ["Barre", "Haltères"])
    assert result == catalog.ExerciseDraft("Rowing", "strength", "Tirage horizontal", "Barre", "gym")
    assert catalog.with_known_spellings(draft, [], []) == draft


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        ("strength", [("reps", True, 1), ("weight", True, 2500)]),
        ("kettlebell", [("reps", True, 1), ("weight", True, 2500)]),
        ("bodyweight", [("reps", True, 1)]),
        ("cardio", [("duration", True, 30), ("distance", False, 100)]),
        ("intervals", [("duration", True, 30)]),
    ],
)
def test_default_fields(category: str, expected: list[tuple[str, bool, int]]) -> None:
    fields = catalog.default_fields(category)
    assert [(f.quantity, f.required, f.increment) for f in fields] == expected


# --- fields

WEIGHT = catalog.core_kind("weight")


def test_core_kind() -> None:
    assert catalog.core_kind("reps") == FieldKind("int")
    with pytest.raises(CatalogError):
        catalog.core_kind("speed")


def test_variable_kind() -> None:
    assert catalog.variable_kind(seat(["1", "2"])) == FieldKind("enum", None, ("1", "2"))
    assert not catalog.variable_kind(seat(["1"])).numeric


def test_field_params_parse_display_units() -> None:
    assert catalog.field_params(WEIGHT, required=True, increment="2,5", default="20") == FieldParams(
        True, 2500, None, 20000, None
    )
    params = catalog.field_params(WEIGHT, required=False, discrete_values="24; 16  20", default="20")
    assert params == FieldParams(False, None, (16000, 20000, 24000), 20000, None)


def test_distance_values_keep_their_unit_token() -> None:
    params = catalog.field_params(
        catalog.core_kind("distance"), required=False, discrete_values="400 m 1 km 1,5"
    )
    assert params.discrete_values == (400, 1000, 1500)


def test_increment_and_values_are_exclusive() -> None:
    with pytest.raises(CatalogError) as caught:
        catalog.field_params(WEIGHT, required=True, increment="2", discrete_values="16 20")
    assert codes(caught) == [("increment", "increment_with_discrete")]


@pytest.mark.parametrize(
    ("kwargs", "problem"),
    [
        ({"increment": "0"}, ("increment", "must_be_positive")),
        ({"increment": "abc"}, ("increment", "not_a_number")),
        ({"increment": "-1"}, ("increment", "negative")),
        ({"discrete_values": "16 x"}, ("discrete_values", "not_a_number")),
        ({"discrete_values": "16 16"}, ("discrete_values", "duplicate_value")),
        ({"discrete_values": "0 16"}, ("discrete_values", "must_be_positive")),
        ({"discrete_values": " ".join(str(n) for n in range(1, 32))}, ("discrete_values", "too_many_values")),
        ({"discrete_values": "16 20", "default": "18"}, ("default", "default_not_in_values")),
        ({"default": "1,23456"}, ("default", "too_many_decimals")),
    ],
)
def test_field_params_refusals(kwargs: dict[str, str], problem: tuple[str, str]) -> None:
    with pytest.raises(CatalogError) as caught:
        catalog.field_params(WEIGHT, required=True, **kwargs)
    assert problem in codes(caught)


def test_duplicate_value_names_the_value_in_display_units() -> None:
    with pytest.raises(CatalogError) as caught:
        catalog.field_params(WEIGHT, required=True, discrete_values="16 16,0")
    assert caught.value.problems[0].params == {"value": "16"}


def test_enum_field_default_must_be_a_key_and_has_no_step() -> None:
    kind = catalog.variable_kind(seat(["1", "2"]))
    assert catalog.field_params(kind, required=True, default="2") == FieldParams(True, None, None, None, "2")
    with pytest.raises(CatalogError) as caught:
        catalog.field_params(kind, required=True, default="9", increment="1", discrete_values="1 2")
    assert codes(caught) == [("increment", "invalid_choice"), ("discrete_values", "invalid_choice")]
    with pytest.raises(CatalogError) as caught:
        catalog.field_params(kind, required=True, default="9")
    assert codes(caught) == [("default", "invalid_choice")]


def test_bool_and_text_defaults() -> None:
    assert catalog.field_params(FieldKind("bool"), required=False, default="1").default_int == 1
    assert catalog.field_params(FieldKind("bool"), required=False, default="0").default_int == 0
    with pytest.raises(CatalogError):
        catalog.field_params(FieldKind("bool"), required=False, default="oui")
    assert catalog.field_params(FieldKind("text"), required=False, default=" bleu ").default_text == "bleu"
    with pytest.raises(CatalogError) as caught:
        catalog.field_params(FieldKind("text"), required=False, default="x" * 41)
    assert codes(caught) == [("default", "too_long")]


def test_decimal_variable_field_uses_its_scale() -> None:
    kind = FieldKind("decimal", 2)
    assert catalog.field_params(kind, required=False, increment="0,25").increment == 25


@pytest.mark.parametrize(
    ("kind", "params"),
    [
        (WEIGHT, FieldParams(discrete_values=())),
        (WEIGHT, FieldParams(default_int=1, default_text="x")),
        (WEIGHT, FieldParams(default_text="x")),
        (FieldKind("bool"), FieldParams(default_int=2)),
        (FieldKind("text"), FieldParams(default_int=2)),
        (FieldKind("text"), FieldParams(discrete_values=(1,))),
        (WEIGHT, FieldParams(increment=-5)),
    ],
)
def test_check_field_on_canonical_values(kind: FieldKind, params: FieldParams) -> None:
    with pytest.raises(CatalogError):
        catalog.check_field(kind, params)


def test_cleared_for_drops_what_the_new_kind_refuses() -> None:
    params = FieldParams(True, 2500, None, 20000, None)
    assert catalog.cleared_for(WEIGHT, params) == params
    assert catalog.cleared_for(FieldKind("enum", None, ("a",)), params) == FieldParams(required=True)


def test_check_measures() -> None:
    catalog.check_measures([FieldSource(core_quantity="reps")])
    catalog.check_measures([FieldSource(variable_scope="set")])
    with pytest.raises(CatalogError) as caught:
        catalog.check_measures([FieldSource(variable_scope="setting")])
    assert codes(caught) == [("field", "last_measure")]
    with pytest.raises(CatalogError):
        catalog.check_measures([])


# --- aliases


def test_alias_draft() -> None:
    draft = catalog.alias_draft(" Bench press ", "Développé couché (barre)", ["DC"])
    assert (draft.alias, draft.normalised) == ("Bench press", "bench press")


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("", "required"),
        ("  ", "required"),
        ("!!", "required"),
        ("x" * 61, "too_long"),
        ("developpe couche (BARRE)", "alias_is_name"),
        ("d.c.", "alias_taken"),
    ],
)
def test_alias_refusals(raw: str, code: str) -> None:
    with pytest.raises(CatalogError) as caught:
        catalog.alias_draft(raw, "Développé couché (barre)", ["D C"])
    assert codes(caught) == [("alias", code)]


def test_sort_key_folds_case_and_accents() -> None:
    assert sorted(["Élastique", "assistance", "Zèbre"], key=catalog.sort_key) == [
        "assistance",
        "Élastique",
        "Zèbre",
    ]


# --- limits (tester, L2)


@pytest.mark.parametrize(("size", "ok"), [(80, True), (81, False)])
def test_exercise_name_limit(size: int, ok: bool) -> None:
    make = lambda: catalog.exercise_draft(name="n" * size, category="strength", location="gym")  # noqa: E731
    if ok:
        assert len(make().name) == size
    else:
        with pytest.raises(CatalogError):
            make()


@pytest.mark.parametrize(("count", "ok"), [(50, True), (51, False)])
def test_enum_values_limit(count: int, ok: bool) -> None:
    values = [ValueInput(str(n)) for n in range(count)]
    make = lambda: catalog.variable_draft(label="Cran", var_type="enum", scope="setting", values=values)  # noqa: E731
    if ok:
        assert len(make().enum_values or ()) == count
    else:
        with pytest.raises(CatalogError):
            make()


@pytest.mark.parametrize(("count", "ok"), [(30, True), (31, False)])
def test_discrete_values_limit(count: int, ok: bool) -> None:
    raw = " ".join(str(n) for n in range(1, count + 1))
    make = lambda: catalog.field_params(FieldKind("weight"), required=True, discrete_values=raw)  # noqa: E731
    if ok:
        assert len(make().discrete_values or ()) == count
    else:
        with pytest.raises(CatalogError):
            make()


@pytest.mark.parametrize(("size", "ok"), [(60, True), (61, False)])
def test_alias_limit(size: int, ok: bool) -> None:
    make = lambda: catalog.alias_draft("a" * size, "Squat", [])  # noqa: E731
    if ok:
        assert make().alias == "a" * size
    else:
        with pytest.raises(CatalogError):
            make()


def test_discrete_values_accept_semicolons_and_sort() -> None:
    params = catalog.field_params(FieldKind("weight"), required=False, discrete_values="24; 16;20")
    assert params.discrete_values == (16000, 20000, 24000)


def test_distance_values_mix_units() -> None:
    params = catalog.field_params(FieldKind("distance"), required=False, discrete_values="400 m 1 1,5 km")
    assert params.discrete_values == (400, 1000, 1500)


def test_zero_discrete_value_is_refused() -> None:
    with pytest.raises(CatalogError) as refused:
        catalog.field_params(FieldKind("weight"), required=False, discrete_values="0 16")
    assert ("discrete_values", "must_be_positive") in codes(refused)


def test_variable_code_suffixes_skip_taken_ones() -> None:
    assert catalog.variable_code("Siège", ["siege", "siege_2"]) == "siege_3"
    assert catalog.variable_code("!!!", ["v"]) == "v_2"


def test_enum_labels_equal_after_folding_are_duplicates() -> None:
    with pytest.raises(CatalogError) as refused:
        catalog.variable_draft(
            label="Prise",
            var_type="enum",
            scope="setting",
            values=[ValueInput("Pronation"), ValueInput("PRONATION ")],
        )
    assert [c for c in codes(refused) if c[1] == "duplicate_value"]


def test_check_linked_measures_names_every_exercise_left_without_measure() -> None:
    measure = catalog.FieldSource(core_quantity="reps")
    setting = catalog.FieldSource(variable_scope="setting")
    catalog.check_linked_measures("delete", [("Squat", [measure, setting])])
    with pytest.raises(CatalogError) as caught:
        catalog.check_linked_measures("scope", [("Planche", [setting]), ("Squat", [measure]), ("Pont", [])])
    assert codes(caught) == [("scope", "variable_last_measure")]
    assert caught.value.problems[0].params == {"exercises": "Planche, Pont"}


def test_removed_enum_keys_are_retired_and_never_reused() -> None:
    one, two = catalog.EnumValue("1", "1"), catalog.EnumValue("2", "2")
    assert catalog.retired_after([one, two], [one], ["0"]) == ("0", "2")
    assert catalog.retired_after([one], [one], ["2"]) == ("2",)
    draft = catalog.variable_draft(
        label="Siège",
        var_type="enum",
        scope="setting",
        values=[ValueInput("1", key="1"), ValueInput("2")],
        existing=[one],
        retired=["2"],
    )
    assert [value.key for value in draft.enum_values or ()] == ["1", "2_2"]
    assert draft.retired_keys == ("2",)
