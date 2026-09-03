#!/usr/bin/env python3
"""Atualiza as ofertas embutidas no dashboard a partir da API RSI."""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests


DASHBOARD = next(Path('.').glob('*.html'), None)
SEED_PATTERN = re.compile(r'(<script>const SEED=)(.*?)(;</script>)', re.DOTALL)
REQUIRED_FIELDS = ('ib', 'c', 'op', 'price', 'speed', 'src')


def fail(message):
    print(f'Erro: {message}', file=sys.stderr)
    raise SystemExit(1)


def fetch_offers(api_url):
    endpoint = urljoin(api_url.rstrip('/') + '/', 'ofertas.json')
    try:
        response = requests.get(
            endpoint,
            headers={'Accept': 'application/json'},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        fail(f'falha ao consultar {endpoint}: {exc}')
    except ValueError as exc:
        fail(f'{endpoint} não retornou JSON válido: {exc}')

    offers = payload.get('offers') if isinstance(payload, dict) else None
    if not isinstance(offers, list) or not offers:
        fail('payload inválido: o campo offers deve ser uma lista não vazia')

    for index, offer in enumerate(offers, start=1):
        if not isinstance(offer, dict):
            fail(f'oferta {index} não é um objeto JSON')
        missing = [field for field in REQUIRED_FIELDS if offer.get(field) in (None, '')]
        if missing:
            fail(f'oferta {index} sem campos obrigatórios: {", ".join(missing)}')
        try:
            if float(offer['price']) <= 0 or float(offer['speed']) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            fail(f'oferta {index} tem preço ou velocidade inválidos')

    return offers, payload.get('meta', {}) if isinstance(payload, dict) else {}


def update_dashboard(offers, api_meta):
    if DASHBOARD is None:
        fail('nenhum dashboard HTML encontrado na raiz do repositório')

    original = DASHBOARD.read_text(encoding='utf-8')
    match = SEED_PATTERN.search(original)
    if not match:
        fail('não foi possível localizar const SEED no dashboard')

    try:
        seed = json.loads(match.group(2))
    except json.JSONDecodeError as exc:
        fail(f'const SEED não contém JSON válido: {exc}')

    if not isinstance(seed, dict) or not all(seed.get(key) for key in ('cities', 'leaders')):
        fail('carga SEED incompleta: cities e leaders são obrigatórios')

    seed['offers'] = offers
    seed.setdefault('meta', {})['updated'] = datetime.now(timezone.utc).isoformat()
    if isinstance(api_meta, dict):
        for key in ('environment', 'coverage'):
            if key in api_meta:
                seed['meta'][f'live{key.title()}'] = api_meta[key]

    replacement = match.group(1) + json.dumps(seed, ensure_ascii=False, separators=(',', ':')) + match.group(3)
    updated = original[:match.start()] + replacement + original[match.end():]
    if updated == original:
        print('Nenhuma alteração necessária.')
        return

    temporary = DASHBOARD.with_suffix(DASHBOARD.suffix + '.tmp')
    temporary.write_text(updated, encoding='utf-8')
    temporary.replace(DASHBOARD)
    print(f'{len(offers)} ofertas atualizadas em {DASHBOARD}')


def main():
    api_url = os.environ.get('RSI_API_URL', '').strip()
    if not api_url:
        fail('RSI_API_URL não configurada')
    offers, api_meta = fetch_offers(api_url)
    update_dashboard(offers, api_meta)


if __name__ == '__main__':
    main()
