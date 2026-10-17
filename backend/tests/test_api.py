"""API-level tests: status codes, the error shape, and hostile input that must never yield a 5xx."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(engine, database_url):
    app = create_app(
        Settings(database_url=database_url, cors_origins=["http://ui.test"]), engine=engine
    )
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def ids(client):
    product = client.post(
        "/api/v1/products",
        json={"sku": "rice-25", "name": "Rice 25kg", "unit": "kg", "reorder_level": "100"},
    ).json()
    a = client.post("/api/v1/locations", json={"code": "a-01", "description": "Rack A"}).json()
    b = client.post("/api/v1/locations", json={"code": "B-01"}).json()
    return {"product": product["id"], "a": a["id"], "b": b["id"]}


def post_in(client, ids, qty="10", cost="40", **extra):
    body = {
        "type": "IN",
        "product_id": ids["product"],
        "to_location_id": ids["a"],
        "quantity": qty,
        "unit_cost": cost,
        "created_by": "tester",
        "reference": "INV-9",
    }
    body.update(extra)
    return client.post("/api/v1/movements", json=body)


def post_out(client, ids, qty, location="a"):
    return client.post(
        "/api/v1/movements",
        json={
            "type": "OUT",
            "product_id": ids["product"],
            "from_location_id": ids[location],
            "quantity": qty,
            "created_by": "tester",
        },
    )


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code
    assert set(error) == {"code", "message", "field", "details", "request_id"}
    assert error["request_id"] == response.headers["x-request-id"]
    return error


# ---------- happy paths ----------


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "database": "ok"}


def test_openapi_docs_are_served(client):
    assert client.get("/openapi.json").status_code == 200


def test_meta_lists_adjustment_reasons(client):
    meta = client.get("/api/v1/meta").json()
    assert meta["adjustment_reasons"] == [
        "damaged",
        "expired",
        "count_correction",
        "theft",
        "other",
    ]


def test_create_product_normalises_sku_and_returns_decimals_as_strings(client, ids):
    product = client.get(f"/api/v1/products/{ids['product']}").json()
    assert product["sku"] == "RICE-25"
    assert product["reorder_level"] == "100.000"
    assert product["is_low_stock"] is True


def test_full_movement_flow(client, ids):
    created = post_in(client, ids, "10", "40.5")
    assert created.status_code == 201
    m = created.json()
    assert m["value"] == "405.00" and m["to_location_code"] == "A-01"
    assert m["created_at"].endswith("Z") or m["created_at"].endswith("+00:00")

    t = client.post(
        "/api/v1/movements",
        json={
            "type": "TRANSFER",
            "product_id": ids["product"],
            "from_location_id": ids["a"],
            "to_location_id": ids["b"],
            "quantity": "4",
            "created_by": "tester",
        },
    )
    assert t.status_code == 201 and t.json()["value"] is None

    adj = client.post(
        "/api/v1/movements",
        json={
            "type": "ADJUSTMENT",
            "product_id": ids["product"],
            "location_id": ids["b"],
            "quantity": "-1",
            "reason_code": "damaged",
            "created_by": "tester",
        },
    )
    assert adj.status_code == 201 and adj.json()["from_location_code"] == "B-01"

    balances = client.get("/api/v1/balances", params={"product_id": ids["product"]}).json()
    assert {b["location_code"]: b["quantity"] for b in balances["items"]} == {
        "A-01": "6.000",
        "B-01": "3.000",
    }
    assert balances["total_quantity"] == "9.000"

    by_location = client.get("/api/v1/balances", params={"location_id": ids["b"]}).json()
    assert len(by_location["items"]) == 1 and by_location["total_quantity"] is None

    history = client.get("/api/v1/movements", params={"product_id": ids["product"]}).json()
    assert history["total"] == 3
    assert [i["type"] for i in history["items"]] == ["ADJUSTMENT", "TRANSFER", "IN"]

    ledger = client.get(f"/api/v1/products/{ids['product']}/ledger").json()
    assert [e["balance_after"] for e in ledger["entries"]] == ["10.000", "10.000", "9.000"]

    csv_text = client.get(f"/api/v1/products/{ids['product']}/ledger.csv").text
    assert csv_text.splitlines()[0].startswith("movement_id,created_at_utc,type")
    assert len(csv_text.strip().splitlines()) == 4


def test_history_filters(client, ids):
    post_in(client, ids, reference="INV-AAA")
    post_in(client, ids, reference="INV-BBB")
    post_out(client, ids, "1")
    r = client.get("/api/v1/movements", params={"reference": "bbb"}).json()
    assert r["total"] == 1
    assert client.get("/api/v1/movements", params={"type": "OUT"}).json()["total"] == 1
    assert client.get("/api/v1/movements", params={"location_id": ids["b"]}).json()["total"] == 0
    page = client.get("/api/v1/movements", params={"limit": 2, "offset": 2}).json()
    assert page["total"] == 3 and len(page["items"]) == 1
    today = client.get(
        "/api/v1/movements", params={"date_from": "2000-01-01", "date_to": "2999-12-31"}
    ).json()
    assert today["total"] == 3
    assert client.get("/api/v1/movements", params={"date_to": "2001-01-01"}).json()["total"] == 0


def test_reversal_endpoint_and_original_marked(client, ids):
    m = post_in(client, ids).json()
    r = client.post(
        f"/api/v1/movements/{m['id']}/reversal",
        json={"reason": "keyed twice", "created_by": "sup"},
    )
    assert r.status_code == 201
    assert r.json()["type"] == "OUT" and r.json()["reverses_movement_id"] == m["id"]
    original = client.get(f"/api/v1/movements/{m['id']}").json()
    assert original["is_reversed"] and original["reversed_by_movement_id"] == r.json()["id"]

    again = client.post(
        f"/api/v1/movements/{m['id']}/reversal", json={"reason": "x", "created_by": "sup"}
    )
    assert_error(again, 409, "ALREADY_REVERSED")
    of_reversal = client.post(
        f"/api/v1/movements/{r.json()['id']}/reversal", json={"reason": "x", "created_by": "s"}
    )
    assert_error(of_reversal, 409, "CANNOT_REVERSE_A_REVERSAL")


def test_reports(client, ids):
    post_in(client, ids, "150", "20")
    assert client.get("/api/v1/reports/low-stock").json() == []
    post_out(client, ids, "50")  # 100 left == reorder level -> low stock
    low = client.get("/api/v1/reports/low-stock").json()
    assert [item["product"]["sku"] for item in low] == ["RICE-25"]
    assert low[0]["shortfall"] == "0.000"

    valuation = client.get("/api/v1/reports/valuation").json()
    assert valuation["total_value"] == "2000.00"

    overview = client.get("/api/v1/reports/stock-overview").json()
    assert [loc["code"] for loc in overview["locations"]] == ["A-01", "B-01"]
    assert overview["rows"][0]["quantities"] == {str(ids["a"]): "100.000"}


def test_reconciliation_endpoints(client, ids, session):
    from decimal import Decimal

    from app.db import repositories as repo
    from app.db.session import transaction

    post_in(client, ids, "10", "5")
    assert client.get("/api/v1/reconciliation").json()["consistent"] is True
    with transaction(session):
        repo.set_cached_balance(session, ids["product"], ids["a"], Decimal("44"))
    report = client.get("/api/v1/reconciliation").json()
    assert report["consistent"] is False
    assert report["balance_drift"][0]["difference"] == "34.000"
    fixed = client.post("/api/v1/reconciliation").json()
    assert fixed["repaired"] is True
    assert client.get("/api/v1/reconciliation").json()["consistent"] is True


def test_product_and_location_updates(client, ids):
    r = client.patch(f"/api/v1/products/{ids['product']}", json={"reorder_level": "5"})
    assert r.status_code == 200 and r.json()["reorder_level"] == "5.000"
    r = client.patch(f"/api/v1/locations/{ids['a']}", json={"description": "Rack A upper"})
    assert r.json()["description"] == "Rack A upper"
    assert client.get("/api/v1/products", params={"search": "rice"}).json()["total"] == 1
    assert client.get("/api/v1/locations").json()["total"] == 2
    assert client.get(f"/api/v1/locations/{ids['b']}").json()["code"] == "B-01"


# ---------- domain errors ----------


def test_insufficient_stock_is_409_with_details(client, ids):
    post_in(client, ids, "5")
    error = assert_error(post_out(client, ids, "5.001"), 409, "INSUFFICIENT_STOCK")
    assert error["details"] == {"location_id": ids["a"], "available": "5", "requested": "5.001"}


@pytest.mark.parametrize("cost", ["0", "-10", "1.00001"])
def test_bad_unit_cost_is_422_rule_violation(client, ids, cost):
    error = assert_error(post_in(client, ids, cost=cost), 422, "INVALID_UNIT_COST")
    assert error["field"] == "unit_cost"


def test_unit_cost_on_out_is_rejected(client, ids):
    r = client.post(
        "/api/v1/movements",
        json={
            "type": "OUT",
            "product_id": ids["product"],
            "from_location_id": ids["a"],
            "quantity": "1",
            "unit_cost": "5",
            "created_by": "t",
        },
    )
    assert_error(r, 422, "VALIDATION_ERROR")


def test_adjustment_other_without_note(client, ids):
    r = client.post(
        "/api/v1/movements",
        json={
            "type": "ADJUSTMENT",
            "product_id": ids["product"],
            "location_id": ids["a"],
            "quantity": "1",
            "reason_code": "other",
            "created_by": "t",
        },
    )
    assert_error(r, 422, "NOTE_REQUIRED")


def test_unknown_adjustment_reason(client, ids):
    r = client.post(
        "/api/v1/movements",
        json={
            "type": "ADJUSTMENT",
            "product_id": ids["product"],
            "location_id": ids["a"],
            "quantity": "1",
            "reason_code": "lost-in-transit",
            "created_by": "t",
        },
    )
    error = assert_error(r, 422, "VALIDATION_ERROR")
    assert error["field"] == "reason_code"


def test_duplicates_are_409(client, ids):
    r = client.post("/api/v1/products", json={"sku": "RICE-25", "name": "x", "unit": "kg"})
    assert_error(r, 409, "DUPLICATE_SKU")
    assert_error(
        client.post("/api/v1/locations", json={"code": "A-01"}), 409, "DUPLICATE_LOCATION_CODE"
    )


def test_not_found_variants(client, ids):
    assert_error(client.get("/api/v1/products/999"), 404, "PRODUCT_NOT_FOUND")
    assert_error(client.get("/api/v1/locations/999"), 404, "LOCATION_NOT_FOUND")
    assert_error(client.get("/api/v1/movements/999"), 404, "MOVEMENT_NOT_FOUND")
    assert_error(
        client.post("/api/v1/movements/999/reversal", json={"reason": "x", "created_by": "s"}),
        404,
        "MOVEMENT_NOT_FOUND",
    )
    assert_error(post_in(client, {**ids, "a": 999}), 404, "LOCATION_NOT_FOUND")
    assert_error(
        client.get("/api/v1/balances", params={"product_id": 999}), 404, "PRODUCT_NOT_FOUND"
    )
    assert_error(client.get("/api/v1/nope"), 404, "NOT_FOUND")
    assert_error(client.delete(f"/api/v1/movements/{ids['a']}"), 405, "METHOD_NOT_ALLOWED")


def test_movements_have_no_update_or_delete_endpoint(client, ids):
    m = post_in(client, ids).json()
    for method in ("put", "patch", "delete"):
        r = getattr(client, method)(f"/api/v1/movements/{m['id']}")
        assert r.status_code == 405


# ---------- hostile input: never a 5xx ----------


@pytest.mark.parametrize(
    "payload",
    [
        "not json at all",
        "{",
        "[]",
        "null",
        '{"type": "IN"}',
        '{"type": "TELEPORT", "product_id": 1, "quantity": "1", "created_by": "x"}',
        '{"type": "IN", "product_id": "abc", "to_location_id": 1, "quantity": "1",'
        ' "unit_cost": "1", "created_by": "x"}',
        '{"type": "IN", "product_id": 1, "to_location_id": 1, "quantity": "NaN",'
        ' "unit_cost": "1", "created_by": "x"}',
        '{"type": "IN", "product_id": 1, "to_location_id": 1, "quantity": "Infinity",'
        ' "unit_cost": "1", "created_by": "x"}',
        '{"type": "IN", "product_id": 1, "to_location_id": 1, "quantity": "1e400",'
        ' "unit_cost": "1", "created_by": "x"}',
        '{"type": "IN", "product_id": 1, "to_location_id": 1, "quantity": true,'
        ' "unit_cost": "1", "created_by": "x"}',
        '{"type": "IN", "product_id": 99999999999999999999, "to_location_id": 1,'
        ' "quantity": "1", "unit_cost": "1", "created_by": "x"}',
        '{"type": "IN", "product_id": 1, "to_location_id": 1, "quantity": "1",'
        ' "unit_cost": "1", "created_by": "   "}',
        '{"type": "OUT", "product_id": 1, "from_location_id": 1, "quantity": [],'
        ' "created_by": "x"}',
    ],
)
def test_malformed_movement_bodies_are_422(client, ids, payload):
    r = client.post(
        "/api/v1/movements", content=payload, headers={"Content-Type": "application/json"}
    )
    assert_error(r, 422, "VALIDATION_ERROR")


def test_quantity_far_too_large_is_a_rule_violation(client, ids):
    assert_error(post_in(client, ids, qty="10000000.001"), 422, "INVALID_QUANTITY")
    assert_error(post_in(client, ids, qty="0"), 422, "INVALID_QUANTITY")
    assert post_in(client, ids, qty="0.001").status_code == 201


@pytest.mark.parametrize(
    "url",
    [
        "/api/v1/products/0",
        "/api/v1/products/-1",
        "/api/v1/products/abc",
        "/api/v1/products/99999999999999999999",
        "/api/v1/products?limit=0",
        "/api/v1/products?limit=100000",
        "/api/v1/products?offset=-1",
        "/api/v1/movements?type=SIDEWAYS",
        "/api/v1/movements?date_from=yesterday",
        "/api/v1/movements?product_id=1e9",
    ],
)
def test_bad_path_and_query_params_are_422(client, url):
    assert_error(client.get(url), 422, "VALIDATION_ERROR")


@pytest.mark.parametrize(
    "params",
    [
        {"date_from": "2026-10-10", "date_to": "2026-10-01"},
        {"date_to": "9999-12-31"},
        {"date_from": "0001-01-01"},
    ],
)
def test_bad_date_ranges_are_422(client, params):
    assert_error(client.get("/api/v1/movements", params=params), 422, "INVALID_DATE_RANGE")


@pytest.mark.parametrize(
    "body",
    [
        {"sku": "", "name": "x", "unit": "kg"},
        {"sku": "has space", "name": "x", "unit": "kg"},
        {"sku": "OK1", "name": "x", "unit": "tonnes"},
        {"sku": "OK1", "name": "", "unit": "kg"},
        {"sku": "OK1", "name": "x", "unit": "kg", "extra": 1},
        {"sku": "X" * 41, "name": "x", "unit": "kg"},
    ],
)
def test_bad_product_bodies_are_422(client, body):
    assert_error(client.post("/api/v1/products", json=body), 422, "VALIDATION_ERROR")


def test_product_unit_cannot_be_changed(client, ids):
    r = client.patch(f"/api/v1/products/{ids['product']}", json={"unit": "pcs"})
    assert_error(r, 422, "VALIDATION_ERROR")


def test_negative_reorder_level_is_rule_violation(client):
    r = client.post(
        "/api/v1/products", json={"sku": "N1", "name": "x", "unit": "kg", "reorder_level": "-1"}
    )
    assert_error(r, 422, "INVALID_REORDER_LEVEL")


def test_reversal_without_reason(client, ids):
    m = post_in(client, ids).json()
    r = client.post(
        f"/api/v1/movements/{m['id']}/reversal", json={"reason": " ", "created_by": "s"}
    )
    assert_error(r, 422, "REASON_REQUIRED")


# ---------- cross-cutting ----------


def test_request_id_is_echoed_when_safe_and_generated_otherwise(client):
    assert (
        client.get("/health", headers={"X-Request-ID": "abc-123"}).headers["x-request-id"]
        == "abc-123"
    )
    generated = client.get("/health", headers={"X-Request-ID": "bad id\n"}).headers["x-request-id"]
    assert generated != "bad id\n" and len(generated) == 32


def test_cors_allows_configured_origin_only(client):
    ok = client.options(
        "/api/v1/products",
        headers={"Origin": "http://ui.test", "Access-Control-Request-Method": "POST"},
    )
    assert ok.headers.get("access-control-allow-origin") == "http://ui.test"
    blocked = client.get("/api/v1/products", headers={"Origin": "http://evil.test"})
    assert "access-control-allow-origin" not in blocked.headers


def test_unexpected_errors_become_500_without_stack_trace(client, monkeypatch):
    from app.services import reports

    def boom(*_args, **_kwargs):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(reports, "valuation", boom)
    r = client.get("/api/v1/reports/valuation")
    error = assert_error(r, 500, "INTERNAL_ERROR")
    assert "secret" not in r.text and "Traceback" not in r.text
    assert error["field"] is None


def test_database_outage_is_503(client, monkeypatch):
    from sqlalchemy.exc import OperationalError

    from app.services import reports

    def down(*_args, **_kwargs):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(reports, "low_stock", down)
    assert_error(client.get("/api/v1/reports/low-stock"), 503, "DATABASE_UNAVAILABLE")


def test_logs_are_json_with_request_id(client, caplog):
    import json

    from app.logging_setup import JsonFormatter

    caplog.set_level("INFO")
    client.get("/api/v1/products/999", headers={"X-Request-ID": "trace-me"})
    formatter = JsonFormatter()
    warn = next(r for r in caplog.records if r.getMessage() == "business rule rejected request")
    assert warn.levelname == "WARNING"
    assert warn.ctx["code"] == "PRODUCT_NOT_FOUND" and warn.ctx["product_id"] == 999
    line = json.loads(formatter.format(warn))
    assert {"ts", "level", "logger", "msg", "request_id", "code", "product_id"} <= set(line)
    assert line["ts"].endswith("Z")
    done = next(r for r in caplog.records if r.getMessage() == "request completed")
    assert done.ctx["status"] == 404 and "duration_ms" in done.ctx
