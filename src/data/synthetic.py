"""Escenarios sintéticos de demostración sobre el catálogo real de la muestra.

Genera sesiones completas (búsqueda → vistas → carrito → pago → compra →
devolución/reseña), órdenes de varios productos por "tema" de categoría,
cuentas/medios/dispositivos señalados, ráfagas de intentos de pago y reenvíos.
Todo usa el espacio ``syn:`` y una semilla fija. Se escribe una sesión por vez en
orden causal para que ``Writer.add`` mantenga pagos, inventario y devoluciones.
"""
import json
import random
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from itertools import accumulate

from .schema import stable_id, utc

SCENARIO_ID = 'demo-synthetic'
DELIVERIES = (('express', 0.25), ('standard', 0.5), ('scheduled', 0.25))
RATINGS = (1, 2, 3, 4, 5)
RATING_WEIGHTS = (0.05, 0.08, 0.17, 0.35, 0.35)


def _parse(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def _time(value):
    return utc(value.replace(microsecond=0).isoformat())


class Generator:
    def __init__(self, db, run, seed, start, end, cfg, envelope):
        self.db, self.run, self.cfg, self.envelope = db, run, cfg, envelope
        self.rng = random.Random(seed)
        self.start, self.end = _parse(start), _parse(end)
        self.events = []  # Solo la sesión actual; se vacía después de escribirla.
        self.counter = 0
        rows = db.execute('SELECT product_id, category_id, category_code, brand, last_observed_price '
                          'FROM catalog ORDER BY product_id LIMIT ?', (cfg['catalog_limit'],)).fetchall()
        if not rows:
            raise ValueError('La generación sintética requiere un catálogo no vacío')
        themes = defaultdict(list)
        for row in rows:
            if row[2]:
                themes[row[2].split('.')[0]].append(row)
        self.themes = {k: v for k, v in themes.items() if len(v) >= 4} or {'all': rows}
        for products in self.themes.values():
            self.rng.shuffle(products)  # el orden fija qué productos serán "populares"
        self.theme_names = sorted(self.themes)
        self.theme_weights = [len(self.themes[t]) for t in self.theme_names]
        self.product_weights = {name: list(accumulate(1 / (rank + 1) for rank in range(len(products))))
                                for name, products in self.themes.items()}
        self.summary = dict(events=0, by_type={}, flags=0, themes=len(self.themes),
                            catalog_products_loaded=len(rows), injected_anomalies=0,
                            injected_duplicates=0, scenarios={}, tail_events=0,
                            max_session_events=0, resend_selection='sqlite_with_replacement')
        self.types, self.scenarios = Counter(), Counter()
        self.candidates = 0

    def _id(self, *parts):
        return stable_id(self.run, SCENARIO_ID, *parts)[:16]

    def _event(self, kind, when, user, session, product=None, **fields):
        self.counter += 1
        event = self.envelope(self.run, 'syn:event:' + stable_id(self.run, SCENARIO_ID, self.counter),
                              _time(when), kind, 'synthetic', user, session, product[0] if product else None)
        if product:
            event.update(category_id=product[1], category_code=product[2], brand=product[3], price=product[4])
        event.update(scenario_id=SCENARIO_ID, **fields)
        self.events.append(event)
        return event

    def _pick(self, theme, n):
        products = self.themes[theme]
        chosen = []
        while len(chosen) < min(n, len(products)):
            product = self.rng.choices(products, cum_weights=self.product_weights[theme])[0]
            if product not in chosen:
                chosen.append(product)
        return chosen

    def _moment(self, margin_hours=1):
        span = max(1, int((self.end - self.start).total_seconds()) - margin_hours * 3600)
        return self.start + timedelta(seconds=self.rng.randrange(span))

    def _query(self, product):
        if product[2] and self.rng.random() < 0.7:
            return product[2].split('.')[-1].replace('_', ' ')
        return product[3] or (product[2] or 'producto').split('.')[0]

    def flags(self):
        n = self.cfg['n_flagged']
        for k in range(n):
            self.db.executemany('INSERT INTO flags VALUES (?, ?, ?)', (
                ('payment_method', f'syn:method:flagged:{k}', 'chargeback_history'),
                ('device', f'syn:device:flagged:{k}', 'emulator_fingerprint'),
                ('account', f'syn:user:fraud:{k}', 'reported_account')))
        return 3 * n

    def shopping(self, index, user):
        session = f'syn:session:{self._id("session", index)}'
        method = f'syn:method:{self._id("method", user)}'
        device = f'syn:device:{self._id("device", user)}'
        theme = self.rng.choices(self.theme_names, self.theme_weights)[0]
        basket = self._pick(theme, self.rng.randint(*self.cfg['basket_size']))
        when = self._moment()
        self._event('search', when, user, session, query=self._query(basket[0]))
        for product in basket + self._pick(theme, 2):
            when += timedelta(seconds=self.rng.randint(5, 90))
            self._event('view', when, user, session, product)
        for product in basket:
            when += timedelta(seconds=self.rng.randint(5, 60))
            self._event('cart', when, user, session, product)
        delivery = self.rng.choices([d for d, _ in DELIVERIES], [w for _, w in DELIVERIES])[0]
        order = f'syn:order:{self._id("order", index)}'
        scheduled = _time(when + timedelta(days=self.rng.randint(1, 5))) if delivery == 'scheduled' else None
        self.db.execute('INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)',
                        (order, user, session, delivery, scheduled, 'synthetic_session', 'synthetic'))
        priority = (10, 'express_delivery') if delivery == 'express' else (0, 'normal')
        common = dict(order_id=order, delivery_type=delivery, scheduled_at=scheduled,
                      priority=priority[0], priority_reason=priority[1])
        failures = self.rng.choices((0, 1, 2), (0.85, 0.1, 0.05))[0]
        for attempt in range(failures + 1):
            when += timedelta(seconds=self.rng.randint(10, 60))
            event = self._event('payment_attempt', when, user, session, basket[0], **common,
                                payment_attempt_id=f'syn:payment:{self._id("pay", index, attempt)}',
                                payment_method_id=method, device_id=device,
                                payment_status='failed' if attempt < failures else 'succeeded')
            if attempt < failures:
                event.update(priority=100, priority_reason='failed_payment')
        purchases = []
        for product in basket:
            when += timedelta(seconds=1)
            purchases.append(self._event('purchase', when, user, session, product, **common,
                                         quantity=self.rng.randint(1, 3)))
        for purchase in purchases:
            product = (purchase['product_id'], purchase['category_id'], purchase['category_code'],
                       purchase['brand'], purchase['price'])
            after = _parse(purchase['event_time'])
            if self.rng.random() < self.cfg['p_return']:
                self._event('return', after + timedelta(days=self.rng.randint(1, 3)), user, session, product,
                            order_id=order, quantity=self.rng.randint(1, purchase['quantity']),
                            original_purchase_event_id=purchase['event_id'])
            if self.rng.random() < self.cfg['p_review']:
                self._event('review', after + timedelta(days=self.rng.randint(2, 6)), user, session, product,
                            order_id=order, original_purchase_event_id=purchase['event_id'],
                            rating=self.rng.choices(RATINGS, RATING_WEIGHTS)[0])

    def browsing(self, index, user):
        session = f'syn:session:{self._id("browse", index)}'
        theme = self.rng.choices(self.theme_names, self.theme_weights)[0]
        products = self._pick(theme, self.rng.randint(2, 6))
        when = self._moment()
        self._event('search', when, user, session, query=self._query(products[0]))
        for product in products:
            when += timedelta(seconds=self.rng.randint(5, 120))
            self._event('view', when, user, session, product)
            if self.rng.random() < 0.15:
                self._event('cart', when + timedelta(seconds=3), user, session, product)

    def fraud_burst(self, index):
        """Ráfaga de intentos fallidos en ~2 minutos; algunos con señalados, otros solo intensidad."""
        n = self.cfg['n_flagged']
        user = f'syn:user:fraud:{index % n}' if index % 2 == 0 else f'syn:user:burst:{index}'
        session = f'syn:session:{self._id("fraud", index)}'
        method = f'syn:method:flagged:{index % n}' if index % 3 == 0 else f'syn:method:{self._id("fmethod", index)}'
        device = f'syn:device:flagged:{index % n}' if index % 3 == 1 else f'syn:device:{self._id("fdevice", index)}'
        theme = self.rng.choices(self.theme_names, self.theme_weights)[0]
        product = self._pick(theme, 1)[0]
        order = f'syn:order:{self._id("fraud-order", index)}'
        self.db.execute('INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)',
                        (order, user, session, 'express', None, 'synthetic_fraud_burst', 'synthetic'))
        when = self._moment()
        for attempt in range(self.rng.randint(6, 10)):
            when += timedelta(seconds=self.rng.randint(3, 15))
            self._event('payment_attempt', when, user, session, product, order_id=order,
                        delivery_type='express', payment_attempt_id=f'syn:payment:{self._id("fpay", index, attempt)}',
                        payment_method_id=method, device_id=device, payment_status='failed',
                        priority=100, priority_reason='failed_payment', is_injected_anomaly=True)

    def _flush(self, write):
        self.summary['max_session_events'] = max(self.summary['max_session_events'], len(self.events))
        for event in self.events:
            event['synthetic_fields'] = [k for k, v in event.items()
                                         if v is not None and k not in {'synthetic_fields', 'is_injected_duplicate'}]
            if event['price'] == '0.00':
                event['quality_flags'].append('zero_price_review')
            seq = write(event)
            if event['event_type'] in {'purchase', 'payment_attempt', 'view'}:
                self.candidates += 1
                self.db.execute('INSERT INTO synthetic_resend_candidates VALUES (?, ?)', (self.candidates, seq))
            self._count(event)
        self.events.clear()

    def _count(self, event):
        self.summary['events'] += 1
        self.types[event['event_type']] += 1
        self.summary['injected_anomalies'] += int(event['is_injected_anomaly'])
        self.summary['injected_duplicates'] += int(event['is_injected_duplicate'])

    def _session(self, kind, index, n_users):
        user = f'syn:user:{self._id("user", self.rng.randrange(n_users))}'
        if kind == 'fraud_burst':
            self.fraud_burst(index)
        else:
            getattr(self, kind)(index, user)

    def _tail(self, index, remaining):
        """Una sesión corta, completa y sin compras para cerrar el presupuesto."""
        user = f'syn:user:{self._id("tail-user", index)}'
        session = f'syn:session:{self._id("tail", index)}'
        theme = self.rng.choices(self.theme_names, self.theme_weights)[0]
        product = self._pick(theme, 1)[0]
        when = self._moment()
        if remaining > 1:
            self._event('search', when, user, session, query=self._query(product))
        for offset in range(1 if remaining > 1 else 0, remaining):
            self._event('view', when + timedelta(seconds=offset), user, session, product)
        self.summary['tail_events'] += remaining
        self.scenarios['tail_browsing'] += 1

    def build(self, write, chunk_size, budget=None):
        """Escribe sesiones acotadas. Los candidatos solo guardan seq en SQLite."""
        self.db.execute('CREATE TABLE synthetic_resend_candidates(id INTEGER PRIMARY KEY, event_seq INTEGER NOT NULL)')
        self.summary['flags'] = self.flags()
        last_commit = 0

        def checkpoint():
            nonlocal last_commit
            if self.summary['events'] - last_commit >= chunk_size:
                self.db.commit()
                last_commit = self.summary['events']

        if budget is None:
            n_users = max(1, self.cfg['n_orders'] // 2)
            for kind, key in (('shopping', 'n_orders'), ('browsing', 'n_browse_sessions'), ('fraud_burst', 'n_fraud_bursts')):
                for index in range(self.cfg[key]):
                    self._session(kind, index, n_users)
                    self.scenarios[kind] += 1
                    self._flush(write)
                    checkpoint()
            resends = min(self.cfg['n_resends'], self.candidates)
            self.summary['resend_selection'] = 'sqlite_without_replacement'
        else:
            target = budget['dynamic_originals']
            n_users = max(1, int(target * self.cfg['users_per_event']))
            kinds = ('shopping', 'browsing', 'fraud_burst')
            weights = [self.cfg['scenario_weights'][kind] for kind in kinds]
            index = 0
            while self.summary['events'] < target:
                remaining = target - self.summary['events']
                kind = self.rng.choices(kinds, weights)[0]
                # Las órdenes de una sesión que no cabe se deshacen antes de escribir eventos.
                self.db.execute('SAVEPOINT candidate_session')
                self._session(kind, index, n_users)
                self.summary['max_session_events'] = max(self.summary['max_session_events'], len(self.events))
                if len(self.events) > remaining:
                    self.db.execute('ROLLBACK TO candidate_session')
                    self.events.clear()
                    self._tail(index, remaining)
                else:
                    self.scenarios[kind] += 1
                self.db.execute('RELEASE candidate_session')
                self._flush(write)
                checkpoint()
                index += 1
            resends = budget['dynamic_resends']
        if resends and not self.candidates:
            raise ValueError('No hay eventos originales elegibles para reenvíos')
        candidate_count = self.candidates
        for _ in range(resends):
            chosen = self.rng.randint(1, candidate_count)
            payload = self.db.execute(
                'SELECT e.payload FROM synthetic_resend_candidates c JOIN events e ON e.seq=c.event_seq WHERE c.id=?',
                (chosen,)).fetchone()[0]
            event = json.loads(payload)
            event['is_injected_duplicate'] = True
            write(event)
            self._count(event)
            if budget is None:
                # Muestreo sin reemplazo, con índices densos, sin una lista en RAM.
                last = self.db.execute('SELECT event_seq FROM synthetic_resend_candidates WHERE id=?', (candidate_count,)).fetchone()[0]
                self.db.execute('UPDATE synthetic_resend_candidates SET event_seq=? WHERE id=?', (last, chosen))
                self.db.execute('DELETE FROM synthetic_resend_candidates WHERE id=?', (candidate_count,))
                candidate_count -= 1
            checkpoint()
        self.summary.update(by_type=dict(self.types), scenarios=dict(self.scenarios),
                            resend_candidates=self.candidates, user_pool_size=n_users)
        self.db.execute('DROP TABLE synthetic_resend_candidates')
        self.db.commit()
        return self.summary


def generate(db, run, seed, start, end, cfg, envelope, write, chunk_size, budget=None):
    return Generator(db, run, seed, start, end, cfg, envelope).build(write, chunk_size, budget)
