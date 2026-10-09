from workforce.design import validate


def names(modules):
    return [m["model"] for m in modules]


def test_valid_spec_is_put_in_dependency_order(tmp_path):
    spec = {"modules": [
        {"model": "InvoiceItem", "fields": ["description:str", "invoice:fk:Invoice", "quantity:int"]},
        {"model": "Invoice", "fields": ["number:str:unique", "customer:fk:Customer"]},
        {"model": "Customer", "fields": ["name:str"]},
    ]}
    ordered, errors, skipped = validate(spec, tmp_path)
    assert not errors
    assert names(ordered) == ["Customer", "Invoice", "InvoiceItem"]


def test_bad_specs_are_rejected(tmp_path):
    assert validate("nonsense", tmp_path)[1]
    assert validate({"modules": [{"model": "A", "fields": ["x:weird"]}]}, tmp_path)[1]
    assert validate({"modules": [{"model": "a", "fields": ["x:str"]}]}, tmp_path)[1]
    assert validate({"modules": [{"model": "Order", "fields": ["ref:str", "buyer:fk:Nobody"]}]}, tmp_path)[1]
    circular = {"modules": [{"model": "A", "fields": ["n:str", "b:fk:B"]},
                            {"model": "B", "fields": ["n:str", "a:fk:A"]}]}
    errors = validate(circular, tmp_path)[1]
    assert errors and "circular" in errors[0]


def test_existing_module_is_skipped_but_can_be_linked(tmp_path):
    (tmp_path / "customers").mkdir()
    spec = {"modules": [{"model": "Customer", "fields": ["name:str"]},
                        {"model": "Invoice", "fields": ["number:str", "customer:fk:Customer"]}]}
    ordered, errors, skipped = validate(spec, tmp_path)
    assert not errors and skipped == ["Customer"] and names(ordered) == ["Invoice"]
