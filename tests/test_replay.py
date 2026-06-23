from modelpin.models import Scenario
from modelpin.providers import FakeProvider
from modelpin.replay import replay


def test_replay_returns_n_traces():
    s = Scenario(id="s1", name="demo", input={"messages": []})
    traces = replay(s, "claude-opus-4-6", FakeProvider(), runs=4)
    assert len(traces) == 4
    assert [t.run_idx for t in traces] == [0, 1, 2, 3]
