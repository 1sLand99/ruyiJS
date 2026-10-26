"""Sample owned browser process-tree CPU and working set without page instrumentation."""
import threading
import time

import psutil


class ProcessSample:
    def __init__(self, pid, interval=.025):
        self.root = psutil.Process(pid)
        self.interval = interval
        self.last_cpu = {}
        self.cpu_seconds = 0.0
        self.peak_rss = 0
        self.samples = 0
        self.errors = 0
        self.stop = threading.Event()

    def sample(self, initial=False):
        try:
            processes = [self.root, *self.root.children(recursive=True)]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self.errors += 1
            return
        rss = 0
        for process in processes:
            try:
                identity = process.pid, process.create_time()
                times = process.cpu_times()
                current = times.user + times.system
                previous = self.last_cpu.get(identity)
                if previous is not None:
                    self.cpu_seconds += max(0, current - previous)
                elif not initial:
                    self.cpu_seconds += current
                self.last_cpu[identity] = current
                rss += process.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                self.errors += 1
        self.peak_rss = max(self.peak_rss, rss)
        self.samples += 1

    def loop(self):
        while not self.stop.wait(self.interval):
            self.sample()

    def __enter__(self):
        self.sample(initial=True)
        self.started = time.perf_counter()
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=3)
        if self.thread.is_alive():
            raise RuntimeError('process sampler thread did not finish')
        self.sample()
        self.result = {'wall_ms': (time.perf_counter() - self.started) * 1000,
            'cpu_ms': self.cpu_seconds * 1000, 'peak_sum_rss_bytes': self.peak_rss,
            'samples': self.samples, 'sample_errors': self.errors}
