from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import re
from typing import List, Dict, Any, Optional

router = APIRouter()

# ---------- utils ----------

def normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def split_top_level(s: str, delim: str) -> List[str]:
    out, buf, depth = [], [], 0
    for ch in s:
        if ch == '<': depth += 1
        elif ch == '>': depth = max(0, depth-1)
        if ch == delim and depth == 0:
            out.append("".join(buf)); buf = []
        else:
            buf.append(ch)
    if buf: out.append("".join(buf))
    return out

# ---------- robust signature detection (public-only) ----------

def _strip_comments(src: str) -> str:
    # Remove /* ... */ and // ... while preserving newlines (positions remain roughly aligned)
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"//[^\n\r]*", "", src)
    return src

def _extract_class_body(src: str) -> Optional[str]:
    """
    Return the exact text inside the outermost braces of `class Solution { ... }`.
    Uses brace counting (not regex) so nested function braces don't break it.
    """
    m = re.search(r"\bclass\s+Solution\b", src)
    if not m:
        return None
    i = m.end()

    # find first '{' after 'class Solution'
    brace_open = src.find("{", i)
    if brace_open == -1:
        return None

    depth = 1
    j = brace_open + 1
    while j < len(src) and depth > 0:
        ch = src[j]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
        j += 1

    if depth != 0:
        return None  # unbalanced braces

    # body is the content between the outermost class braces
    return src[brace_open + 1 : j - 1]

def detect_signature(code: str) -> Optional[Dict[str, Any]]:
    """
    Find the first function DEFINITION inside any public: span of class Solution.
    If there is no public: span at all, fall back to scanning the whole class body.
    """
    code_nc = _strip_comments(code)
    body = _extract_class_body(code_nc)
    if body is None:
        return None

    # Build access spans: [(label, start, end), ...]
    labels = list(re.finditer(r"(public|private|protected)\s*:", body))
    public_spans: list[tuple[int,int]] = []

    if labels:
        for i, m in enumerate(labels):
            label = m.group(1)
            start = m.end()
            end = labels[i+1].start() if i+1 < len(labels) else len(body)
            if label == "public":
                public_spans.append((start, end))
        # If there are access labels but no public span, do NOT scan private/protected.
        if not public_spans:
            return None
        search_spaces = [body[s:e] for (s, e) in public_spans]
    else:
        # No explicit access labels → treat the whole class body as a single public-ish space.
        search_spaces = [body]

    # Header regex; we’ll additionally require the next non-space char after header is '{'
    header_re = re.compile(
        r"([A-Za-z_:\s<>\[\],&*\d]+?)\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*(?:const\s*)?(?:noexcept\s*)?",
        re.DOTALL
    )

    def next_non_space(text: str, idx: int) -> str:
        m = re.search(r"\S", text[idx:])
        return text[idx + m.start()] if m else ""

    def scan(space: str) -> Optional[Dict[str, Any]]:
        for m in header_re.finditer(space):
            ret = normalize_ws(m.group(1))
            name = m.group(2)
            if name == "Solution":  # skip constructor
                continue
            # Definition (not just declaration): must be followed by '{'
            nxt = next_non_space(space, m.end())
            if nxt != "{":
                continue

            params_raw = m.group(3).strip()
            params: List[Dict[str, str]] = []
            if params_raw:
                for p in split_top_level(params_raw, ','):
                    seg = normalize_ws(re.sub(r"^\s*const\s+", "", p.strip()))
                    if not seg:
                        continue
                    last_space = seg.rfind(' ')
                    if last_space == -1:
                        ptype = seg.replace('&','').replace('const','').strip()
                        pname = ''
                    else:
                        ptype = seg[:last_space].replace('&','').replace('const','').strip()
                        pname = seg[last_space+1:].strip()
                    params.append({"type": ptype, "name": pname})
            return {"ret": ret, "name": name, "params": params}
        return None

    # Prefer public spans or whole body if no labels existed
    for sp in search_spaces:
        hit = scan(sp)
        if hit:
            return hit
    return None

# ---------- includes ----------

def includes_block(prefer_bits: bool, needs_string: bool) -> str:
    if prefer_bits:
        return "#include <bits/stdc++.h>\nusing namespace std;\n"
    incs = ["#include <iostream>", "#include <vector>"]
    if needs_string:
        incs.append("#include <string>")
    return "\n".join(incs) + "\nusing namespace std;\n"

