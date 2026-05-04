code = "value = 41 + 1"
exec code

globals_ns = {}
exec code in globals_ns


def run_with_scope(code_text, g, l):
    exec code_text in g, l
    return l


locals_ns = {}
run_with_scope("answer = 42", globals_ns, locals_ns)