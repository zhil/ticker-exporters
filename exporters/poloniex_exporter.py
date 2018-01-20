#!/usr/bin/env python3

import logging
import time
import os
import yaml
import sys
import json
from prometheus_client import write_to_textfile, start_http_server
from prometheus_client.core import REGISTRY, GaugeMetricFamily, CounterMetricFamily
from poloniex import Poloniex

log = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=os.environ.get("LOGLEVEL", "INFO"))

settings = {}


def _settings():
    global settings

    settings = {
        'poloniex_exporter': {
            'prom_folder': '/var/lib/node_exporter',
            'interval': 60,
            'export': 'text',
            'listen_port': 9304,
            'api_key': '',
            'api_secret': '',
        },
    }
    config_file = '/etc/poloniex_exporter/poloniex_exporter.yaml'
    cfg = {}
    if os.path.isfile(config_file):
        with open(config_file, 'r') as ymlfile:
            cfg = yaml.load(ymlfile)
    if cfg.get('poloniex_exporter'):
        if cfg['poloniex_exporter'].get('prom_folder'):
            settings['poloniex_exporter']['prom_folder'] = cfg['poloniex_exporter']['prom_folder']
        if cfg['poloniex_exporter'].get('interval'):
            settings['poloniex_exporter']['interval'] = cfg['poloniex_exporter']['interval']
        if cfg['poloniex_exporter'].get('export') in ['text', 'http']:
            settings['poloniex_exporter']['export'] = cfg['poloniex_exporter']['export']
        if cfg['poloniex_exporter'].get('listen_port'):
            settings['poloniex_exporter']['listen_port'] = cfg['poloniex_exporter']['listen_port']
        if cfg['poloniex_exporter'].get('api_key'):
            settings['poloniex_exporter']['api_key'] = cfg['poloniex_exporter']['api_key']
        if cfg['poloniex_exporter'].get('api_secret'):
            settings['poloniex_exporter']['api_secret'] = cfg['poloniex_exporter']['api_secret']


class PoloniexCollector:
    def __init__(self):
        self.__POLO = Poloniex(settings['poloniex_exporter']['api_key'], settings['poloniex_exporter']['api_secret'])

    def _translate(self, currency):
        r = currency
        if currency == 'DASH':
            r = 'DSH'
        if currency == 'XBT':
            r = 'BTC'
        if currency == 'DOGE':
            r = 'XDG'
        if currency == 'STR':
            r = 'XLM'
        return r

    def _getExchangeRates(self):
        tickers = self.__POLO.returnTicker()
        result = []
        for ticker in tickers:
            log.debug('Got {} - {}'.format(ticker, tickers[ticker]))
            currencies = ticker.split('_')
            result.append({
                'source_currency': self._translate(currencies[1]),
                'target_currency': self._translate(currencies[0]),
                'value': float(tickers[ticker]['last']),
            })

        log.debug('Found the following ticker rates: {}'.format(result))
        return result

    def _getAccounts(self):
        result = []
        balances = []
        try:
            balances = self.__POLO.returnBalances()
        except (
            poloniex.PoloniexError
        ) as e:
            log.warning('Could not retrieve balances. The error follows.')
            log.warning(e)

        for balance in balances:
            log.debug('Got balance for {}: {}'.format(balance, balances[balance]))
            result.append({
                'currency': self._translate(balance),
                'balance': float(balances[balance]),
            })
        log.debug('Returning the following balances: {}'.format(result))
        return result

    def collect(self):
        metrics = {
            'exchange_rate': GaugeMetricFamily(
                'exchange_rate',
                'Current exchange rates',
                labels=['source_currency', 'target_currency', 'exchange']
            ),
            'account_balance': GaugeMetricFamily(
                'account_balance',
                'Account Balance',
                labels=['source_currency', 'currency', 'account', 'type']
            ),
        }

        for exchange_rate in self._getExchangeRates():
            metrics['exchange_rate'].add_metric(
                value=exchange_rate['value'],
                labels=[
                    exchange_rate['source_currency'],
                    exchange_rate['target_currency'],
                    'poloniex'
                ]
            )

        for account in self._getAccounts():
            if account['balance'] > 0:
                metrics['account_balance'].add_metric(
                    value=(account['balance']),
                    labels=[
                        account['currency'],
                        account['currency'],
                        'poloniex',
                        'poloniex'
                    ]
                )

        for m in metrics.values():
            yield m


def _collect_to_text():
    while True:
        e = PoloniexCollector()
        write_to_textfile('{0}/poloniex_exporter.prom'.format(settings['poloniex_exporter']['prom_folder']), e)
        time.sleep(int(settings['poloniex_exporter']['interval']))


def _collect_to_http():
    start_http_server(int(settings['poloniex_exporter']['listen_port']))
    while True:
        time.sleep(int(settings['poloniex_exporter']['interval']))


if __name__ == '__main__':
    _settings()
    log.debug('Loaded settings: {}'.format(settings))
    REGISTRY.register(PoloniexCollector())
    if settings['poloniex_exporter']['export'] == 'text':
        _collect_to_text()
    if settings['poloniex_exporter']['export'] == 'http':
        _collect_to_http()
