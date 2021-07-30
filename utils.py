def calculate_target_exit_price(percent, current_price):
    target_price = float(current_price) * float(percent)
    target_price = float(current_price) + float(target_price)
    return float('{:.4f}'.format(float(target_price))[:-1])


def calculate_quantity(balance, current_price, step_size):
    quantity = float(balance) / float(current_price) * float(0.9995)
    quantity = str(quantity)
    return float(quantity[:quantity.find('.') + step_size + 1])


def calculate_sell_quantity(balance, step_size):
    quantity = float(balance) - (float(balance) - float(balance) * float(0.9995))
    quantity = str(quantity)
    print(f'quantity == {quantity}')
    return float(quantity[:quantity.find('.') + step_size + 1])


def calculate_stop_loss_price(current_price, percent=0.02):
    stop_loss_amount = float(current_price) * float(percent)
    stop_price = float(current_price) - stop_loss_amount
    stop_limit_price = float(current_price) * float(0.021)
    stop_limit_price = float(current_price) - stop_limit_price
    stop_price = float('{:.7f}'.format(float(stop_price))[:-1])
    stop_limit_price = float('{:.7f}'.format(float(stop_limit_price))[:-1])
    return stop_price, stop_limit_price


def calculate_time_difference(start, end):
    time_difference = (start - end)
    # total_seconds = time_difference.total_seconds()
    hours = int(time_difference.seconds / (60 * 60))
    minutes = int((time_difference.seconds / 60) % 60)
    return f'{hours}h {minutes}m' if hours > 0 else f'{minutes}m'


def calculate_price_difference(start_price, end_price):
    price_diff = float(end_price) - float(start_price)
    return float('{:.5f}'.format(float(price_diff))[:-1])


def calculate_win_los_percent(start_price, end_price):
    price_diff = (float(end_price) / float(start_price)) * 100 - 100
    return float('{:.2f}'.format(float(price_diff))[:-1])


def calculate_win_los_percent_with_decimal(start_price, end_price):
    price_diff = ((float(start_price) / float(end_price)) * 100.00) - 100.00
    return round(price_diff, 2)


def extract_balance_symbol_from_pair(pair):
    return pair[-4:]


def extract_ticker_symbol_from_pair(pair):
    return pair[:-4]


def get_price_filter_tick_size(pair_info):
    f = [i["tickSize"] for i in pair_info["filters"] if i["filterType"] == "PRICE_FILTER"][0]
    return f.index("1") - 1


def get_quantity_step_size(pair_info):
    f = [i["stepSize"] for i in pair_info["filters"] if i["filterType"] == "LOT_SIZE"][0]
    return f.index("1") - 1


def get_min_notional(pair_info):
    f = [i["minNotional"] for i in pair_info["filters"] if i["filterType"] == "MIN_NOTIONAL"][0]
    return float(f)


def get_price_tick_quantity_step_min_notional(pair_info):
    price_tick_size = [i["tickSize"] for i in pair_info["filters"] if i["filterType"] == "PRICE_FILTER"][0]
    price_tick_size = price_tick_size.index("1") - 1
    quantity_step_size = [i["stepSize"] for i in pair_info["filters"] if i["filterType"] == "LOT_SIZE"][0]
    quantity_step_size = quantity_step_size.index("1") - 1
    min_notional = [i["minNotional"] for i in pair_info["filters"] if i["filterType"] == "MIN_NOTIONAL"][0]
    min_notional = float(min_notional)
    return price_tick_size, quantity_step_size, min_notional
