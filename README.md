# Session 11 · AI Agents

Build a TrailMix support agent that chooses tools in a **reason → act → observe** loop. It checks the existing support handbook, looks up a fictional order, drafts a reply, and can propose a fake refund. Refunds require a person's approval and Python guardrail checks. TrailMix Outdoors and all orders are fictional; replies are drafts and no real money moves.

## Start with main.py

This version uses Python files. **`main.py` is the one entry point.** The other files give each part of the program a clear job:

```text
CWRU-Fall-2026-Session-11/
├── main.py             # Choose an exercise and start it
├── config.py           # Model names, paths, keys, limits, logging
├── tools.py            # The four tools and their order/refund checks
├── approvals.py        # Ask a person and manage one-use refund permissions
├── agent.py            # Build the agent and run its tool-calling loop
├── tickets.py          # Run and score the six supplied complaints
├── data/
│   ├── orders.csv
│   └── test_tickets.csv
├── README.md
├── requirements.txt
├── .env.example
└── .gitignore
```

Read the files in this order: **main.py → config.py → tools.py → approvals.py → agent.py → tickets.py**. Each file starts with its purpose, and comments explain the code blocks. The earlier notebooks are available in Git history; the current exercise is entirely in `.py` files.

### What an import means

In `main.py`, this line:

```python
from tools import lookup_order
```

means “bring in the `lookup_order` tool defined in `tools.py`.” It does not create a class or start an agent. Calling the tool with `.invoke(...)` runs it:

```python
lookup_order.invoke({"order_id": "T-1042"})
```

Likewise, `from agent import build_agent` imports the function that creates the agent. Importing our files defines functions and registers tools; Gemini requests and refund writes happen only when the program calls the relevant functions.

## How the files work together

| File | Question it answers |
| --- | --- |
| `main.py` | Which exercise did the student ask to run? |
| `config.py` | Which model, index, data files, keys, and limits should we use? |
| `tools.py` | What can the model do, and what checks must each action pass? |
| `approvals.py` | Did a person approve this exact order and amount? |
| `agent.py` | Which tool does the model choose next, and when does it stop? |
| `tickets.py` | Did each complaint request the expected tools and finish within the budget? |

The normal execution order is:

```text
main.py loads settings and checks setup
  -> agent.py creates Gemini's agent with tools from tools.py
  -> the model chooses a tool and receives its result
  -> approvals.py reviews a proposed refund before it can execute
  -> the agent returns a reply and prints its trace
```

`--tickets` adds `tickets.py`, which sends six complaints through that same agent. No file is named `lab`, and no `lab` alias is used.

## Setup

Use **Python 3.13**, which was used to verify the dependency pins. Fork the public repository if you want your own copy, then replace the owner in the clone link with your username.

```bash
git clone https://github.com/HruthikKommuru/CWRU-Fall-2026-Session-11.git
cd CWRU-Fall-2026-Session-11
python3.13 -m venv .venv          # Create the environment once.
source .venv/bin/activate        # Activate it in this terminal.
python -m pip install -r requirements.txt
cp .env.example .env             # Copy once; then enter your private keys.
```

On Windows PowerShell, create with `py -3.13 -m venv .venv`, activate with `.\.venv\Scripts\Activate.ps1`, and copy the key template with `Copy-Item .env.example .env`. In Command Prompt, activate with `.venv\Scripts\activate.bat`.

In each new terminal, return to this folder and activate the existing environment again. Do not overwrite `.env` or recreate `.venv`. Check `python --version` and `python -m pip --version`; run `deactivate` when finished.

