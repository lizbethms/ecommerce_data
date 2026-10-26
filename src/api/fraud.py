"""Arranque: uvicorn src.api.fraud:create_app --factory --workers 1."""
from contextlib import asynccontextmanager
import json
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.service.fraud import FraudService, ConflictError
from src.service.history import PersistenceError


class EventRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    evento: dict


class EntityRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    motivo: str = Field(min_length=1)


def translate(result):
    signals = result['risk_signals']
    frequency = signals['frequency']
    statuses = {'processed': 'procesado', 'duplicate': 'duplicado',
                'not_applicable': 'no_aplica', 'outside_window': 'fuera_de_ventana'}
    return dict(evento_id=result['event_id'], estado=statuses[result['status']], senales_riesgo=dict(
        pertenencias=[dict(clave=m['key'], positivo_bloom=m['bloom_positive'],
                           verificado=m['verified'], falso_positivo=m['false_positive'])
                      for m in signals['memberships']],
        frecuencia=None if frequency is None else dict(
            clave=frequency['key'], inicio_ventana=frequency['window_start'], fin_ventana=frequency['window_end'],
            estimacion=frequency['estimate'], conteo_exacto=frequency['exact_count'],
            candidato=frequency['candidate'], verificado=frequency['verified'], contabilizado=frequency['counted']),
        decision='revisar' if signals['decision'] == 'review' else 'continuar',
        motivos=[{'flagged_entity': 'entidad_senalada', 'high_frequency': 'alta_frecuencia'}[r]
                 for r in signals['reasons']]))


def create_app(history_path=None, config=None):
    @asynccontextmanager
    async def lifespan(app):
        selected = config
        if selected is None and os.environ.get('FRAUDE_CONFIG'):
            with open(os.environ['FRAUDE_CONFIG'], encoding='utf-8') as stream:
                selected = json.load(stream)
        app.state.service = FraudService(history_path or os.environ.get('FRAUDE_HISTORIAL', 'data/fraude/historial.csv'), selected)
        try:
            yield
        finally:
            app.state.service.close()

    app = FastAPI(title='API de fraude — etapa 6', version='1.0.0', lifespan=lifespan)

    def call(action):
        try:
            return action()
        except ConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except PersistenceError as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.post('/fraude/eventos')
    def event(body: EventRequest):
        return call(lambda: translate(app.state.service.process(body.evento)))

    @app.put('/fraude/entidades/{tipo}/{identificador}')
    def put_entity(tipo: str, identificador: str, body: EntityRequest):
        return call(lambda: app.state.service.change_entity(tipo, identificador, body.motivo))

    @app.delete('/fraude/entidades/{tipo}/{identificador}')
    def delete_entity(tipo: str, identificador: str):
        return call(lambda: app.state.service.change_entity(tipo, identificador))

    @app.get('/fraude/entidades')
    def entities():
        return app.state.service.entities()

    @app.get('/fraude/metricas')
    def metrics():
        return app.state.service.metrics()

    @app.get('/fraude/salud')
    def health():
        if app.state.service.history.failed:
            raise HTTPException(503, 'Historial no disponible')
        return dict(estado='disponible', historial='recuperado')

    return app
