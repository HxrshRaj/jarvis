from app.services import evals

API = "/api/v1"


def test_eval_suite_is_deterministic():
    assert evals.run_suite() == evals.run_suite()


def test_eval_suite_reports_core_guarantees():
    r = evals.run_suite()["results"]
    assert r["permission_enforcement"]["enforcement_accuracy"] == 1.0 and not r["permission_enforcement"]["failures"]
    assert r["citations_and_termination"]["termination"]["terminates_within_bound"] is True
    assert r["citations_and_termination"]["no_evidence_skips_model"] is True
    assert r["citations_and_termination"]["citation_validator_accuracy"] == 1.0
    assert r["provider_failure_planning"]["fell_back_safely"] == r["provider_failure_planning"]["cases"]
    assert r["rag_retrieval"]["recall_at_3"] >= 0.9 and r["rag_retrieval"]["out_of_scope_returning_hits"] == 0
    assert r["tool_selection"]["selection_accuracy"] >= 0.9
    assert "response_usefulness" in r["skipped"]  # live-LLM evals are never silently reported as passed


def test_eval_api_stores_runs(client, auth):
    run = client.post(f"{API}/evals/run", headers=auth).json()
    assert run["config"]["eval_version"] == evals.EVAL_VERSION and "planner" in run["config"]["prompt_versions"]
    listed = client.get(f"{API}/evals", headers=auth).json()["runs"]
    assert listed[0]["id"] == run["id"]
    assert client.get(f"{API}/evals").status_code == 401


def test_ml_report_endpoint(client, auth):
    r = client.get(f"{API}/ml/report", headers=auth).json()
    assert r["dataset"]["synthetic"] is True and set(r["decision"]["natural_macro_f1"]) >= {"rules", "sklearn", "torch"}


def test_auth_endpoints_are_rate_limited_per_ip(client):
    from app.config import get_settings

    get_settings().auth_rate_limit_per_minute = 5
    codes = [client.post(f"{API}/auth/login", json={"email": "x@example.com", "password": "wrong-password-1"}).status_code for _ in range(8)]
    assert codes[:5] == [401] * 5 and 429 in codes[5:]
    get_settings().auth_rate_limit_per_minute = 20


def test_general_limit_is_per_token_and_preflight_is_exempt(client):
    from tests.conftest import make_user
    from app.config import get_settings

    a, b = make_user(client, "a@example.com"), make_user(client, "b@example.com")
    get_settings().rate_limit_per_minute = 4
    assert 429 in [client.get(f"{API}/tools", headers=a).status_code for _ in range(8)]
    assert client.get(f"{API}/tools", headers=b).status_code == 200  # user B unaffected by user A's burst
    pre = [client.options(f"{API}/tools", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"}).status_code
           for _ in range(30)]
    assert 429 not in pre
