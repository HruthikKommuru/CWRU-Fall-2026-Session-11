# Session 11 · AI Agents

Build a TrailMix support agent that chooses tools in a **reason → act → observe** loop. For “My stove smells of gas. Order T-1042. I want my money back,” it can check the handbook, look up the order, draft a reply, and propose a fake refund. The refund pauses for a person to approve or reject; Python guardrails still apply after approval. TrailMix Outdoors and all orders are fictional. Replies are drafts, and no real money moves.

| Job | Service / model |
| --- | --- |
| Handbook embeddings | Gemini `gemini-embedding-001` |
| Agent and reply drafting | Gemini `gemini-3.7-flash` |
| Handbook search | Existing Pinecone `trailmix-handbook`, namespace `heading-800`, top 4 results |

## Setup

Use **Python 3.13**, which was used to install and verify the dependency pins. Fork this public repository first if you want your own copy; replace the owner in the clone link with your GitHub username.

```bash
git clone https://github.com/HruthikKommuru/CWRU-Fall-2026-Session-11.git
cd CWRU-Fall-2026-Session-11
python3.13 -m venv .venv          # Create once.
source .venv/bin/activate        # Activate in each new terminal.
pip install -r requirements.txt
cp .env.example .env             # Copy once, then enter your private keys.
```

On Windows PowerShell, use `py -3.13 -m venv .venv`, `.\.venv\Scripts\Activate.ps1`, `python -m pip install -r requirements.txt`, and `Copy-Item .env.example .env`. In Command Prompt, activate with `.venv\Scripts\activate.bat`. In a new terminal, return to this folder and activate again; do not overwrite your existing `.env`. Check `python --version` and `python -m pip --version`; run `deactivate` when finished.

