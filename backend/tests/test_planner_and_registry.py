import pytest

from app.config import get_settings
from app.llm.providers import LLMError, MockProvider
from app.services.planner import Plan, PlanError, PlanStep, make_plan, rule_plan, validate_plan
from app.tools.registry import ToolRegistry, ToolSpec, get_registry


class FakeLLM:
    name, is_real = "fake", True

    def __init__(self, out=None, exc=None):
        self.out, self.exc = out, exc

    def complete(self, system, user, *, json_mode=False):
        if self.exc:
            raise self.exc
        return self.out


def test_registry_metadata_complete():
    tools = {t.name: t.describe() for t in get_registry().all()}
    assert {"list_directory", "read_file", "search_files", "calculate_statistics", "task_history", "run_command"} <= set(tools)
    for d in tools.values():
        assert d["input_schema"] and d["output_schema"] and d["description"] and d["timeout"] > 0


def test_duplicate_tool_rejected():
    r = ToolRegistry()
    spec = get_registry().get("read_file")
    r.register(spec)
    with pytest.raises(ValueError):
        r.register(spec)


def test_validate_plan_rejects_unknown_tool_and_bad_args():
    reg = get_registry()
    with pytest.raises(PlanError):
        validate_plan(Plan(steps=[PlanStep(tool="format_disk")]), reg)
    with pytest.raises(PlanError):
        validate_plan(Plan(steps=[PlanStep(tool="read_file", args={})]), reg)
    with pytest.raises(PlanError):
        validate_plan(Plan(steps=[PlanStep(tool="calculate_statistics", args={"values": "abc"})]), reg)


def test_plan_step_limit():
    steps = [PlanStep(tool="task_history", args={})] * (get_settings().max_plan_steps + 1)
    with pytest.raises(PlanError):
        validate_plan(Plan(steps=steps), get_registry())


def test_rule_planner_examples():
    assert [s.tool for s in rule_plan("what is the mean of 1, 2, 3?").steps] == ["calculate_statistics"]
    assert rule_plan("run the tests").steps[0].args["argv"][:3] == ["python", "-m", "pytest"]
    assert rule_plan("read README.md").steps[0].args == {"path": "README.md"}
    assert rule_plan("tell me a joke").steps == []


def test_llm_plan_used_when_valid():
    out = '{"steps":[{"tool":"list_directory","args":{"path":"."},"description":"ls"}],"success_criteria":["ok"]}'
    r = make_plan("x", get_registry(), FakeLLM(out))
    assert r.source == "llm" and r.plan.steps[0].tool == "list_directory"


@pytest.mark.parametrize("llm", [
    FakeLLM(out="not json"),
    FakeLLM(out='{"steps":[{"tool":"shell","args":{"cmd":"rm -rf /"}}]}'),
    FakeLLM(out='{"steps":[{"tool":"read_file","args":{"path":5}}]}'),
    FakeLLM(exc=LLMError("boom")),
])
def test_bad_llm_plans_fall_back_to_rules(llm):
    r = make_plan("list the files in the project", get_registry(), llm)
    assert r.source == "rules" and r.notes
    assert all(get_registry().get(s.tool) for s in r.plan.steps)


def test_mock_provider_is_honest():
    assert "No language-model provider" in MockProvider().complete("", "hi")
