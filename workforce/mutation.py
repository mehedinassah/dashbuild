"""Mutation check: break the new code in small ways. If the tests still pass,
the tests are not really checking anything."""
import ast
import copy

SWAP_BIN = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Add, ast.Div: ast.Mult,
            ast.FloorDiv: ast.Mult, ast.Mod: ast.Mult}
SWAP_CMP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt,
            ast.Eq: ast.NotEq, ast.NotEq: ast.Eq}


class _Mutator(ast.NodeTransformer):
    def __init__(self, target):
        self.target, self.n, self.desc = target, 0, None

    def _hit(self, desc):
        hit = self.n == self.target
        self.n += 1
        if hit:
            self.desc = desc
        return hit

    def visit_BinOp(self, node):
        self.generic_visit(node)
        t = type(node.op)
        if t in SWAP_BIN and self._hit(f"line {node.lineno}: changed an arithmetic operator"):
            node.op = SWAP_BIN[t]()
        return node

    def visit_Compare(self, node):
        self.generic_visit(node)
        t = type(node.ops[0])
        if t in SWAP_CMP and self._hit(f"line {node.lineno}: changed a comparison"):
            node.ops[0] = SWAP_CMP[t]()
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        if self._hit(f"line {node.lineno}: swapped and/or"):
            node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        return node

    def visit_Constant(self, node):
        v = node.value
        if isinstance(v, bool):
            if self._hit(f"line {node.lineno}: flipped a True/False"):
                return ast.copy_location(ast.Constant(not v), node)
        elif isinstance(v, (int, float)):
            if self._hit(f"line {node.lineno}: changed the number {v}"):
                return ast.copy_location(ast.Constant(v + 1), node)
        return node

    def visit_UnaryOp(self, node):
        self.generic_visit(node)
        if isinstance(node.op, ast.Not) and self._hit(f"line {node.lineno}: removed a 'not'"):
            return node.operand
        return node

    def visit_Expr(self, node):
        self.generic_visit(node)
        if isinstance(node.value, ast.Call) and self._hit(
                f"line {node.lineno}: removed a statement that calls something (for example a save)"):
            return ast.copy_location(ast.Pass(), node)
        return node

    def visit_Return(self, node):
        self.generic_visit(node)
        if node.value is not None and not (isinstance(node.value, ast.Constant) and node.value.value is None):
            if self._hit(f"line {node.lineno}: made the function return None"):
                node.value = ast.Constant(None)
        return node


def _target(tree, name, class_name):
    body = tree.body
    if class_name:
        cls = next((n for n in body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
        if cls is None:
            return None
        body = cls.body
    return next((n for n in body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name == name), None)


def mutants(src, name, class_name=None, limit=8):
    """Return [(description, mutated_source)] for the named function."""
    tree = ast.parse(src)
    node = _target(tree, name, class_name)
    if node is None:
        return []
    counter = _Mutator(-1)
    counter.visit(copy.deepcopy(node))
    total = counter.n
    if total == 0:
        return []
    idxs = list(range(total))
    if total > limit:
        idxs = [round(i * (total - 1) / (limit - 1)) for i in range(limit)]
        idxs = sorted(set(idxs))
    out = []
    for i in idxs:
        t2 = copy.deepcopy(tree)
        m = _Mutator(i)
        m.visit(_target(t2, name, class_name))
        ast.fix_missing_locations(t2)
        out.append((m.desc, ast.unparse(t2) + "\n"))
    return out
