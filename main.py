import json
import requests
import asyncio
from typing import Optional
from fastapi import Depends, BackgroundTasks, FastAPI
from config import Settings, get_settings
import bn_client as bn_client
import utils as utils
import redis_client as redis_client
import models as models
import post_transactions as post_trans

app = FastAPI()
st_loss_profit_tasks = []


@app.get("/")
def read_root():
    return {"Hello": "World"}


async def place_order(signal: models.Signal, background_tasks: BackgroundTasks):
    settings = get_settings()
    bn = bn_client.BinanceClientAsync(api_key=settings.api_key, secret_key=settings.api_secret)
    pair = signal.ticker_pair.upper()
    # if signal.side.upper() == 'SELL':
    # await cancel_st_tasks_and_open_orders(bn, pair)
    # To calculate buy quantity and trade FIAT symbol name.
    balance_symbol = utils.extract_balance_symbol_from_pair(pair)
    # To calculate sell quantity.
    ticker_symbol = utils.extract_ticker_symbol_from_pair(pair)
    # if the transaction sell is
    if signal.side.upper() == 'SELL':
        balance_symbol = ticker_symbol
    price, balance = await bn.get_price_and_balance(pair, balance_symbol)
    symbol_info = await get_symbol_info(bn, pair)
    # For testing
    quantity = 0.0
    if signal.side.upper() == 'BUY':
        # balance = 30.00
        quantity = utils.calculate_quantity(balance, price, symbol_info['quantity_step_size'])

    if signal.side.upper() == 'SELL':
        stop_loss_order_id = redis_client.get_from_cache(f'{pair}_stop_loss_orderId')
        # take_profit_order_id = redis_client.get_from_cache(f'{pair}_order_limit_maker_orderId')
        if stop_loss_order_id is not None:
            await bn.cancel_order(pair, stop_loss_order_id)

        quantity = utils.calculate_sell_quantity(balance, symbol_info['quantity_step_size'])

    min_notional_quantity = float(quantity) * float(price)
    min_notional = float(symbol_info['min_notional'])
    if min_notional_quantity > min_notional:
        # If the side sell then cancel all open orders and st bg tasks
        await cancel_st_tasks_and_open_orders(pair)
        # order = await bn.create_order(pair, signal.side.upper(), 90, 'LIMIT', float(price))
        order = await bn.create_order(pair, signal.side.upper(), quantity, 'LIMIT', float(price))
        # Check the status if it is filled test
        order_status = None
        if order is not None:
            order_status = await bn.query_order(pair, order['orderId'])
        cancel_order = None
        if order_status is not None:
            if order_status['status'] != 'FILLED':
                # Wait 2 seconds
                await asyncio.sleep(2)
                cancel_order = await bn.cancel_order(pair, order['orderId'])
                if cancel_order is not None:
                    await place_order(signal, background_tasks)
                    return
            if signal.side.upper() == 'BUY':
                placed_order = models.PlacedOrder(
                    id=order['orderId'],
                    price=order['price'],
                    quantity=order['origQty'],
                    status=order['status'],
                    symbol=pair
                )
                redis_client.set_to_cache('placed_order', placed_order.json())
                # background_tasks.add_task(task_list, placed_order)
                # background_tasks.add_task(place_stop_loss_order, signal.ticker_pair.upper(), order['price'],
                #                          order['origQty'])
                # redis_client.delete_key(f'{signal.ticker_pair.upper()}_lslp')
                # await task_list(order['price'], signal.ticker_pair.upper())
                # background_tasks.add_task(stop_loss_update, order['price'], signal.ticker_pair.upper())
                # await stop_loss_update(order['price'], signal.ticker_pair.upper())
                await task_list(placed_order)
            print(order)
        # print(f'price = {price} balance = {balance}')
        return {
            'price': price,
            'balance': balance,
            'order': order,
            'cancel_order': cancel_order
        }
    else:
        print(f'min_notional qty {min_notional_quantity} is less then {min_notional}')
        return {'min_notional': 'Not enough quantity'}


@app.post("/signal/")
async def create_item(signal: models.Signal, background_tasks: BackgroundTasks):
    settings = get_settings()
    if signal.passphrase != settings.hook_secret:
        return {'no_neo': 'no way'}
    background_tasks.add_task(place_order, signal, background_tasks)
    # order = await place_order(signal, background_tasks)
    return {
        'order': 'has been placed',
        # 'order_is': order
    }
    # return {'dont_buy': True}


async def get_symbol_info(bn, pair):
    await bn.open()
    symbol_info_from_redis = redis_client.get_from_cache(f'symbol_info_{pair}')
    symbol_info = None
    if symbol_info_from_redis is not None:
        symbol_info = json.loads(symbol_info_from_redis)
    else:
        symbol_info = await bn.get_symbol_exchange_info(pair)
        price_tick_size, quantity_step_size, min_notional = utils.get_price_tick_quantity_step_min_notional(symbol_info)
        symbol_info = {
            'price_tick_size': price_tick_size,
            'quantity_step_size': quantity_step_size,
            'min_notional': min_notional,
            'orderTypes': symbol_info['orderTypes']
        }
        redis_client.set_to_cache(key=f'symbol_info_{pair}', value=json.dumps(symbol_info))
    return symbol_info


