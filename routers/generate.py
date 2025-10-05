from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import re
from typing import List, Dict, Any, Optional

router = APIRouter()

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

def detect_signature(code: str) -> Optional[Dict[str, Any]]:
    # 1) Extract class body
    cls = re.search(r"class\s+Solution\s*{([\s\S]*?)}\s*;?", code, re.M)
    if not cls:
        return None
    body = cls.group(1)

    # 2) Try inside first public: block
    blocks = re.split(r"public\s*:", body, maxsplit=1)
    search_space = [blocks[1]] if len(blocks) == 2 else []

    # 3) Fallback: search whole body as well
    search_space.append(body)

    sig_regex = re.compile(
        r"([A-Za-z_:\s<>\[\],&*\d]+?)\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*(?:const\s*)?(?:noexcept\s*)?",
        re.DOTALL
    )

    for space in search_space:
        m = sig_regex.search(space)
        if not m:
            continue

        ret = normalize_ws(m.group(1))
        name = m.group(2)
        if name == "Solution":     # skip constructor
            # try next match in same space
            m2 = sig_regex.search(space, m.end())
            if not m2:
                continue
            ret = normalize_ws(m2.group(1))
            name = m2.group(2)
            if name == "Solution":
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
                    ptype = seg.replace('&', '').replace('const', '').strip()
                    pname = ''
                else:
                    ptype = seg[:last_space].replace('&', '').replace('const', '').strip()
                    pname = seg[last_space+1:].strip()
                params.append({"type": ptype, "name": pname})

        return {"ret": ret, "name": name, "params": params}

    return None


INCLUDES = """#include <iostream>
#include <vector>
#include <string>
#include <queue>
#include <stack>
#include <algorithm>
#include <limits>
#include <unordered_map>
#include <unordered_set>
#include <map>
#include <set>
#include <cmath>
#include <cctype>
#include <numeric>
#include <sstream>
using namespace std;
"""

READERS = r"""
// --- Input readers ---
vector<int> readVectorInt(){
    int n; if(!(cin>>n)) n=0;
    vector<int> v(n);
    for(int i=0;i<n;++i) cin>>v[i];
    return v;
}
vector<vector<int>> readMatrixInt(){
    int m,n; cin>>m>>n;
    vector<vector<int>> a(m, vector<int>(n));
    for(int i=0;i<m;++i) for(int j=0;j<n;++j) cin>>a[i][j];
    return a;
}
"""

PRINTERS = r"""
// --- Printers (JSON-like) ---
template <typename T> void printScalar(const T& x){ cout << x; }
void printScalar(const bool& b){ cout << (b ? "true" : "false"); }
void printScalar(const string& s){ cout << '"' << s << '"'; }

template <typename T> void printAny(const T& x){ printScalar(x); }
template <typename T>
void printAny(const vector<T>& v){
    cout << "[";
    for(size_t i=0;i<v.size();++i){
        printAny(v[i]);
        if(i+1<v.size()) cout << ",";
    }
    cout << "]";
}
"""

def param_decl(p: Dict[str, str]) -> str:
    t = re.sub(r"\s+", "", p["type"])
    name = p["name"] or "arg"
    if t in ("vector<vector<int>>", "vector<vector<int> >"):
        return f"auto {name} = readMatrixInt();"
    if t == "vector<int>":
        return f"auto {name} = readVectorInt();"
    if t == "int":
        return f"int {name}; cin >> {name};"
    if t == "double":
        return f"double {name}; cin >> {name};"
    if t == "bool":
        return f"int __b; cin >> __b; bool {name} = (__b!=0);"
    if t == "string":
        return f"string {name}; cin >> {name};"
    if re.search(r"vector\s*<\s*vector\s*<\s*int\s*>\s*>\s*", p["type"]):
        return f"auto {name} = readMatrixInt();"
    if re.search(r"vector\s*<\s*int\s*>\s*", p["type"]):
        return f"auto {name} = readVectorInt();"
    return f"/* TODO: unsupported param type: {p['type']} {name} */"

def arg_list(params: List[Dict[str,str]]) -> str:
    return ", ".join([(p["name"] or "").strip() for p in params])