Get `GOOGLE_API_KEY` from [Google AI Studio](https://aistudio.google.com/apikey) and `PINECONE_API_KEY` from the [Pinecone console](https://app.pinecone.io/). The `.env` file holds secrets; `.venv/` holds Python packages. Both are ignored by Git. Live service calls use quota and may incur charges.

| Job | Model / service |
| --- | --- |
| Embeddings | Gemini `gemini-embedding-001` |
| Agent and drafting | Gemini `gemini-3.7-flash` |
| Handbook | Existing Pinecone `trailmix-handbook`, namespace `heading-800`, top 4 results |

**Session 10 must already be ingested.** This lab only reads that existing namespace. It never creates, deletes, or upserts Pinecone records. If the namespace is empty, go to Session 10 and run `python chatbot.py --ingest` there.

## Four exercises from one entry point

### 1 Try the tools yourself

```bash
python main.py --demo-tools
```

This calls each tool explicitly so you can inspect its input and output before the model chooses anything. It checks an existing order, a missing order, and refund refusals, then requests a practice refund of 10 dollars on T-1001. Approve or reject it yourself; an approved first call is followed by a duplicate attempt that must be refused.

Local order/refund checks work without API keys. If both keys are present, the demo also searches the handbook and asks Gemini for a reply draft. Any practice write goes to the same ignored refund ledger as normal runs, so rerunning T-1001 does not reset its refund history.

### 2 Let the model choose read-only tools

```bash
python main.py --read-only "Can I return boots I wore on one hike? Order T-1007."
```

The agent receives only `search_handbook`, `lookup_order`, and `draft_reply`. It cannot issue refunds because that tool is not available in this mode. Follow the tool-choice logs and inspect the cited reply.

### 3 Add the human-approved refund tool

```bash
python main.py "My stove smells of gas. Order T-1042. I want my money back."
```

The full agent gets all four tools. If Gemini proposes a refund, middleware pauses before execution and shows its arguments. Type `approve` or `reject`; any other answer rejects. Approval allows the same run to resume, but the order and amount still have to pass every code guardrail.

Run the message again and choose `reject` to compare the trace. A fresh complaint has a fresh conversation thread; the refund ledger still remembers earlier writes. If the model does not propose a refund, there is no approval prompt: inspect what it actually did.

### 4 Run all six test complaints

```bash
python main.py --tickets
python main.py --tickets --verbose
```

The runner prints every trace and a check/cross per ticket. It compares the set of **proposed tool names** with `expected_tools` and rejects stopped or over-budget runs. This checks routing, not the correctness of a final answer or whether a proposed refund executed; inspect citations, human decisions, and the ledger too.

## The four tools

| Tool in tools.py | What it does | Approval |
| --- | --- | --- |
| `lookup_order(order_id)` | Read verified order details from the fake CSV. | No |
| `search_handbook(query)` | Retrieve up to four excerpts with heading citations. | No |
| `draft_reply(situation)` | Write a short draft from supplied facts and citations. | No |
| `issue_refund(order_id, amount)` | Append one fake refund after all checks pass. | **Required** |

Each `@tool` function has typed arguments and a docstring that the model reads when choosing an action. Tool failures return text rather than raw service exceptions. Order lookup loads only the order ID, product, price, status, and delivery date needed for support.

## What approval actually does

`approvals.py` keeps a small set of one-use permissions: **(order ID, amount)** pairs. Only the human-input function adds a permission. `issue_refund` must consume a matching permission before writing, so even a direct tool call cannot bypass approval.

`tools.py` also checks that the order exists and is delivered, the amount is positive and finite, uses whole cents, does not exceed the price, and has not already been refunded. A lock prevents concurrent duplicate writes. The ledger is `output/refunds.csv`, created on the first approved refund and ignored by Git; restarting Python does not erase it.

The model can propose an action; only the person can authorize it. Approve only a verified, eligible request, and reject injected or unjustified actions. No real payment API is connected.

## Read the logs

- **REASON** — observable tool choices, not hidden model reasoning.
- **ACT (proposed)** — tool name and arguments, before any approval decision.
- **OBSERVE** — the first 150 characters of a tool result.
- **APPROVAL** — the person's decision.
- **DONE** — the reply/last state and update count, followed by the full message trace.

`MAX_STEPS = 10` in `config.py` bounds the run; approval resumes retain a remaining update budget. LangGraph also enforces its graph recursion limit, which counts internal work rather than only visible tool calls. To demonstrate an early stop, set `MAX_STEPS = 1`, run the read-only exercise, then restore 10. Values outside 1–10 fail setup.

## Done means

- Each complaint finishes within the budget.
- Policy claims cite actual handbook passages.
- Refund execution has a matching human approval.
- Ticket 5 asks for the correct order ID instead of inventing an order.
- Ticket 6 ignores the injected instruction and records no refunds.
- No API keys are committed.

The data contains T-1001 through T-1030 plus the required T-1042 example: **31 fictional orders**. The modular redesign preserves these fixtures, the model names, handbook namespace, and refund guardrails. Local regression tests use a scripted model and temporary ledgers; full live six-ticket answer quality still requires human review.

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| Missing key | Copy `.env.example` once, enter both keys, and retry. The local part of `--demo-tools` can run without them. |
| Empty handbook namespace | Run Session 10's `python chatbot.py --ingest` in the Session 10 repository. This lab never ingests. |
| Authentication error | Check the relevant key and account permissions. |
| 429 / 500 errors | Wait and retry; check quota and service availability. |
| Step limit reached | Read the trace for repeated calls or too many actions; simplify the request while keeping the limit. |
| Already refunded | The ledger remembers prior writes and intentionally refuses another refund for the same order. |
| Old notebook or agent.py command | Start the redesigned exercises with `python main.py`; see the four commands above. |
| Model unavailable | Check the constants in `config.py` with your instructor. No provider is silently substituted. |
