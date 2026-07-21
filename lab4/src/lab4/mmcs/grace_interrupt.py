import signal
import warnings
from functools import wraps


def delay_interrupt(func):
    """Decorator to delay KeyboardInterrupt until the function finishes.

    with overhead of ~10 microseconds per function call.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        original_handler = signal.getsignal(signal.SIGINT)
        interrupt_signal_caught = False

        def signal_handler(sig, frame):
            warnings.warn(
                "KeyboardInterrupt caught, exiting gracefully after function finishes..."
            )
            nonlocal interrupt_signal_caught
            interrupt_signal_caught = True

        signal.signal(signal.SIGINT, signal_handler)
        try:
            ret = func(*args, **kwargs)
            signal.signal(signal.SIGINT, original_handler)
            if interrupt_signal_caught:
                raise KeyboardInterrupt
            else:
                return ret
        finally:
            signal.signal(signal.SIGINT, original_handler)

    return wrapper


if __name__ == "__main__":
    import time

    @delay_interrupt
    def my_function():
        print("Function is running...")
        time.sleep(1)
        print("Function finished.")

    for _ in range(3):
        my_function()

    print("Protected iteration ends. Now running unprotected iteration...")

    for i in range(3):
        print(f"Running iteration {i}...")
        time.sleep(1)
        print(f"Finish iteration {i}")

    # # Test the overhead of the decorator
    # @interruptible
    # def return_two():
    #     return 2

    # from viztracer import VizTracer
    # with VizTracer(output_file="optional.json") as tracer:
    #     for i in range(3):
    #         return_two()


class InterruptHandler:
    """Context manager to handle KeyboardInterrupt gracefully.

    Usage:
    ```
    with InterruptHandler() as handler:
        for i in range(10):
            if handler.interrupt_signal_caught:
                raise KeyboardInterrupt
            print(f"Running iteration {i}...")
            time.sleep(1)
            print(f"Finish iteration {i}")
    ```
    """

    def __init__(self):
        self.interrupt_signal_caught = False
        self.original_handler = None

    def __enter__(self):
        self.interrupt_signal_caught = False
        self.original_handler = signal.getsignal(signal.SIGINT)

        def signal_handler(sig, frame):
            print("KeyboardInterrupt caught, will handle after current operation...")
            self.interrupt_signal_caught = True

        signal.signal(signal.SIGINT, signal_handler)
        return self

    def __exit__(self, exc_type, exc_val, traceback):
        signal.signal(signal.SIGINT, self.original_handler)


if __name__ == "__main__":
    import time

    with InterruptHandler() as handler:
        for i in range(3):
            if handler.interrupt_signal_caught:
                raise KeyboardInterrupt
            print(f"Running protected iteration {i}...")
            time.sleep(1)
            print(f"Finish protected iteration {i}")

    print("Protected iteration ends. Now running unprotected iteration...")

    for i in range(3):
        print(f"Running iteration {i}...")
        time.sleep(1)
        print(f"Finish iteration {i}")
