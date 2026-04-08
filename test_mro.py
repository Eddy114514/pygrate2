import sys


# Warns: classic lookup would find A.do_this before C.do_this,
# but hypothetical C3 would find C.do_this first.
class A:
    def do_this(self):
        return "A"


class B(A):
    pass


class C(A):
    def do_this(self):
        return "C"


class D(B, C):
    pass

sys.stdout.write("warns: %s\n" % D().do_this())


# Does not warn: classic order and C3 order differ, but both still resolve
# do_this to the same defining class because only SafeA provides it.
class SafeA:
    def do_this(self):
        return "SafeA"


class SafeB(SafeA):
    pass


class SafeC(SafeA):
    pass


class SafeD(SafeB, SafeC):
    pass

sys.stdout.write("safe: %s\n" % SafeD().do_this())
