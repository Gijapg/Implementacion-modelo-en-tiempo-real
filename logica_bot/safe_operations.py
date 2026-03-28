import MetaTrader5 as mt5
import time
from datetime import datetime, timedelta, timezone


partial_tp_tracker = {}

def partial_take_profit(symbol, order_type, entry_price, take_profit):
    global partial_tp_tracker

    # Limpiar tickets de operaciones cerradas
    clean_closed_positions()

    # Obtener información del símbolo
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"Símbolo {symbol} no encontrado.")
        return

    if not symbol_info.visible:
        if not mt5.symbol_select(symbol, True):
            print(f"No se pudo habilitar el símbolo {symbol}.")
            return

    # Intentar obtener el precio actual con un pequeño retraso para asegurar la disponibilidad de datos
    time.sleep(0.5)
    price_data = mt5.symbol_info_tick(symbol)
    if price_data is None:
        print(f"No se encontraron precios para el símbolo {symbol}.")
        return

    current_price = price_data.ask if order_type == 'buy' else price_data.bid
    partial_tp_price = entry_price + 0.7 * (take_profit - entry_price) if order_type == 'buy' else entry_price - 0.5 * (entry_price - take_profit)

    #print(f"Precio actual: {current_price}")
    #print(f"Precio objetivo para ganancia parcial: {partial_tp_price}")

    # Verificar si el precio alcanzó el objetivo del 50% del TP
    if (order_type == 'buy' and current_price >= partial_tp_price) or (order_type == 'sell' and current_price <= partial_tp_price):
        # Obtener posiciones abiertas para el símbolo
        positions = mt5.positions_get(symbol=symbol)
        if positions is None or len(positions) == 0:
            print(f"No hay posiciones abiertas para el símbolo {symbol}.")
            return

        for pos in positions:
            # Verificar que el tipo de orden coincida y no se haya procesado antes
            if ((order_type == 'buy' and pos.type == mt5.ORDER_TYPE_BUY) or
                (order_type == 'sell' and pos.type == mt5.ORDER_TYPE_SELL)) and pos.ticket not in partial_tp_tracker:

                # Calcular el volumen a cerrar (50%)
                volume_to_close = pos.volume * 0.7
                volume_to_close = round(volume_to_close, 2)  # Ajustar al formato permitido

                #print(f"Volumen a cerrar: {volume_to_close}")

                # Obtener el precio justo antes de la solicitud para garantizar que es el más actual
                price_data = mt5.symbol_info_tick(symbol)
                if price_data is None:
                    print(f"No se encontraron precios para el símbolo {symbol}.")
                    return

                #print(f"Precio para la solicitud: {price_data.ask if order_type == 'buy' else price_data.bid}")

                # Crear solicitud para cerrar parcialmente con los valores existentes de TP y SL
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": volume_to_close,
                    "type": mt5.ORDER_TYPE_BUY if pos.type == 1 else mt5.ORDER_TYPE_SELL,
                    "position": pos.ticket,
                    "price": price_data.ask if pos.type == mt5.ORDER_TYPE_SELL else price_data.bid,  # Usar el precio actual
                    "deviation": 50,  # Aumentar el margen de desviación permitido
                    #"magic": pos.magic,
                    "comment": "Cierre parcial de ganancia",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }

                # Enviar solicitud
                result = mt5.order_send(request)
                if result.retcode == mt5.TRADE_RETCODE_DONE:
                    print(f"Ganancia parcial tomada: {volume_to_close} lotes cerrados.")
                    #log_operation(f"Ganancia parcial tomada: {volume_to_close} lotes cerrados.")
                    # Agregar el ticket al tracker para evitar repetir
                    partial_tp_tracker[pos.ticket] = True
                #else:
                    #print(f"Error al cerrar parcialmente: {result.retcode}. Detalles: {result.comment}")
    #else:
        #print("El precio aún no alcanza el 50% del TP.")

def clean_closed_positions():
    """Limpia los tickets de operaciones cerradas del diccionario."""
    # Obtener los tickets de las posiciones actualmente abiertas
    open_positions = mt5.positions_get()
    open_tickets = {pos.ticket for pos in open_positions} if open_positions else set()

    # Eliminar del tracker los tickets que ya no están abiertos
    closed_tickets = [ticket for ticket in partial_tp_tracker if ticket not in open_tickets]
    for ticket in closed_tickets:
        del partial_tp_tracker[ticket]
        print(f"Ticket {ticket} eliminado del tracker (posición cerrada).")




def break_even(symbol, order_type, entry_price, take_profit, stop_loss):
    """Mueve el stop loss al punto de equilibrio si se alcanza el 20% del take profit."""
    break_even_price = entry_price
    target_price = entry_price + 0.5 * (take_profit - entry_price) if order_type == 'buy' else entry_price - 0.5 * (entry_price - take_profit)
    
    # Obtener todas las posiciones abiertas para el símbolo
    positions = mt5.positions_get(symbol=symbol)
    if positions is None or len(positions) == 0:
        print("Error: No se pudo obtener la posición actual.")
        return
    
    # Iterar sobre todas las posiciones abiertas
    for pos in positions:
        if pos.type == mt5.ORDER_TYPE_BUY:
            order_type = 'buy'
        elif pos.type == mt5.ORDER_TYPE_SELL:
            order_type = 'sell'

        # Asegurarnos de que el take profit se mantenga en la solicitud
        current_take_profit = pos.tp

        # Obtener el precio actual
        price_data = mt5.symbol_info_tick(symbol)
        if price_data is None:
            print("Error: No se pudo obtener el precio actual.")
            return
        
        current_price = price_data.ask if order_type == 'buy' else price_data.bid
        target_40_price = entry_price + 0.4 * (take_profit - entry_price) if order_type == 'buy' else entry_price - 0.4 * (entry_price - take_profit)
        target_70_price = entry_price + 0.7 * (take_profit - entry_price) if order_type == 'buy' else entry_price - 0.4 * (entry_price - take_profit)
        
        # Verificar si se alcanza el 20% del take profit
        if (order_type == 'buy' and current_price >= target_price and current_price < target_70_price ) or (order_type == 'sell' and current_price <= target_price and current_price > target_70_price):
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": symbol,
                "sl": break_even_price,
                "tp": current_take_profit,  # Mantener el take profit actual
                "position": pos.ticket,
                "deviation": 10,
                #"magic": 234000,
                "comment": "Stop Loss moved to Break Even",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"Stop Loss movido al punto de equilibrio: {break_even_price}. Take Profit: {current_take_profit}.")
            #else:
                #print(f"Error al mover el Stop Loss: {result.retcode}")
        #else:
            #print(f"La condición para mover el Stop Loss no se ha cumplido aún para la posición con ticket {pos.ticket}.")





def monitor_positions():
    #print("funcion M funcionando")
    positions = mt5.positions_get()
    if positions is not None: 
        for pos in positions:
            symbol = pos.symbol
            order_type = 'buy' if pos.type == mt5.ORDER_TYPE_BUY else 'sell'
            entry_price = pos.price_open
            tp = pos.tp
            sl = pos.sl
            volume = pos.volume
            #partial_take_profit(symbol, order_type, entry_price, tp)
            break_even(symbol, order_type, entry_price, tp, sl)
        
       




