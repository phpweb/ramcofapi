import websockets
import json
import models as models
from config import get_settings
import redis_client
import config as config
import bn_client as bn_client
import utils as utils


async def watch_live(placed_order: models.PlacedOrder):
    symbol = placed_order.symbol.lower()
    uri = f"wss://stream.binance.com:9443/ws/{symbol}@aggTrade"
    async with websockets.connect(uri) as websocket:
        while True:
            res = await websocket.recv()
            await compare_live_percent_change(res)


async def compare_live_percent_change(msg):
    msg = json.loads(msg)
    current_price = msg['p']
    placed_order = redis_client.get_from_cache('placed_order')
    if placed_order is not None:
        placed_order = json.loads(placed_order)
        bought_price = placed_order['price']
        symbol = placed_order['symbol']
        print(f'bought_price = {bought_price}, symbol = {symbol}, current_price = {current_price}')
        # await stop_loss_update(bought_price, symbol, current_price)
        await stop_loss_only(bought_price, symbol, current_price)
    else:
        print('There is no placed order: post_transactions.py line 32')

async def stop_loss_only(bought_price, symbol, current_price):
    percent_var = 0.2
    percent = float(1 - percent_var / 100)
    stop_price = float(bought_price) * float(percent)
    stop_loss_order_id = redis_client.get_from_cache(f'{symbol}_stop_loss_orderId')
    if stop_loss_order_id is None:
        await place_stop_loss_order_update(symbol, stop_price)


async def stop_loss_update(bought_price, symbol, current_price):
    percent_var = 0.5
    percent = float(1 - percent_var / 100)
    stop_price = float(bought_price) * float(percent)
    last_stop_price = redis_client.get_from_cache(f'{symbol}_lslp')
    if last_stop_price is None:
        await place_stop_loss_order_update(symbol, stop_price)
        redis_client.set_to_cache(f'{symbol}_lslp', str(stop_price))
        last_stop_price = stop_price
    print(f'bought price = {bought_price}')
    win_lose_percent = calculate_current_win_lose_percent(current_price, last_stop_price, 4)
    print(f'win lose percent = {win_lose_percent}')
    update_percent = 0.05
    if win_lose_percent > update_percent:
        percent_var = 0.3
        percent = float(1 - percent_var / 100)
        redis_client.delete_key(f'{symbol}_lslp')
        stop_price = float(current_price) * float(percent)
        await place_stop_loss_order_update(symbol, stop_price)
        redis_client.set_to_cache(f'{symbol}_lslp', str(current_price))


async def place_stop_loss_order_update(symbol, stop_price):
    settings = get_settings()
    bn = bn_client.BinanceClientAsync(api_key=settings.api_key, secret_key=settings.api_secret)
    stop_loss_order_id = redis_client.get_from_cache(f'{symbol}_stop_loss_orderId')
    if stop_loss_order_id is not None:
        # take_profit_order_id = redis_client.get_from_cache(f'{pair}_order_limit_maker_orderId')
        await bn.cancel_order(symbol, stop_loss_order_id)

    symbol_info_from_redis = redis_client.get_from_cache(f'symbol_info_{symbol}')
    symbol_info = json.loads(symbol_info_from_redis)
    symbol_asset = utils.extract_ticker_symbol_from_pair(symbol)
    quantity = await bn.get_balance(symbol_asset)
    step_size = symbol_info['quantity_step_size']
    print(f'quantity = {quantity} step size = {step_size}')
    quantity = utils.calculate_sell_quantity(quantity, symbol_info['quantity_step_size'])
    price = "{:0.0{}f}".format(stop_price, symbol_info['price_tick_size'])
    stop_price = price
    stop_loss_limit = await bn.order_stop_loss_limit(symbol, 'SELL', quantity, stop_price, price)
    print('waht is stop loss order')
    print(stop_loss_limit)
    if stop_loss_limit is not None:
        redis_client.set_to_cache(f'{symbol}_stop_loss_orderId', stop_loss_limit['orderId'])
    return stop_loss_limit


def calculate_win_los_percent_with_decimal(current_price, bought_price):
    price_diff = ((float(current_price) / float(bought_price)) * 100.00) - 100.00
    return round(price_diff, 2)


def calculate_current_win_lose_percent(current_price, bought_price, price_tick_size):
    bought_price = "{:0.0{}f}".format(float(bought_price), price_tick_size)
    current_price = "{:0.0{}f}".format(float(current_price), price_tick_size)
    # percent = float(bought_price) / float(current_price)
    percent = round(float(((float(current_price) * 100) / float(bought_price)) - 100), 2)
    return percent


def calculate_current_win_lose_percent(current_price, bought_price, price_tick_size):
    bought_price = "{:0.0{}f}".format(float(bought_price), price_tick_size)
    current_price = "{:0.0{}f}".format(float(current_price), price_tick_size)
    # percent = float(bought_price) / float(current_price)
    percent = round(float(((float(current_price) * 100) / float(bought_price)) - 100), 2)
    return percent


async def cancel_stop_loss_order(symbol, order_id):
    settings = get_settings()
    bn = bn_client.BinanceClientAsync(api_key=settings.api_key, secret_key=settings.api_secret)
    cancel_stop_loss_limit = await bn.cancel_order(symbol, order_id)
    return cancel_stop_loss_limit


async def place_stop_loss_order(symbol, side, quantity, stop_price, price, second=None):
    settings = get_settings()
    bn = bn_client.BinanceClientAsync(api_key=settings.api_key, secret_key=settings.api_secret)
    order_stop_loss_limit = await bn.order_stop_loss_limit(symbol, side, quantity, stop_price, price)
    redis_client.set_to_cache(f'{symbol}_stop_loss_orderId', order_stop_loss_limit['orderId'])
    if second == 'second':
        redis_client.set_to_cache(f'{symbol}_second_stop_loss_order_id', order_stop_loss_limit['orderId'])
    return order_stop_loss_limit


async def place_order_limit_maker(symbol, side, quantity, price):
    settings = get_settings()
    bn = bn_client.BinanceClientAsync(api_key=settings.api_key, secret_key=settings.api_secret)
    order_limit_maker = await bn.order_limit_maker(symbol, side, quantity, price)
    print('waht is order_limit_maker')
    print(order_limit_maker)
    redis_client.set_to_cache(f'{symbol}_order_limit_maker_orderId', order_limit_maker['orderId'])
    return order_limit_maker


async def place_oco_order(symbol, side, quantity, price, stop_price, stop_limit_price):
    settings = get_settings()
    bn = bn_client.BinanceClientAsync(api_key=settings.api_key, secret_key=settings.api_secret)
    oco_order = await bn.create_oco_order(symbol, side, quantity, price, stop_price, stop_limit_price)
    print('waht is oco_order')
    print(oco_order)
    redis_client.set_to_cache(f'{symbol}_order_limit_maker_orderId', oco_order[0]['orderId'])
    return oco_order
