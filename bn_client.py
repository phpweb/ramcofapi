import time
import datetime
# import pytz
# import dateparser
# import requests
import aiohttp
import asyncio
import hmac
import hashlib
# import decimal
# import pprint
# import numbers
# import sys
# import random
from urllib.parse import urljoin, urlencode


class BinanceException(Exception):
    def __init__(self, status_code, data=None):

        self.status_code = status_code
        if data:
            self.code = data['code']
            self.msg = data['msg']
            message = f"{status_code} [{self.code}] {self.msg}"
        else:
            self.code = None
            self.msg = None
            message = f"status_code={status_code}"

        # Python 2.x
        # super(BinanceException, self).__init__(message)
        super().__init__(message)


class BinanceClientAsync:
    BASE_URL = 'https://api.binance.com'

    def __init__(self, api_key, secret_key, recv_window=6000, test=False, retry=3):
        self.api_key = api_key
        self.secret_key = secret_key
        self.recvWindow = recv_window
        self.headers = {
            'X-MBX-APIKEY': api_key
        }
        self.TEST = test
        self.session = aiohttp.ClientSession()
        self.retry = retry

    async def open(self):
        self.session = aiohttp.ClientSession()

    async def close(self):
        await self.session.close()

    async def _handle_reponse(self, r):
        if r.status == 200:
            data = await r.json()
            return data
        elif r.status == 400:
            data = await r.json()
            code = data['code']
            msg = data['msg']
            print(f'unknown order sent mi bi bakkkkkkkk code={code} message = {msg}')
            pass
        else:
            if r.headers['Content-Type'].startswith('application/json'):
                raise BinanceException(status_code=r.status, data=await r.json())
            else:
                raise BinanceException(status_code=r.status, data=None)

    def _sign(self, params):
        params['timestamp'] = int(time.time() * 1000)
        query_string = urlencode(params)
        params['signature'] = hmac.new(self.secret_key.encode('utf-8'), query_string.encode('utf-8'),
                                       hashlib.sha256).hexdigest()

    async def _retry_request(self, fn):
        retry_count = 0
        while True:
            try:
                return await fn()
            except aiohttp.client_exceptions.ClientOSError as e:
                print(e)
                retry_count += 1
                if retry_count >= self.retry:
                    raise e
                await asyncio.sleep(pow(2, retry_count - 1))  # 1, 2, 4
            except BinanceException as e:
                if e.code == -1001:  # DISCONNECTED, Internal error; unable to process your request. Please try again.
                    print(e)
                    retry_count += 1
                    if retry_count >= self.retry:
                        raise e
                    await asyncio.sleep(pow(2, retry_count - 1))  # 1, 2, 4
                elif e.status_code == 502:  # maybe want to handle all 5XX error?
                    print(e)
                    retry_count += 1
                    if retry_count >= self.retry:
                        raise e
                    await asyncio.sleep(pow(2, retry_count - 1))  # 1, 2, 4
                else:
                    raise e

    async def get_time(self):
        path = '/api/v1/time'
        params = None

        url = urljoin(self.BASE_URL, path)
        data = []
        async with self.session.get(url) as r:
            if r.status == 200:
                data = await r.json()
                return data
            else:
                raise BinanceException(status_code=r.status, data=data)

    async def get_balance(self, asset_symbol):
        path = '/api/v3/account'
        params = {
            'recvWindow': 50000,
        }
        url = urljoin(self.BASE_URL, path)
        data = []
        self._sign(params)
        try:
            async with self.session.get(url, headers=self.headers, params=params) as r:
                if r.status == 200:
                    data = await r.json()
                    if "balances" in data:
                        for bal in data['balances']:
                            if bal['asset'].lower() == asset_symbol.lower():
                                return bal['free']
                else:
                    raise BinanceException(status_code=r.status, data=data)
        except aiohttp.ClientConnectorError as e:
            print('Connection Error', str(e))

    async def get_exchange_info(self):
        path = '/api/v1/exchangeInfo'
        params = None

        url = urljoin(self.BASE_URL, path)
        async with self.session.get(url, params=params) as r:
            return await self._handle_reponse(r)

    async def get_symbol_exchange_info(self, symbol):
        path = '/api/v1/exchangeInfo'
        params = None

        url = urljoin(self.BASE_URL, path)
        async with self.session.get(url, params=params) as r:
            if r.status == 200:
                data = await r.json()
                for item in data['symbols']:
                    if item['symbol'] == symbol.upper():
                        return item
            return await self._handle_reponse(r)

    async def get_price(self, symbol=None):
        path = '/api/v3/ticker/price'
        params = {

        }
        if symbol:
            params['symbol'] = symbol

        url = urljoin(self.BASE_URL, path)
        async with self.session.get(url, headers=self.headers, params=params) as r:
            return await self._handle_reponse(r)

    async def get_tasks_response(self, session, url, params):
        async with session.get(url, headers=self.headers, params=params) as r:
            return await self._handle_reponse(r)

    async def get_price_and_balance(self, pair_symbol, balance_symbol):
        price_path = '/api/v3/ticker/price'
        price_params = {
            'symbol': pair_symbol
        }
        balance_path = '/api/v3/account'
        balance_params = {
            'recvWindow': 50000,
        }
        price_url = urljoin(self.BASE_URL, price_path)
        balance_url = urljoin(self.BASE_URL, balance_path)
        self._sign(balance_params)
        # client = self.session
        async with self.session as client:
            price, balance = await asyncio.gather(
                self.get_tasks_response(client, price_url, params=price_params),
                self.get_tasks_response(client, balance_url, balance_params)
            )
            bal_free = None
            if "balances" in balance:
                for bal in balance['balances']:
                    if bal['asset'].lower() == balance_symbol.lower():
                        bal_free = bal
            return price['price'], bal_free['free']

    async def get_order_book(self, symbol, limit=100):
        # path = '/api/v1/depth'
        path = '/api/v3/depth'
        params = {
            'symbol': symbol,
            'limit': limit
        }

        url = urljoin(self.BASE_URL, path)

        async def request():
            async with self.session.get(url, headers=self.headers, params=params) as r:
                return await self._handle_reponse(r)

        return await self._retry_request(request)

    async def order_limit_maker(self, symbol, side, quantity, price):
        return await self.create_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type='LIMIT_MAKER',
            price=price)

    async def order_stop_loss_limit(self, symbol, side, quantity, stop_price, price):
        return await self.create_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type='STOP_LOSS_LIMIT',
            price=price,
            stop_price=stop_price,
            time_in_force='GTC')

    async def order_market(self, symbol, side, quantity):
        return await self.create_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type='MARKET',
            price=None,
            time_in_force=None)

    async def create_order(self, symbol, side, quantity, order_type, price, time_in_force=None, stop_price=None):
        path = '/api/v3/order'
        # if self.TEST:
        #    path = '/api/v3/order/test'

        params = {
            'symbol': symbol,
            'side': side,
            'quantity': quantity,
            'type': order_type,
            'recvWindow': 50000,
            'timeInForce': 'GTC'
        }

        if price is not None:
            params['price'] = price
        if time_in_force is not None:
            params['timeInForce'] = time_in_force
        if stop_price is not None:
            params['stopPrice'] = stop_price
        if order_type == 'LIMIT_MAKER':
            del params['timeInForce']
        self._sign(params)

        url = urljoin(self.BASE_URL, path)

        async with self.session.post(url, headers=self.headers, params=params) as r:
            return await self._handle_reponse(r)

    async def query_order(self, symbol, order_id):
        path = '/api/v3/order'

        params = {
            'symbol': symbol,
            'orderId': order_id,
            'recvWindow': 50000,
        }

        self._sign(params)

        url = urljoin(self.BASE_URL, path)

        # status: NEW, PARTIALLY_FILLED, FILLED, CANCELED, PENDING_CANCEL, REJECTED, EXPIRED
        async def request():
            async with self.session.get(url, headers=self.headers, params=params) as r:
                return await self._handle_reponse(r)

        return await self._retry_request(request)

    async def cancel_order(self, symbol, order_id):
        path = '/api/v3/order'

        params = {
            'symbol': symbol,
            'orderId': order_id,
            'recvWindow': 50000
        }

        self._sign(params)

        url = urljoin(self.BASE_URL, path)

        async with self.session.delete(url, headers=self.headers, params=params) as r:
            return await self._handle_reponse(r)

    async def get_kline_data(self, symbol, interval, limit=500, start_time=None, end_time=None):
        path = '/api/v1/klines'

        # interval: 1m, 3m, 5m, 15m, 30m
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }

        if start_time is not None:
            params['startTime'] = start_time
        if end_time is not None:
            params['endTime'] = end_time

        url = urljoin(self.BASE_URL, path)

        async def request():
            async with self.session.get(url, headers=self.headers, params=params) as r:
                return await self._handle_reponse(r)

        return await self._retry_request(request)

    async def get_trades(self, symbol, from_id=None, limit=500, start_time=None):
        path = '/api/v3/myTrades'

        params = {
            'symbol': symbol
        }

        if from_id:
            params['fromId'] = from_id
        if start_time:
            params['startTime'] = start_time
        if limit:
            params['limit'] = limit

        self._sign(params)

        url = urljoin(self.BASE_URL, path)

        async with self.session.get(url, headers=self.headers, params=params) as r:
            return await self._handle_reponse(r)

    async def create_oco_order(self, symbol, side, quantity, price, stop_price, stop_limit_price):
        path = '/api/v3/order/oco'
        # if self.TEST:
        #    path = '/api/v3/order/test'

        params = {
            'symbol': symbol,
            'side': side,
            'quantity': quantity,
            'price': price,
            'stopPrice': stop_price,
            'stopLimitPrice': stop_limit_price,
            'recvWindow': 50000,
            'stopLimitTimeInForce': 'GTC'
        }

        self._sign(params)

        url = urljoin(self.BASE_URL, path)

        async with self.session.post(url, headers=self.headers, params=params) as r:
            return await self._handle_reponse(r)

    async def query_oco_order(self, order_list_id):
        path = '/api/v3/orderList'

        params = {
            'orderListId': order_list_id
        }

        self._sign(params)

        url = urljoin(self.BASE_URL, path)

        async def request():
            async with self.session.get(url, headers=self.headers, params=params) as r:
                return await self._handle_reponse(r)

        return await self._retry_request(request)

    async def cancel_all_open_order(self, symbol):
        path = '/api/v3/openOrders'

        params = {
            'symbol': symbol,
            'recvWindow': 50000
        }

        self._sign(params)

        url = urljoin(self.BASE_URL, path)

        async with self.session.delete(url, headers=self.headers, params=params) as r:
            return await self._handle_reponse(r)

    async def get_all_open_order(self, symbol):
        path = '/api/v3/openOrders'

        params = {
            'symbol': symbol,
            'recvWindow': 50000
        }

        self._sign(params)

        url = urljoin(self.BASE_URL, path)

        async with self.session.get(url, headers=self.headers, params=params) as r:
            return await self._handle_reponse(r)
