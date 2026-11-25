# AI tools used and their impact

> **Edit before submitting.** The brief asks you to document how AI tools helped *your* workflow and
> warns about plagiarism. Everything below is accurate for how this repo was produced, but add what you
> personally changed, tested and decided, and be ready to explain every module in the interview.

## Tools
| Tool | Used for |
|---|---|
| **Claude (claude.ai chat, with a code-execution sandbox)** | Wrote the first draft of the architecture, rule set, perception lexicon, SQLite schema, Q&A router, LangGraph tool layer, tests, diagrams (Graphviz), README and report; ran the tests and the 50k-frame scalability script and fixed what they exposed |
| LangGraph / LangChain / Groq *(optional layer)* | Tool-calling agent over the index (`llm_agent.py`) |
| Graphviz | Architecture, pipeline and data-model diagrams |

## Workflow and impact
1. **Design:** asked for an architecture that satisfies the four problem-statement points; chose "text captions as simulated VLM + SQLite index + deterministic rules" for testability.
2. **Generate:** Claude produced the modules; the **alert rules** and **object-detection logic** are the AI-generated components the brief asks for.
3. **Verify:** test suite + scalability script run in a sandbox. Failures found and fixed: non-deterministic `hash()` in the semantic index, `F-150` tokenisation, "leaves package"/"exits vehicle" misread as exits, Q&A filters dropped on "when" questions, alert spam, context truncation cutting the newest data.
4. **Document:** diagrams, README, report generated from real run outputs.

## What the AI got wrong / needed human judgement
* First semantic search used trigram hashing that ranked "delivery person" -> intruder frames; fixed by weighting words over trigrams and damping synonym sets (still a toy index).
* A test asserted the wrong "last truck at garage" time (19:02); the code was right (23:30), the test was wrong.
* Thresholds (3-min dwell, 15-min cooldown, night hours) are assumptions that a human operator should tune.

## Your turn (fill in)
* What you changed in the prompts/rules/config:
* What you learned (SQLite FTS5, entity tracking, LangGraph tools):
* Which parts you rewrote or extended:
* If you are new to LangChain / VLMs, say so here: the brief says effort and learning approach are evaluated.
