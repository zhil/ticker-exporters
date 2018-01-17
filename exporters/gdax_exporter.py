#!/usr/bin/env python3

import logging
import time
import os
import yaml
import sys
import gdax
import requests
import json
from operator import itemgetter
from prometheus_client import write_to_textfile, start_http_server
from prometheus_client.core import REGISTRY, GaugeMetricFamily, CounterMetricFamily

log = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=os.environ.get("LOGLEVEL", "INFO"))

settings = {}


def _settings():
    global settings

    settings = {
        'gdax_exporter': {
            'prom_folder': '/var/lib/node_exporter',
            'interval': 60,
            'export': 'text',
            'listen_port': 9306,
        },
    }
    config_file = '/etc/gdax_exporter/gdax_exporter.yaml'
    cfg = {}
    if os.path.isfile(config_file):
        with open(config_file, 'r') as ymlfile:
            cfg = yaml.load(ymlfile)
    if cfg.get('gdax_exporter'):
        if cfg['gdax_exporter'].get('prom_folder'):
            settings['gdax_exporter']['prom_folder'] = cfg['gdax_exporter']['prom_folder']
        if cfg['gdax_exporter'].get('interval'):
            settings['gdax_exporter']['interval'] = cfg['gdax_exporter']['interval']
        if cfg['gdax_exporter'].get('export') in ['text', 'http']:
            settings['gdax_exporter']['export'] = cfg['gdax_exporter']['export']
        if cfg['gdax_exporter'].get('listen_port'):
            settings['gdax_exporter']['listen_port'] = cfg['gdax_exporter']['listen_port']


class GdaxCollector:
    rates = {}

    def _getExchangeRates(self):
        try:
            pc = gdax.PublicClient()
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.ReadTimeout,
            requests.packages.urllib3.exceptions.ReadTimeoutError
        ) as e:
            log.warning(e)
            pc = None
        if pc:
            products = pc.get_products()
            for product in products:
                time.sleep(1)  # We don't want to spam the API
                try:
                    product_trades = pc.get_product_trades(product_id=product['id'])
                except (
                    json.decoder.JSONDecodeError
                ) as e:
                    log.warning('Could not get the ticker data for {}. The exception follows.'.format(product))
                    log.warning(e)
                    product_trades = None
                if isinstance(product_trades, list) and product_trades:
                    latest_trade = sorted(product_trades, key=itemgetter('trade_id'))[-1]
                    self.rates.update({
                        '{}-{}'.format(product['base_currency'], product['quote_currency']): {
                            'base_currency': product['base_currency'],
                            'quote_currency': product['quote_currency'],
                            'value': float(latest_trade['price']),
                        }
                    })
                else:
                    log.warning('Received invalid response. The content follows.')
                    log.warning(product_trades)
            pc = None

    def collect(self):
        self._getExchangeRates()
        if self.rates:
            metrics = {
                'exchange_rate': GaugeMetricFamily(
                    'exchange_rate',
                    'Current exchange rates',
                    labels=['source_currency', 'target_currency', 'exchange']
                ),
            }
            for rate in self.rates:
                metrics['exchange_rate'].add_metric(
                    value=self.rates[rate]['value'],
                    labels=[
                        self.rates[rate]['base_currency'],
                        self.rates[rate]['quote_currency'],
                        'gdax'
                    ]
                )

            for m in metrics.values():
                yield m


def _collect_to_text():
    while True:
        e = GdaxCollector()
        write_to_textfile('{0}/gdax_exporter.prom'.format(settings['gdax_exporter']['prom_folder']), e)
        time.sleep(int(settings['gdax_exporter']['interval']))


def _collect_to_http():
    REGISTRY.register(GdaxCollector())
    start_http_server(int(settings['gdax_exporter']['listen_port']))
    while True:
        time.sleep(int(settings['gdax_exporter']['interval']))


if __name__ == '__main__':
    _settings()
    log.debug('Loaded settings: {}'.format(settings))
    if settings['gdax_exporter']['export'] == 'text':
        _collect_to_text()
    if settings['gdax_exporter']['export'] == 'http':
        _collect_to_http()
