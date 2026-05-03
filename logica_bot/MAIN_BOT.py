from logica_bot.ORDENES import *
from logica_bot.safe_operations import *
from backend_14 import get_candle_data
from logica_bot.estrategias import *


def logica_bot(symbol, candles_data):

    #check_pending_orders_tp(symbol)
    #monitor_positions()

    df_candles = pd.DataFrame(candles_data)
    df_candles['Date'] = pd.to_datetime(df_candles.index)
    df_candles.set_index('Date', inplace=True)
    df_candles.index.name = 'Date'

    if (symbol == 'USDJPY'):
        candles_data2 = get_candle_data(symbol, mt5.TIMEFRAME_H1, 1010)

        df_candles2 = pd.DataFrame(
            candles_data2,
            columns=['time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
        )

        df_candles2['Date'] = pd.to_datetime(df_candles2['time'], unit='s')  
        df_candles2.set_index('Date', inplace=True)

        df_candles2.drop('time', axis=1, inplace=True)
        #print(df_candles2.head())
        
        Wavelet_HMM_Strategy(df_candles2, symbol, MODEL_FILE = f'wavelet_hmm_model_USDJPY_20260130_2234.pkl', wavelet_window=12, wavelet_level=2, wavelet_type='db4', consolidation_required=1)
    
  



 

    
            
            
    

