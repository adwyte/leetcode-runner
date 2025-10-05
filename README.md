# LeetCode Class → Runnable C++

Paste a `class Solution { ... }` and get a full `main.cpp` with input parsing & JSON-like output.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