async def place_order_limit_maker(symbol, bought_price, quantity):
    settings = get_settings()
    bn = bn_client.BinanceClientAsync(api_key=settings.api_key, secret_key=settings.api_secret)
    symbol_info_from_redis = redis_client.get_from_cache(f'symbol_info_{symbol}')
    symbol_info = json.loads(symbol_info_from_redis)
    quantity = utils.calculate_sell_quantity(quantity, symbol_info['quantity_step_size'])
    price = float(1 + 0.005) * float(bought_price)
    price = "{:0.0{}f}".format(price, symbol_info['price_tick_size'])
    order_limit_maker = await bn.order_limit_maker(symbol, 'SELL', quantity, price)
    print('waht is order_limit_maker')
    print(order_limit_maker)
    redis_client.set_to_cache(f'{symbol}_order_limit_maker_orderId', order_limit_maker['orderId'])
    return order_limit_maker


async def place_stop_loss_order(symbol, bought_price, quantity):
    settings = get_settings()
    bn = bn_client.BinanceClientAsync(api_key=settings.api_key, secret_key=settings.api_secret)
    symbol_info_from_redis = redis_client.get_from_cache(f'symbol_info_{symbol}')
    symbol_info = json.loads(symbol_info_from_redis)
    quantity = utils.calculate_sell_quantity(quantity, symbol_info['quantity_step_size'])
    price = float(1 - 0.004) * float(bought_price)
    price = "{:0.0{}f}".format(price, symbol_info['price_tick_size'])
    stop_price = price
    stop_loss_limit = await bn.order_stop_loss_limit(symbol, 'SELL', quantity, stop_price, price)
    print('waht is stop loss order')
    print(stop_loss_limit)
    redis_client.set_to_cache(f'{symbol}_stop_loss_orderId', stop_loss_limit['orderId'])
    return stop_loss_limit


@app.get("/stop/{current_price}")
def read_root(current_price: float):
    symbol = 'TLMBUSD'
    bought_price = 0.2920
    percent_var = 0.3
    percent = float(1 - percent_var / 100)
    stop_price = bought_price * percent
    last_stop_price = redis_client.get_from_cache(f'{symbol}_lslp')
    if last_stop_price is None:
        redis_client.set_to_cache(f'{symbol}_lslp', str(stop_price))
    win_lose_percent = calculate_current_win_lose_percent(current_price, last_stop_price, 4)
    new_stop_price = 0.0
    if win_lose_percent > percent_var:
        redis_client.delete_key(f'{symbol}_lslp')
        new_stop_price = float(current_price * percent)
        redis_client.set_to_cache(f'{symbol}_lslp', str(new_stop_price))
    return {
        'last_stop_price': last_stop_price,
        'current_price': current_price,
        'percent_var': percent_var,
        'percent': percent,
        'win_lose_percent': win_lose_percent,
        'new_stop_price': new_stop_price
    }


async def stop_loss_update(bought_price, symbol):
    current_price = get_current_price(symbol)
    percent_var = 0.5
    percent = float(1 - percent_var / 100)
    stop_price = float(bought_price) * float(percent)
    last_stop_price = redis_client.get_from_cache(f'{symbol}_lslp')
    if last_stop_price is None:
        await place_stop_loss_order_update(symbol, stop_price)
        redis_client.set_to_cache(f'{symbol}_lslp', str(stop_price))
    print(f'bought price = {bought_price}')
    win_lose_percent = calculate_current_win_lose_percent(current_price, bought_price, 4)
    print(f'win lose percent = {win_lose_percent}')
    new_stop_price = 0.0
    update_percent = 0.05
    if win_lose_percent > update_percent:
        percent_var = 0.3
        percent = float(1 - percent_var / 100)
        redis_client.delete_key(f'{symbol}_lslp')
        new_stop_price = current_price
        stop_price = float(current_price) * float(percent)
        await place_stop_loss_order_update(symbol, stop_price)
        redis_client.set_to_cache(f'{symbol}_lslp', str(stop_price))
    await asyncio.sleep(2)
    if float(new_stop_price) > 0:
        bought_price = new_stop_price
    await stop_loss_update(bought_price, symbol)


def calculate_current_win_lose_percent(current_price, bought_price, price_tick_size):
    print(f'current_price= {current_price}, bought_price = {bought_price}, price_tick_size = {price_tick_size}')
    bought_price = "{:0.0{}f}".format(float(bought_price), price_tick_size)
    current_price = "{:0.0{}f}".format(float(current_price), price_tick_size)
    # percent = float(bought_price) / float(current_price)
    percent = round(float(((float(current_price) * 100) / float(bought_price)) - 100), 2)
    return percent


def get_current_price(symbol):
    url = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}")
    data = url.json()
    return data['price']


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


async def task_list(data: Optional[models.PlacedOrder] = None, cancel_task=None):
    if len(st_loss_profit_tasks) > 0:
        for task in st_loss_profit_tasks:
            task.cancel()
    for i in range(1):
        if cancel_task is not True:
            st_loss_profit_tasks.append(asyncio.create_task(post_trans.watch_live(data)))
    if len(st_loss_profit_tasks) > 0:
        # await asyncio.gather(*st_loss_profit_tasks, return_exceptions=True)
        await asyncio.gather(*st_loss_profit_tasks)


async def cancel_st_tasks_and_open_orders(pair):
    await task_list(cancel_task=True)
    redis_client.delete_key(f'{pair}_stop_loss_orderId')
    redis_client.delete_key(f'{pair}_lslp')
    redis_client.delete_key('placed_order')
    redis_client.delete_key(f'{pair}_order_limit_maker_orderId')
    redis_client.delete_key(f'{pair}_second_stop_loss_order_id')
