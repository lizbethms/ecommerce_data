"""Modelos de entrada: reflejan el esquema de events.parquet.

Los campos son opcionales a propósito: la validación de negocio la hace
ServicioIngesta, que devuelve un rechazo observable con su motivo en lugar de
un error 422 genérico.
"""
from pydantic import BaseModel, ConfigDict, Field


class EventoIn(BaseModel):
    model_config = ConfigDict(extra='allow', json_schema_extra={'example': {
        'event_id': 'demo:event:1', 'event_time': '2019-10-01T08:00:00Z', 'event_type': 'purchase',
        'user_id': 'demo:user:1', 'user_session': 'demo:session:1', 'product_id': '1004856',
        'category_id': '2053013555631882655', 'category_code': 'electronics.smartphone',
        'brand': 'samsung', 'price': '130.76', 'order_id': 'demo:order:1', 'quantity': 1,
        'delivery_type': 'express'}})

    event_id: str | None = None
    schema_version: str | None = '1.0'
    event_time: str | None = None
    ingested_at: str | None = None
    event_type: str | None = None
    event_origin: str | None = None
    source_row_id: int | None = None
    generation_run_id: str | None = None
    synthetic_fields: list[str] = Field(default_factory=list)
    user_id: str | int | None = None
    user_session: str | None = None
    product_id: str | int | None = None
    category_id: str | int | None = None
    category_code: str | None = None
    brand: str | None = None
    price: str | float | int | None = None
    order_id: str | None = None
    quantity: int | None = None
    delivery_type: str | None = None
    scheduled_at: str | None = None
    priority: int | None = None
    priority_reason: str | None = None
    payment_attempt_id: str | None = None
    payment_method_id: str | None = None
    device_id: str | None = None
    payment_status: str | None = None
    query: str | None = None
    rating: int | None = None
    original_purchase_event_id: str | None = None
    scenario_id: str | None = None
    is_injected_duplicate: bool = False
    is_injected_anomaly: bool = False
    quality_flags: list[str] = Field(default_factory=list)


class ConsultaFraude(BaseModel):
    user_id: str | None = None
    device_id: str | None = None
    payment_method_id: str | None = None
    event_time: str | None = Field(None, description='ISO UTC; por defecto, el último tiempo observado')
