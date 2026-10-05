"""V4 work item 8: thinking is a property of the act, and a call that thinks past its budget is a failure.

No model and no R: a fake client returns the shapes vLLM returns.
  python mcp/test_v4_thinking.py
"""
import os, sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bregsurv_agent import boundary  # noqa: E402

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


class FakeClient:
    base_url = "http://fake"

    def __init__(self, content, finish, reasoning=None):
        self.content, self.finish, self.reasoning = content, finish, reasoning
        self.chat = NS(completions=NS(create=self.create))
        self.sent = None

    def create(self, **kw):
        self.sent = kw
        msg = NS(content=self.content, reasoning_content=self.reasoning, model_extra={})
        return NS(choices=[NS(message=msg, finish_reason=self.finish)],
                  usage=NS(prompt_tokens=100, completion_tokens=kw["max_tokens"]))


SCHEMA = {"type": "object", "properties": {"reasoning": {"type": "string"}}, "required": ["reasoning"]}


def call(client, name="intent"):
    return boundary._chat(client, "m", "sys", "user", SCHEMA, name, max_tokens=300)


# A. which acts think
for env, act, want in [("", "analysis_plan", True), ("", "next_step", True), ("", "intent", False),
                       ("", "role_extraction", False), ("auto", "analysis_plan", True),
                       ("on", "intent", True), ("off", "analysis_plan", False),
                       ("intent,report_prose", "intent", True), ("intent,report_prose", "analysis_plan", False)]:
    os.environ["BREGSURV_THINKING"] = env
    check(f"A thinks({act!r}) under BREGSURV_THINKING={env!r} is {want}", boundary.thinks(act) is want)
os.environ.pop("BREGSURV_THINKING", None)

# B. decoding follows: a thinking act is sampled at 0.6/0.95, a reading act greedy, a writing act 0.7/0.8
d = boundary.decoding_for("analysis_plan")
check("B a thinking act decodes at 0.6 / 0.95 and says so", d["temperature"] == 0.6 and d["top_p"] == 0.95 and d["thinking"] is True)
d = boundary.decoding_for("intent")
check("B a reading act decodes greedily with thinking off", d["temperature"] == 0.0 and d["thinking"] is False)
d = boundary.decoding_for("report_prose")
check("B a writing act decodes at 0.7 / 0.8 with thinking off", d["temperature"] == 0.7 and d["thinking"] is False)

# C. the switch reaches the server and the allowance is added only when the act thinks
c = FakeClient('{"reasoning": "ok"}', "stop")
call(c, "intent")
check("C a reading act sends enable_thinking=False",
      c.sent["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False and c.sent["max_tokens"] == 300)
c = FakeClient('{"reasoning": "ok"}', "stop", reasoning="thought")
call(c, "analysis_plan")
check("C a thinking act sends enable_thinking=True and gets the allowance (default 8000)",
      c.sent["extra_body"]["chat_template_kwargs"]["enable_thinking"] is True
      and c.sent["max_tokens"] == 300 + boundary.THINKING_ALLOWANCE and boundary.THINKING_ALLOWANCE == 8000)

# D. thinking past the budget with no answer is a failure, recorded as one
boundary.call_log(clear=True)
c = FakeClient(None, "length", reasoning="x" * 12000)
try:
    call(c, "analysis_plan")
    check("D an unanswered truncated call raises", False)
except ValueError as e:
    check("D an unanswered truncated call raises", "no answer" in str(e))
rec = boundary.call_log()[-1]
check("D the call record says why, with the thinking length",
      rec.get("error", "").startswith("no answer") and "12000 characters" in rec["error"] and rec["finish_reason"] == "length")
c = FakeClient("", "length")
try:
    call(c, "intent")
    check("D an empty truncated answer from a reading act raises too", False)
except ValueError:
    check("D an empty truncated answer from a reading act raises too", True)

# E. an ordinary answer is unchanged
c = FakeClient('{"reasoning": "the request names followup_days"}', "stop")
out = call(c, "intent")
check("E an ordinary answer parses as before", out == {"reasoning": "the request names followup_days"})

print(f"\n{len(FAILS)} failed" if FAILS else "\nall passed")
sys.exit(1 if FAILS else 0)
