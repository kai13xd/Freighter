import io
import pstats
import cProfile
from pstats import SortKey
from ansicolor import *

ITERATIONS = 100
TESTSTRING = "This is a test string."


def test():
    for i in range(ITERATIONS):
        print(ansi_format(TESTSTRING, AnsiTrueColor(1.0, 0.0, 0.0), AnsiBackground.NONE,
              AnsiAttribute.UNDERLINE, AnsiAttribute.ITALIC, AnsiAttribute.BOLD))


if __name__ == "__main__":
    s = io.StringIO()
    pr = cProfile.Profile()
    pr.enable()
    test()
    pr.disable()
    pstats.Stats(pr, stream=s).sort_stats(SortKey.CUMULATIVE).print_stats()
    print(s.getvalue())
