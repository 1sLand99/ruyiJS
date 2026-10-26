from ruyijs import Context


with Context() as context:
    context.eval("globalThis.answer = 40")
    print(context.eval("answer + 2"))
