"""Reloj de reproducción independiente del tiempo de dominio."""
import asyncio
from datetime import datetime


class ReplayClock:
    def __init__(self, mode, rate, burst_size, burst_interval, historical_speed):
        if mode not in {'constant', 'burst', 'historical', 'unlimited'}:
            raise ValueError('Modo desconocido')
        if rate <= 0 or burst_size <= 0 or burst_interval < 0 or historical_speed <= 0:
            raise ValueError('Parámetros de reproducción inválidos')
        self.mode, self.rate = mode, rate
        self.burst_size, self.burst_interval = burst_size, burst_interval
        self.historical_speed = historical_speed
        self.started = None
        self.first_event = None

    async def wait(self, index, event_time):
        loop = asyncio.get_running_loop()
        current = datetime.fromisoformat(event_time.replace('Z', '+00:00')).timestamp()
        if self.started is None:
            self.started, self.first_event = loop.time(), current
        if self.mode == 'constant':
            target = index / self.rate
        elif self.mode == 'burst':
            target = (index // self.burst_size) * self.burst_interval
        elif self.mode == 'historical':
            target = (current - self.first_event) / self.historical_speed
        else:
            return
        await asyncio.sleep(max(0, self.started + target - loop.time()))
