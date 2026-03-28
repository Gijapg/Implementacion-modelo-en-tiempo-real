import MetaTrader5 as mt5
import pandas as pd
from logica_bot.safe_operations import *

import logging

logger = logging.getLogger(__name__)


def is_price_valid(symbol, price, order_type):
    # Verificar que el precio no sea 0 o negativo
    if price <= 0:
        logger.error(f"Error: Precio inválido para {symbol} (precio: {price})")
        return False

    # Obtener información del símbolo
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        logger.error(f"Error: No se pudo obtener información para {symbol}")
        return False

    # Verificar que el precio esté dentro de los límites permitidos
    if order_type == mt5.ORDER_TYPE_BUY:
        if price < symbol_info.bid:  # El precio de compra no puede ser menor que el Bid actual
            logger.error(f"Error: Precio de compra ({price}) es menor que el Bid actual ({symbol_info.bid})")
            return False
    elif order_type == mt5.ORDER_TYPE_SELL:
        if price > symbol_info.ask:  # El precio de venta no puede ser mayor que el Ask actual
            logger.error(f"Error: Precio de venta ({price}) es mayor que el Ask actual ({symbol_info.ask})")
            return False

    return True


def calculate_lot_size(entry_price, stop_loss_price, op_type, risk_percent, symbol):
    
    # Obtener el balance de la cuenta
    account_info = mt5.account_info()
    if account_info is None:
        logger.error("Error: No se pudo obtener información de la cuenta")
        return 0.01
    
    account_balance = account_info.balance
    if account_balance <= 0:
        logger.error("Error: Balance de cuenta inválido")
        return 0.01
    
    # Obtener información del símbolo
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        logger.error(f"Error: No se pudo obtener información del símbolo {symbol}")
        return 0.01
    
    # Calcular el valor monetario a riskear
    risk_amount = account_balance * (risk_percent / 100.0)
    
    # Calcular la distancia del stop loss en pips
    if op_type == mt5.ORDER_TYPE_SELL:
        sl_distance_points = abs(entry_price - stop_loss_price)
    else:
        sl_distance_points = abs(stop_loss_price - entry_price)
    
    # Calcular el valor de un pip para el par
    tick_size = symbol_info.trade_tick_size
    tick_value = symbol_info.trade_tick_value
    point = symbol_info.point
    
    # Evitar división por cero
    if tick_size <= 0 or point <= 0:
        logger.error("Error: Valores de tick_size o point inválidos")
        return 0.01
    
    point_value = tick_value / (tick_size / point)
    
    # Calcular el tamaño de lote requerido
    money_at_risk_per_lot = (sl_distance_points / point) * point_value
    
    if money_at_risk_per_lot <= 0:
        return 0.01  # Valor por defecto seguro
    
    lots = risk_amount / money_at_risk_per_lot
    
    # Ajustar a los límites del broker y redondear
    min_lot = symbol_info.volume_min
    max_lot = symbol_info.volume_max
    lot_step = symbol_info.volume_step
    
    lots = max(min_lot, min(max_lot, lots))
    lots = round(lots / lot_step) * lot_step
    
    logger.info(f"Symbol: {symbol}, Balance: {account_balance:.2f}, RiskAmount: {risk_amount:.2f}, Lots: {lots:.2f}")
    return lots


def send_om(symbol, action, sl, tp, magic, coment, risk_percent):

    positions = mt5.positions_get(symbol=symbol)
    if len(positions) > 0:
        # Filtrar por magic number si es necesario
        for position in positions:
            if position.magic == magic:
                logger.info(f"Ya existe una posición abierta para {symbol} con magic {magic}")
                logger.info(f"Ticket: {position.ticket}, Tipo: {'BUY' if position.type == 0 else 'SELL'}")
                return None

    order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL
    price = mt5.symbol_info_tick(symbol).ask if action == "BUY" else mt5.symbol_info_tick(symbol).bid

    if not is_price_valid(symbol, price, order_type):
        return None


    lots = calculate_lot_size(price, sl, order_type, risk_percent, symbol)

    # Crear la solicitud de orden
    order = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lots,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 10,  
        "magic": magic,
        "comment": coment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC  
    }

    # Enviar la orden
    result = mt5.order_send(order)
    if result is None:
        logger.error(f"{coment} Error: mt5.order_send() devolvió None")
        logger.error("Último error de MT5:", mt5.last_error())
        return None

    # Manejar errores específicos
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error(f"{coment} Error al enviar la orden: {result.retcode}")
        logger.error("Último error de MT5:", mt5.last_error())
        return None

    logger.info(f'Orden om para {coment} ejecutada exitosamente.')
    return result