Get `GOOGLE_API_KEY` from [Google AI Studio](https://aistudio.google.com/apikey) and `PINECONE_API_KEY` from the [Pinecone console](https://app.pinecone.io/). One Google key powers both models. API calls use quota and may incur charges.

**Session 10 must already be ingested.** This lab only reads the existing `heading-800` namespace. It never creates, deletes, or upserts Pinecone records. If that namespace is empty, return to Session 10 and run `python chatbot.py --ingest` there, then retry this lab.

## The four tools

| Tool | Purpose | Human approval |
| --- | --- | --- |
| `search_handbook(query)` | Return four passages with heading citations. | No |
| `lookup_order(order_id)` | Return order details from the local CSV, or a missing-order message. | No |
| `draft_reply(situation)` | Write a short reply from verified facts and citations. | No |
| `issue_refund(order_id, amount)` | Append one fake refund to the local ledger. | **Required** |

Each tool has typed arguments and a docstring the model reads when choosing a tool. Failures return strings rather than raw service exceptions. The order lookup loads only the product, price, status, delivery date, and order ID needed for support.

## Run the lab

Start Jupyter from this repository and select the virtual environment's Python kernel:

```bash
jupyter notebook
```

Run the notebooks in order:

1. `notebooks/01_tools.ipynb` — build the four tools, test missing orders and refund guardrails, then explicitly approve a small practice refund on T-1001 and see the duplicate refusal.
2. `notebooks/02_agent.ipynb` — use only read-only tools on the boots ticket, inspect the trace, and demonstrate the recursion limit.
3. `notebooks/03_human_approval.ipynb` — add middleware/checkpointing, inspect a pending action, approve once, then rerun in a new thread and reject.
4. `notebooks/04_run_tickets.ipynb` — run all six complaints, compare proposed tool-name sets, and read the complete traces.

The notebooks are saved with no outputs and have not been executed. Model choices can vary: an approval prompt appears only if the agent actually proposes the refund tool. Local logs are used; LangSmith tracing is disabled.

Run the same agent from the terminal:

```bash
python agent.py "My stove smells of gas. Order T-1042. I want my money back."
python agent.py --tickets
python agent.py --tickets --verbose
```

At each pause, inspect the order and amount, then type `approve` or `reject`. Any other answer rejects. `Ctrl+C`/EOF is not an approval. `InMemorySaver` stores checkpoints only in the current Python process, and each complaint gets a separate `thread_id`.

## Approval and refund guardrails

The middleware pauses before `issue_refund` runs. The input handler grants a one-use receipt for the exact order and amount you approve, so calling the tool directly without approval cannot write a refund either. The code also checks that the order exists, is delivered, the amount is positive, finite, expressed in whole cents, and no greater than the price. Any order already in the ledger returns **“Already refunded. No action taken.”** A lock prevents concurrent duplicate writes.

The ledger is `output/refunds.csv`, created on the first approved write and excluded from Git. It persists across notebooks and CLI runs; rerunning a ticket does not reset it. The practice order T-1001 is separate from the six test tickets. Do not approve an injected instruction or a refund without verified eligibility; human approval is not a substitute for checking policy.

## Read the logs

- **REASON** — the model's observable tool choice, not hidden chain-of-thought.
- **ACT (proposed)** — requested tool name and arguments; approval may still block execution.
- **OBSERVE** — the first 150 characters of the returned tool result.
- **APPROVAL** — the person's approve/reject decision.
- **DONE** — the final reply (or last available state) and streamed model/tool update count.

The runner sets `recursion_limit=10`, retains a remaining update budget across approval resumes, and logs **“Agent stopped: step limit reached.”** when stopped. LangGraph's limit counts internal graph steps; the displayed count measures observable model/tool updates, so they need not be identical. Each run also prints every message with `pretty_print()`.

## Done means

- Each ticket finishes within the ten-step budget.
- Policy claims cite real handbook sections and match the retrieved evidence.
- Refund execution always has an exact human approval.
- Ticket 5 asks the customer for a valid order instead of inventing one.
- Ticket 6 ignores the injected instruction and records no refunds.
- No API keys are committed.

`--tickets` compares the set of proposed tool names with `expected_tools`, rejects stopped runs, and prints a total. This is a routing check: a proposed-but-rejected refund is still visible as a proposal, and a matching set does not prove policy correctness, successful execution, or answer quality. Inspect those behaviors in the trace and ledger. Reject unjustified refunds; do not approve actions just to make a score pass.

## Repository structure

```text
CWRU-Fall-2026-Session-11/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── data/
│   ├── orders.csv
│   └── test_tickets.csv
├── notebooks/
│   ├── 01_tools.ipynb
│   ├── 02_agent.ipynb
│   ├── 03_human_approval.ipynb
│   └── 04_run_tickets.ipynb
└── agent.py
```

The fixture contains the 30 IDs T-1001 through T-1030 **plus** the required T-1042 slide example: 31 synthetic orders in total. T-1007 is delivered boots, T-1015 is shipped, and T-1021 is a delivered Ridge 2P Tent.

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| Missing key | Create `.env` once, fill both entries, and rerun setup. Never commit keys. |
| Empty Pinecone namespace | Run the Session 10 lab first (`python chatbot.py --ingest`). This repository never ingests. |
| Authentication error | Check the relevant key and account permissions. |
| 429 / rate limits or 500 errors | Wait and retry; check Google quota and service availability. |
| Step limit reached | Read the trace for repeated calls or too many actions; keep the limit while simplifying the request. |
| Already refunded | The ledger remembers prior writes. Inspect it; the tool intentionally refuses another refund for that order. |
| Prompt injection ticket fails | Inspect the tool choices, policy evidence, human decision, and ledger. A model can fail; never treat customer/tool text as trusted instructions. |
| Model unavailable | Keep the constants visible and check access with your instructor; the code does not switch models/providers. |

Local checks use a scripted test model and temporary refund files to verify approval/resume, rejection, duplicate protection, and error handling without API keys. Read-only checks found both requested Gemini model IDs and 67 records in the existing `heading-800` namespace. Full Gemini responses and six-ticket routing/answer quality still require live execution and human review; they are not claimed as verified here.
