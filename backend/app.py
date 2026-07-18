from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import yfinance as yf
import pandas as pd
import numpy as np
import json, os, time, sqlite3, threading
from datetime import datetime, timedelta
from contextlib import contextmanager
from research_agent import (
    GPTResearchAgent,
    MissingOpenAIKey,
    ResearchAgentError,
    ResearchOutputError,
    configured_model,
    configured_reasoning_effort,
    openai_is_configured,
    run_deterministic_demo,
)
from research_tools import (
    DEFAULT_SYMBOLS as RESEARCH_DEFAULT_SYMBOLS,
    DEMO_MARKET,
    DEMO_SCENARIO,
    DEMO_SYMBOL,
    MARKET_CONFIG as RESEARCH_MARKET_CONFIG,
    PERIOD_OBSERVATIONS as RESEARCH_PERIODS,
    ResearchDataUnavailable,
    ResearchToolbox,
    ResearchValidationError,
    validate_research_request,
)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA_DIR = os.path.abspath(
    os.environ.get('AETERNUS_DATA') or os.path.join(PROJECT_ROOT, 'data')
)
FRONTEND_DIR = os.path.abspath(
    os.environ.get('AETERNUS_FRONTEND') or os.path.join(PROJECT_ROOT, 'frontend')
)

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path='')
app.config['MAX_CONTENT_LENGTH'] = 128 * 1024
CORS(app, resources={r'/api/*': {'origins': [
    'http://127.0.0.1:5000',
    'http://localhost:5000',
]}})
os.makedirs(DATA_DIR, exist_ok=True)

# ── SQLite Setup ─────────────────────────────────────────────────
DB_PATH = os.path.join(DATA_DIR, 'aeternus_market_intelligence.db')
_db_lock = threading.Lock()

def _migrate_alerts_table():
    """Add new columns to alerts table if they don't exist."""
    new_cols = [
        ('name', 'TEXT DEFAULT ""'),
        ('alert_type', 'TEXT DEFAULT "price"'),
        ('indicator', 'TEXT DEFAULT ""'),
        ('condition', 'TEXT DEFAULT ""'),
        ('threshold', 'REAL DEFAULT 0'),
        ('note', 'TEXT DEFAULT ""'),
    ]
    with get_db() as db:
        existing = {row[1] for row in db.execute('PRAGMA table_info(alerts)').fetchall()}
        for col, col_def in new_cols:
            if col not in existing:
                try:
                    db.execute(f'ALTER TABLE alerts ADD COLUMN {col} {col_def}')
                    print(f'[DB] Migrated: added alerts.{col}')
                except Exception as e:
                    print(f'[DB] Migration skip {col}: {e}')


