"""FIFO acotada: put espera cuando no hay capacidad (contrapresión)."""
import asyncio


class BoundedFIFO(asyncio.Queue):
    def __init__(self, capacity):
        if capacity <= 0:
            raise ValueError('La capacidad debe ser positiva')
        super().__init__(maxsize=capacity)
        self.peak_size = 0
        self.blocked_puts = 0

    async def put(self, item):
        if self.full():
            self.blocked_puts += 1
        await super().put(item)
        self.peak_size = max(self.peak_size, self.qsize())
