"""
Latency Simulator
-----------------
Models round-trip latency from order submission to exchange acknowledgement.
Uses a log-normal distribution to mimic realistic network/exchange jitter.
"""
import asyncio
import math
import random
from dataclasses import dataclass


@dataclass
class LatencyConfig:
    base_us: int = 500          # median latency in microseconds
    jitter_us: int = 200        # std-dev of Gaussian jitter
    tail_probability: float = 0.01   # P(experiencing a tail-latency spike)
    tail_multiplier: float = 10.0    # spike = base * multiplier


class LatencySimulator:
    def __init__(self, config: LatencyConfig | None = None) -> None:
        self.config = config or LatencyConfig()

    def sample_us(self) -> int:
        """Draw a latency sample in microseconds."""
        if random.random() < self.config.tail_probability:
            # Tail spike
            latency = self.config.base_us * self.config.tail_multiplier
        else:
            latency = max(1, random.gauss(self.config.base_us, self.config.jitter_us))
        return int(latency)

    async def delay(self) -> int:
        """Sleep for the sampled latency and return the actual delay in µs."""
        latency_us = self.sample_us()
        await asyncio.sleep(latency_us / 1_000_000)
        return latency_us