@contextmanager
def get_db():
    """Thread-safe SQLite connection with WAL mode for concurrency."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """Create all tables and migrate data from legacy JSON files."""
    with get_db() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS user_stocks (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                market    TEXT NOT NULL,
                code      TEXT NOT NULL,
                name      TEXT NOT NULL,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(market, code)
            );
            CREATE TABLE IF NOT EXISTS journal (
                id         INTEGER PRIMARY KEY,
                code       TEXT NOT NULL,
                name       TEXT NOT NULL,
                action     TEXT NOT NULL CHECK(action IN ('buy','sell')),
                price      REAL NOT NULL,
                shares     REAL NOT NULL,
                amount     REAL NOT NULL,
                date       TEXT NOT NULL,
                note       TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS alerts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                code       TEXT NOT NULL,
                name       TEXT DEFAULT '',
                alert_type TEXT NOT NULL DEFAULT 'price',
                target     REAL,
                direction  TEXT NOT NULL DEFAULT 'above',
                indicator  TEXT DEFAULT '',
                condition  TEXT DEFAULT '',
                threshold  REAL DEFAULT 0,
                note       TEXT DEFAULT '',
                triggered  INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );
            -- migrate old alerts table if needed

            CREATE INDEX IF NOT EXISTS idx_journal_code ON journal(code);
            CREATE INDEX IF NOT EXISTS idx_alerts_code  ON alerts(code);
            -- Add new columns to existing alerts table (migration)
            PRAGMA ignore_check_constraints = 1;

        ''')

    # ── Migrate legacy JSON → SQLite (one-time) ──────────────────
    _migrate_json_to_sqlite()

def _migrate_json_to_sqlite():
    """Silently migrate existing JSON files into SQLite (idempotent)."""
    def load_json_file(fname, default):
        p = os.path.join(DATA_DIR, fname)
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return default

    # user_stocks.json
    us = load_json_file('user_stocks.json', {})
    if us:
        with get_db() as db:
            for market, stocks in us.items():
                for i, s in enumerate(stocks):
                    try:
                        db.execute(
                            'INSERT OR IGNORE INTO user_stocks (market,code,name,sort_order) VALUES (?,?,?,?)',
                            (market, s['code'], s.get('name', s['code']), i)
                        )
                    except Exception:
                        pass
        os.rename(os.path.join(DATA_DIR, 'user_stocks.json'),
                  os.path.join(DATA_DIR, 'user_stocks.json.migrated'))

    # journal.json
    journal = load_json_file('journal.json', [])
    if journal:
        with get_db() as db:
            for t in journal:
                try:
                    db.execute(
                        'INSERT OR IGNORE INTO journal (id,code,name,action,price,shares,amount,date,note) VALUES (?,?,?,?,?,?,?,?,?)',
                        (t['id'], t['code'], t['name'], t['action'],
                         t['price'], t['shares'], t['amount'], t['date'], t.get('note',''))
                    )
                except Exception:
                    pass
        os.rename(os.path.join(DATA_DIR, 'journal.json'),
                  os.path.join(DATA_DIR, 'journal.json.migrated'))

    # alerts.json
    alerts = load_json_file('alerts.json', {})
    if alerts:
        with get_db() as db:
            for code, alert_list in alerts.items():
                for a in alert_list:
                    try:
                        db.execute(
                            'INSERT INTO alerts (code,target,direction,triggered) VALUES (?,?,?,?)',
                            (code, a['target'], a['direction'], int(a.get('triggered', False)))
                        )
                    except Exception:
                        pass
        os.rename(os.path.join(DATA_DIR, 'alerts.json'),
                  os.path.join(DATA_DIR, 'alerts.json.migrated'))

# Initialise DB on startup
init_db()

DEFAULT_STOCKS = {
    "taiwan": [
        {"code":"2330.TW","name":"台積電"},{"code":"2317.TW","name":"鴻海"},
        {"code":"2454.TW","name":"聯發科"},{"code":"2308.TW","name":"台達電"},
        {"code":"2882.TW","name":"國泰金"},{"code":"2412.TW","name":"中華電"},
        {"code":"2303.TW","name":"聯電"},{"code":"1301.TW","name":"台塑"},
        {"code":"2881.TW","name":"富邦金"},{"code":"0050.TW","name":"元大台灣50"}
    ],
    "japan": [
        {"code":"7203.T","name":"Toyota"},{"code":"9984.T","name":"SoftBank Group"},
        {"code":"6758.T","name":"Sony"},{"code":"8306.T","name":"Mitsubishi UFJ"},
        {"code":"9432.T","name":"NTT"},{"code":"6861.T","name":"Keyence"},
        {"code":"7974.T","name":"Nintendo"},{"code":"4063.T","name":"Shin-Etsu Chemical"},
        {"code":"8035.T","name":"Tokyo Electron"},{"code":"2644.T","name":"GX半導體ETF"}
    ],
    "shanghai": [
        {"code":"600519.SS","name":"貴州茅台"},{"code":"601318.SS","name":"中國平安"},
        {"code":"600036.SS","name":"招商銀行"},{"code":"601166.SS","name":"興業銀行"},
        {"code":"600276.SS","name":"恒瑞醫藥"},{"code":"600887.SS","name":"伊利股份"},
        {"code":"601688.SS","name":"華泰證券"},{"code":"600009.SS","name":"上海機場"},
        {"code":"600030.SS","name":"中信證券"},{"code":"510050.SS","name":"上證50ETF"}
    ]
}

# load_json / save_json removed — all storage now via SQLite (get_db)

def compute_indicators(df):
    c=df['Close'];h=df['High'];l=df['Low'];v=df['Volume']
    df['SMA20']=c.rolling(20).mean();df['SMA50']=c.rolling(50).mean()
    df['EMA12']=c.ewm(span=12,adjust=False).mean();df['EMA26']=c.ewm(span=26,adjust=False).mean()
    df['MACD']=df['EMA12']-df['EMA26'];df['Signal']=df['MACD'].ewm(span=9,adjust=False).mean()
    df['MACD_Hist']=df['MACD']-df['Signal']
    d=c.diff();g=d.where(d>0,0).rolling(14).mean();ls=(-d.where(d<0,0)).rolling(14).mean()
    df['RSI']=100-(100/(1+g/(ls+1e-10)))
    df['BB_mid']=c.rolling(20).mean();std=c.rolling(20).std()
    df['BB_upper']=df['BB_mid']+2*std;df['BB_lower']=df['BB_mid']-2*std
    l14=l.rolling(14).min();h14=h.rolling(14).max()
    rsv=(c-l14)/(h14-l14+1e-10)*100
    df['K']=rsv.ewm(com=2,adjust=False).mean();df['D']=df['K'].ewm(com=2,adjust=False).mean()
    df['WR']=(h14-c)/(h14-l14+1e-10)*-100
    obv=[0]
    for i in range(1,len(c)):
        obv.append(obv[-1]+(v.iloc[i] if c.iloc[i]>c.iloc[i-1] else -v.iloc[i] if c.iloc[i]<c.iloc[i-1] else 0))
    df['OBV']=obv
    # min_periods=1 ensures short-period data (1mo) still gets support/resistance values
    roll_n = min(20, max(5, len(c) // 3))
    df['Support']    = c.rolling(roll_n, min_periods=1).min()
    df['Resistance'] = c.rolling(roll_n, min_periods=1).max()
    # Anomaly: volume spike (>2x 20-day avg)
    try:
        vol_ma=v.rolling(20).mean()
        df['VOL_RATIO']=v/(vol_ma+1e-10)
        df['ANOMALY']=(df['VOL_RATIO']>2.0)
    except:
        df['VOL_RATIO']=1.0
        df['ANOMALY']=False
    return df

def sf(v,d=2):
    try:
        f=float(v)
        return None if (np.isnan(f) or np.isinf(f)) else round(f,d)
    except: return None

_cache = {}
_fail_counts = {}   # track consecutive failures per code
_RETRY_DELAYS = [2, 5, 15]  # seconds between retries

def get_df(code, period='3mo'):
    now = time.time()
    key = f"{code}_{period}"
    if key in _cache and now - _cache[key][0] < 300:
        return _cache[key][1]

    last_err = None
    for attempt, delay in enumerate([0] + _RETRY_DELAYS, start=1):
        if delay:
            time.sleep(delay)
        try:
            df = yf.Ticker(code).history(period=period)
            if df is not None and not df.empty:
                df.index = df.index.tz_localize(None)
                _cache[key] = (now, df)
                _fail_counts.pop(code, None)   # reset failure counter on success
                return df
        except Exception as e:
            last_err = e
            print(f"[retry {attempt}] Error fetching {code}: {e}")

    # All retries exhausted — record failure
    _fail_counts[code] = _fail_counts.get(code, 0) + 1
    print(f"[FAIL] {code} failed after {len(_RETRY_DELAYS)+1} attempts. "
          f"Consecutive failures: {_fail_counts[code]}. Last error: {last_err}")
    return None

# ── Intraday data fetcher (minute bars) ─────────────────────────
# yfinance interval→period mapping:
#   5m  → max 60d,  15m → max 60d,  60m → max 730d
_INTRADAY_CACHE = {}
_INTRADAY_TTL   = 120  # 2 minutes

def get_df_intraday(code, interval='5m'):
    now = time.time()
    key = f"{code}_{interval}"
    if key in _INTRADAY_CACHE and now - _INTRADAY_CACHE[key][0] < _INTRADAY_TTL:
        return _INTRADAY_CACHE[key][1]
    try:
        period_map = {'5m': '5d', '15m': '5d', '60m': '60d'}
        period = period_map.get(interval, '5d')
        df = yf.Ticker(code).history(period=period, interval=interval)
        if df is None or df.empty:
            return None
        df.index = pd.to_datetime(df.index)
        if df.index.tz is not None:
            df.index = df.index.tz_convert('Asia/Taipei').tz_localize(None)
        _INTRADAY_CACHE[key] = (now, df)
        return df
    except Exception as e:
        print(f"[intraday] Error {code} {interval}: {e}")
        return None


@app.route('/api/intraday', methods=['GET'])
def get_intraday():
    code     = request.args.get('code')
    interval = request.args.get('interval', '5m')
    if not code:
        return jsonify({'error': 'No code'}), 400
    if interval not in ('5m', '15m', '60m'):
        return jsonify({'error': 'Invalid interval'}), 400
    df = get_df_intraday(code, interval)
    if df is None or df.empty:
        return jsonify({'error': f'No intraday data for {code}'}), 404
    result = []
    for idx, row in df.iterrows():
        result.append({
            'time':   idx.strftime('%Y-%m-%d %H:%M'),
            'open':   sf(row['Open']),
            'high':   sf(row['High']),
            'low':    sf(row['Low']),
            'close':  sf(row['Close']),
            'volume': int(row['Volume']) if not pd.isna(row['Volume']) else 0,
        })
    return jsonify(result)


@app.route('/api/health', methods=['GET'])
def health_check():
    """Return connectivity status and recent failure counts."""
    return jsonify({
        'status': 'ok',
        'cached_symbols': len(_cache),
        'fail_counts': _fail_counts,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    })

def get_fundamentals(code):
    try:
        t=yf.Ticker(code)
        info=t.info
        return {
            'long_name':   info.get('longName') or info.get('shortName') or code,
            'currency':    info.get('currency') or info.get('financialCurrency'),
            'exchange':    info.get('exchange') or info.get('fullExchangeName'),
            'pe_ratio':    sf(info.get('trailingPE') or info.get('forwardPE')),
            'eps':         sf(info.get('trailingEps')),
            'dividend_yield': sf((info.get('dividendYield') or 0)*100,2),
            'market_cap':  info.get('marketCap'),
            'pb_ratio':    sf(info.get('priceToBook')),
            'revenue':     info.get('totalRevenue'),
            'profit_margin': sf((info.get('profitMargins') or 0)*100,2),
            'roe':         sf((info.get('returnOnEquity') or 0)*100,2),
            'debt_ratio':  sf(info.get('debtToEquity')),
            '52w_high':    sf(info.get('fiftyTwoWeekHigh')),
            '52w_low':     sf(info.get('fiftyTwoWeekLow')),
            'avg_volume':  info.get('averageVolume'),
            'sector':      info.get('sector','--'),
            'industry':    info.get('industry','--'),
            'description': (info.get('longBusinessSummary') or '')[:300],
        }
    except Exception as e:
        print(f"Fundamentals error {code}: {e}")
        return {}

def _build_indicators(df):
    """Pre-compute all indicators needed by backtest strategies."""
    c = df['Close']
    out = {}
    # RSI 14
    delta = c.diff()
    gain  = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss  = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    out['rsi'] = 100 - (100 / (1 + gain / (loss + 1e-10)))
    # MACD
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    out['macd']   = ema12 - ema26
    out['signal'] = out['macd'].ewm(span=9, adjust=False).mean()
    # Bollinger 20
    mid = c.rolling(20).mean(); std = c.rolling(20).std()
    out['bb_upper'] = mid + 2 * std
    out['bb_lower'] = mid - 2 * std
    # KD Stochastic
    lo14 = df['Low'].rolling(14).min(); hi14 = df['High'].rolling(14).max()
    out['k'] = 100 * (c - lo14) / (hi14 - lo14 + 1e-10)
    out['d'] = out['k'].rolling(3).mean()
    # Volume ratio
    out['vol_ratio'] = df['Volume'] / (df['Volume'].rolling(20).mean() + 1e-10)
    # MA families
    def ma(n): return c.rolling(n).mean()
    out['ma5']=ma(5); out['ma10']=ma(10); out['ma20']=ma(20)
    out['ma50']=ma(50); out['ma120']=ma(120)
    return out

def _eval_condition(cond, i, c, ind, params):
    """Return True if condition cond is met at bar i."""
    if i < 1: return False
    rsi   = ind['rsi']
    macd  = ind['macd'];  sig  = ind['signal']
    k     = ind['k'];     d    = ind['d']
    bbu   = ind['bb_upper']; bbl = ind['bb_lower']
    vr    = ind['vol_ratio']
    ma5   = ind['ma5'];  ma10 = ind['ma10']
    ma20  = ind['ma20']; ma50 = ind['ma50']; ma120 = ind['ma120']

    p  = lambda s: params.get(s)   # shorthand

    def v(series): return float(series.iloc[i])
    def pv(series): return float(series.iloc[i-1])

    if cond == 'rsi_oversold':
        th = float(p('rsi_os') or 30); return v(rsi) < th
    if cond == 'rsi_overbought':
        th = float(p('rsi_ob') or 70); return v(rsi) > th
    if cond == 'macd_cross_up':
        return v(macd) > v(sig) and pv(macd) <= pv(sig)
    if cond == 'macd_cross_down':
        return v(macd) < v(sig) and pv(macd) >= pv(sig)
    if cond == 'macd_above':
        return v(macd) > v(sig)
    if cond == 'macd_below':
        return v(macd) < v(sig)
    if cond == 'kd_cross_up':
        return v(k) > v(d) and pv(k) <= pv(d)
    if cond == 'kd_cross_down':
        return v(k) < v(d) and pv(k) >= pv(d)
    if cond == 'kd_oversold':
        th = float(p('kd_os') or 20); return v(k) < th and v(d) < th
    if cond == 'kd_overbought':
        th = float(p('kd_ob') or 80); return v(k) > th and v(d) > th
    s  = int(p('ma_short') or 20); l = int(p('ma_long') or 50)
    ms = c.rolling(s).mean(); ml = c.rolling(l).mean()
    if cond == 'ma_cross_up':
        return v(ms) > v(ml) and pv(ms) <= pv(ml)
    if cond == 'ma_cross_down':
        return v(ms) < v(ml) and pv(ms) >= pv(ml)
    if cond == 'price_above_ma20':
        return float(c.iloc[i]) > v(ma20)
    if cond == 'price_below_ma20':
        return float(c.iloc[i]) < v(ma20)
    if cond == 'price_above_ma50':
        return float(c.iloc[i]) > v(ma50)
    if cond == 'price_above_ma120':
        return float(c.iloc[i]) > v(ma120)
    if cond == 'bb_break_upper':
        return float(c.iloc[i]) > v(bbu) and float(c.iloc[i-1]) <= float(bbu.iloc[i-1])
    if cond == 'bb_break_lower':
        return float(c.iloc[i]) < v(bbl) and float(c.iloc[i-1]) >= float(bbl.iloc[i-1])
    if cond == 'bb_above_mid':
        mid = (v(bbu) + v(bbl)) / 2; return float(c.iloc[i]) > mid
    if cond == 'vol_spike':
        th = float(p('vol_th') or 1.5); return v(vr) > th
    if cond == 'vol_shrink':
        return v(vr) < 0.7
    return False

def run_backtest(df, strategy, params):
    df  = df.copy(); c = df['Close']
    ind = _build_indicators(df)
    buy_conds  = []
    sell_conds = []

    if strategy == 'custom':
        # params['buy_conds'] and params['sell_conds'] are lists of condition ids
        buy_conds  = params.get('buy_conds',  [])
        sell_conds = params.get('sell_conds', [])
        if not buy_conds:  buy_conds  = ['macd_cross_up']
        if not sell_conds: sell_conds = ['macd_cross_down']
    elif strategy == 'ma_cross':
        buy_conds  = ['ma_cross_up']
        sell_conds = ['ma_cross_down']
    elif strategy == 'rsi':
        buy_conds  = ['rsi_oversold']
        sell_conds = ['rsi_overbought']
    elif strategy == 'macd':
        buy_conds  = ['macd_cross_up']
        sell_conds = ['macd_cross_down']
    elif strategy == 'bollinger':
        buy_conds  = ['bb_break_lower']
        sell_conds = ['bb_break_upper']

    signals = pd.Series(0, index=df.index)
    for i in range(1, len(df)):
        buy_ok  = buy_conds  and all(_eval_condition(cond, i, c, ind, params) for cond in buy_conds)
        sell_ok = sell_conds and all(_eval_condition(cond, i, c, ind, params) for cond in sell_conds)
        if buy_ok:  signals.iloc[i] =  1
        if sell_ok: signals.iloc[i] = -1

    trades = []; position = None
    for i in range(len(df)):
        sig   = signals.iloc[i]
        price = float(c.iloc[i])
        date  = df.index[i].strftime('%Y-%m-%d')
        if sig == 1 and position is None:
            position = {'entry_date': date, 'entry_price': price}
        elif sig == -1 and position is not None:
            pnl = (price - position['entry_price']) / position['entry_price'] * 100
            trades.append({'entry_date': position['entry_date'], 'entry_price': round(position['entry_price'], 2),
                           'exit_date': date, 'exit_price': round(price, 2),
                           'pnl_pct': round(pnl, 2), 'win': pnl > 0})
            position = None
    if position is not None:
        lp = float(c.iloc[-1])
        pnl = (lp - position['entry_price']) / position['entry_price'] * 100
        trades.append({'entry_date': position['entry_date'], 'entry_price': round(position['entry_price'], 2),
                       'exit_date': df.index[-1].strftime('%Y-%m-%d'), 'exit_price': round(lp, 2),
                       'pnl_pct': round(pnl, 2), 'win': pnl > 0, 'open': True})

    total = len(trades); wins = sum(1 for t in trades if t['win'])
    losses = total - wins
    return {
        'stats': {
            'total_trades': total,
            'win_rate':     round(wins / total * 100, 1) if total else 0,
            'total_return': round(sum(t['pnl_pct'] for t in trades), 2) if total else 0,
            'avg_win':      round(np.mean([t['pnl_pct'] for t in trades if t['win']]), 2) if wins else 0,
            'avg_loss':     round(np.mean([t['pnl_pct'] for t in trades if not t['win']]), 2) if losses else 0,
            'wins': wins, 'losses': losses,
        },
        'trades':      trades[-30:],
        'buy_points':  [{'date': df.index[i].strftime('%Y-%m-%d'), 'price': float(c.iloc[i])}
                        for i in range(len(signals)) if signals.iloc[i] == 1],
        'sell_points': [{'date': df.index[i].strftime('%Y-%m-%d'), 'price': float(c.iloc[i])}
                        for i in range(len(signals)) if signals.iloc[i] == -1],
    }

def analyze_signals(df):
    df=compute_indicators(df.copy());last=df.iloc[-1];prev=df.iloc[-2] if len(df)>1 else last
    close=float(last['Close']);signals=[];score=0
    rsi=sf(last['RSI'])
    if rsi:
        if rsi<30: signals.append({'indicator':'RSI','signal':'rsi_buy','detail':f'RSI={rsi:.1f}','type':'buy'});score+=2
        elif rsi<45: signals.append({'indicator':'RSI','signal':'rsi_bull','detail':f'RSI={rsi:.1f}','type':'weak_buy'});score+=1
        elif rsi>70: signals.append({'indicator':'RSI','signal':'rsi_sell','detail':f'RSI={rsi:.1f}','type':'sell'});score-=2
        elif rsi>55: signals.append({'indicator':'RSI','signal':'rsi_bear','detail':f'RSI={rsi:.1f}','type':'weak_sell'});score-=1
        else: signals.append({'indicator':'RSI','signal':'中性','detail':f'RSI={rsi:.1f} 中性區間','type':'neutral'})
    macd=sf(last['MACD'],4);sig=sf(last['Signal'],4);pm=sf(prev['MACD'],4);ps=sf(prev['Signal'],4)
    if macd is not None and sig is not None:
        if macd>sig and pm<=ps: signals.append({'indicator':'MACD','signal':'macd_buy','detail':'','type':'buy'});score+=2
        elif macd<sig and pm>=ps: signals.append({'indicator':'MACD','signal':'macd_sell','detail':'','type':'sell'});score-=2
        elif macd>sig: signals.append({'indicator':'MACD','signal':'macd_bull','detail':'','type':'weak_buy'});score+=1
        else: signals.append({'indicator':'MACD','signal':'macd_bear','detail':'','type':'weak_sell'});score-=1
    s20=sf(last['SMA20']);s50=sf(last['SMA50']);ps20=sf(prev['SMA20']);ps50=sf(prev['SMA50'])
    if s20 and s50:
        if s20>s50 and ps20<=ps50: signals.append({'indicator':'MA','signal':'ma_buy','detail':f'SMA20({s20})>SMA50({s50})','type':'buy'});score+=2
        elif s20<s50 and ps20>=ps50: signals.append({'indicator':'MA','signal':'ma_sell','detail':f'SMA20({s20})<SMA50({s50})','type':'sell'});score-=2
        elif s20>s50: signals.append({'indicator':'MA','signal':'ma_bull','detail':f'SMA20({s20})>SMA50({s50})','type':'weak_buy'});score+=1
        else: signals.append({'indicator':'MA','signal':'ma_bear','detail':f'SMA20({s20})<SMA50({s50})','type':'weak_sell'});score-=1
    bbu=sf(last['BB_upper']);bbl=sf(last['BB_lower']);bbm=sf(last['BB_mid'])
    if bbu and bbl:
        if close<bbl: signals.append({'indicator':'BB','signal':'bb_buy','detail':f'<{bbl}','type':'buy'});score+=2
        elif close>bbu: signals.append({'indicator':'BB','signal':'bb_sell','detail':f'>{bbu}','type':'sell'});score-=2
        elif close>bbm: signals.append({'indicator':'BB','signal':'bb_bull','detail':'','type':'weak_buy'});score+=1
        else: signals.append({'indicator':'BB','signal':'bb_bear','detail':'','type':'weak_sell'});score-=1
    k=sf(last['K']);d=sf(last['D']);pk=sf(prev['K']);pd_=sf(prev['D'])
    if k and d:
        if k>d and pk<=pd_: signals.append({'indicator':'KD','signal':'kd_buy','detail':f'K={k:.1f} D={d:.1f}','type':'buy'});score+=1
        elif k<d and pk>=pd_: signals.append({'indicator':'KD','signal':'kd_sell','detail':f'K={k:.1f} D={d:.1f}','type':'sell'});score-=1
        elif k<20: signals.append({'indicator':'KD','signal':'kd_buy','detail':f'K={k:.1f}','type':'buy'});score+=1
        elif k>80: signals.append({'indicator':'KD','signal':'kd_sell','detail':f'K={k:.1f}','type':'sell'});score-=1
    # Anomaly check
    vr=sf(last['VOL_RATIO'],1)
    if vr and vr>2.0:
        cp=float(last['Close']);pp=float(prev['Close'])
        direction='放量上漲' if cp>pp else '放量下跌'
        signals.append({'indicator':'VOL','signal':'vol_spike','detail':f'{vr}x/{direction}','type':'warning'})
    if score>=4: rec={'action':'強力買入','color':'#00e87a','score':score}
    elif score>=2: rec={'action':'買入','color':'#5eead4','score':score}
    elif score>=1: rec={'action':'偏多觀望','color':'#86efac','score':score}
    elif score<=-4: rec={'action':'強力賣出','color':'#ff3d5a','score':score}
    elif score<=-2: rec={'action':'賣出','color':'#fb7185','score':score}
    elif score<=-1: rec={'action':'偏空觀望','color':'#fca5a5','score':score}
    else: rec={'action':'中性觀望','color':'#94a3b8','score':score}
    return {'signals':signals,'recommendation':rec}

# ── ROUTES ──────────────────────────────────────────────────────
@app.route('/')
def index(): return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/vendor/<path:filename>')
def vendor(filename):
    return send_from_directory(os.path.join(FRONTEND_DIR, 'vendor'), filename)

@app.route('/api/stocks/<market>',methods=['GET'])
def get_market_stocks(market):
    with get_db() as db:
        rows = db.execute(
            'SELECT code,name FROM user_stocks WHERE market=? ORDER BY sort_order,id',
            (market,)
        ).fetchall()
    user_stocks = [{'code': r['code'], 'name': r['name']} for r in rows]
    return jsonify(DEFAULT_STOCKS.get(market, []) + user_stocks)

@app.route('/api/stocks/<market>/reorder',methods=['POST'])
def reorder_stocks(market):
    order = request.json.get('order', [])
    with get_db() as db:
        for i, code in enumerate(order):
            db.execute(
                'UPDATE user_stocks SET sort_order=? WHERE market=? AND code=?',
                (i, market, code)
            )
    return jsonify({'success': True})

@app.route('/api/quote',methods=['GET'])
def get_quote():
    code=request.args.get('code')
    if not code: return jsonify({'error':'No code'}),400
    try:
        df=get_df(code,'5d')
        if df is None or df.empty: return jsonify({'error':f'No data for {code}'}),404
        last=df.iloc[-1];prev=df.iloc[-2] if len(df)>1 else last
        price=float(last['Close']);pc=float(prev['Close']);chg=price-pc;pct=(chg/pc*100) if pc else 0
        return jsonify({'code':code,'price':round(price,2),'volume':int(last['Volume']),
            'change':round(chg,2),'change_pct':round(pct,2),
            'high':round(float(last['High']),2),'low':round(float(last['Low']),2),'open':round(float(last['Open']),2)})
    except Exception as e: return jsonify({'error':str(e)}),500

@app.route('/api/history',methods=['GET'])
def get_history():
    code=request.args.get('code');period=request.args.get('period','3mo')
    if not code: return jsonify({'error':'No code'}),400
    try:
        df=get_df(code,period)
        if df is None or df.empty: return jsonify({'error':f'No data for {code}'}),404
        df=compute_indicators(df);result=[]
        for idx,row in df.iterrows():
            result.append({'date':idx.strftime('%Y-%m-%d'),
                'open':sf(row['Open']),'high':sf(row['High']),'low':sf(row['Low']),'close':sf(row['Close']),'volume':int(row['Volume']),
                'SMA20':sf(row['SMA20']),'SMA50':sf(row['SMA50']),'EMA12':sf(row['EMA12']),'EMA26':sf(row['EMA26']),
                'MACD':sf(row['MACD'],4),'Signal':sf(row['Signal'],4),'MACD_Hist':sf(row['MACD_Hist'],4),
                'RSI':sf(row['RSI']),'BB_upper':sf(row['BB_upper']),'BB_mid':sf(row['BB_mid']),'BB_lower':sf(row['BB_lower']),
                'K':sf(row['K']),'D':sf(row['D']),'WR':sf(row['WR']),'OBV':sf(row['OBV'],0),
                'Support':sf(row['Support']),'Resistance':sf(row['Resistance']),
                'vol_ratio':sf(row['VOL_RATIO'],2),'anomaly':bool(row['ANOMALY'])})
        return jsonify(result)
    except Exception as e: return jsonify({'error':str(e)}),500

@app.route('/api/fundamentals',methods=['GET'])
def fundamentals():
    code=request.args.get('code')
    if not code: return jsonify({'error':'No code'}),400
    # Cache fundamentals for 1 hour
    key=f"fund_{code}";now=time.time()
    if key in _cache and now-_cache[key][0]<3600: return jsonify(_cache[key][1])
    data=get_fundamentals(code);_cache[key]=(now,data)
    return jsonify(data)

@app.route('/api/analysis',methods=['GET'])
def get_analysis():
    code=request.args.get('code')
    if not code: return jsonify({'error':'No code'}),400
    try:
        df=get_df(code,'3mo')
        if df is None or df.empty: return jsonify({'error':f'No data for {code}'}),404
        return jsonify(analyze_signals(df))
    except Exception as e: return jsonify({'error':str(e)}),500

@app.route('/api/backtest',methods=['POST'])
def backtest():
    data=request.json;code=data.get('code');strategy=data.get('strategy','ma_cross')
    period=data.get('period','1y');params=data.get('params',{})
    if not code: return jsonify({'error':'No code'}),400
    try:
        df=get_df(code,period)
        if df is None or df.empty: return jsonify({'error':f'No data for {code}'}),404
        return jsonify(run_backtest(df,strategy,params))
    except Exception as e: return jsonify({'error':str(e)}),500

# ── TRADE JOURNAL ────────────────────────────────────────────────
@app.route('/api/journal',methods=['GET'])
def get_journal():
    with get_db() as db:
        rows = db.execute('SELECT * FROM journal ORDER BY date DESC, id DESC').fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/journal',methods=['POST'])
def add_trade():
    t = request.json
    required = ['code','name','action','price','shares','date']
    if not all(t.get(k) for k in required): return jsonify({'error':'Missing fields'}),400
    trade_id = int(time.time() * 1000)
    amount   = round(float(t['price']) * float(t['shares']), 2)
    with get_db() as db:
        db.execute(
            'INSERT INTO journal (id,code,name,action,price,shares,amount,date,note) VALUES (?,?,?,?,?,?,?,?,?)',
            (trade_id, t['code'], t['name'], t['action'],
             float(t['price']), float(t['shares']), amount, t['date'], t.get('note',''))
        )
    trade = {'id':trade_id,'code':t['code'],'name':t['name'],'action':t['action'],
             'price':float(t['price']),'shares':float(t['shares']),'amount':amount,
             'date':t['date'],'note':t.get('note','')}
    return jsonify({'success':True,'trade':trade})

@app.route('/api/journal/<int:trade_id>',methods=['DELETE'])
def delete_trade(trade_id):
    with get_db() as db:
        db.execute('DELETE FROM journal WHERE id=?', (trade_id,))
    return jsonify({'success':True})

@app.route('/api/journal/pnl',methods=['GET'])
def get_pnl():
    with get_db() as db:
        rows = db.execute('SELECT * FROM journal ORDER BY date ASC, id ASC').fetchall()
    journal = [dict(r) for r in rows]
    positions = {}
    for t in journal:
        code = t['code']
        if code not in positions:
            positions[code] = {'code':code,'name':t['name'],'shares':0,'avg_cost':0,'realized':0}
        p = positions[code]
        if t['action'] == 'buy':
            total_cost = p['avg_cost']*p['shares'] + t['price']*t['shares']
            p['shares'] += t['shares']
            p['avg_cost'] = total_cost / p['shares'] if p['shares'] > 0 else 0
        elif t['action'] == 'sell':
            realized = (t['price'] - p['avg_cost']) * min(t['shares'], p['shares'])
            p['realized'] += realized
            p['shares'] = max(0, p['shares'] - t['shares'])
            if p['shares'] == 0: p['avg_cost'] = 0
    result = []
    for code, p in positions.items():
        if p['shares'] > 0 or p['realized'] != 0:
            current_price = None
            try:
                df = get_df(code, '5d')
                if df is not None and not df.empty:
                    current_price = round(float(df.iloc[-1]['Close']), 2)
            except: pass
            unrealized = (current_price - p['avg_cost']) * p['shares'] if current_price and p['shares'] > 0 else 0
            result.append({'code':code,'name':p['name'],'shares':round(p['shares'],2),
                'avg_cost':round(p['avg_cost'],2),'current_price':current_price,
                'market_value':round(current_price*p['shares'],2) if current_price else None,
                'unrealized':round(unrealized,2),'realized':round(p['realized'],2),
                'total_pnl':round(unrealized+p['realized'],2),
                'pnl_pct':round(unrealized/((p['avg_cost']*p['shares']) or 1)*100,2) if p['shares']>0 else 0})
    return jsonify(result)

@app.route('/api/stocks/<market>',methods=['POST'])
def add_stock(market):
    data = request.json
    code = data.get('code','').strip(); name = data.get('name', code).strip()
    if not code: return jsonify({'error':'No code'}),400
    existing = [s['code'] for s in DEFAULT_STOCKS.get(market,[])]
    with get_db() as db:
        existing += [r['code'] for r in db.execute(
            'SELECT code FROM user_stocks WHERE market=?', (market,)).fetchall()]
        if code in existing: return jsonify({'error':'Stock already exists'}),409
        db.execute('INSERT INTO user_stocks (market,code,name) VALUES (?,?,?)', (market,code,name))
    return jsonify({'success':True})

@app.route('/api/stocks/<market>/<path:code>',methods=['DELETE'])
def remove_stock(market, code):
    with get_db() as db:
        db.execute('DELETE FROM user_stocks WHERE market=? AND code=?', (market, code))
    return jsonify({'success':True})


def _check_one_alert(alert, quote_price, df=None):
    """
    Check if a single alert condition is met.
    Returns True if triggered, False otherwise.
    """
    atype = alert.get('alert_type', 'price')
    direction = alert.get('direction', 'above')
    threshold = float(alert.get('threshold') or 0)

    if atype == 'price':
        target = alert.get('target')
        if target is None: return False
        target = float(target)
        if direction == 'above': return quote_price >= target
        if direction == 'below': return quote_price <= target

    if df is None or df.empty: return False

    try:
        df2 = compute_indicators(df.copy())
        last = df2.iloc[-1]
        prev = df2.iloc[-2] if len(df2) > 1 else last

        if atype == 'rsi':
            rsi = sf(last['RSI'])
            if rsi is None: return False
            if direction == 'above': return rsi >= threshold   # overbought
            if direction == 'below': return rsi <= threshold   # oversold

        elif atype == 'macd':
            macd = sf(last['MACD'], 4); sig = sf(last['Signal'], 4)
            pm   = sf(prev['MACD'], 4); ps  = sf(prev['Signal'], 4)
            if None in (macd, sig, pm, ps): return False
            if direction == 'cross_up':   return macd > sig and pm <= ps
            if direction == 'cross_down': return macd < sig and pm >= ps
            if direction == 'above':      return macd > sig
            if direction == 'below':      return macd < sig

        elif atype == 'ma':
            s20 = sf(last['SMA20']); s50 = sf(last['SMA50'])
            ps20= sf(prev['SMA20']); ps50= sf(prev['SMA50'])
            if None in (s20, s50, ps20, ps50): return False
            if direction == 'cross_up':   return s20 > s50 and ps20 <= ps50
            if direction == 'cross_down': return s20 < s50 and ps20 >= ps50
            if direction == 'above':      return s20 > s50
            if direction == 'below':      return s20 < s50

        elif atype == 'kd':
            k = sf(last['K']); d_ = sf(last['D'])
            pk= sf(prev['K']); pd= sf(prev['D'])
            if None in (k, d_, pk, pd): return False
            if direction == 'cross_up':   return k > d_ and pk <= pd
            if direction == 'cross_down': return k < d_ and pk >= pd
            if direction == 'above':      return k >= threshold
            if direction == 'below':      return k <= threshold

        elif atype == 'bb':
            close = float(last['Close'])
            bbu = sf(last['BB_upper']); bbl = sf(last['BB_lower'])
            if None in (bbu, bbl): return False
            if direction == 'above': return close >= bbu    # breakout upper
            if direction == 'below': return close <= bbl    # breakdown lower

        elif atype == 'volume':
            vr = sf(last['VOL_RATIO'], 1)
            if vr is None: return False
            return vr >= threshold

    except Exception as e:
        print(f"[alert check] error: {e}")
    return False


@app.route('/api/alerts/check', methods=['POST'])
def check_alerts_now():
    """Manually trigger alert checking for a specific stock."""
    code = (request.json or {}).get('code')
    if not code: return jsonify({'error':'No code'}), 400
    try:
        with get_db() as db:
            rows = db.execute(
                'SELECT * FROM alerts WHERE code=? AND triggered=0', (code,)
            ).fetchall()
        if not rows: return jsonify({'triggered': []})

        quote_price = None
        df = None
        triggered = []
        for row in rows:
            alert = dict(row)
            atype = alert.get('alert_type', 'price')
            if quote_price is None:
                try:
                    import yfinance as yf
                    t_ = yf.Ticker(code)
                    info = t_.fast_info
                    quote_price = float(info.last_price or 0)
                except: quote_price = 0
            if df is None and atype != 'price':
                df = get_df(code, '3mo')
                if df is not None: df = compute_indicators(df.copy())

            if _check_one_alert(alert, quote_price, df):
                with get_db() as db:
                    db.execute('UPDATE alerts SET triggered=1 WHERE id=?', (alert['id'],))
                triggered.append(alert['id'])

        return jsonify({'triggered': triggered, 'count': len(triggered)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/alerts',methods=['GET'])
def get_alerts():
    with get_db() as db:
        rows = db.execute('SELECT * FROM alerts ORDER BY id').fetchall()
    result = {}
    for r in rows:
        r = dict(r)
        code = r['code']
        if code not in result: result[code] = []
        result[code].append({
            'id':         r['id'],
            'alert_type': r.get('alert_type','price'),
            'target':     r.get('target'),
            'direction':  r.get('direction','above'),
            'indicator':  r.get('indicator',''),
            'condition':  r.get('condition',''),
            'threshold':  r.get('threshold',0),
            'note':       r.get('note',''),
            'triggered':  bool(r['triggered']),
            'name':       r.get('name',''),
        })
    return jsonify(result)

@app.route('/api/alerts',methods=['POST'])
def set_alert():
    data       = request.json or {}
    code       = data.get('code')
    name       = data.get('name', '')
    alert_type = data.get('alert_type', 'price')   # price | rsi | macd | ma | kd | volume
    target     = data.get('target')
    direction  = data.get('direction', 'above')     # above | below | cross_up | cross_down
    indicator  = data.get('indicator', '')
    condition  = data.get('condition', '')
    threshold  = data.get('threshold', 0)
    note       = data.get('note', '')

    if not code: return jsonify({'error':'Missing code'}), 400
    if alert_type == 'price' and target is None:
        return jsonify({'error':'Missing target price'}), 400

    with get_db() as db:
        db.execute(
            'INSERT INTO alerts (code,name,alert_type,target,direction,indicator,condition,threshold,note) '
            'VALUES (?,?,?,?,?,?,?,?,?)',
            (code, name, alert_type,
             float(target) if target is not None else None,
             direction, indicator, condition,
             float(threshold) if threshold else 0, note)
        )
    return jsonify({'success': True})

@app.route('/api/alerts/<path:alert_id>', methods=['DELETE'])
def delete_alert(alert_id):
    with get_db() as db:
        # Try numeric ID first, fallback to code (backward compat)
        if alert_id.isdigit():
            db.execute('DELETE FROM alerts WHERE id=?', (int(alert_id),))
        else:
            db.execute('DELETE FROM alerts WHERE code=?', (alert_id,))
    return jsonify({'success': True})

# ── COMPARE ─────────────────────────────────────────────────────
@app.route('/api/compare', methods=['POST'])
def compare():
    data = request.json
    codes   = data.get('codes', [])[:6]   # max 6 stocks
    period  = data.get('period', '3mo')
    metric  = data.get('metric', 'close')  # close | return | volume
    if not codes: return jsonify({'error': 'No codes'}), 400
    result = {}
    for code in codes:
        try:
            df = get_df(code, period)
            if df is None or df.empty: continue
            df = compute_indicators(df)
            # Normalize price to % return from first day
            closes = df['Close'].tolist()
            base   = closes[0] if closes[0] else 1
            dates  = [d.strftime('%Y-%m-%d') for d in df.index]
            if metric == 'return':
                values = [round((c - base) / base * 100, 2) for c in closes]
            elif metric == 'volume':
                values = [int(v) for v in df['Volume'].tolist()]
            elif metric == 'rsi':
                values = [sf(v) for v in df['RSI'].tolist()]
            else:
                values = [sf(c) for c in closes]
            last = df.iloc[-1]; prev = df.iloc[-2] if len(df) > 1 else last
            price = float(last['Close']); pc = float(prev['Close'])
            result[code] = {
                'dates':  dates,
                'values': values,
                'price':  round(price, 2),
                'change_pct': round((price - pc) / pc * 100, 2) if pc else 0,
                'rsi':    sf(last['RSI']) if 'RSI' in last else None,
                'vol_ratio': sf(last['VOL_RATIO'], 1) if 'VOL_RATIO' in last else None,
                'anomaly': bool(last['ANOMALY']) if 'ANOMALY' in last else False,
            }
        except Exception as e:
            print(f"Compare error {code}: {e}")
    return jsonify(result)

# ── SCANNER ──────────────────────────────────────────────────────
@app.route('/api/scan', methods=['POST'])
def scan():
    data       = request.json
    market     = data.get('market', 'taiwan')
    conditions = data.get('conditions', {})
    # Collect all stocks to scan
    with get_db() as db:
        user_rows = [dict(r) for r in db.execute(
            'SELECT code, name FROM user_stocks WHERE market=?', (market,)).fetchall()]
    all_stocks = DEFAULT_STOCKS.get(market, []) + user_rows
    results = []
    for s in all_stocks:
        code = s['code']
        try:
            df = get_df(code, '3mo')
            if df is None or df.empty: continue
            df  = compute_indicators(df)
            last = df.iloc[-1]; prev = df.iloc[-2] if len(df) > 1 else last
            price = float(last['Close']); pc = float(prev['Close'])
            chg_pct = round((price - pc) / pc * 100, 2) if pc else 0
            rsi     = sf(last['RSI'])
            k       = sf(last['K']); d_ = sf(last['D'])
            macd    = sf(last['MACD'], 4); sig = sf(last['Signal'], 4)
            pm      = sf(prev['MACD'], 4); ps  = sf(prev['Signal'], 4)
            vr      = sf(last['VOL_RATIO'], 1)
            s20     = sf(last['SMA20']); s50 = sf(last['SMA50'])
            bbu     = sf(last['BB_upper']); bbl = sf(last['BB_lower'])

            # Evaluate conditions
            matched = []
            failed  = []

            def chk(cond_key, ok, label):
                (matched if ok else failed).append(label)

            if 'rsi_oversold' in conditions:
                v = float(conditions['rsi_oversold'])
                chk('rsi_oversold', rsi and rsi < v, f'RSI<{v}({rsi:.1f})')
            if 'rsi_overbought' in conditions:
                v = float(conditions['rsi_overbought'])
                chk('rsi_overbought', rsi and rsi > v, f'RSI>{v}({rsi:.1f})')
            if 'macd_golden' in conditions and conditions['macd_golden']:
                ok = macd and sig and pm and ps and macd > sig and pm <= ps
                chk('macd_golden', ok, 'MACD金叉')
            if 'macd_dead' in conditions and conditions['macd_dead']:
                ok = macd and sig and pm and ps and macd < sig and pm >= ps
                chk('macd_dead', ok, 'MACD死叉')
            if 'kd_golden' in conditions and conditions['kd_golden']:
                pk = sf(prev['K']); pd_ = sf(prev['D'])
                ok = k and d_ and pk and pd_ and k > d_ and pk <= pd_
                chk('kd_golden', ok, 'KD金叉')
            if 'ma_golden' in conditions and conditions['ma_golden']:
                ps20_ = sf(prev['SMA20']); ps50_ = sf(prev['SMA50'])
                ok = s20 and s50 and ps20_ and ps50_ and s20 > s50 and ps20_ <= ps50_
                chk('ma_golden', ok, '均線金叉')
            if 'above_ma20' in conditions and conditions['above_ma20']:
                chk('above_ma20', s20 and price > s20, f'股價>{s20}(SMA20)')
            if 'below_bb_lower' in conditions and conditions['below_bb_lower']:
                chk('below_bb_lower', bbl and price < bbl, f'跌破布林下軌({bbl})')
            if 'volume_spike' in conditions:
                v = float(conditions['volume_spike'])
                chk('volume_spike', vr and vr >= v, f'量比≥{v}({vr}x)')
            if 'change_pct_min' in conditions:
                v = float(conditions['change_pct_min'])
                chk('change_pct_min', chg_pct >= v, f'漲幅≥{v}%({chg_pct}%)')
            if 'change_pct_max' in conditions:
                v = float(conditions['change_pct_max'])
                chk('change_pct_max', chg_pct <= v, f'漲幅≤{v}%({chg_pct}%)')

            if not matched and not failed: continue
            if failed: continue  # All conditions must match
            results.append({
                'code': code, 'name': s['name'],
                'price': round(price, 2), 'change_pct': chg_pct,
                'rsi': rsi, 'vol_ratio': vr,
                'matched': matched,
                'anomaly': bool(last['ANOMALY']),
            })
        except Exception as e:
            print(f"Scan error {code}: {e}")
    # Sort by abs change desc
    results.sort(key=lambda x: abs(x['change_pct']), reverse=True)
    return jsonify(results)

# ── ANOMALY FEED ─────────────────────────────────────────────────
@app.route('/api/anomalies', methods=['GET'])
def get_anomalies():
    market = request.args.get('market', 'taiwan')
    with get_db() as db:
        user_rows = [dict(r) for r in db.execute(
            'SELECT code, name FROM user_stocks WHERE market=?', (market,)).fetchall()]
    all_stocks = DEFAULT_STOCKS.get(market, []) + user_rows
    results = []
    for s in all_stocks:
        try:
            df = get_df(s['code'], '1mo')
            if df is None or df.empty: continue
            df = compute_indicators(df)
            # Find anomaly days in last 5 trading days
            recent = df.tail(5)
            for idx, row in recent.iterrows():
                if bool(row['ANOMALY']):
                    close = float(row['Close'])
                    prev_close = float(df.loc[:idx]['Close'].iloc[-2]) if len(df.loc[:idx]) > 1 else close
                    direction = '放量上漲 ▲' if close >= prev_close else '放量下跌 ▼'
                    results.append({
                        'code': s['code'], 'name': s['name'],
                        'date': idx.strftime('%Y-%m-%d'),
                        'price': round(close, 2),
                        'vol_ratio': sf(row['VOL_RATIO'], 1),
                        'direction': direction,
                        'change_pct': round((close - prev_close) / prev_close * 100, 2) if prev_close else 0,
                    })
        except: pass
    results.sort(key=lambda x: x['date'], reverse=True)
    return jsonify(results[:30])

# ── RISK ANALYSIS (Beta, Volatility, Sharpe) ─────────────────────
BENCHMARK = {
    'taiwan':   '^TWII',    # Taiwan Weighted Index
    'japan':    '^N225',    # Nikkei 225
    'shanghai': '000001.SS' # Shanghai Composite
}

@app.route('/api/risk', methods=['GET'])
def get_risk():
    code   = request.args.get('code')
    market = request.args.get('market', 'taiwan')
    period = request.args.get('period', '1y')
    if not code: return jsonify({'error': 'No code'}), 400

    cache_key = f"risk_{code}_{period}"
    now = time.time()
    if cache_key in _cache and now - _cache[cache_key][0] < 3600:
        return jsonify(_cache[cache_key][1])

    try:
        # Fetch stock and benchmark
        df_stock = get_df(code, period)
        bench_code = BENCHMARK.get(market, '^TWII')
        df_bench = get_df(bench_code, period)

        if df_stock is None or df_stock.empty:
            return jsonify({'error': f'No data for {code}'}), 404

        # Daily returns
        stock_ret = df_stock['Close'].pct_change().dropna()

        # Annualised volatility
        vol_daily  = float(stock_ret.std())
        vol_annual = round(vol_daily * np.sqrt(252) * 100, 2)

        # Max drawdown
        cumulative = (1 + stock_ret).cumprod()
        rolling_max = cumulative.cummax()
        drawdown = (cumulative - rolling_max) / rolling_max
        max_drawdown = round(float(drawdown.min()) * 100, 2)

        # Sharpe ratio (risk-free = 2%)
        rf_daily   = 0.02 / 252
        excess_ret = stock_ret - rf_daily
        sharpe     = round(float(excess_ret.mean() / (stock_ret.std() + 1e-10) * np.sqrt(252)), 2)

        # Beta vs benchmark
        beta = None
        corr = None
        bench_ret_series = None
        if df_bench is not None and not df_bench.empty:
            bench_ret = df_bench['Close'].pct_change().dropna()
            # Align dates
            aligned = pd.concat([stock_ret, bench_ret], axis=1, join='inner')
            aligned.columns = ['stock', 'bench']
            if len(aligned) > 20:
                cov   = aligned.cov().iloc[0, 1]
                var_b = float(aligned['bench'].var())
                beta  = round(cov / (var_b + 1e-10), 2)
                corr  = round(float(aligned.corr().iloc[0, 1]), 2)
                bench_ret_series = aligned['bench']

        # Total return
        total_ret = round(float((df_stock['Close'].iloc[-1] / df_stock['Close'].iloc[0] - 1) * 100), 2)

        # Monthly returns heatmap data
        monthly = stock_ret.copy()
        monthly.index = pd.to_datetime(monthly.index)
        monthly_grouped = monthly.groupby([monthly.index.year, monthly.index.month]).sum() * 100
        monthly_data = []
        for (yr, mo), val in monthly_grouped.items():
            monthly_data.append({'year': int(yr), 'month': int(mo), 'return': round(float(val), 2)})

        # Return distribution buckets
        bins = [-np.inf, -4, -2, -1, 0, 1, 2, 4, np.inf]
        labels = ['<-4%', '-4~-2%', '-2~-1%', '-1~0%', '0~1%', '1~2%', '2~4%', '>4%']
        counts, _ = np.histogram(stock_ret * 100, bins=bins)
        dist = [{'range': labels[i], 'count': int(counts[i])} for i in range(len(labels))]

        result = {
            'code': code,
            'period': period,
            'total_return': total_ret,
            'vol_annual': vol_annual,
            'max_drawdown': max_drawdown,
            'sharpe': sharpe,
            'beta': beta,
            'correlation': corr,
            'benchmark': bench_code,
            'trading_days': len(stock_ret),
            'monthly_returns': monthly_data,
            'return_dist': dist,
            # Cumulative return series for chart
            'cum_returns': [
                {'date': d.strftime('%Y-%m-%d'), 'value': round(float(v) * 100 - 100, 2)}
                for d, v in zip(df_stock['Close'].index[1:],
                                (df_stock['Close'].pct_change().dropna() + 1).cumprod())
            ]
        }
        _cache[cache_key] = (now, result)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── HEATMAP: sector/industry breakdown ────────────────────────────
# Predefined sector mapping for the three markets
SECTOR_STOCKS = {
    'taiwan': {
        '半導體': [
            {'code':'2330.TW','name':'台積電'},
            {'code':'2303.TW','name':'聯電'},
            {'code':'2454.TW','name':'聯發科'},
            {'code':'3711.TW','name':'日月光投控'},
            {'code':'2379.TW','name':'瑞昱'},
        ],
        '電子代工': [
            {'code':'2317.TW','name':'鴻海'},
            {'code':'2354.TW','name':'鴻準'},
            {'code':'2382.TW','name':'廣達'},
            {'code':'2357.TW','name':'華碩'},
        ],
        '金融保險': [
            {'code':'2882.TW','name':'國泰金'},
            {'code':'2881.TW','name':'富邦金'},
            {'code':'2891.TW','name':'中信金'},
            {'code':'2886.TW','name':'兆豐金'},
        ],
        '電信': [
            {'code':'2412.TW','name':'中華電'},
            {'code':'3045.TW','name':'台灣大'},
            {'code':'4904.TW','name':'遠傳'},
        ],
        '電源/零組件': [
            {'code':'2308.TW','name':'台達電'},
            {'code':'6669.TW','name':'緯穎'},
            {'code':'3008.TW','name':'大立光'},
        ],
        '傳產/石化': [
            {'code':'1301.TW','name':'台塑'},
            {'code':'1303.TW','name':'南亞'},
            {'code':'1326.TW','name':'台化'},
        ],
        'ETF': [
            {'code':'0050.TW','name':'元大台灣50'},
            {'code':'0056.TW','name':'元大高股息'},
        ],
    },
    'japan': {
        '汽車': [
            {'code':'7203.T','name':'Toyota'},
            {'code':'7267.T','name':'Honda'},
            {'code':'7269.T','name':'Suzuki'},
        ],
        '科技/半導體': [
            {'code':'8035.T','name':'Tokyo Electron'},
            {'code':'6857.T','name':'Advantest'},
            {'code':'6861.T','name':'Keyence'},
            {'code':'2644.T','name':'GX半導體ETF'},
        ],
        '電子/消費': [
            {'code':'6758.T','name':'Sony'},
            {'code':'7974.T','name':'Nintendo'},
            {'code':'6752.T','name':'Panasonic'},
        ],
        '金融': [
            {'code':'8306.T','name':'Mitsubishi UFJ'},
            {'code':'8316.T','name':'Sumitomo Mitsui'},
        ],
        '電信': [
            {'code':'9432.T','name':'NTT'},
            {'code':'9984.T','name':'SoftBank'},
        ],
        '化工/材料': [
            {'code':'4063.T','name':'Shin-Etsu Chem'},
            {'code':'6501.T','name':'Hitachi'},
        ],
    },
    'shanghai': {
        '白酒/消費': [
            {'code':'600519.SS','name':'貴州茅台'},
            {'code':'000858.SZ','name':'五糧液'},
            {'code':'600887.SS','name':'伊利股份'},
        ],
        '金融/保險': [
            {'code':'601318.SS','name':'中國平安'},
            {'code':'601166.SS','name':'興業銀行'},
            {'code':'600036.SS','name':'招商銀行'},
            {'code':'600030.SS','name':'中信證券'},
        ],
        '醫藥': [
            {'code':'600276.SS','name':'恒瑞醫藥'},
            {'code':'300750.SZ','name':'寧德時代'},
        ],
        '能源/交通': [
            {'code':'600009.SS','name':'上海機場'},
            {'code':'601688.SS','name':'華泰證券'},
        ],
        'ETF': [
            {'code':'510050.SS','name':'上證50ETF'},
        ],
    }
}

@app.route('/api/heatmap', methods=['GET'])
def get_heatmap():
    market = request.args.get('market', 'taiwan')
    sectors = SECTOR_STOCKS.get(market, {})
    result  = {}

    for sector, stocks in sectors.items():
        result[sector] = []
        for s in stocks:
            try:
                df = get_df(s['code'], '5d')
                if df is None or df.empty:
                    result[sector].append({**s, 'change_pct': None, 'price': None})
                    continue
                last  = df.iloc[-1]
                prev  = df.iloc[-2] if len(df) > 1 else last
                price = float(last['Close'])
                pc    = float(prev['Close'])
                chg   = round((price - pc) / pc * 100, 2) if pc else 0
                result[sector].append({**s, 'price': round(price, 2), 'change_pct': chg})
            except:
                result[sector].append({**s, 'change_pct': None, 'price': None})
    return jsonify(result)


# ── PORTFOLIO CHART DATA ─────────────────────────────────────────
@app.route('/api/portfolio/chart', methods=['GET'])
def portfolio_chart():
    """Returns portfolio allocation + historical value data for charts"""
    with get_db() as db:
        rows = db.execute('SELECT * FROM journal ORDER BY date ASC, id ASC').fetchall()
    journal = [dict(r) for r in rows]
    if not journal:
        return jsonify({'positions': [], 'history': []})

    # Build current positions
    positions = {}
    for t in sorted(journal, key=lambda x: x['date']):
        code = t['code']
        if code not in positions:
            positions[code] = {'code': code, 'name': t['name'], 'shares': 0, 'avg_cost': 0, 'cost_basis': 0}
        p = positions[code]
        if t['action'] == 'buy':
            total_cost = p['avg_cost'] * p['shares'] + t['price'] * t['shares']
            p['shares'] += t['shares']
            p['avg_cost'] = total_cost / p['shares'] if p['shares'] > 0 else 0
            p['cost_basis'] = p['avg_cost'] * p['shares']
        elif t['action'] == 'sell':
            p['shares'] = max(0, p['shares'] - t['shares'])
            p['cost_basis'] = p['avg_cost'] * p['shares']

    # Get current prices & build allocation
    allocation = []
    total_value = 0
    total_cost  = 0
    for code, p in positions.items():
        if p['shares'] <= 0:
            continue
        current_price = p['avg_cost']
        try:
            df = get_df(code, '5d')
            if df is not None and not df.empty:
                current_price = float(df.iloc[-1]['Close'])
        except: pass
        mkt_val = round(current_price * p['shares'], 2)
        total_value += mkt_val
        total_cost  += p['cost_basis']
        allocation.append({
            'code':          code,
            'name':          p['name'],
            'shares':        round(p['shares'], 2),
            'avg_cost':      round(p['avg_cost'], 2),
            'current_price': round(current_price, 2),
            'market_value':  mkt_val,
            'cost_basis':    round(p['cost_basis'], 2),
            'pnl':           round(mkt_val - p['cost_basis'], 2),
            'pnl_pct':       round((mkt_val - p['cost_basis']) / p['cost_basis'] * 100, 2) if p['cost_basis'] else 0,
        })

    allocation.sort(key=lambda x: x['market_value'], reverse=True)

    return jsonify({
        'positions':   allocation,
        'total_value': round(total_value, 2),
        'total_cost':  round(total_cost, 2),
        'total_pnl':   round(total_value - total_cost, 2),
        'total_pnl_pct': round((total_value - total_cost) / total_cost * 100, 2) if total_cost else 0,
    })

# [main block moved to end of file]

# ── PORTFOLIO ANALYTICS ──────────────────────────────────────────
@app.route('/api/portfolio/analytics', methods=['GET'])
def portfolio_analytics():
    with get_db() as db:
        rows = db.execute('SELECT * FROM journal ORDER BY date ASC, id ASC').fetchall()
    journal = [dict(r) for r in rows]
    if not journal:
        return jsonify({'error': 'No trades'}), 404

    # Build positions
    positions = {}
    for t in sorted(journal, key=lambda x: x['date']):
        code = t['code']
        if code not in positions:
            positions[code] = {'code': code, 'name': t['name'], 'shares': 0, 'avg_cost': 0, 'invested': 0, 'realized': 0}
        p = positions[code]
        if t['action'] == 'buy':
            total_cost = p['avg_cost'] * p['shares'] + t['price'] * t['shares']
            p['shares'] += t['shares']
            p['avg_cost'] = total_cost / p['shares'] if p['shares'] > 0 else 0
            p['invested'] += t['amount']
        elif t['action'] == 'sell':
            realized = (t['price'] - p['avg_cost']) * min(t['shares'], p['shares'])
            p['realized'] += realized
            p['shares'] = max(0, p['shares'] - t['shares'])
            if p['shares'] == 0: p['avg_cost'] = 0

    # Get current prices & build analytics
    holdings = []
    total_invested = 0
    total_market_value = 0
    total_realized = 0

    for code, p in positions.items():
        if p['shares'] <= 0 and p['realized'] == 0:
            continue
        current_price = None
        try:
            df = get_df(code, '5d')
            if df is not None and not df.empty:
                current_price = round(float(df.iloc[-1]['Close']), 2)
        except: pass

        market_value = round(current_price * p['shares'], 2) if current_price and p['shares'] > 0 else 0
        cost_basis   = round(p['avg_cost'] * p['shares'], 2)
        unrealized   = round(market_value - cost_basis, 2)
        pnl_pct      = round(unrealized / cost_basis * 100, 2) if cost_basis > 0 else 0

        holdings.append({
            'code': code, 'name': p['name'],
            'shares': round(p['shares'], 2),
            'avg_cost': round(p['avg_cost'], 2),
            'current_price': current_price,
            'cost_basis': cost_basis,
            'market_value': market_value,
            'unrealized': unrealized,
            'realized': round(p['realized'], 2),
            'pnl_pct': pnl_pct,
            'weight': 0,  # filled below
        })
        total_market_value += market_value
        total_realized += p['realized']

    # Compute weights
    for h in holdings:
        h['weight'] = round(h['market_value'] / total_market_value * 100, 1) if total_market_value > 0 else 0

    total_unrealized = sum(h['unrealized'] for h in holdings)

    # Daily portfolio value history (last 60 days via yfinance)
    history = []
    try:
        active = [h for h in holdings if h['shares'] > 0 and h['current_price']]
        if active:
            from datetime import datetime, timedelta
            all_closes = {}
            for h in active:
                df = get_df(h['code'], '3mo')
                if df is not None and not df.empty:
                    for idx, row in df.iterrows():
                        d = idx.strftime('%Y-%m-%d')
                        if d not in all_closes:
                            all_closes[d] = 0
                        all_closes[d] += float(row['Close']) * h['shares']
            history = [{'date': d, 'value': round(v, 2)} for d, v in sorted(all_closes.items())]
    except Exception as e:
        print(f"History error: {e}")

    return jsonify({
        'holdings': sorted(holdings, key=lambda x: x['market_value'], reverse=True),
        'summary': {
            'total_market_value': round(total_market_value, 2),
            'total_unrealized': round(total_unrealized, 2),
            'total_realized': round(total_realized, 2),
            'total_pnl': round(total_unrealized + total_realized, 2),
            'num_holdings': len([h for h in holdings if h['shares'] > 0]),
        },
        'history': history,
    })

# ── PDF REPORT DATA ──────────────────────────────────────────────
@app.route('/api/report_data', methods=['GET'])
def report_data():
    """Return all data needed for client-side PDF generation"""
    code   = request.args.get('code')
    market = request.args.get('market', 'taiwan')
    if not code: return jsonify({'error': 'No code'}), 400
    try:
        df = get_df(code, '3mo')
        if df is None or df.empty: return jsonify({'error': f'No data for {code}'}), 404
        df = compute_indicators(df)

        # Quote
        last = df.iloc[-1]; prev = df.iloc[-2] if len(df) > 1 else last
        price = float(last['Close']); pc = float(prev['Close'])
        quote = {
            'price': round(price, 2), 'change': round(price - pc, 2),
            'change_pct': round((price - pc) / pc * 100, 2) if pc else 0,
            'high': round(float(last['High']), 2), 'low': round(float(last['Low']), 2),
            'volume': int(last['Volume']),
        }

        # Signals
        analysis = analyze_signals(df)

        # Fundamentals
        fund = get_fundamentals(code)

        # Recent price history (last 60 rows)
        recent = []
        for idx, row in df.tail(60).iterrows():
            recent.append({'date': idx.strftime('%Y-%m-%d'),
                'open': sf(row['Open']), 'high': sf(row['High']),
                'low': sf(row['Low']), 'close': sf(row['Close']),
                'volume': int(row['Volume']), 'SMA20': sf(row['SMA20']),
                'SMA50': sf(row['SMA50']), 'RSI': sf(row['RSI']),
                'MACD': sf(row['MACD'], 4), 'Signal': sf(row['Signal'], 4),
            })

        return jsonify({
            'code': code, 'market': market,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'quote': quote, 'analysis': analysis,
            'fundamentals': fund, 'history': recent,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── EXCEL EXPORT ─────────────────────────────────────────────────
import io, openpyxl
from openpyxl.styles import (Font, PatternFill, Alignment, Border, Side,
                               GradientFill)
from openpyxl.utils import get_column_letter
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.series import DataPoint

def _xl_style(wb):
    """Return a dict of named cell styles for consistent formatting."""
    return {
        'title':   {'font': Font(name='Arial', bold=True, size=14, color='FFFFFF'),
                    'fill': PatternFill('solid', fgColor='1E3A5F'),
                    'align': Alignment(horizontal='center', vertical='center')},
        'h1':      {'font': Font(name='Arial', bold=True, size=11, color='FFFFFF'),
                    'fill': PatternFill('solid', fgColor='2563EB'),
                    'align': Alignment(horizontal='left', vertical='center', wrap_text=True)},
        'h2':      {'font': Font(name='Arial', bold=True, size=10, color='FFFFFF'),
                    'fill': PatternFill('solid', fgColor='3B82F6'),
                    'align': Alignment(horizontal='left', vertical='center')},
        'label':   {'font': Font(name='Arial', bold=True, size=9, color='1E293B'),
                    'fill': PatternFill('solid', fgColor='EFF6FF'),
                    'align': Alignment(horizontal='left', vertical='center')},
        'value':   {'font': Font(name='Arial', size=9, color='0F172A'),
                    'fill': PatternFill('solid', fgColor='F8FAFC'),
                    'align': Alignment(horizontal='right', vertical='center')},
        'pos':     {'font': Font(name='Arial', bold=True, size=9, color='15803D'),
                    'fill': PatternFill('solid', fgColor='F0FDF4'),
                    'align': Alignment(horizontal='right', vertical='center')},
        'neg':     {'font': Font(name='Arial', bold=True, size=9, color='DC2626'),
                    'fill': PatternFill('solid', fgColor='FEF2F2'),
                    'align': Alignment(horizontal='right', vertical='center')},
        'thr':     {'font': Font(name='Arial', bold=True, size=9, color='FFFFFF'),
                    'fill': PatternFill('solid', fgColor='374151'),
                    'align': Alignment(horizontal='center', vertical='center')},
        'trow_a':  {'font': Font(name='Arial', size=9, color='0F172A'),
                    'fill': PatternFill('solid', fgColor='F8FAFC'),
                    'align': Alignment(horizontal='center', vertical='center')},
        'trow_b':  {'font': Font(name='Arial', size=9, color='0F172A'),
                    'fill': PatternFill('solid', fgColor='FFFFFF'),
                    'align': Alignment(horizontal='center', vertical='center')},
        'note':    {'font': Font(name='Arial', size=8, italic=True, color='64748B'),
                    'fill': PatternFill('solid', fgColor='FFFFFF'),
                    'align': Alignment(horizontal='left', vertical='center', wrap_text=True)},
    }

def _apply(ws, cell, style):
    if style.get('font'):    cell.font       = style['font']
    if style.get('fill'):    cell.fill       = style['fill']
    if style.get('align'):   cell.alignment  = style['align']
    if style.get('number'):  cell.number_format = style['number']

def _border(thin=True):
    s = Side(style='thin' if thin else 'hair', color='CBD5E1')
    return Border(left=s, right=s, top=s, bottom=s)

def _col_width(ws, col, width):
    ws.column_dimensions[get_column_letter(col)].width = width

def _row_height(ws, row, height):
    ws.row_dimensions[row].height = height

def _merged_title(ws, style, row, c1, c2, text, height=28):
    ws.merge_cells(start_row=row, start_column=c1, end_row=row, end_column=c2)
    cell = ws.cell(row=row, column=c1, value=text)
    _apply(ws, cell, style['title'])
    _row_height(ws, row, height)

def _section_header(ws, style, row, c1, c2, text):
    ws.merge_cells(start_row=row, start_column=c1, end_row=row, end_column=c2)
    cell = ws.cell(row=row, column=c1, value=text)
    _apply(ws, cell, style['h1'])
    _row_height(ws, row, 20)

def _kv(ws, style, row, lbl_col, val_col, label, value, val_style='value', merge_val_to=None):
    lc = ws.cell(row=row, column=lbl_col, value=label)
    _apply(ws, lc, style['label'])
    lc.border = _border()
    if merge_val_to:
        ws.merge_cells(start_row=row, start_column=val_col,
                       end_row=row, end_column=merge_val_to)
    vc = ws.cell(row=row, column=val_col, value=value)
    _apply(ws, vc, style[val_style])
    vc.border = _border()
    _row_height(ws, row, 17)

# ── Sheet 1: Summary ────────────────────────────────────────────
def _build_summary_sheet(wb, style, journal_rows, positions, generated_at):
    ws = wb.active
    ws.title = '📊 總覽'
    ws.sheet_view.showGridLines = False

    # Freeze pane
    ws.freeze_panes = 'A4'

    # Title
    _col_width(ws, 1, 18); _col_width(ws, 2, 16); _col_width(ws, 3, 16)
    _col_width(ws, 4, 16); _col_width(ws, 5, 16); _col_width(ws, 6, 16)
    _col_width(ws, 7, 14)

    _merged_title(ws, style, 1, 1, 7, '  🌏 Aeternus Market Intelligence — 投資組合總覽', 32)
    ws.merge_cells('A2:G2')
    ts = ws['A2']
    ts.value = f'  產生時間：{generated_at}'
    ts.font  = Font(name='Arial', size=9, italic=True, color='94A3B8')
    ts.fill  = PatternFill('solid', fgColor='1E3A5F')
    ts.alignment = Alignment(horizontal='left', vertical='center')
    _row_height(ws, 2, 16)

    # KPI bar
    total_cost   = sum(p.get('avg_cost', 0) * p.get('shares', 0) for p in positions if p['shares'] > 0)
    total_mktval = sum(p.get('market_value') or 0 for p in positions if p['shares'] > 0)
    total_unr    = sum(p.get('unrealized', 0) for p in positions)
    total_rlz    = sum(p.get('realized', 0) for p in positions)
    total_pnl    = total_unr + total_rlz
    pnl_pct      = total_pnl / total_cost * 100 if total_cost else 0
    hold_count   = sum(1 for p in positions if p['shares'] > 0)

    kpis = [
        ('持倉股數',   f'{hold_count} 支',  'value'),
        ('總市值',     f'{total_mktval:,.0f}',  'value'),
        ('總成本',     f'{total_cost:,.0f}',    'value'),
        ('未實現損益', f'{total_unr:+,.0f}',    'pos' if total_unr >= 0 else 'neg'),
        ('已實現損益', f'{total_rlz:+,.0f}',    'pos' if total_rlz >= 0 else 'neg'),
        ('總報酬率',   f'{pnl_pct:+.2f}%',      'pos' if pnl_pct >= 0 else 'neg'),
        ('交易筆數',   f'{len(journal_rows)} 筆', 'value'),
    ]
    for ci, (lbl, val, vs) in enumerate(kpis, start=1):
        lc = ws.cell(row=3, column=ci, value=lbl)
        lc.font = Font(name='Arial', bold=True, size=8, color='94A3B8')
        lc.fill = PatternFill('solid', fgColor='0F172A')
        lc.alignment = Alignment(horizontal='center', vertical='bottom')
        lc.border = _border()
        vc = ws.cell(row=4, column=ci, value=val)
        vc.font = Font(name='Arial', bold=True, size=13,
                       color=('15803D' if vs == 'pos' else ('DC2626' if vs == 'neg' else '0F172A')))
        vc.fill = PatternFill('solid', fgColor='F8FAFC')
        vc.alignment = Alignment(horizontal='center', vertical='center')
        vc.border = _border()
    _row_height(ws, 3, 14)
    _row_height(ws, 4, 28)

    # Holdings table
    row = 6
    _section_header(ws, style, row, 1, 7, '  📋 持倉明細')
    row += 1
    headers = ['股票代碼', '名稱', '持股數', '均成本', '現價', '市值', '未實現損益']
    for ci, h in enumerate(headers, 1):
        c = ws.cell(row=row, column=ci, value=h)
        _apply(ws, c, style['thr'])
        c.border = _border()
    _row_height(ws, row, 18)
    row += 1

    holdings = [p for p in positions if p.get('shares', 0) > 0]
    for ri, p in enumerate(holdings):
        s = style['trow_a'] if ri % 2 == 0 else style['trow_b']
        pnl = p.get('unrealized', 0)
        vals = [p['code'], p['name'], p['shares'], p.get('avg_cost'), p.get('current_price'),
                p.get('market_value'), pnl]
        for ci, v in enumerate(vals, 1):
            cell = ws.cell(row=row, column=ci, value=v)
            if ci >= 3 and v is not None:  # numeric columns
                vs = 'pos' if (ci == 7 and isinstance(v, (int, float)) and v >= 0) else \
                     'neg' if (ci == 7 and isinstance(v, (int, float)) and v < 0) else s['__class__'].__name__
                _apply(ws, cell, style.get(vs, s))
                if ci in (4, 5, 6):
                    cell.number_format = '#,##0.00'
                elif ci == 7:
                    cell.number_format = '+#,##0.00;-#,##0.00'
            else:
                _apply(ws, cell, s)
            cell.border = _border()
        _row_height(ws, row, 17)
        row += 1

    # Realized PnL section
    row += 1
    _section_header(ws, style, row, 1, 7, '  💰 已實現損益彙總')
    row += 1
    closed = [p for p in positions if p.get('shares', 0) == 0 and p.get('realized', 0) != 0]
    if closed:
        for ci, h in enumerate(['股票代碼', '名稱', '已實現損益'], 1):
            c = ws.cell(row=row, column=ci, value=h)
            _apply(ws, c, style['thr']); c.border = _border()
        _row_height(ws, row, 18); row += 1
        for ri, p in enumerate(closed):
            rlz = p.get('realized', 0)
            vs = 'pos' if rlz >= 0 else 'neg'
            for ci, v in enumerate([p['code'], p['name'], rlz], 1):
                cell = ws.cell(row=row, column=ci, value=v)
                _apply(ws, cell, style[vs] if ci == 3 else (style['trow_a'] if ri%2==0 else style['trow_b']))
                cell.border = _border()
                if ci == 3: cell.number_format = '+#,##0.00;-#,##0.00'
            _row_height(ws, row, 17); row += 1
    else:
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=7)
        c = ws.cell(row=row, column=1, value='  尚無已實現損益記錄')
        _apply(ws, c, style['note']); _row_height(ws, row, 16)


# ── Sheet 2: Trade Journal ───────────────────────────────────────
def _build_journal_sheet(wb, style, journal_rows):
    ws = wb.create_sheet('📝 交易日誌')
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = 'A3'

    widths = [14, 14, 8, 10, 10, 12, 30]
    for i, w in enumerate(widths, 1): _col_width(ws, i, w)

    _merged_title(ws, style, 1, 1, 7, '  📝 交易日誌')
    headers = ['日期', '股票代碼', '名稱', '操作', '股數', '價格', '金額', '備註']
    for ci, h in enumerate(headers, 1):
        c = ws.cell(row=2, column=ci, value=h)
        _apply(ws, c, style['thr']); c.border = _border()
    _col_width(ws, 8, 24)
    _row_height(ws, 2, 20)

    for ri, t in enumerate(sorted(journal_rows, key=lambda x: x['date'], reverse=True)):
        row = ri + 3
        is_buy = t['action'] == 'buy'
        action_style = 'pos' if is_buy else 'neg'
        action_text  = '買入' if is_buy else '賣出'
        s = style['trow_a'] if ri % 2 == 0 else style['trow_b']
        cells = [t['date'], t['code'], t['name'], action_text,
                 t['shares'], t['price'], t['amount'], t.get('note', '')]
        for ci, v in enumerate(cells, 1):
            cell = ws.cell(row=row, column=ci, value=v)
            if ci == 4:
                _apply(ws, cell, style[action_style])
            else:
                _apply(ws, cell, s)
            if ci in (5, 6): cell.number_format = '#,##0.00'
            if ci == 7:      cell.number_format = '#,##0'
            cell.border = _border()
        _row_height(ws, row, 16)


# ── Sheet 3: Price History ───────────────────────────────────────
def _build_history_sheet(wb, style, history_rows, code, name):
    ws = wb.create_sheet(f'📈 {code[:8]}')
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = 'A3'

    _merged_title(ws, style, 1, 1, 10, f'  📈 {name} ({code}) — 近期歷史行情')
    headers = ['日期', '開盤', '最高', '最低', '收盤', '成交量',
               'SMA20', 'SMA50', 'RSI', 'MACD']
    widths  = [12, 10, 10, 10, 10, 14, 10, 10, 8, 10]
    for i, (h, w) in enumerate(zip(headers, widths), 1):
        c = ws.cell(row=2, column=i, value=h)
        _apply(ws, c, style['thr']); c.border = _border()
        _col_width(ws, i, w)
    _row_height(ws, 2, 20)

    fmt = '#,##0.00'
    for ri, row_data in enumerate(reversed(history_rows)):
        row = ri + 3
        s = style['trow_a'] if ri % 2 == 0 else style['trow_b']
        vals = [row_data.get('date'), row_data.get('open'), row_data.get('high'),
                row_data.get('low'), row_data.get('close'), row_data.get('volume'),
                row_data.get('SMA20'), row_data.get('SMA50'),
                row_data.get('RSI'), row_data.get('MACD')]
        for ci, v in enumerate(vals, 1):
            cell = ws.cell(row=row, column=ci, value=v)
            _apply(ws, cell, s)
            if ci in range(2, 6): cell.number_format = fmt
            if ci == 6:           cell.number_format = '#,##0'
            if ci in (7, 8, 9):   cell.number_format = '#,##0.00'
            if ci == 10:          cell.number_format = '#,##0.0000'
            cell.border = _border()
        _row_height(ws, row, 15)

    # Add a line chart for Close price
    if len(history_rows) >= 5:
        n = min(len(history_rows), 120)
        chart = LineChart()
        chart.title  = f'{code} 收盤價走勢'
        chart.style  = 10
        chart.height = 12; chart.width = 24
        chart.y_axis.title = '價格'
        chart.x_axis.title = '日期'
        data = Reference(ws, min_col=5, min_row=2, max_row=2+n)
        chart.add_data(data, titles_from_data=True)
        chart.series[0].graphicalProperties.line.solidFill = '2563EB'
        chart.series[0].graphicalProperties.line.width = 15000
        cats = Reference(ws, min_col=1, min_row=3, max_row=2+n)
        chart.set_categories(cats)
        ws.add_chart(chart, f'A{3 + n + 3}')


# ── Sheet 4: Alerts ──────────────────────────────────────────────
def _build_alerts_sheet(wb, style, alerts_dict):
    ws = wb.create_sheet('🔔 警報設定')
    ws.sheet_view.showGridLines = False

    _merged_title(ws, style, 1, 1, 5, '  🔔 價格警報設定')
    headers = ['股票代碼', '目標價', '方向', '狀態', '設定時間']
    widths  = [16, 12, 10, 12, 20]
    for i, (h, w) in enumerate(zip(headers, widths), 1):
        c = ws.cell(row=2, column=i, value=h)
        _apply(ws, c, style['thr']); c.border = _border()
        _col_width(ws, i, w)
    _row_height(ws, 2, 20)

    row = 3
    for code, alert_list in alerts_dict.items():
        for ri, a in enumerate(alert_list):
            s = style['trow_a'] if row % 2 == 0 else style['trow_b']
            direction = '↑ 突破' if a['direction'] == 'above' else '↓ 跌破'
            status    = '✅ 已觸發' if a.get('triggered') else '⏳ 等待中'
            vs        = 'pos' if a.get('triggered') else 'value'
            vals = [code, a['target'], direction, status, a.get('created_at','')]
            for ci, v in enumerate(vals, 1):
                cell = ws.cell(row=row, column=ci, value=v)
                _apply(ws, cell, style[vs] if ci == 4 else s)
                if ci == 2: cell.number_format = '#,##0.00'
                cell.border = _border()
            _row_height(ws, row, 16)
            row += 1


@app.route('/api/export/excel', methods=['GET'])
def export_excel():
    """Export full portfolio + journal + alerts to a styled .xlsx file."""
    code   = request.args.get('code')   # optional: single stock history
    market = request.args.get('market', 'taiwan')

    with get_db() as db:
        journal_rows = [dict(r) for r in
                        db.execute('SELECT * FROM journal ORDER BY date DESC, id DESC').fetchall()]
        alerts_dict_raw = {}
        for r in db.execute('SELECT * FROM alerts ORDER BY code, id').fetchall():
            r = dict(r)
            if r['code'] not in alerts_dict_raw: alerts_dict_raw[r['code']] = []
            alerts_dict_raw[r['code']].append(r)

    # Calculate positions (reuse get_pnl logic)
    positions_map = {}
    for t in sorted(journal_rows, key=lambda x: x['date']):
        c2 = t['code']
        if c2 not in positions_map:
            positions_map[c2] = {'code': c2, 'name': t['name'], 'shares': 0,
                                  'avg_cost': 0, 'realized': 0}
        p = positions_map[c2]
        if t['action'] == 'buy':
            total_cost = p['avg_cost'] * p['shares'] + t['price'] * t['shares']
            p['shares'] += t['shares']
            p['avg_cost'] = total_cost / p['shares'] if p['shares'] > 0 else 0
        elif t['action'] == 'sell':
            realized = (t['price'] - p['avg_cost']) * min(t['shares'], p['shares'])
            p['realized'] += realized
            p['shares'] = max(0, p['shares'] - t['shares'])
            if p['shares'] == 0: p['avg_cost'] = 0

    positions = []
    for c2, p in positions_map.items():
        current_price = None
        try:
            df2 = get_df(c2, '5d')
            if df2 is not None and not df2.empty:
                current_price = round(float(df2.iloc[-1]['Close']), 2)
        except: pass
        unrealized = (current_price - p['avg_cost']) * p['shares'] \
                     if current_price and p['shares'] > 0 else 0
        positions.append({
            'code': c2, 'name': p['name'],
            'shares': round(p['shares'], 2),
            'avg_cost': round(p['avg_cost'], 2),
            'current_price': current_price,
            'market_value': round(current_price * p['shares'], 2) if current_price else None,
            'unrealized': round(unrealized, 2),
            'realized': round(p['realized'], 2),
        })

    # Optional: single stock price history
    history_rows = []
    stock_name   = code or ''
    if code:
        try:
            df3 = get_df(code, '1y')
            if df3 is not None and not df3.empty:
                df3 = compute_indicators(df3)
                for idx, row in df3.iterrows():
                    history_rows.append({
                        'date': idx.strftime('%Y-%m-%d'),
                        'open': sf(row['Open']), 'high': sf(row['High']),
                        'low': sf(row['Low']),   'close': sf(row['Close']),
                        'volume': int(row['Volume']),
                        'SMA20': sf(row['SMA20']), 'SMA50': sf(row['SMA50']),
                        'RSI': sf(row['RSI']), 'MACD': sf(row.get('MACD'), 4),
                    })
                try:
                    ticker     = yf.Ticker(code)
                    stock_name = ticker.info.get('shortName', code)
                except: pass
        except: pass

    # Build workbook
    wb    = openpyxl.Workbook()
    style = _xl_style(wb)
    gen   = datetime.now().strftime('%Y-%m-%d %H:%M')

    _build_summary_sheet(wb, style, journal_rows, positions, gen)
    _build_journal_sheet(wb, style, journal_rows)
    if history_rows:
        _build_history_sheet(wb, style, history_rows, code, stock_name)
    if alerts_dict_raw:
        _build_alerts_sheet(wb, style, alerts_dict_raw)

    # Stream to response
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    fname_date = datetime.now().strftime('%Y%m%d_%H%M')
    fname      = f'AeternusMarketIntelligence_{fname_date}.xlsx'
    if code:
        fname = f'{code}_{fname_date}.xlsx'

    from flask import send_file
    return send_file(
        buf,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=fname,
    )


# ════════════════════════════════════════════════════════════════
#  NEWS & SENTIMENT ANALYSIS
#  新聞來源：Yahoo Finance RSS + Google Finance RSS
#  情緒分析：Ollama 本機模型（或 rule-based fallback）
# ════════════════════════════════════════════════════════════════
import xml.etree.ElementTree as ET
import html, re as _re

_NEWS_CACHE = {}
_NEWS_TTL   = 600  # 10 minutes

def _fetch_rss(url, timeout=8):
    """Fetch RSS feed and return list of {title, link, published, summary}."""
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; StockBot/1.0)'
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
        root = ET.fromstring(raw)
        ns   = {'atom': 'http://www.w3.org/2005/Atom'}
        items = []

        # RSS 2.0 format
        for item in root.iter('item'):
            title = item.findtext('title') or ''
            link  = item.findtext('link')  or ''
            pub   = item.findtext('pubDate') or ''
            desc  = item.findtext('description') or ''
            items.append({
                'title':     html.unescape(_re.sub(r'<[^>]+>', '', title)).strip(),
                'link':      link.strip(),
                'published': pub.strip(),
                'summary':   html.unescape(_re.sub(r'<[^>]+>', '', desc))[:200].strip(),
            })

        # Atom format
        if not items:
            for entry in root.findall('.//atom:entry', ns) or root.findall('.//{http://www.w3.org/2005/Atom}entry'):
                title = entry.findtext('{http://www.w3.org/2005/Atom}title') or ''
                link_el = entry.find('{http://www.w3.org/2005/Atom}link')
                link    = (link_el.get('href') if link_el is not None else '') or ''
                pub     = entry.findtext('{http://www.w3.org/2005/Atom}published') or ''
                summary = entry.findtext('{http://www.w3.org/2005/Atom}summary') or ''
                items.append({
                    'title':     html.unescape(_re.sub(r'<[^>]+>', '', title)).strip(),
                    'link':      link.strip(),
                    'published': pub.strip(),
                    'summary':   html.unescape(_re.sub(r'<[^>]+>', '', summary))[:200].strip(),
                })
        return items[:15]
    except Exception as e:
        print(f'[RSS] Error fetching {url}: {e}')
        return []


def _get_news_for_code(code, name):
    """Fetch news from multiple RSS sources for a stock."""
    now = time.time()
    if code in _NEWS_CACHE and now - _NEWS_CACHE[code][0] < _NEWS_TTL:
        return _NEWS_CACHE[code][1]

    # Strip exchange suffix for query
    query  = name or code.split('.')[0]
    ticker = code.split('.')[0]

    # Yahoo Finance RSS (works without API key)
    sources = [
        f'https://finance.yahoo.com/rss/headline?s={code}',
        f'https://news.google.com/rss/search?q={urllib.parse.quote(query)}+stock&hl=zh-TW&gl=TW&ceid=TW:zh-Hant',
    ]

    # Add market-specific sources
    if code.endswith('.TW') or code.endswith('.TWO'):
        sources.append(f'https://news.google.com/rss/search?q={urllib.parse.quote(ticker)}+台股&hl=zh-TW&gl=TW&ceid=TW:zh-Hant')
    elif code.endswith('.T'):
        sources.append(f'https://news.google.com/rss/search?q={urllib.parse.quote(query)}+株価&hl=ja&gl=JP&ceid=JP:ja')
    elif code.endswith('.SS') or code.endswith('.SZ'):
        sources.append(f'https://news.google.com/rss/search?q={urllib.parse.quote(query)}+股票&hl=zh-CN&gl=CN&ceid=CN:zh-Hans')

    all_news = []
    seen_titles = set()
    for src in sources:
        for item in _fetch_rss(src):
            t = item['title'].lower()
            if t and t not in seen_titles:
                seen_titles.add(t)
                all_news.append(item)
        if len(all_news) >= 20:
            break

    _NEWS_CACHE[code] = (now, all_news[:20])
    return all_news[:20]


def _rule_based_sentiment(title, summary):
    """Fast rule-based sentiment scoring as Ollama fallback."""
    pos_words = ['上漲','漲停','創高','突破','強勢','買入','增持','看好','獲利','成長',
                 'surge','rally','gain','beat','strong','buy','upgrade','profit','growth','record',
                 '上涨','涨停','买入','增持']
    neg_words = ['下跌','跌停','虧損','崩跌','賣出','降評','警告','風險','衰退','虧損',
                 'fall','drop','loss','miss','weak','sell','downgrade','warning','risk','decline',
                 '下跌','跌停','卖出','降评','亏损']
    text = (title + ' ' + summary).lower()
    pos  = sum(1 for w in pos_words if w in text)
    neg  = sum(1 for w in neg_words if w in text)
    if pos > neg:   return 'positive', pos - neg
    if neg > pos:   return 'negative', neg - pos
    return 'neutral', 0


@app.route('/api/news', methods=['GET'])
def get_news():
    code = request.args.get('code')
    name = request.args.get('name', '')
    if not code:
        return jsonify({'error': 'No code'}), 400
    news = _get_news_for_code(code, name)
    # Add rule-based sentiment for each item
    for item in news:
        sent, score = _rule_based_sentiment(item['title'], item.get('summary',''))
        item['sentiment']       = sent
        item['sentiment_score'] = score
    return jsonify(news)


@app.route('/api/news/analyze', methods=['POST'])
def analyze_news_sentiment():
    """Use Ollama to analyze sentiment of news titles in batch."""
    data    = request.json or {}
    code    = data.get('code', '')
    name    = data.get('name', '')
    titles  = data.get('titles', [])
    model   = data.get('model', OLLAMA_MODEL)

    if not titles:
        return jsonify({'error': 'No titles'}), 400

    titles_text = '\n'.join([f'{i+1}. {t}' for i, t in enumerate(titles[:10])])
    prompt = f"""以下是關於 {name}（{code}）的新聞標題，請分析每則新聞對股價的情緒傾向。