# ---------- IO generation ----------

def gen_input_for_param(p: Dict[str, str]) -> str:
    t = re.sub(r"\s+", "", p["type"])
    name = p["name"] or "arg"
    if t in ("vector<vector<int>>", "vector<vector<int> >"):
        return f"""\
int m, n; cin >> m >> n;
vector<vector<int>> {name}(m, vector<int>(n));
for (int i = 0; i < m; ++i) {{
    for (int j = 0; j < n; ++j) {{
        cin >> {name}[i][j];
    }}
}}"""
    if t == "vector<int>":
        return f"""\
int n; cin >> n;
vector<int> {name}(n);
for (int i = 0; i < n; ++i) cin >> {name}[i];"""
    if t == "int":
        return f"int {name}; cin >> {name};"
    if t == "double":
        return f"double {name}; cin >> {name};"
    if t == "bool":
        return f"int __b; cin >> __b; bool {name} = (__b != 0);"
    if t == "string":
        return f"string {name}; cin >> {name};"
    return f"/* TODO: unsupported param type: {p['type']} {name} */"

def join_args(params: List[Dict[str, str]]) -> str:
    return ", ".join([(p["name"] or "").strip() for p in params])


def gen_output_for_ret(ret_type: str, out_var: str="out") -> str:
    rt = re.sub(r"\s+", "", ret_type)
    if rt.startswith("vector<vector<"):
        return f"""\
for (const auto& row : {out_var}) {{
    if (row.size() == 2) {{
        cout << row[0] << " " << row[1] << "\\n";
    }} else {{
        for (size_t j = 0; j < row.size(); ++j) {{
            if (j) cout << ' ';
            cout << row[j];
        }}
        cout << "\\n";
    }}
}}"""
    if rt.startswith("vector<"):
        return f"""\
for (size_t i = 0; i < {out_var}.size(); ++i) {{
    if (i) cout << ' ';
    cout << {out_var}[i];
}}
cout << "\\n";"""
    return f'cout << {out_var} << "\\n";'


def indent_block(s: str, pad: str = "    ") -> str:
    lines = s.splitlines()
    return "\n".join((pad + ln) if ln.strip() != "" else ln for ln in lines)


def build_main(sig: Dict[str, Any]) -> str:
    input_blocks = [gen_input_for_param(p) for p in sig["params"]]
    decls = "\n\n".join(indent_block(b) for b in input_blocks) if input_blocks else "    /* no params */"
    args = join_args(sig["params"])
    out_print = indent_block(gen_output_for_ret(sig["ret"], "out"))
    return f"""
int main(){{
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

{decls}

    Solution sol;
    auto out = sol.{sig['name']}({args});
{out_print}
    return 0;
}}"""

# ---------- route ----------

@router.post("/generate")
async def generate(request: Request):
    data = await request.json()
    code = data.get("code", "")
    prefer_bits = bool(data.get("preferBits", False))

    sig = detect_signature(code)
    if not sig:
        inc = includes_block(prefer_bits, needs_string=("string" in code))
        generated = f"""{inc}

{code.strip()}

// Signature not detected. Please edit main() accordingly.
int main(){{
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    // Example for a matrix input:
    int m, n; cin >> m >> n;
    vector<vector<int>> a(m, vector<int>(n));
    for (int i = 0; i < m; ++i) for (int j = 0; j < n; ++j) cin >> a[i][j];

    Solution sol;
    // auto out = sol.YOUR_METHOD(a);
    // TODO: print output as needed
    return 0;
}}
"""
        return JSONResponse({"generated_code": generated.strip(), "signature": None})

    needs_string = ("string" in code) or any(re.sub(r"\s+","", p["type"]) == "string" for p in sig["params"])
    inc = includes_block(prefer_bits, needs_string)
    main_block = build_main(sig)

    final = f"""{inc}
{code.strip()}

{main_block}
"""
    pretty = f"{sig['ret']} {sig['name']}(" + ", ".join(f"{p['type']} {p['name']}".strip() for p in sig["params"]) + ")"
    return JSONResponse({"generated_code": final.strip(), "signature": pretty})