def main_from_template(func_name: str, tpl: str) -> str:
    if tpl == "matrixInt":
        return f"""
int main(){{
    ios::sync_with_stdio(false); cin.tie(nullptr);
    auto a = readMatrixInt();
    Solution sol;
    auto out = sol.{func_name}(a);
    printAny(out); cout << "\\n";
    return 0;
}}"""
    if tpl == "vecInt":
        return f"""
int main(){{
    ios::sync_with_stdio(false); cin.tie(nullptr);
    auto v = readVectorInt();
    Solution sol;
    auto out = sol.{func_name}(v);
    printAny(out); cout << "\\n";
    return 0;
}}"""
    if tpl == "singleInt":
        return f"""
int main(){{
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int x; cin >> x;
    Solution sol;
    auto out = sol.{func_name}(x);
    printAny(out); cout << "\\n";
    return 0;
}}"""
    if tpl == "singleDouble":
        return f"""
int main(){{
    ios::sync_with_stdio(false); cin.tie(nullptr);
    double x; cin >> x;
    Solution sol;
    auto out = sol.{func_name}(x);
    printAny(out); cout << "\\n";
    return 0;
}}"""
    if tpl == "singleString":
        return f"""
int main(){{
    ios::sync_with_stdio(false); cin.tie(nullptr);
    string s; cin >> s;
    Solution sol;
    auto out = sol.{func_name}(s);
    printAny(out); cout << "\\n";
    return 0;
}}"""
    if tpl == "singleLineString":
        return f"""
int main(){{
    ios::sync_with_stdio(false); cin.tie(nullptr);
    string s; getline(cin, s); if(s.empty()) getline(cin, s);
    Solution sol;
    auto out = sol.{func_name}(s);
    printAny(out); cout << "\\n";
    return 0;
}}"""
    if tpl == "bool01":
        return f"""
int main(){{
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int b; cin >> b; bool x = (b!=0);
    Solution sol;
    auto out = sol.{func_name}(x);
    printAny(out); cout << "\\n";
    return 0;
}}"""
    return f"""
int main(){{
    ios::sync_with_stdio(false); cin.tie(nullptr);
    auto a = readMatrixInt();
    Solution sol;
    auto out = sol.{func_name}(a);
    printAny(out); cout << "\\n";
    return 0;
}}"""

def build_code(user_code: str, io_template: str) -> Dict[str, Any]:
    sig = detect_signature(user_code or "")
    template_used = io_template

    if not sig:
        code = f"""{INCLUDES}
{READERS}
{PRINTERS}

{user_code.strip()}

{main_from_template("solve", "matrixInt")}
"""
        return {"generated_code": code.strip(), "signature": None, "template_used": "matrixInt"}

    func = sig["name"]; params = sig["params"]

    if io_template == "auto":
        tpl = "matrixInt"
        if params:
            t0 = re.sub(r"\s+", "", params[0]["type"])
            if t0 in ("vector<vector<int>>", "vector<vector<int> >"): tpl = "matrixInt"
            elif t0 == "vector<int>": tpl = "vecInt"
            elif t0 == "int": tpl = "singleInt"
            elif t0 == "double": tpl = "singleDouble"
            elif t0 == "string": tpl = "singleString"
            elif t0 == "bool": tpl = "bool01"
        template_used = tpl

    if template_used != "auto":
        main_block = main_from_template(func, template_used)
    else:
        decls = "\n    ".join(param_decl(p) for p in params) or "/* no params */"
        args = arg_list(params)
        main_block = f"""
int main(){{
    ios::sync_with_stdio(false); cin.tie(nullptr);

    {decls}

    Solution sol;
    auto out = sol.{func}({args});
    printAny(out); cout << "\\n";
    return 0;
}}"""

    full = f"""{INCLUDES}
{READERS}
{PRINTERS}

{user_code.strip()}

{main_block}
"""
    pretty_sig = f"{sig['ret']} {sig['name']}(" + ", ".join(f"{p['type']} {p['name']}".strip() for p in params) + ")"
    return {"generated_code": full.strip(), "signature": pretty_sig, "template_used": template_used}

@router.post("/generate")
async def generate(request: Request):
    data = await request.json()
    code = data.get("code", "")
    io_template = data.get("ioTemplate", "auto")
    try:
        return JSONResponse(build_code(code, io_template))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
