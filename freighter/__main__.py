from .cli import main

from functools import wraps
import numpy as np
import time

from .fileformats import GameCubeTexture, ImageFormat

iterations = 1


def timeit(func, iterations: int = iterations):
    iters = range(iterations)

    @wraps(func)
    def timeit_wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        for i in iters:
            result = func(*args, **kwargs)
        end_time = time.perf_counter()
        total_time = end_time - start_time
        print(f"Function {func.__name__}{args} {kwargs} Took {total_time:.4f} seconds")

    return timeit_wrapper


@timeit
def test1():
    texture = GameCubeTexture("test.png")
    texture.gpu_encode_test()


if __name__ is "__main__":
    # import cProfile
    # pr = cProfile.Profile()
    # pr.enable()
    main()
    # pr.disable()
    # pr.print_stats(sort='time')