{titles_text}

請以 JSON 格式回覆，格式如下（只輸出 JSON，不要其他文字）：
{{
  "overall": "positive/negative/neutral",
  "overall_summary": "整體市場情緒一句話摘要（繁體中文，20字以內）",
  "items": [
    {{"index": 1, "sentiment": "positive/negative/neutral", "reason": "原因（10字以內）"}},
    ...
  ]
}}"""

    try:
        payload = json.dumps({
            'model':   model,
            'messages': [{'role': 'user', 'content': prompt}],
            'stream':  False,
            'options': {'temperature': 0.2, 'num_predict': 600},
        }).encode('utf-8')
        req = urllib.request.Request(
            OLLAMA_URL, data=payload,
            headers={'Content-Type': 'application/json'}, method='POST'
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        reply = result.get('message', {}).get('content', '')
        # Extract JSON from reply
        match = _re.search(r'\{[\s\S]*\}', reply)
        if match:
            analysis = json.loads(match.group())
            return jsonify({'success': True, 'analysis': analysis})
        return jsonify({'success': False, 'error': 'JSON parse failed', 'raw': reply[:200]})
    except urllib.error.URLError:
        return jsonify({'success': False, 'error': 'Ollama 未啟動，使用規則分析'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})



# ════════════════════════════════════════════════════════════════
#  多週期共振分析
#  同時分析日線(3mo)、週線(1y)、月線(2y)
#  只有多個週期同時發出同方向訊號才視為「共振」
# ════════════════════════════════════════════════════════════════

def resample_to_weekly(df):
    """Resample daily OHLCV to weekly."""
    for freq in ('W', 'W-SUN', 'W-FRI'):
        try:
            result = df.resample(freq).agg({
                'Open': 'first', 'High': 'max', 'Low': 'min',
                'Close': 'last', 'Volume': 'sum'
            }).dropna()
            if result is not None and not result.empty:
                return result
        except Exception:
            continue
    return df

def resample_to_monthly(df):
    """Resample daily OHLCV to monthly. Try 'ME' (pandas>=2.2) else 'M'."""
    for freq in ('ME', 'M', 'MS'):
        try:
            result = df.resample(freq).agg({
                'Open': 'first', 'High': 'max', 'Low': 'min',
                'Close': 'last', 'Volume': 'sum'
            }).dropna()
            if result is not None and not result.empty:
                return result
        except Exception:
            continue
    return df

def _quick_signals(df):
    """Fast signal extraction: RSI / MACD / MA direction."""
    if df is None or len(df) < 15:
        return None
    df2 = compute_indicators(df.copy())
    last = df2.iloc[-1]
    prev = df2.iloc[-2] if len(df2) > 1 else last

    signals = {}

    # RSI direction
    rsi = sf(last['RSI'])
    if rsi:
        if rsi < 35:   signals['rsi'] = 'bull'
        elif rsi > 65: signals['rsi'] = 'bear'
        elif rsi < 50: signals['rsi'] = 'mild_bull'
        else:          signals['rsi'] = 'mild_bear'

    # MACD direction
    macd = sf(last['MACD'], 4); sig_ = sf(last['Signal'], 4)
    pm   = sf(prev['MACD'], 4); ps   = sf(prev['Signal'], 4)
    if macd is not None and sig_ is not None:
        if macd > sig_ and pm <= ps:   signals['macd'] = 'cross_bull'
        elif macd < sig_ and pm >= ps: signals['macd'] = 'cross_bear'
        elif macd > sig_:              signals['macd'] = 'bull'
        else:                          signals['macd'] = 'bear'

    # MA direction
    s20 = sf(last['SMA20']); s50 = sf(last['SMA50'])
    if s20 and s50:
        signals['ma'] = 'bull' if s20 > s50 else 'bear'

    # KD
    k = sf(last['K']); d = sf(last['D'])
    if k and d:
        if k < 25:   signals['kd'] = 'bull'
        elif k > 75: signals['kd'] = 'bear'
        elif k > d:  signals['kd'] = 'mild_bull'
        else:        signals['kd'] = 'mild_bear'

    # Price vs SMA20
    close = float(last['Close'])
    if s20:
        signals['price_ma'] = 'bull' if close > s20 else 'bear'

    return signals


def _score_direction(sigs):
    """Return (bull_count, bear_count, score) from signals dict."""
    bull = sum(1 for v in sigs.values() if 'bull' in v)
    bear = sum(1 for v in sigs.values() if 'bear' in v)
    return bull, bear, bull - bear


def analyze_resonance(code):
    """
    Fetch daily data, resample to weekly/monthly,
    compute signals per timeframe and detect resonance.
    Returns dict with per-timeframe signals and resonance summary.
    """
    # Need at least 2y of data for monthly
    df_full = get_df(code, '2y')
    if df_full is None or len(df_full) < 30:
        return {'error': 'Insufficient data'}

    # Slice timeframes
    df_daily   = df_full.tail(63)        # ~3 months daily
    df_weekly  = resample_to_weekly(df_full).tail(52)   # ~1 year weekly
    df_monthly = resample_to_monthly(df_full).tail(24)  # 2 year monthly

    sigs_d = _quick_signals(df_daily)
    sigs_w = _quick_signals(df_weekly)
    sigs_m = _quick_signals(df_monthly)

    if not sigs_d:
        return {'error': 'Cannot compute signals'}

    # ── Per-indicator cross-timeframe resonance ──────────────────
    resonance_items = []
    indicators = ['rsi', 'macd', 'ma', 'kd', 'price_ma']
    ind_labels  = {'rsi':'RSI','macd':'MACD','ma':'MA','kd':'KD','price_ma':'Price/MA20'}

    for ind in indicators:
        d_sig = sigs_d.get(ind)
        w_sig = sigs_w.get(ind) if sigs_w else None
        m_sig = sigs_m.get(ind) if sigs_m else None

        if not d_sig: continue

        d_bull = 'bull' in d_sig
        w_bull = 'bull' in w_sig if w_sig else None
        m_bull = 'bull' in m_sig if m_sig else None

        # Count matching timeframes
        frames = [('D', d_bull), ('W', w_bull), ('M', m_bull)]
        active = [(f, b) for f, b in frames if b is not None]
        agree_bull = sum(1 for _, b in active if b)
        agree_bear = sum(1 for _, b in active if not b)
        total = len(active)

        if agree_bull == total:
            strength = 'strong_bull'
        elif agree_bear == total:
            strength = 'strong_bear'
        elif agree_bull > agree_bear:
            strength = 'mild_bull'
        elif agree_bear > agree_bull:
            strength = 'mild_bear'
        else:
            strength = 'neutral'

        resonance_items.append({
            'indicator': ind_labels.get(ind, ind),
            'daily':     d_sig,
            'weekly':    w_sig,
            'monthly':   m_sig,
            'strength':  strength,
            'frames':    {f: ('bull' if b else 'bear') if b is not None else None
                         for f, b in frames},
        })

    # ── Overall resonance score ──────────────────────────────────
    strong_bull = sum(1 for r in resonance_items if r['strength'] == 'strong_bull')
    strong_bear = sum(1 for r in resonance_items if r['strength'] == 'strong_bear')
    mild_bull   = sum(1 for r in resonance_items if r['strength'] == 'mild_bull')
    mild_bear   = sum(1 for r in resonance_items if r['strength'] == 'mild_bear')

    overall_score = strong_bull * 2 + mild_bull - strong_bear * 2 - mild_bear

    if strong_bull >= 3:
        overall = 'strong_bull'
        summary = 'resonance_strong_bull'
    elif strong_bear >= 3:
        overall = 'strong_bear'
        summary = 'resonance_strong_bear'
    elif overall_score >= 3:
        overall = 'mild_bull'
        summary = 'resonance_mild_bull'
    elif overall_score <= -3:
        overall = 'mild_bear'
        summary = 'resonance_mild_bear'
    else:
        overall = 'neutral'
        summary = 'resonance_neutral'

    # ── Per-timeframe overall direction ──────────────────────────
    def timeframe_summary(sigs):
        if not sigs: return None
        bull, bear, score = _score_direction(sigs)
        return {'bull': bull, 'bear': bear, 'score': score,
                'direction': 'bull' if score > 0 else 'bear' if score < 0 else 'neutral'}

    return {
        'resonance':  resonance_items,
        'overall':    overall,
        'summary':    summary,
        'score':      {'strong_bull': strong_bull, 'strong_bear': strong_bear,
                       'mild_bull': mild_bull, 'mild_bear': mild_bear,
                       'net': overall_score},
        'timeframes': {
            'daily':   timeframe_summary(sigs_d),
            'weekly':  timeframe_summary(sigs_w),
            'monthly': timeframe_summary(sigs_m),
        },
        'last_price': sf(float(df_full.iloc[-1]['Close'])),
    }


@app.route('/api/resonance', methods=['GET'])
def get_resonance():
    code = request.args.get('code')
    if not code:
        return jsonify({'error': 'No code'}), 400
    cache_key = f"res_{code}"
    now = time.time()
    if cache_key in _cache and now - _cache[cache_key][0] < 600:
        return jsonify(_cache[cache_key][1])
    try:
        result = analyze_resonance(code)
        _cache[cache_key] = (now, result)
        return jsonify(result)
    except Exception as e:
        print(f"Resonance error {code}: {e}")
        return jsonify({'error': str(e)}), 500


# ════════════════════════════════════════════════════════════════
#  K線型態識別引擎
#  支援：頭肩頂/底、雙頂/底、三角收斂（上升/下降/對稱）、
#        旗形整理、矩形箱型、楔形
# ════════════════════════════════════════════════════════════════

def detect_patterns(df):
    """
    Detect chart patterns in OHLCV DataFrame.
    Returns list of pattern dicts:
    { name, type(bullish/bearish/neutral), start_idx, end_idx,
      key_points, description, confidence }
    """
    if len(df) < 20:
        return []

    c = df['Close'].values
    h = df['High'].values
    l = df['Low'].values
    dates = [idx.strftime('%Y-%m-%d') for idx in df.index]
    n = len(c)
    patterns = []

    # ── Pivot detection helpers ──────────────────────────────────
    def local_highs(window=5):
        """Return indices that are local highs."""
        idx = []
        for i in range(window, n - window):
            if h[i] == max(h[i-window:i+window+1]):
                idx.append(i)
        return idx

    def local_lows(window=5):
        """Return indices that are local lows."""
        idx = []
        for i in range(window, n - window):
            if l[i] == min(l[i-window:i+window+1]):
                idx.append(i)
        return idx

    peaks = local_highs(5)
    troughs = local_lows(5)

    # ── 1. Head and Shoulders (Top) ──────────────────────────────
    for i in range(len(peaks) - 2):
        p1, p2, p3 = peaks[i], peaks[i+1], peaks[i+2]
        if p3 - p1 < 15: continue  # too compressed
        lsh, head, rsh = h[p1], h[p2], h[p3]
        # Head must be highest, shoulders roughly equal
        if head <= lsh or head <= rsh: continue
        sym = abs(lsh - rsh) / head
        if sym > 0.06: continue  # shoulders too asymmetric
        # Find neckline troughs between shoulders
        nt = [t for t in troughs if p1 < t < p2]
        nt2 = [t for t in troughs if p2 < t < p3]
        if not nt or not nt2: continue
        nl1, nl2 = l[nt[-1]], l[nt2[0]]
        neckline = (nl1 + nl2) / 2
        conf = min(95, int(70 + (1 - sym/0.06) * 25))
        patterns.append({
            'name': '頭肩頂', 'type': 'bearish',
            'start_idx': p1, 'end_idx': p3,
            'start_date': dates[p1], 'end_date': dates[p3],
            'key_points': [
                {'date': dates[p1], 'price': round(lsh,2), 'label': '左肩'},
                {'date': dates[p2], 'price': round(head,2), 'label': '頭'},
                {'date': dates[p3], 'price': round(rsh,2), 'label': '右肩'},
            ],
            'neckline': round(neckline, 2),
            'description': f'頭肩頂型態，頸線位 {neckline:.2f}，跌破頸線確認反轉',
            'confidence': conf,
        })

    # ── 2. Inverse Head and Shoulders (Bottom) ───────────────────
    for i in range(len(troughs) - 2):
        t1, t2, t3 = troughs[i], troughs[i+1], troughs[i+2]
        if t3 - t1 < 15: continue
        lsh, head, rsh = l[t1], l[t2], l[t3]
        if head >= lsh or head >= rsh: continue
        sym = abs(lsh - rsh) / abs(head) if head != 0 else 1
        if sym > 0.06: continue
        nt = [p for p in peaks if t1 < p < t2]
        nt2 = [p for p in peaks if t2 < p < t3]
        if not nt or not nt2: continue
        nl1, nl2 = h[nt[-1]], h[nt2[0]]
        neckline = (nl1 + nl2) / 2
        conf = min(95, int(70 + (1 - sym/0.06) * 25))
        patterns.append({
            'name': '頭肩底', 'type': 'bullish',
            'start_idx': t1, 'end_idx': t3,
            'start_date': dates[t1], 'end_date': dates[t3],
            'key_points': [
                {'date': dates[t1], 'price': round(lsh,2), 'label': '左肩'},
                {'date': dates[t2], 'price': round(head,2), 'label': '頭'},
                {'date': dates[t3], 'price': round(rsh,2), 'label': '右肩'},
            ],
            'neckline': round(neckline, 2),
            'description': f'頭肩底型態，頸線位 {neckline:.2f}，突破頸線確認反轉',
            'confidence': conf,
        })

    # ── 3. Double Top ────────────────────────────────────────────
    for i in range(len(peaks) - 1):
        p1, p2 = peaks[i], peaks[i+1]
        if p2 - p1 < 8: continue
        if p2 - p1 > 60: continue
        diff = abs(h[p1] - h[p2]) / max(h[p1], h[p2])
        if diff > 0.03: continue  # peaks must be close in price
        valley = [t for t in troughs if p1 < t < p2]
        if not valley: continue
        v_price = l[valley[0]]
        pullback = (min(h[p1],h[p2]) - v_price) / min(h[p1],h[p2])
        if pullback < 0.03: continue
        conf = min(92, int(65 + (1-diff/0.03)*27))
        patterns.append({
            'name': '雙頂 (M頭)', 'type': 'bearish',
            'start_idx': p1, 'end_idx': p2,
            'start_date': dates[p1], 'end_date': dates[p2],
            'key_points': [
                {'date': dates[p1], 'price': round(h[p1],2), 'label': '頂1'},
                {'date': dates[p2], 'price': round(h[p2],2), 'label': '頂2'},
            ],
            'neckline': round(v_price, 2),
            'description': f'雙頂型態，支撐頸線 {v_price:.2f}，跌破後看跌',
            'confidence': conf,
        })

    # ── 4. Double Bottom ─────────────────────────────────────────
    for i in range(len(troughs) - 1):
        t1, t2 = troughs[i], troughs[i+1]
        if t2 - t1 < 8: continue
        if t2 - t1 > 60: continue
        diff = abs(l[t1] - l[t2]) / max(abs(l[t1]), abs(l[t2]), 1e-10)
        if diff > 0.03: continue
        peak = [p for p in peaks if t1 < p < t2]
        if not peak: continue
        p_price = h[peak[0]]
        bounce = (p_price - max(l[t1],l[t2])) / max(abs(max(l[t1],l[t2])), 1e-10)
        if bounce < 0.03: continue
        conf = min(92, int(65 + (1-diff/0.03)*27))
        patterns.append({
            'name': '雙底 (W底)', 'type': 'bullish',
            'start_idx': t1, 'end_idx': t2,
            'start_date': dates[t1], 'end_date': dates[t2],
            'key_points': [
                {'date': dates[t1], 'price': round(l[t1],2), 'label': '底1'},
                {'date': dates[t2], 'price': round(l[t2],2), 'label': '底2'},
            ],
            'neckline': round(p_price, 2),
            'description': f'雙底型態，阻力頸線 {p_price:.2f}，突破後看漲',
            'confidence': conf,
        })

    # ── 5. Triangle patterns (last 30~60 bars) ───────────────────
    def fit_line(xs, ys):
        """Simple linear regression, return (slope, intercept, r2)."""
        if len(xs) < 2: return 0, ys[0] if ys else 0, 0
        xs = np.array(xs, dtype=float)
        ys = np.array(ys, dtype=float)
        xm, ym = xs.mean(), ys.mean()
        denom = ((xs - xm)**2).sum()
        if denom == 0: return 0, ym, 0
        slope = ((xs-xm)*(ys-ym)).sum() / denom
        intercept = ym - slope * xm
        y_pred = slope * xs + intercept
        ss_res = ((ys - y_pred)**2).sum()
        ss_tot = ((ys - ym)**2).sum()
        r2 = 1 - ss_res/ss_tot if ss_tot > 0 else 0
        return slope, intercept, r2

    for seg_len in [30, 45, 60]:
        if n < seg_len + 5: continue
        seg_start = n - seg_len
        seg_peaks   = [p for p in peaks   if p >= seg_start]
        seg_troughs = [t for t in troughs if t >= seg_start]
        if len(seg_peaks) < 3 or len(seg_troughs) < 3: continue

        rs, ri, rr2 = fit_line(seg_peaks,   [h[p] for p in seg_peaks])
        ss, si, sr2 = fit_line(seg_troughs, [l[t] for t in seg_troughs])

        if rr2 < 0.5 or sr2 < 0.5: continue

        converge = (rs < 0 and ss > 0)          # symmetric triangle
        asc      = (rs >= 0 and ss > 0 and abs(rs) < abs(ss))  # ascending
        desc     = (rs < 0 and ss <= 0 and abs(rs) > abs(ss))  # descending

        if converge:
            patterns.append({
                'name': '對稱三角收斂', 'type': 'neutral',
                'start_idx': seg_start, 'end_idx': n-1,
                'start_date': dates[seg_start], 'end_date': dates[-1],
                'key_points': [],
                'trendlines': {
                    'upper': {'slope': round(rs,4), 'intercept': round(ri,2)},
                    'lower': {'slope': round(ss,4), 'intercept': round(si,2)},
                },
                'description': '對稱三角收斂，等待方向突破，成交量萎縮為佳',
                'confidence': int(min(92, (rr2+sr2)/2*100)),
            })
        elif asc:
            patterns.append({
                'name': '上升三角形', 'type': 'bullish',
                'start_idx': seg_start, 'end_idx': n-1,
                'start_date': dates[seg_start], 'end_date': dates[-1],
                'key_points': [],
                'trendlines': {
                    'upper': {'slope': round(rs,4), 'intercept': round(ri,2)},
                    'lower': {'slope': round(ss,4), 'intercept': round(si,2)},
                },
                'description': '上升三角形，上方壓力逐步收窄，突破看多',
                'confidence': int(min(90, (rr2+sr2)/2*100)),
            })
        elif desc:
            patterns.append({
                'name': '下降三角形', 'type': 'bearish',
                'start_idx': seg_start, 'end_idx': n-1,
                'start_date': dates[seg_start], 'end_date': dates[-1],
                'key_points': [],
                'trendlines': {
                    'upper': {'slope': round(rs,4), 'intercept': round(ri,2)},
                    'lower': {'slope': round(ss,4), 'intercept': round(si,2)},
                },
                'description': '下降三角形，下方支撐逐步收窄，跌破看空',
                'confidence': int(min(90, (rr2+sr2)/2*100)),
            })
        break  # one triangle per stock

    # ── 6. Rectangle / Box ───────────────────────────────────────
    if len(seg_peaks := [p for p in peaks if p >= n-40]) >= 2 and        len(seg_troughs := [t for t in troughs if t >= n-40]) >= 2:
        top_prices    = [h[p] for p in seg_peaks]
        bottom_prices = [l[t] for t in seg_troughs]
        top_range    = (max(top_prices) - min(top_prices)) / max(top_prices)
        bottom_range = (max(bottom_prices) - min(bottom_prices)) / max(bottom_prices) if max(bottom_prices) else 1
        if top_range < 0.04 and bottom_range < 0.04:
            box_top    = round(np.mean(top_prices), 2)
            box_bottom = round(np.mean(bottom_prices), 2)
            patterns.append({
                'name': '矩形整理', 'type': 'neutral',
                'start_idx': min(seg_peaks+seg_troughs), 'end_idx': n-1,
                'start_date': dates[min(seg_peaks+seg_troughs)], 'end_date': dates[-1],
                'key_points': [],
                'box': {'top': box_top, 'bottom': box_bottom},
                'description': f'矩形箱型整理，壓力 {box_top}，支撐 {box_bottom}，方向突破後加速',
                'confidence': int(min(88, (1-top_range/0.04)*(1-bottom_range/0.04)*88)),
            })

    # Deduplicate — keep highest confidence per type
    seen_types = {}
    unique = []
    for p in sorted(patterns, key=lambda x: -x['confidence']):
        key = p['name']
        if key not in seen_types:
            seen_types[key] = True
            unique.append(p)
    return unique[:6]  # max 6 patterns per stock


@app.route('/api/patterns', methods=['GET'])
def get_patterns():
    code   = request.args.get('code')
    period = request.args.get('period', '6mo')
    if not code:
        return jsonify({'error': 'No code'}), 400
    cache_key = f"pat_{code}_{period}"
    now = time.time()
    if cache_key in _cache and now - _cache[cache_key][0] < 600:
        return jsonify(_cache[cache_key][1])
    df = get_df(code, period)
    if df is None or df.empty:
        return jsonify({'error': 'No data'}), 404
    try:
        result = detect_patterns(df)
        _cache[cache_key] = (now, result)
        return jsonify(result)
    except Exception as e:
        print(f"Pattern error {code}: {e}")
        return jsonify([])

# ════════════════════════════════════════════════════════════════
#  WEEKLY REPORT SYSTEM
#  - 每週一凌晨 00:05 自動產生
#  - 也可透過 /api/report/generate 手動觸發
#  - 報告存於 data/reports/YYYY-WNN.json
# ════════════════════════════════════════════════════════════════
import threading, calendar

REPORTS_DIR = os.path.join(DATA_DIR, 'reports')
os.makedirs(REPORTS_DIR, exist_ok=True)

def _build_weekly_report():
    """Build the weekly report dict and save to JSON."""
    now   = datetime.now()
    year, week, _ = now.isocalendar()
    fname = os.path.join(REPORTS_DIR, f'{year}-W{week:02d}.json')

    # ── 1. Journal data ──────────────────────────────────────────
    week_start = now - timedelta(days=now.weekday() + 7)  # last Mon
    week_end   = week_start + timedelta(days=6)           # last Sun
    ws = week_start.strftime('%Y-%m-%d')
    we = week_end.strftime('%Y-%m-%d')

    with get_db() as db:
        all_trades = [dict(r) for r in
                      db.execute('SELECT * FROM journal ORDER BY date ASC, id ASC').fetchall()]
        week_trades = [t for t in all_trades if ws <= t['date'] <= we]

    # ── 2. Position P&L ─────────────────────────────────────────
    positions = {}
    for t in all_trades:
        c = t['code']
        if c not in positions:
            positions[c] = {'code':c,'name':t['name'],'shares':0,'avg_cost':0,'realized':0}
        p = positions[c]
        if t['action'] == 'buy':
            total = p['avg_cost']*p['shares'] + t['price']*t['shares']
            p['shares'] += t['shares']
            p['avg_cost'] = total / p['shares'] if p['shares'] > 0 else 0
        elif t['action'] == 'sell':
            p['realized'] += (t['price'] - p['avg_cost']) * min(t['shares'], p['shares'])
            p['shares'] = max(0, p['shares'] - t['shares'])
            if p['shares'] == 0: p['avg_cost'] = 0

    holdings = []
    mkt_total = 0
    cost_total = 0
    unrealized_total = 0
    for c, p in positions.items():
        if p['shares'] <= 0: continue
        try:
            df = get_df(c, '5d')
            cp = round(float(df.iloc[-1]['Close']), 2) if df is not None and not df.empty else None
        except: cp = None
        unr = (cp - p['avg_cost']) * p['shares'] if cp else 0
        mv  = cp * p['shares'] if cp else 0
        cost = p['avg_cost'] * p['shares']
        mkt_total       += mv
        cost_total      += cost
        unrealized_total += unr
        holdings.append({
            'code': c, 'name': p['name'],
            'shares': round(p['shares'], 2),
            'avg_cost': round(p['avg_cost'], 2),
            'current_price': cp,
            'market_value': round(mv, 2),
            'unrealized': round(unr, 2),
            'unrealized_pct': round(unr / cost * 100, 2) if cost else 0,
        })

    realized_total = sum(p['realized'] for p in positions.values())

    # ── 3. Weekly winners / losers ──────────────────────────────
    week_pnl = {}
    for t in week_trades:
        if t['code'] not in week_pnl: week_pnl[t['code']] = {'name':t['name'],'pnl':0}
        if t['action'] == 'sell':
            p = positions.get(t['code'])
            if p: week_pnl[t['code']]['pnl'] += (t['price'] - p['avg_cost']) * t['shares']
    sorted_pnl = sorted(week_pnl.items(), key=lambda x: x[1]['pnl'], reverse=True)
    winners = [{'code':k,'name':v['name'],'pnl':round(v['pnl'],2)} for k,v in sorted_pnl if v['pnl']>0][:3]
    losers  = [{'code':k,'name':v['name'],'pnl':round(v['pnl'],2)} for k,v in sorted_pnl if v['pnl']<0][-3:]

    # ── 4. Market performance (indices) ─────────────────────────
    INDICES = {
        'taiwan':   [('0050.TW','台灣加權（ETF）'),('2330.TW','台積電')],
        'japan':    [('7203.T','豐田'),('9984.T','軟銀')],
        'shanghai': [('510050.SS','上證50 ETF'),('600519.SS','貴州茅台')],
    }
    market_perf = {}
    for mkt, codes in INDICES.items():
        market_perf[mkt] = []
        for code, label in codes:
            try:
                df = get_df(code, '5d')
                if df is not None and len(df) >= 2:
                    prev  = float(df.iloc[-2]['Close'])
                    curr  = float(df.iloc[-1]['Close'])
                    chg   = round((curr - prev) / prev * 100, 2)
                    market_perf[mkt].append({'code':code,'label':label,'price':round(curr,2),'change_pct':chg})
            except: pass

    # ── 5. Triggered alerts this week ───────────────────────────
    with get_db() as db:
        triggered = [dict(r) for r in
                     db.execute('SELECT * FROM alerts WHERE triggered=1').fetchall()]

    # ── 6. Assemble report ──────────────────────────────────────
    report = {
        'year': year, 'week': week,
        'period': f'{ws} ~ {we}',
        'generated_at': now.strftime('%Y-%m-%d %H:%M'),
        'portfolio': {
            'holdings': len(holdings),
            'market_value': round(mkt_total, 2),
            'cost': round(cost_total, 2),
            'unrealized': round(unrealized_total, 2),
            'unrealized_pct': round(unrealized_total / cost_total * 100, 2) if cost_total else 0,
            'realized': round(realized_total, 2),
            'total_pnl': round(unrealized_total + realized_total, 2),
            'holdings_detail': sorted(holdings, key=lambda x: abs(x['unrealized']), reverse=True),
        },
        'week_trades': week_trades,
        'week_winners': winners,
        'week_losers':  losers,
        'market_perf':  market_perf,
        'triggered_alerts': triggered,
    }

    with open(fname, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f'[WeeklyReport] Saved → {fname}')
    return report


def _schedule_weekly():
    """Schedule next Monday 00:05 run using threading.Timer."""
    now  = datetime.now()
    days_until_monday = (7 - now.weekday()) % 7 or 7
    next_monday = now.replace(hour=0, minute=5, second=0, microsecond=0) + timedelta(days=days_until_monday)
    delay = (next_monday - now).total_seconds()
    print(f'[WeeklyReport] Next auto-generate: {next_monday.strftime("%Y-%m-%d %H:%M")} (in {delay/3600:.1f}h)')
    def run():
        try: _build_weekly_report()
        except Exception as e: print(f'[WeeklyReport] Error: {e}')
        _schedule_weekly()   # reschedule
    timer = threading.Timer(delay, run)
    timer.daemon = True
    timer.start()

# Start scheduler when app loads, except in isolated tests and tooling.
if os.environ.get('AETERNUS_DISABLE_BACKGROUND_TASKS') != '1':
    _schedule_weekly()


@app.route('/api/report/generate', methods=['POST'])
def generate_report():
    """Manually trigger weekly report generation."""
    try:
        report = _build_weekly_report()
        return jsonify({'success': True, 'report': report})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/report/list', methods=['GET'])
def list_reports():
    """Return list of saved report files, newest first."""
    files = sorted(
        [f for f in os.listdir(REPORTS_DIR) if f.endswith('.json')],
        reverse=True
    )
    reports = []
    for fname in files[:12]:   # max 12 weeks
        try:
            with open(os.path.join(REPORTS_DIR, fname), encoding='utf-8') as f:
                r = json.load(f)
            reports.append({
                'filename': fname,
                'year': r.get('year'), 'week': r.get('week'),
                'period': r.get('period'),
                'generated_at': r.get('generated_at'),
                'holdings': r['portfolio'].get('holdings', 0),
                'total_pnl': r['portfolio'].get('total_pnl', 0),
            })
        except: pass
    return jsonify(reports)


@app.route('/api/report/<filename>', methods=['GET'])
def get_report(filename):
    """Return a specific report by filename."""
    # Security: only allow YYYY-WNN.json pattern
    import re as _re
    if not _re.match(r'^\d{4}-W\d{2}\.json$', filename):
        return jsonify({'error': 'Invalid filename'}), 400
    fpath = os.path.join(REPORTS_DIR, filename)
    if not os.path.exists(fpath):
        return jsonify({'error': 'Not found'}), 404
    with open(fpath, encoding='utf-8') as f:
        return jsonify(json.load(f))


# ════════════════════════════════════════════════════════════════
#  BUILD WEEK: EVIDENCE-GROUNDED GPT-5.6 RESEARCH AGENT
# ════════════════════════════════════════════════════════════════

@app.route('/api/research/config', methods=['GET'])
def research_config():
    """Return public research configuration without exposing credentials."""
    try:
        effort = configured_reasoning_effort()
        config_error = None
    except ResearchValidationError as exc:
        effort = None
        config_error = str(exc)
    return jsonify({
        'openai_configured': openai_is_configured(),
        'model': configured_model(),
        'reasoning_effort': effort,
        'configuration_error': config_error,
        'markets': [
            {'id': key, 'label': value['label'], 'currency': value['currency']}
            for key, value in RESEARCH_MARKET_CONFIG.items()
        ],
        'periods': list(RESEARCH_PERIODS.keys()),
        'demo': {
            'symbol': DEMO_SYMBOL,
            'market': DEMO_MARKET,
            'period': '1y',
            'question': DEMO_SCENARIO,
            'data_as_of': '2026-06-30',
            'data_mode': 'synthetic_demo',
            'credential_free_fallback': True,
        },
    })


@app.route('/api/research/symbols', methods=['GET'])
def research_symbols():
    market = (request.args.get('market') or '').strip().lower()
    if market not in RESEARCH_DEFAULT_SYMBOLS:
        return jsonify({
            'error': {'code': 'invalid_market', 'message': 'Unsupported research market.'}
        }), 400
    return jsonify({
        'market': market,
        'symbols': RESEARCH_DEFAULT_SYMBOLS[market],
        'demo_mode': market == DEMO_MARKET,
    })


@app.route('/api/research/run', methods=['POST'])
def run_research_agent():
    """Run deterministic tools and an optional GPT-5.6 structured synthesis."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({
            'error': {'code': 'invalid_json', 'message': 'A JSON request body is required.'}
        }), 400

    try:
        validated = validate_research_request(
            payload.get('symbol'),
            payload.get('market'),
            payload.get('period'),
            payload.get('question'),
            payload.get('demo_mode', False),
        )
        prefer_gpt = payload.get('prefer_gpt', True)
        if not isinstance(prefer_gpt, bool):
            raise ResearchValidationError('prefer_gpt must be a boolean.')

        toolbox = ResearchToolbox(
            validated,
            history_loader=get_df,
            profile_loader=get_fundamentals,
        )
        if validated.demo_mode and (not prefer_gpt or not openai_is_configured()):
            report = run_deterministic_demo(validated, toolbox)
        else:
            report = GPTResearchAgent().run(validated, toolbox)
        return jsonify(report)
    except ResearchValidationError as exc:
        return jsonify({
            'error': {'code': 'invalid_request', 'message': str(exc)}
        }), 400
    except ResearchDataUnavailable as exc:
        return jsonify({
            'error': {'code': 'data_unavailable', 'message': str(exc)}
        }), 404
    except MissingOpenAIKey as exc:
        return jsonify({
            'error': {'code': 'missing_api_key', 'message': str(exc)}
        }), 503
    except ResearchOutputError as exc:
        print(f'[ResearchOutput] {exc}')
        return jsonify({
            'error': {
                'code': 'unverified_model_output',
                'message': 'GPT output could not be verified against deterministic evidence.',
            }
        }), 502
    except ResearchAgentError as exc:
        print(f'[ResearchAgent] {exc}')
        return jsonify({
            'error': {'code': 'agent_failed', 'message': 'The research agent did not complete.'}
        }), 502
    except Exception as exc:
        print(f'[ResearchAgentUnexpected] {type(exc).__name__}: {exc}')
        return jsonify({
            'error': {'code': 'provider_error', 'message': 'The research provider request failed.'}
        }), 502

