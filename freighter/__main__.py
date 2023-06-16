from freighter.main import main
import time
from functools import wraps
from freighter.fileformats import GameCubeTexture, ImageFormat


iterations = 10000


def timeit(func):
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


# @timeit
# def test1():
#     texture = GameCubeTexture("test.png")
#     texture.gpu_encode_test()


if __name__ == "__main__":
    # import cProfile

    # pr = cProfile.Profile()
    # pr.enable()
    main()
    # pr.disable()
    # pr.print_stats(sort="cumtime")
