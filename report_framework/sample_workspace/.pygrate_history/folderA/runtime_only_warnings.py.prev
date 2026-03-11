from cStringIO import StringIO
from tokenize import tokenize


class Comparable(object):
    def __cmp__(self, other):
        return 1 - 1


def compare_pair(left, right):
    return cmp(left, right)


left = Comparable()
right = Comparable()
cmp_result = compare_pair(left, right)

handle = file("/tmp/report_framework_sample_warning.txt", "w")
handle.write("x")
handle.close()

token_stream = StringIO("x=1\n")
try:
    list(tokenize(token_stream.readline))
except TypeError:
    pass
