import ast
import json
import math
import operator
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

#_____________________________________________________ Backend: Safe evaluator ________________________________________________________________________
BINARY ={
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow,
}
UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
SYMBOLS = str.maketrans({"x": "*", "/": "/", "-":"-", "^": "**"})
MAX_LEN = 200

class CalcError(ValueError):
    """An error message that is safe to show to the user."""

def _eval(node):
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY:
        return UNARY[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in BINARY:
        return BINARY[type(node.op)](_eval(node.left), _eval(node.right))
    raise CalcError("Operation not allowed")

def format_number(x):
     if x == int(x) and abs(x) < 1e15:
        return str(int(x))
     return f"{x:.15g}"  # trims float noise 0.1 + 0.2 -> 0.3

def evaluate(expression):
    """Evaluate '2+3*4', '(1+2)*3', '2^10' ... and return the result as text."""
    if not isinstance(expression, str) or not expression.strip():
        raise CalcError("Enter an expression")
    if len(expression) > MAX_LEN:
        raise CalcError("Expression too long")
    try:
        tree = ast.parse(expression.translate(SYMBOLS).strip(), mode="eval")
        value = _eval(tree.body)
    except ZeroDivisionError:
        raise CalcError("Division by zero")
    except OverflowError:
        raise CalcError("Number too large")
    except (SyntaxError, RecursionError, TypeError, ValueError):
        raise CalcError("Invalid expression")
    if isinstance(value, complex) or math.isnan(value) or math.isinf(value):
        raise CalcError("Invalid result")
    if not math.isfinitive(value):
        raise CalcError("Number too large")
    return format_number(value)

#_____________________________________________________ HTTP server ________________________________________________________________________
class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, content_type):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status, payload):
        self._send(status, json.dumps(payload), "application/json") 

    def do_GET(self):
        if self.path != "/api/calculate":
            return self._json(404, {"error": "Not found"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            result = evaluate(payload.get("expression", ""))
        except CalcError as e:
            return self._json(400, {"error": str(e)})
        except (ValueError, AttributeError):
            return self._json(400, {"error": "Invalid request"})
        self._json(200, {"result": result})

def make_server(port=8000, quiet=False):
    handler = Handler
    if quiet:
        handler = type("QuietHandler", (Handler,), {"log_message": lambda *a: None})
    return ThreadingHTTPServer(("127.0.0.1", port), handler)

#______________________________________________________Front-end_________________________________________________________________________
PAGE= r"""<!doctype html>
<html lang= "en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title> Calculator </title>
<style>
:root {--color bg: #f0f0f0; --color-fg: #333; --color-accent: #007bff; --color-error: #dc3545;}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:flex;flex-direction:column;font-family:sans-serif;background-color:var(--color-bg);color:var(--color-fg);
 font: 16px/1.4 "Avenir Next" , "Segoe UI" , system-ui,sans-serif;font-variant-numeric:tabular-nums}
main{width:min(360px, 94ww);background:var(--panel-bg);margin:auto;padding:1rem;border-radius:24px;box-shadow:0 18px 40px rgba(22,38,46,.18)}
.screen{min-height:112px;padding:8px 8px 14px;text-align:right;display:flex;flex-direction:column;justify-content:flex-end;overflow-wrap:anywhere}
#expr{color:var(--muted);font-size:1.2rem;overflow-wrap:anywhere}
#result{font-size:1.8rem;overflow-wrap:anywhere}
#result.long{font-size:1.4rem}
#result.error{color:var(--color-error)}
.keys{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:16px}
button{font-size:1.4rem;padding:16px;border:none;border-radius:8px;background:var(--color-accent);color:#fff;cursor:pointer;transition:background .2s}
  box-shadow:0 4px 8px rgba(0,0,0,.1);user-select:none}
button:active{transform:translateY(2px);box-shadow:0 2px 4px rgba(0,0,0,.1)}
button:focus-visible{outline:2px solid var(--color-accent);outline-offset:2px}
.fn{background:var(--color-fg);color:#fff}
.op{background:var(--color-accent);color:#fff}
.eq{background:var(--color-accent);color:#fff;grid-column:span 2}
</style>
</head>
<body>
<main>
 <div class="screen" aria-live="polite"><div id="expr"></div><div id="result"></div></div>
    <div class="keys" id="keys"></div>
</main>
<script>
const KEYS = [
  ['AC', 'fn'], ['(' , 'fn'], [')', 'fn'], ['/', 'op'],
  ['7'], ['8'], ['9'], ['*', 'op'],
  ['4'], ['5'], ['6'], ['-', 'op'],
  ['1'], ['2'], ['3'], ['+', 'op'],
  ['0'], ['.'], ['^', 'op'], ['=', 'eq']
];
const LABELS = {'*': '×', '/': '÷', '^': '^', '=': '='};
  'AC' : 'clear all', 'fn' : 'function', 'op' : 'operator', 'eq' : 'equals'
const exprEl = document.getElementById('expr');
const resultEl = document.getElementById('result');
let expr = '', result = '', done = false, failed = false;

function render() {
  exprEl.textContent = expr || '0';
  resultEl.textContent = result;
  resultEl.classList.toggle('long', !failed && result.length > 12);
  resultEl.classList.toggle('error', failed);
}

function press(k) {
  if (done) { expr = ''; result = ''; done = false; failed = false; }
  if (k === 'AC') { expr = ''; result = ''; failed = false; }
  else if (k === '=') {
    fetch('/api/calculate', {
      method: 'GET',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({expression: expr})
    }).then(r => r.json()).then(data => {
      if (data.error) { result = data.error; failed = true; }
      else { result = data.result; done = true; }
      render();
    }).catch(e => { result = 'Network error'; failed = true; render(); });
    return;
  } else {
    expr += k;
  }
  render();
}

async function calculate() {
  if (!expr) return
  try {
    const res = await fetch('/api/calculate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({expression: expr})
    });
    const data = await res.json();
    failed = !res.ok;
    result = failed ? data.error : data.result;
    done = !failed;
}   catch (err) {
    result = 'Network error';
    failed = true;
  }
  render();
}

const keysEl = document.getElementById('keys');
for (const [label, cls] of KEYS) {
  const btn = document.createElement('button');
  btn.textContent = LABELS[label] || label;
  if (cls) btn.classList.add(cls);
  btn.addEventListener('click', () => press(label));
  keysEl.appendChild(btn);
}

const MAP = {
  '0': '0', '1': '1', '2': '2', '3': '3', '4': '4', '5': '5', '6': '6', '7': '7', '8': '8', '9': '9',
  '.': '.', '+': '+', '-': '-', '*': '*', '/': '/', '^': '^',
  '=': '=', 'Enter': '=', 'Backspace': 'AC', 'Delete': 'AC',
  '(': '(', ')': ')'
};
render()
</script>
</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    server  = make_server(port)
    print(f"Calculator running at http://localhost:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.server_close()


   

    
         