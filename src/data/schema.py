"""Contrato serializable: IDs como texto y dinero como decimal textual."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib

SOURCE_COLUMNS = ('event_time', 'event_type', 'product_id', 'category_id',
                  'category_code', 'brand', 'price', 'user_id', 'user_session')
TYPES = {'view', 'cart', 'purchase', 'payment_attempt', 'return', 'review', 'search'}


def utc(value):
    parsed = datetime.fromisoformat(value.replace(' UTC', '+00:00').replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Fecha sin zona horaria')
    return parsed.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def stable_id(*parts):
    return hashlib.sha256('\x1f'.join(map(str, parts)).encode()).hexdigest()


def money(value):
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError):
        raise ValueError('Precio no convertible') from None
    if not amount.is_finite() or amount < 0 or amount != amount.quantize(Decimal('0.01')):
        raise ValueError('Precio negativo, no finito o con más de dos decimales')
    return format(amount, '.2f')


def validate(event):
    if event['event_type'] not in TYPES:
        raise ValueError('Tipo de evento desconocido')
    utc(event['event_time'])
    if not event['event_id'] or not event['user_id'] or not event['user_session']:
        raise ValueError('Identidad incompleta')
    if event['event_type'] != 'search' and not event.get('product_id'):
        raise ValueError('Producto requerido')
    if event.get('price') is not None:
        money(event['price'])
    if event['event_type'] in {'purchase', 'return'}:
        if not event.get('order_id') or event.get('quantity', 0) <= 0:
            raise ValueError('Orden y cantidad positiva requeridas')
    if event['event_type'] == 'return' and not event.get('original_purchase_event_id'):
        raise ValueError('Referencia de compra requerida')
    if event['event_type'] == 'payment_attempt':
        if any(not event.get(k) for k in ('order_id', 'payment_attempt_id', 'payment_method_id', 'device_id', 'payment_status')):
            raise ValueError('Pago incompleto')
    if event['event_type'] == 'search' and not event.get('query'):
        raise ValueError('Consulta requerida')
    if event['event_type'] == 'review' and not 1 <= event.get('rating', 0) <= 5:
        raise ValueError('Puntuación inválida')
    if event.get('delivery_type') == 'scheduled':
        if not event.get('scheduled_at') or utc(event['scheduled_at']) < event['event_time']:
            raise ValueError('Entrega programada incoherente')
