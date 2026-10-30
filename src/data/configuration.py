"""Perfiles y presupuestos de preparación; las fracciones usan redondeo half-up."""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
import math
import re


SYNTHETIC_DEFAULTS = {
    'fraction': 0.20,
    'scenario_weights': {'shopping': 0.60, 'browsing': 0.35, 'fraud_burst': 0.05},
    'basket_size': [2, 4], 'p_return': 0.08, 'p_review': 0.30,
    'resend_fraction': 0.005, 'include_controlled': True,
    'n_flagged': 5, 'users_per_event': 0.05,
    'catalog_limit': 10000, 'catalog_source_rows': 10000,
}


def parse_size(value):
    match = re.fullmatch(r'([1-9][0-9]*)([KM]?)', str(value).upper())
    if not match:
        raise ValueError('size debe ser un entero positivo o un tamaño como 1K, 100K o 10M')
    return int(match[1]) * {'': 1, 'K': 1000, 'M': 1000000}[match[2]]


def merge(base, overrides):
    result = deepcopy(base)
    for key, value in overrides.items():
        result[key] = merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else deepcopy(value)
    return result


def resolve_profile(config, profile=None):
    profiles = config.get('profiles', {})
    resolved = {key: deepcopy(value) for key, value in config.items() if key != 'profiles'}
    if profile is not None:
        if profile not in profiles:
            raise ValueError(f'Perfil desconocido: {profile}; disponibles: {", ".join(profiles)}')
        resolved = merge(resolved, profiles[profile])
        resolved['profile'] = profile
        if 'size' not in resolved:
            raise ValueError(f'El perfil {profile} requiere size')
        resolved['size'] = parse_size(resolved['size'])
    return resolved


def portion(total, fraction):
    return int((Decimal(total) * Decimal(str(fraction))).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _integer(value, name, minimum=1):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f'{name} debe ser un entero >= {minimum}')


def normalize_synthetic(config):
    """Acepta el modo por presupuesto o la configuración histórica por escenarios."""
    budgeted = 'fraction' in config
    allowed = set(SYNTHETIC_DEFAULTS) if budgeted else {
        'n_orders', 'n_browse_sessions', 'n_fraud_bursts', 'n_flagged', 'n_resends',
        'p_return', 'p_review', 'basket_size', 'catalog_limit',
    }
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(f'Configuración synthetic desconocida: {sorted(unknown)}')
    result = merge(SYNTHETIC_DEFAULTS, config) if budgeted else merge(
        {'basket_size': [2, 4], 'catalog_limit': 10000}, config)
    for name in ('p_return', 'p_review') + (('fraction', 'resend_fraction', 'users_per_event') if budgeted else ()):
        value = result.get(name)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f'{name} debe estar entre 0 y 1')
    _integer(result.get('n_flagged'), 'n_flagged')
    _integer(result['catalog_limit'], 'catalog_limit')
    basket = result['basket_size']
    if not isinstance(basket, (list, tuple)) or len(basket) != 2:
        raise ValueError('basket_size debe contener [mínimo, máximo]')
    for value in basket:
        _integer(value, 'basket_size')
    if not basket[0] <= basket[1] <= 100:
        raise ValueError('basket_size requiere mínimo <= máximo <= 100')
    if budgeted:
        _integer(result['catalog_source_rows'], 'catalog_source_rows')
        if not isinstance(result['include_controlled'], bool):
            raise ValueError('include_controlled debe ser booleano')
        weights = result['scenario_weights']
        if not isinstance(weights, dict) or set(weights) != {'shopping', 'browsing', 'fraud_burst'}:
            raise ValueError('scenario_weights requiere shopping, browsing y fraud_burst')
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in weights.values()) or not 0 < sum(weights.values()) < math.inf:
            raise ValueError('Los pesos deben ser finitos, no negativos y sumar más de cero')
    else:
        for name in ('n_orders', 'n_browse_sessions', 'n_fraud_bursts', 'n_resends'):
            _integer(result.get(name), name, 0)
    return result


def event_budget(size, synthetic, controlled_size):
    if size is None:
        raise ValueError('synthetic.fraction requiere --size o --profile; no admite --all-source/sample')
    _integer(size, 'size')
    total = portion(size, synthetic['fraction'])
    controlled = controlled_size if synthetic['include_controlled'] else 0
    resends = portion(total, synthetic['resend_fraction'])
    dynamic = total - controlled
    if dynamic < 0 or resends > max(0, dynamic - 1):
        raise ValueError('Presupuesto sintético insuficiente para escenarios controlados y reenvíos; ajuste las fracciones o include_controlled')
    return {'total': size, 'real': size - total, 'synthetic': total,
            'controlled': controlled, 'dynamic': dynamic,
            'dynamic_originals': dynamic - resends, 'dynamic_resends': resends}
