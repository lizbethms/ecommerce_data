"""Descripción de la máquina que ejecuta una medición (la rúbrica exige reportar la plataforma)."""
import os
import platform
import subprocess
import sys


def _procesador():
    try:
        if sys.platform == 'win32':
            import winreg
            clave = r'HARDWARE\DESCRIPTION\System\CentralProcessor\0'
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, clave) as registro:
                return winreg.QueryValueEx(registro, 'ProcessorNameString')[0].strip()
        if sys.platform == 'darwin':
            return subprocess.run(['sysctl', '-n', 'machdep.cpu.brand_string'],
                                  capture_output=True, text=True, timeout=5).stdout.strip()
        with open('/proc/cpuinfo', encoding='utf-8') as cpuinfo:
            for linea in cpuinfo:
                if linea.startswith('model name'):
                    return linea.split(':', 1)[1].strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return platform.processor() or None


def _ram_bytes():
    try:
        if sys.platform == 'win32':
            import ctypes

            class Estado(ctypes.Structure):
                _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                            ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                            ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                            ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                            ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
            estado = Estado(dwLength=ctypes.sizeof(Estado))
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(estado))
            return estado.ullTotalPhys
        if sys.platform == 'darwin':
            return int(subprocess.run(['sysctl', '-n', 'hw.memsize'],
                                      capture_output=True, text=True, timeout=5).stdout)
        return os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
    except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
        return None


def plataforma():
    return dict(sistema=platform.platform(), python=platform.python_version(),
                implementacion=platform.python_implementation(), procesador=_procesador(),
                nucleos_logicos=os.cpu_count(), ram_bytes=_ram_bytes())