# ════════════════════════════════════════════════════════════════
#  OLLAMA AI PROXY
#  前端 → Flask /api/ai/chat → Ollama localhost:11434
#  支援串流 (stream=True)，模型可在請求中指定
# ════════════════════════════════════════════════════════════════
import urllib.request, urllib.error, urllib.parse

OLLAMA_URL   = 'http://localhost:11434/api/chat'
OLLAMA_MODEL = 'llama3.2'   # 預設模型，可在前端設定中覆蓋

@app.route('/api/ai/chat', methods=['POST'])
def ai_chat():
    """Proxy to local Ollama instance with streaming support."""
    data   = request.json or {}
    model  = data.get('model', OLLAMA_MODEL)
    messages = data.get('messages', [])
    system   = data.get('system', '')

    if not messages:
        return jsonify({'error': 'No messages'}), 400

    # Prepend system message if provided
    payload_msgs = []
    if system:
        payload_msgs.append({'role': 'system', 'content': system})
    payload_msgs.extend(messages)

    payload = json.dumps({
        'model':    model,
        'messages': payload_msgs,
        'stream':   False,
        'options':  {'temperature': 0.7, 'num_predict': 800},
    }).encode('utf-8')

    try:
        req = urllib.request.Request(
            OLLAMA_URL,
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        reply = result.get('message', {}).get('content', '')
        return jsonify({'reply': reply, 'model': model})

    except urllib.error.URLError as e:
        # Ollama not running or not installed
        msg = str(e.reason) if hasattr(e, 'reason') else str(e)
        return jsonify({'error': 'Ollama 未啟動：' + msg}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/models', methods=['GET'])
def ai_models():
    """Return list of locally available Ollama models."""
    try:
        req = urllib.request.Request('http://localhost:11434/api/tags', method='GET')
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        models = [m['name'] for m in data.get('models', [])]
        return jsonify({'models': models, 'running': True})
    except:
        return jsonify({'models': [], 'running': False})


# ── Background alert auto-check (every 5 min during market hours) ─
def _auto_check_alerts():
    """Run in background thread, check all untriggered alerts."""
    import datetime
    while True:
        try:
            time.sleep(300)  # every 5 minutes
            now = datetime.datetime.now()
            # Only run during Taiwan/Japan/Shanghai market hours (roughly 8:00-16:00 local)
            if not (8 <= now.hour <= 16):
                continue
            with get_db() as db:
                rows = db.execute(
                    'SELECT DISTINCT code FROM alerts WHERE triggered=0'
                ).fetchall()
            codes = [r['code'] for r in rows]
            if not codes:
                continue
            for code in codes:
                try:
                    with get_db() as db:
                        alerts = [dict(r) for r in db.execute(
                            'SELECT * FROM alerts WHERE code=? AND triggered=0', (code,)
                        ).fetchall()]
                    if not alerts:
                        continue
                    # get quote
                    import yfinance as yf
                    info = yf.Ticker(code).fast_info
                    price = float(info.last_price or 0)
                    df = None
                    for alert in alerts:
                        if alert.get('alert_type','price') != 'price' and df is None:
                            df = get_df(code, '3mo')
                        if _check_one_alert(alert, price, df):
                            with get_db() as db:
                                db.execute('UPDATE alerts SET triggered=1 WHERE id=?', (alert['id'],))
                            print(f'[Alert] TRIGGERED: {code} id={alert["id"]} type={alert.get("alert_type","price")}')
                except Exception as e:
                    print(f'[Alert] check error {code}: {e}')
        except Exception as e:
            print(f'[AlertThread] error: {e}')

if os.environ.get('AETERNUS_DISABLE_BACKGROUND_TASKS') != '1':
    _alert_thread = threading.Thread(target=_auto_check_alerts, daemon=True)
    _alert_thread.start()

if __name__ == '__main__':
    _migrate_alerts_table()
    import signal, sys

    print('=' * 50)
    print('  Aeternus Market Intelligence')
    print('  http://localhost:5000')
    print('  按 Ctrl+C 關閉伺服器')
    print('=' * 50)

    def _shutdown(sig, frame):
        print('\n[Server] 正在關閉...')
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # use_reloader=False prevents the double-process issue on Windows
    # that causes WinError 10038 on Ctrl+C
    app.run(
        debug=False,
        port=5000,
        host='127.0.0.1',
        use_reloader=False,
        threaded=True,
    )
