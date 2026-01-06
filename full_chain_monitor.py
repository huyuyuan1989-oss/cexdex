"""
🔗 全鏈資金流向深度分析系統 v2.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
功能特色：
├─ 📡 多時間框架動能分析 (1H/24H/7D/30D)
├─ 🚨 異常流動性偵測 (Liquidity Anomaly)
├─ 🔄 鏈間資金流動追蹤 (Cross-Chain Flow)
├─ 🆕 新幣首發偵測 (New Token Detection)
├─ 📊 歷史趨勢追蹤 (SQLite 持久化)
├─ 🔔 Discord 即時通知
├─ ⚡ 非同步高速請求 (8x 加速)
├─ 📄 多格式報告匯出 (HTML/CSV/JSON)
└─ 🔁 定時自動執行
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import asyncio
import aiohttp
import sqlite3
import json
import os
import csv
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from colorama import Fore, Style, init
from jinja2 import Template


# ================= 初始化 =================
init(autoreset=True)

# 設定日誌系統
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "chain_monitor.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ================= 1. 配置區 (Configuration) =================

# Discord Webhook URLs (支援多個通知頻道)
# GitHub Secret: 用逗號分隔多個 URL，例如: url1,url2
_webhook_env = os.getenv("DISCORD_WEBHOOK_URL_ENV", "")
if _webhook_env:
    # 去重並過濾空值
    _raw_urls = [url.strip() for url in _webhook_env.split(",") if url.strip()]
    DISCORD_WEBHOOK_URLS = list(dict.fromkeys(_raw_urls))
else:
    # 本地開發用的預設值
    DISCORD_WEBHOOK_URLS = [
        "https://discord.com/api/webhooks/1457246054394363990/6vOf6A1Tg6ndqE-NNvfwEPgJM6NQgZCcmwUY5zYn1enVdBI1kMj140KT3Iq4DUD7_u4N"
    ]

# 監控配置
TOP_N_CHAINS = 20           # 監控前 20 名公鏈
MOMENTUM_THRESHOLD = 0.0    # 資金流動閾值 (%) - 設為 0 以監控所有鏈
BUYING_PRESSURE_ALERT = 3.0 # 買壓係數警報閾值
LIQUIDITY_MIN = 50000       # 最低流動性 ($)
VOLUME_MIN = 100000         # 最低交易量 ($)

# 異常偵測閾值
LIQUIDITY_SURGE_THRESHOLD = 50   # 流動性暴增警報 (%)
LIQUIDITY_DROP_THRESHOLD = -30   # 流動性驟減警報 (%)

# 定時執行間隔 (秒) - 設為 0 則只執行一次
SCHEDULE_INTERVAL = 1800  # 30 分鐘自動執行一次

# 資料庫路徑
DB_PATH = Path(__file__).parent / "chain_data.db"

# 報告輸出路徑
REPORT_DIR = Path(__file__).parent / "reports"
REPORT_DIR.mkdir(exist_ok=True)

# ==== GitHub Pages 設定 (用於 Discord 顯示報告連結) ====
# 格式: https://<用戶名>.github.io/<倉庫名>/reports/
# 請將下面的 URL 改成您的 GitHub Pages 網址
GITHUB_PAGES_BASE_URL = os.getenv(
    "GITHUB_PAGES_URL", 
    "https://huyuyuan1989-oss.github.io/cexdex/reports/"  # 報告存放在 reports/ 資料夾
)

# 公鏈名稱映射表 (DefiLlama -> DEX Screener)
# 包含 TVL 前 30 名的公鏈
CHAIN_MAPPING = {
    # 第 1-10 名
    'Ethereum': 'ethereum',
    'Solana': 'solana',
    'BSC': 'bsc',
    'Binance Smart Chain': 'bsc',
    'Tron': 'tron',
    'Base': 'base',
    'Arbitrum': 'arbitrum',
    'Arbitrum One': 'arbitrum',
    'Bitcoin': 'bitcoin',
    
    # 第 11-20 名
    'Avalanche': 'avalanche',
    'Polygon': 'polygon',
    'Sui': 'sui',
    'Hyperliquid L1': 'hyperliquid',
    'OP Mainnet': 'optimism',
    'Optimism': 'optimism',
    'Aptos': 'aptos',
    'Cronos': 'cronos',
    'Vaulta': 'eos',  # EOS 改名為 Vaulta
    'Mantle': 'mantle',
    
    # 第 21-30 名 (備用)
    'Starknet': 'starknet',
    'Sei': 'sei',
    'Fantom': 'fantom',
    'zkSync Era': 'zksync',
    'Linea': 'linea',
    'Scroll': 'scroll',
    'Blast': 'blast',
    'Manta': 'manta',
    'Near': 'near',
    'Cardano': 'cardano',
    'PulseChain': 'pulsechain',
    'Gnosis': 'gnosis',
    'TON': 'ton',
    'Hedera': 'hedera',
    'Algorand': 'algorand',
    'Flow': 'flow',
    'XRPL': 'xrpl',
    'Injective': 'injective',
    'Osmosis': 'osmosis',
    'Stellar': 'stellar',
    'MultiversX': 'multiversx',
    'Movement': 'movement',
    'Flare': 'flare',
    'Hydration': 'hydration',
    'dYdX': 'dydx',
    'Stacks': 'stacks',
    'Kaia': 'kaia',
}

# 忽略名單 (穩定幣、封裝幣、原生幣)
IGNORE_TOKENS = {
    'USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'USDD', 'BUSD', 'FRAX', 'LUSD', 'USDP',
    'WETH', 'WBTC', 'WBNB', 'WSOL', 'STETH', 'WSTETH', 'RETH', 'CBETH', 'FRXETH',
    'ETH', 'BNB', 'SOL', 'BTC', 'MATIC', 'AVAX', 'ARB', 'OP', 'SUI', 'APT', 'SEI'
}

# ================= 2. 資料庫模組 (Database) =================

def init_database():
    """初始化 SQLite 資料庫 (使用 context manager 確保連線正確關閉)"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # 公鏈歷史數據表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chain_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    chain_name TEXT,
                    tvl REAL,
                    change_1d REAL,
                    change_7d REAL,
                    change_30d REAL,
                    status TEXT
                )
            ''')
            
            # 代幣推薦歷史表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS token_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    chain_id TEXT,
                    symbol TEXT,
                    price REAL,
                    change_24h REAL,
                    volume REAL,
                    liquidity REAL,
                    buying_pressure REAL,
                    url TEXT,
                    net_flow_count INTEGER DEFAULT 0,
                    net_volume REAL DEFAULT 0
                )
            ''')

            # 自動遷移：嘗試添加 net_flow_count (如果不存在)
            try:
                cursor.execute("ALTER TABLE token_history ADD COLUMN net_flow_count INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass

            # 自動遷移：嘗試添加 net_volume (如果不存在)
            try:
                cursor.execute("ALTER TABLE token_history ADD COLUMN net_volume REAL DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            
            # 系統績效追蹤表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS performance_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recommendation_date DATE,
                    symbol TEXT,
                    chain_id TEXT,
                    entry_price REAL,
                    current_price REAL,
                    price_change_pct REAL,
                    check_date DATE
                )
            ''')
            
            conn.commit()
            logger.info("📦 資料庫初始化完成")
    except sqlite3.Error as e:
        logger.error(f"❌ 資料庫初始化失敗: {e}")
        raise

def save_chain_data(chains):
    """儲存公鏈數據到資料庫 (使用 context manager)"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            for chain in chains:
                cursor.execute('''
                    INSERT INTO chain_history (chain_name, tvl, change_1d, change_7d, change_30d, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    chain['chain_name'],
                    chain['tvl'],
                    chain['change_1d'],
                    chain['change_7d'],
                    chain.get('change_30d', 0),
                    chain['status']
                ))
            
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"❌ 儲存公鏈數據失敗: {e}")

def save_token_data(chain_id, tokens):
    """儲存代幣數據到資料庫 (使用 context manager)"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            for token in tokens:
                try:
                    price_str = token['price'].replace('$', '').replace(',', '')
                    
                    # 計算估算的淨流入金額 (Volume Delta)
                    txns_diff = token.get('txns_diff', 0)
                    # 反推總筆數 (因為 txns_diff = buys - sells，我們需要 buys + sells)
                    # 但 token dict 中沒有直接儲存 buys/sells，只存了 txns_diff。
                    # 我們需要在 analyze_assets_async 中傳遞 buys/sells 或 total_txns
                    # 暫時使用 simplified estimation: 如果 txns_diff > 0 則 net_volume 為正
                    # 更精確的做法是讀取 token['buys'] 和 token['sells'] 如果有的話
                    # 根據 Step 1896，token_data 只有 txns_diff.
                    # 讓我修改一下 analyze_assets_async 先?
                    # 或者直接用 Volume * (txns_diff / (txns_diff if txns_diff > 0 else 1)) <-- No.
                    
                    # 補救：如果無法取得精確 total_txns，假設 ratio = 0.1 (保守估計)
                    # 不，我們必須準確。
                    # 讓我們假設 token 中有 total_txns。我需要在 analyze_assets_async 加進去。
                    # 現在先寫 SQL，等下改 analyze。
                    total_txns = token.get('total_txns', 1)
                    if total_txns == 0: total_txns = 1
                    
                    net_volume = token['volume'] * (txns_diff / total_txns)

                    cursor.execute('''
                        INSERT INTO token_history (chain_id, symbol, price, change_24h, volume, liquidity, buying_pressure, url, net_flow_count, net_volume)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        chain_id,
                        token['symbol'],
                        float(price_str),
                        token['change_24h'],
                        token['volume'],
                        token['liquidity'],
                        token['pressure'],
                        token['url'],
                        txns_diff,
                        net_volume
                    ))
                except (ValueError, KeyError) as e:
                    logger.warning(f"⚠️ 跳過無效代幣數據 {token.get('symbol', 'N/A')}: {e}")
                    continue
            
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"❌ 儲存代幣數據失敗: {e}")

def get_yesterday_recommendations():
    """獲取昨日推薦的代幣 (使用 context manager)"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            
            cursor.execute('''
                SELECT symbol, chain_id, price, change_24h
                FROM token_history
                WHERE DATE(timestamp) = ?
            ''', (yesterday,))
            
            return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"❌ 獲取昨日推薦失敗: {e}")
        return []

def calculate_system_accuracy():
    """計算系統推薦準確率 (使用 context manager)"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # 獲取過去 7 天的推薦
            week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            
            cursor.execute('''
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN change_24h > 0 THEN 1 ELSE 0 END) as profitable
                FROM token_history
                WHERE DATE(timestamp) >= ?
            ''', (week_ago,))
            
            result = cursor.fetchone()
            
            if result and result[0] > 0:
                return {
                    'total_recommendations': result[0],
                    'profitable_count': result[1] or 0,
                    'accuracy': ((result[1] or 0) / result[0]) * 100
                }
    except sqlite3.Error as e:
        logger.error(f"❌ 計算準確率失敗: {e}")
    
    return {'total_recommendations': 0, 'profitable_count': 0, 'accuracy': 0}

def get_consecutive_risers():
    """
    📈 連續上漲追蹤：找出連續多天上漲的代幣
    返回連續 2 天以上每次 change_24h > 0 的代幣
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # 獲取過去 7 天有記錄的代幣
            cursor.execute('''
                SELECT symbol, chain_id, 
                       GROUP_CONCAT(change_24h) as changes,
                       COUNT(*) as appearances,
                       MAX(liquidity) as max_liquidity,
                       MAX(volume) as max_volume
                FROM token_history
                WHERE timestamp >= datetime('now', '-7 days')
                GROUP BY symbol, chain_id
                HAVING appearances >= 2
            ''')
            
            results = cursor.fetchall()
            consecutive_risers = []
            
            for row in results:
                symbol, chain_id, changes_str, appearances, max_liq, max_vol = row
                
                try:
                    changes = [float(c) for c in changes_str.split(',')]
                    
                    # 計算連續上漲天數 (從最近往前數)
                    consecutive_days = 0
                    for change in reversed(changes):
                        if change > 0:
                            consecutive_days += 1
                        else:
                            break
                    
                    if consecutive_days >= 2:
                        consecutive_risers.append({
                            'symbol': symbol,
                            'chain_id': chain_id,
                            'consecutive_days': consecutive_days,
                            'recent_changes': changes[-3:] if len(changes) >= 3 else changes,
                            'max_liquidity': max_liq or 0,
                            'max_volume': max_vol or 0,
                            'label': f"🔥 連漲 {consecutive_days} 天"
                        })
                except (ValueError, AttributeError):
                    continue
            
            # 按連續天數排序
            consecutive_risers.sort(key=lambda x: x['consecutive_days'], reverse=True)
            return consecutive_risers[:10]
            
    except sqlite3.Error as e:
        logger.error(f"❌ 獲取連續上漲代幣失敗: {e}")
        return []

def get_volume_anomalies():
    """
    📊 量能異常偵測：找出交易量突然暴增的代幣
    條件：今日交易量 > 7日平均的 2 倍
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                WITH RecentVolume AS (
                    SELECT symbol, chain_id, volume, liquidity,
                           AVG(volume) OVER (PARTITION BY symbol, chain_id) as avg_volume,
                           ROW_NUMBER() OVER (PARTITION BY symbol, chain_id ORDER BY timestamp DESC) as rn
                    FROM token_history
                    WHERE timestamp >= datetime('now', '-7 days')
                )
                SELECT symbol, chain_id, volume, avg_volume, liquidity,
                       CASE WHEN avg_volume > 0 THEN volume / avg_volume ELSE 0 END as volume_ratio
                FROM RecentVolume
                WHERE rn = 1 AND avg_volume > 0 AND volume > avg_volume * 2
                ORDER BY volume_ratio DESC
                LIMIT 10
            ''')
            
            results = cursor.fetchall()
            anomalies = []
            
            for row in results:
                symbol, chain_id, volume, avg_vol, liquidity, ratio = row
                anomalies.append({
                    'symbol': symbol,
                    'chain_id': chain_id,
                    'current_volume': volume or 0,
                    'avg_volume': avg_vol or 0,
                    'volume_ratio': round(ratio, 1) if ratio else 0,
                    'liquidity': liquidity or 0,
                    'label': f"📢 量能 {round(ratio, 1)}x"
                })
            
            return anomalies
            
    except sqlite3.Error as e:
        logger.error(f"❌ 獲取量能異常代幣失敗: {e}")
        return []

def get_ranking_changes():
    """
    🔄 排名變化追蹤：比對當前與上次報告的排名變化
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # 獲取上次報告的代幣排名 (按買壓排序)
            cursor.execute('''
                WITH LastReport AS (
                    SELECT symbol, chain_id, buying_pressure, liquidity,
                           ROW_NUMBER() OVER (PARTITION BY chain_id ORDER BY buying_pressure DESC) as prev_rank,
                           timestamp
                    FROM token_history
                    WHERE DATE(timestamp) = (
                        SELECT DATE(MAX(timestamp))
                        FROM token_history
                        WHERE DATE(timestamp) < DATE('now')
                    )
                ),
                CurrentReport AS (
                    SELECT symbol, chain_id, buying_pressure, liquidity,
                           ROW_NUMBER() OVER (PARTITION BY chain_id ORDER BY buying_pressure DESC) as curr_rank
                    FROM token_history
                    WHERE DATE(timestamp) = DATE('now')
                )
                SELECT 
                    c.symbol, c.chain_id, 
                    l.prev_rank, c.curr_rank,
                    c.buying_pressure,
                    c.liquidity,
                    CASE 
                        WHEN l.prev_rank IS NULL THEN 'new'
                        WHEN c.curr_rank < l.prev_rank THEN 'up'
                        WHEN c.curr_rank > l.prev_rank THEN 'down'
                        ELSE 'same'
                    END as change_type,
                    COALESCE(l.prev_rank - c.curr_rank, 0) as rank_change
                FROM CurrentReport c
                LEFT JOIN LastReport l ON c.symbol = l.symbol AND c.chain_id = l.chain_id
                WHERE c.curr_rank <= 10
                ORDER BY c.chain_id, c.curr_rank
            ''')
            
            results = cursor.fetchall()
            ranking_changes = {}
            
            for row in results:
                symbol, chain_id, prev_rank, curr_rank, pressure, liquidity, change_type, rank_change = row
                
                if chain_id not in ranking_changes:
                    ranking_changes[chain_id] = []
                
                label = ""
                if change_type == 'new':
                    label = "⬆️ 新進榜"
                elif change_type == 'up':
                    label = f"↗️ +{rank_change}"
                elif change_type == 'down':
                    label = f"↘️ {rank_change}"
                
                ranking_changes[chain_id].append({
                    'symbol': symbol,
                    'prev_rank': prev_rank,
                    'curr_rank': curr_rank,
                    'change_type': change_type,
                    'rank_change': rank_change,
                    'pressure': pressure or 0,
                    'liquidity': liquidity or 0,
                    'label': label
                })
            
            return ranking_changes
            
    except sqlite3.Error as e:
        logger.error(f"❌ 獲取排名變化失敗: {e}")
        return {}

def get_long_term_growth_tokens():
    """
    📈 長線成長追蹤：比對資料庫歷史數據，找出近一季持續成長的代幣
    
    條件：
    1. 90 天前有記錄
    2. 流動性成長 > 20%
    3. 出現次數 > 5 次 (確保不是偶然)
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # 計算 90 天前的日期
            quarter_ago = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
            
            # 查詢：找出 90 天內多次出現、且流動性持續增加的代幣
            cursor.execute('''
                WITH TokenStats AS (
                    SELECT 
                        symbol,
                        chain_id,
                        COUNT(*) as appearances,
                        MIN(liquidity) as min_liquidity,
                        MAX(liquidity) as max_liquidity,
                        AVG(liquidity) as avg_liquidity,
                        MIN(DATE(timestamp)) as first_seen,
                        MAX(DATE(timestamp)) as last_seen,
                        AVG(change_24h) as avg_change,
                        SUM(CASE WHEN net_flow_count > 0 THEN 1 ELSE 0 END) as positive_flow_days,
                        SUM(net_volume) as accumulated_net_volume
                    FROM token_history
                    WHERE DATE(timestamp) >= ?
                    GROUP BY symbol, chain_id
                    HAVING COUNT(*) >= 3
                )
                SELECT 
                    symbol,
                    chain_id,
                    appearances,
                    min_liquidity,
                    max_liquidity,
                    avg_liquidity,
                    first_seen,
                    last_seen,
                    avg_change,
                    CASE 
                        WHEN min_liquidity > 0 THEN ((max_liquidity - min_liquidity) / min_liquidity * 100)
                        ELSE 0
                    END as liquidity_growth_pct,
                    positive_flow_days,
                    accumulated_net_volume
                FROM TokenStats
                WHERE max_liquidity > 100000
                AND min_liquidity > 10000
                ORDER BY accumulated_net_volume DESC, liquidity_growth_pct DESC
                LIMIT 20
            ''', (quarter_ago,))
            
            results = cursor.fetchall()
            
            long_term_growth = []
            for row in results:
                symbol, chain_id, appearances, min_liq, max_liq, avg_liq, first_seen, last_seen, avg_change, growth_pct, pos_days, acc_net_vol = row
                
                # 只要流動性成長 > 20% 才納入
                if growth_pct > 20:
                    long_term_growth.append({
                        'symbol': symbol,
                        'chain_id': chain_id,
                        'appearances': appearances,
                        'first_seen': first_seen,
                        'last_seen': last_seen,
                        'min_liquidity': min_liq,
                        'max_liquidity': max_liq,
                        'avg_liquidity': avg_liq,
                        'avg_change_24h': avg_change,
                        'liquidity_growth_pct': round(growth_pct, 1),
                        'positive_flow_days': pos_days,
                        'accumulated_net_volume': acc_net_vol
                    })
            
            return long_term_growth
    except sqlite3.Error as e:
        logger.error(f"❌ 獲取長線成長代幣失敗: {e}")
        return []

# ================= 3. Discord 通知模組 (Notifications) =================

async def send_discord_notification(session, embed_data, content=None):
    """發送 Discord 通知"""
    payload = {"embeds": [embed_data] if isinstance(embed_data, dict) else embed_data}
    if content:
        payload["content"] = content
    
    # 去重處理
    unique_urls = list(set([u for u in DISCORD_WEBHOOK_URLS if u]))
    
    for url in unique_urls:
        try:
            async with session.post(url, json=payload) as response:
                if response.status == 204:
                    logger.info(f"✅ Discord 通知發送成功")
                else:
                    logger.warning(f"⚠️ Discord 回應 ({url[-5:]}): {response.status}")
        except Exception as e:
            logger.error(f"❌ Discord 通知失敗: {e}")

async def send_discord_multi_embed(session, embeds, content=None):
    """發送多個 Embed 的通知 (Discord 單次最多 10 個)"""
    payload = {"embeds": embeds[:10]}
    if content:
        payload["content"] = content
    
    # 去重處理
    unique_urls = list(set([u for u in DISCORD_WEBHOOK_URLS if u]))
    
    for url in unique_urls:
        try:
            async with session.post(url, json=payload) as response:
                if response.status == 204:
                    logger.info(f"✅ Discord 批量通知發送成功 ({len(embeds)} 個 embed)")
                else:
                    logger.warning(f"⚠️ Discord 回應 ({url[-5:]}): {response.status}")
        except Exception as e:
            logger.error(f"❌ Discord 通知失敗: {e}")

def calculate_momentum_score(chain):
    """計算動能評分 (0-100)"""
    score = 50  # 基準分
    
    # 24H 變動加分
    if chain['change_1d'] > 5:
        score += 30
    elif chain['change_1d'] > 2:
        score += 20
    elif chain['change_1d'] > 0.5:
        score += 10
    elif chain['change_1d'] < -2:
        score -= 20
    
    # 加速度加分
    if chain['change_7d'] > 0 and (chain['change_1d'] * 7) > chain['change_7d']:
        score += 15  # 加速流入
    
    # 7D 趨勢加分
    if chain['change_7d'] > 10:
        score += 10
    elif chain['change_7d'] > 5:
        score += 5
    
    return min(100, max(0, score))

def get_investment_suggestion(chain, tokens):
    """生成投資建議"""
    momentum_score = calculate_momentum_score(chain)
    
    if momentum_score >= 80:
        return "🔥 **強烈關注** - 資金正在快速湧入，建議密切追蹤頭部代幣"
    elif momentum_score >= 65:
        return "✅ **適合佈局** - 趨勢向上，可考慮分批進場"
    elif momentum_score >= 50:
        return "⏳ **觀望為主** - 動能一般，等待更明確信號"
    else:
        return "⚠️ **謹慎評估** - 資金流出跡象，注意風險控制"

def format_large_number(num):
    """格式化大數字 (1.5B, 234M, 56K)"""
    if num >= 1_000_000_000:
        return f"${num / 1_000_000_000:.2f}B"
    elif num >= 1_000_000:
        return f"${num / 1_000_000:.2f}M"
    elif num >= 1_000:
        return f"${num / 1_000:.1f}K"
    else:
        return f"${num:.0f}"

def create_chain_alert_embed(chain, tokens=None, flow_analysis=None):
    """建立詳細公鏈警報 Embed (含多時間框架 + 資金流向)"""
    status_color = {
        "🔥 資金暴衝": 0xFF4500,      # 橙紅色
        "🚀 加速流入": 0x00FF00,      # 綠色
        "🟢 穩健增長": 0x32CD32,      # 淺綠色
        "⚠️ 資金流出": 0xFF0000,      # 紅色
    }
    
    momentum_score = calculate_momentum_score(chain)
    suggestion = get_investment_suggestion(chain, tokens)
    
    # 構建動能條
    filled = int(momentum_score / 10)
    momentum_bar = "🟩" * filled + "⬜" * (10 - filled)
    
    # 多時間框架分析
    c1d = chain['change_1d']
    c7d = chain['change_7d']
    c30d = chain.get('change_30d', 0)
    c90d = chain.get('change_90d', 0)
    
    # 趨勢判定
    if c1d > 0 and c7d > 0 and c30d > 0:
        trend = "📈 **短中長期多頭**"
        trend_emoji = "🟢"
    elif c1d > 0 and c30d < 0:
        trend = "🔄 **短期反彈中**"
        trend_emoji = "🟡"
    elif c1d < 0 and c30d > 0:
        trend = "📉 **短期回調**"
        trend_emoji = "🟡"
    elif c1d < 0 and c7d < 0 and c30d < 0:
        trend = "⚠️ **持續下跌**"
        trend_emoji = "🔴"
    else:
        trend = "➖ **盤整中**"
        trend_emoji = "⚪"
    
    # 計算資金流入金額估算
    daily_flow = chain['tvl'] * (chain['change_1d'] / 100)
    weekly_flow = chain['tvl'] * (chain['change_7d'] / 100)
    monthly_flow = chain['tvl'] * (c30d / 100)
    
    # 資金流向分析
    flow_section = ""
    if flow_analysis:
        breakdown = flow_analysis.get('breakdown', {})
        dominant = flow_analysis.get('dominant_flow', '')
        dominant_pct = flow_analysis.get('dominant_pct', 0)
        
        flow_names = {
            'native': '🔷 原生幣',
            'stablecoin': '💵 穩定幣',
            'btc': '🟡 BTC',
            'altcoin': '🚀 Altcoin'
        }
        
        flow_parts = []
        for cat in ['native', 'stablecoin', 'btc', 'altcoin']:
            if cat in breakdown and breakdown[cat]['volume_pct'] > 0:
                marker = "▶" if cat == dominant else ""
                flow_parts.append(f"{marker}{flow_names[cat]} {breakdown[cat]['volume_pct']:.1f}%")
        
        if flow_parts:
            flow_section = f"\n📊 **資金流向:** {' | '.join(flow_parts)}"
            
            # 添加流向提示
            if dominant == 'altcoin' and dominant_pct > 30:
                flow_section += f"\n🎯 **Alpha 機會！** 資金主要流向個別代幣"
            elif dominant == 'stablecoin' and dominant_pct > 40:
                flow_section += f"\n⚠️ **避險情緒** 資金流向穩定幣"
    
    description = f"""
**{chain['status']}** {trend_emoji}

{momentum_bar} **動能 {momentum_score}/100**

**📈 多時間框架分析:**
┣ 24H: **{c1d:+.2f}%** | 1週: **{c7d:+.2f}%**
┗ 1月: **{c30d:+.2f}%** | 3月: **{c90d:+.2f}%**

{trend}{flow_section}

💡 **投資建議:**
{suggestion}
"""
    
    fields = [
        {"name": "  TVL", "value": format_large_number(chain['tvl']), "inline": True},
        {"name": "💵 24H 流動", "value": format_large_number(abs(daily_flow)) + (" ↗" if daily_flow > 0 else " ↘"), "inline": True},
        {"name": "💵 7D 流動", "value": format_large_number(abs(weekly_flow)) + (" ↗" if weekly_flow > 0 else " ↘"), "inline": True},
    ]
    
    # ==== 📊 新增：市場情緒 ====
    if flow_analysis and flow_analysis.get('market_sentiment'):
        ms = flow_analysis['market_sentiment']
        fields.append({
            "name": "📊 市場情緒", 
            "value": f"{ms['sentiment']}\n買賣比: {ms['buy_sell_ratio']:.2f} | 漲跌比: {ms['bullish_pct']:.0f}%", 
            "inline": True
        })
    
    # 鯨魚吸籌 (穩健累積)
    if flow_analysis and flow_analysis.get('accumulating_tokens'):
        acc_tokens = flow_analysis['accumulating_tokens']
        acc_lines = []
        for t in acc_tokens[:3]:
            # 簡化累積理由以適應 Embed 寬度
            # reason 範例: "存活98天 | 買52賣38 (58%買入)"
            reason = t.get('accumulation_reason', '')
            # 嘗試縮短: "98天 | 58%買入"
            try:
                parts = reason.split('|')
                days = parts[0].replace('存活', '').strip()
                ratio = parts[1].split('(')[1].replace(')', '').strip() if '(' in parts[1] else parts[1]
                short_reason = f"⏳{days} | 📈{ratio}"
            except:
                short_reason = reason
            
            acc_lines.append(f"• **[{t['symbol']}]({t['url']})** {short_reason}")
        
        if acc_lines:
            fields.append({"name": "🐋 鯨魚潛伏 (穩健累積)", "value": "\n".join(acc_lines), "inline": False})
    
    # ==== 🔷 新增：原生幣熱門交易對 ====
    if flow_analysis and flow_analysis.get('native_pairs'):
        native_lines = []
        for np in flow_analysis['native_pairs'][:3]:
            accel_icon = "🚀" if np['momentum_accel'] > 1.5 else ("📈" if np['momentum_accel'] > 1 else "📉")
            native_lines.append(f"• **{np['symbol']}/{np['quote']}** {np['change_1h']:+.1f}% {accel_icon}{np['momentum_accel']}x")
        
        if native_lines:
            fields.append({"name": "🔷 原生幣交易對", "value": "\n".join(native_lines), "inline": False})
    
    # ==== ⚡ 新增：動能加速代幣 ====
    if flow_analysis and flow_analysis.get('momentum_tokens'):
        mom_lines = []
        for mt in flow_analysis['momentum_tokens'][:3]:
            mom_lines.append(f"• **[{mt['symbol']}]({mt['url']})** {mt['alert']} ({mt['momentum_accel']}x)")
        
        if mom_lines:
            fields.append({"name": "⚡ 動能加速 (短期爆發)", "value": "\n".join(mom_lines), "inline": False})

    # 如果有代幣數據，添加快速預覽
    if tokens and len(tokens) > 0:
        token_lines = []
        for t in tokens[:5]:
            pressure_warn = "⚠️" if t['pressure'] > BUYING_PRESSURE_ALERT else ""
            token_lines.append(f"• **{t['symbol']}** {t['change_24h']:+.1f}% | 買壓:{t['pressure']:.1f}{pressure_warn}")
        fields.append({"name": "🔥 熱門代幣 Top 5", "value": "\n".join(token_lines), "inline": False})
        
        # 添加第一個代幣的連結
        if tokens[0].get('url'):
            fields.append({"name": "  查看詳情", "value": f"[DEX Screener]({tokens[0]['url']})", "inline": False})
    
    return {
        "title": f"📡 {chain['chain_name']} 公鏈深度分析",
        "description": description,
        "color": status_color.get(chain['status'], 0x3498DB),
        "fields": fields,
        "footer": {"text": f"🔗 全鏈資金流向監控系統 v3.0 | DefiLlama + DEX Screener"},
        "timestamp": datetime.utcnow().isoformat(),
        "thumbnail": {"url": get_chain_icon(chain['chain_name'])}
    }

def get_chain_icon(chain_name):
    """獲取公鏈圖標 URL"""
    icons = {
        "Ethereum": "https://icons.llama.fi/ethereum.png",
        "Solana": "https://icons.llama.fi/solana.png",
        "Binance Smart Chain": "https://icons.llama.fi/bsc.png",
        "Arbitrum One": "https://icons.llama.fi/arbitrum.png",
        "Base": "https://icons.llama.fi/base.png",
        "Polygon": "https://icons.llama.fi/polygon.png",
        "Avalanche": "https://icons.llama.fi/avalanche.png",
        "Optimism": "https://icons.llama.fi/optimism.png",
        "Sui": "https://icons.llama.fi/sui.png",
        "Aptos": "https://icons.llama.fi/aptos.png",
        "Tron": "https://icons.llama.fi/tron.png",
    }
    return icons.get(chain_name, "https://icons.llama.fi/ethereum.png")

def create_token_alert_embed(chain_name, tokens, chain_data=None):
    """建立詳細代幣警報 Embed"""
    if not tokens:
        return None
    
    description = ""
    
    for i, token in enumerate(tokens[:5], 1):
        # 狀態判定
        if token['change_24h'] > 20:
            status = "🚀 暴漲"
        elif token['change_24h'] > 5:
            status = "📈 強勢"
        elif token['change_24h'] > 0:
            status = "🟢 上漲"
        elif token['change_24h'] > -5:
            status = "🔴 下跌"
        else:
            status = "💥 暴跌"
        
        # 買壓評級
        if token['pressure'] > 5:
            pressure_rating = "🔥🔥🔥 極度活躍"
        elif token['pressure'] > 2:
            pressure_rating = "🔥🔥 高度活躍"
        elif token['pressure'] > 1:
            pressure_rating = "🔥 活躍"
        else:
            pressure_rating = "💤 一般"
        
        description += f"""
**{i}. [{token['symbol']}]({token['url']})** {status}
┣ 💵 價格: `{token['price']}`
┣ 📊 24H: **{token['change_24h']:+.2f}%**
┣ 📈 交易量: {format_large_number(token['volume'])}
┣ 💧 流動性: {format_large_number(token['liquidity'])}
┗ 🔥 買壓係數: **{token['pressure']:.2f}** ({pressure_rating})
"""
    
    # 計算整體熱度
    avg_pressure = sum(t['pressure'] for t in tokens) / len(tokens)
    avg_change = sum(t['change_24h'] for t in tokens) / len(tokens)
    
    if avg_pressure > 2 and avg_change > 5:
        market_heat = "🔥🔥🔥 極度火熱"
    elif avg_pressure > 1 or avg_change > 0:
        market_heat = "🔥 市場活躍"
    else:
        market_heat = "❄️ 相對冷淡"
    
    fields = [
        {"name": "📊 平均漲跌幅", "value": f"{avg_change:+.2f}%", "inline": True},
        {"name": "🔥 平均買壓", "value": f"{avg_pressure:.2f}", "inline": True},
        {"name": "🌡️ 市場熱度", "value": market_heat, "inline": True},
    ]
    
    return {
        "title": f"🔍 {chain_name} - Top 5 熱錢流向詳細分析",
        "description": description,
        "color": 0x9B59B6,
        "fields": fields,
        "footer": {"text": "💡 提示：買壓係數 = 24H交易量/流動性，越高代表換手越激烈 | 點擊代幣名稱查看圖表"},
        "timestamp": datetime.utcnow().isoformat()
    }

def create_new_token_embed(tokens):
    """建立詳細新幣警報 Embed"""
    if not tokens:
        return {
            "title": "🆕 新幣首發偵測",
            "description": "暫無符合條件的新幣（流動性 > $50K）",
            "color": 0xE91E63,
            "footer": {"text": "持續監控中..."},
            "timestamp": datetime.utcnow().isoformat()
        }
    
    description = "**⚠️ 警告：新幣風險極高，請務必 DYOR！**\n\n"
    
    for i, token in enumerate(tokens[:10], 1):
        age_hours = token.get('age_hours', 999)
        if age_hours < 1:
            age_str = "🆕 剛上線"
        elif age_hours < 24:
            age_str = f"⏰ {age_hours}小時前"
        else:
            age_str = f"📅 {age_hours // 24}天前"
        
        # 風險評估
        if age_hours < 6 and token['liquidity'] < 100000:
            risk = "🔴 極高風險"
        elif age_hours < 24:
            risk = "🟠 高風險"
        else:
            risk = "🟡 中等風險"
        
        description += f"""**{i}. [{token['symbol']}]({token['url']})**
┣ 🔗 鏈: {token['chain'].upper()}
┣ 💧 流動性: {format_large_number(token['liquidity'])}
┣ {age_str}
┗ {risk}

"""
    
    return {
        "title": "🆕 新幣首發偵測報告",
        "description": description,
        "color": 0xE91E63,
        "fields": [
            {"name": "📊 偵測數量", "value": str(len(tokens)), "inline": True},
            {"name": "🔍 篩選條件", "value": "流動性 > $50K", "inline": True},
            {"name": "⚠️ 風險提示", "value": "新幣波動極大，建議小倉位試水", "inline": False},
        ],
        "footer": {"text": "💡 DYOR = Do Your Own Research 請自行研究"},
        "timestamp": datetime.utcnow().isoformat()
    }

def create_long_term_growth_embed(tokens):
    """建立長線成長代幣警報 Embed"""
    if not tokens:
        return None
    
    description = "**📈 這些代幣在過去 3 個月內流動性持續穩健增長，值得長期關注！**\n\n"
    
    for i, token in enumerate(tokens[:5], 1):
        growth_emoji = "🔥" if token['liquidity_growth_pct'] > 100 else "🌳"
        
        description += f"""**{i}. {token['symbol']} ({token['chain_id']})**
┣ 💧 流動性成長: **+{token['liquidity_growth_pct']}%** {growth_emoji}
┣ 📅 首次記錄: {token['first_seen']}
┗ 👁️ 出現次數: {token['appearances']} 次

"""
    
    return {
        "title": "🌳 長線價值發現 (90天追蹤)",
        "description": description,
        "color": 0x2ECC71,
        "footer": {"text": "基於歷史數據分析 | 篩選條件: 流動性持續增長 > 20%"},
        "timestamp": datetime.utcnow().isoformat()
    }

def create_cross_chain_embed(flows):
    """建立詳細鏈間資金流動 Embed"""
    if not flows:
        return {
            "title": "🔄 鏈間資金流動偵測",
            "description": "暫無偵測到顯著的跨鏈資金遷移",
            "color": 0x3498DB,
            "footer": {"text": "持續監控中..."},
            "timestamp": datetime.utcnow().isoformat()
        }
    
    description = "**💡 資金遷移往往預示新的投資機會！**\n\n"
    
    for i, flow in enumerate(flows[:5], 1):
        strength = flow['strength']
        if strength > 10:
            signal = "🔥🔥🔥 極強信號"
        elif strength > 5:
            signal = "🔥🔥 強信號"
        else:
            signal = "🔥 一般信號"
        
        description += f"""**{i}. {flow['from_chain']} ➡️ {flow['to_chain']}**
┣ 📤 流出: **{flow['from_change']:+.2f}%**
┣ 📥 流入: **{flow['to_change']:+.2f}%**
┗ 📊 信號強度: {signal}

"""
    
    # 找出最熱門的目標鏈
    target_chains = {}
    for flow in flows:
        target_chains[flow['to_chain']] = target_chains.get(flow['to_chain'], 0) + flow['to_change']
    
    if target_chains:
        hottest = max(target_chains, key=target_chains.get)
        fields = [
            {"name": "🎯 最熱目標鏈", "value": hottest, "inline": True},
            {"name": "📊 偵測流動數", "value": str(len(flows)), "inline": True},
            {"name": "💡 操作建議", "value": f"關注 {hottest} 上的新機會", "inline": False},
        ]
    else:
        fields = []
    
    return {
        "title": "🔄 鏈間資金流動深度分析",
        "description": description,
        "color": 0x3498DB,
        "fields": fields,
        "footer": {"text": "🔗 資金遷移追蹤 | 數據實時更新"},
        "timestamp": datetime.utcnow().isoformat()
    }

def create_summary_embed(stats, chains=None, all_tokens=None, cex_data=None):
    """建立詳細每日摘要 Embed (含 CEX 監控)"""
    # 找出表現最佳的鏈和代幣
    best_chain = None
    best_token = None
    
    if chains:
        best_chain = max(chains, key=lambda x: x['change_1d'])
    
    if all_tokens:
        all_token_list = []
        for chain_tokens in all_tokens.values():
            all_token_list.extend(chain_tokens)
        if all_token_list:
            best_token = max(all_token_list, key=lambda x: x['change_24h'])
    
    description = f"""
**📡 全鏈資金流向監控系統 v2.5**
━━━━━━━━━━━━━━━━━━━━━━

本次掃描已完成，以下是關鍵數據摘要：
"""
    
    if best_chain:
        description += f"""
🏆 **最強公鏈:** {best_chain['chain_name']} ({best_chain['change_1d']:+.2f}%)
"""
    
    if best_token:
        description += f"""🥇 **最強代幣:** {best_token['symbol']} ({best_token['change_24h']:+.2f}%)
"""

    # CEX 監控 (新增)
    if cex_data:
        cex_desc = ""
        for cex in cex_data[:3]:
            icon = "🟢" if cex['change_1d'] > 0 else "🔴"
            cex_desc += f"{icon} **{cex['name']}**: {cex['change_1d']:+.2f}% (TVL: ${cex['tvl']/1e9:.1f}B)\n"
        
        description += f"""
**🏦 交易所 (CEX) 資金概況:**
{cex_desc}
"""
    
    fields = [
        {"name": "🔗 掃描公鏈", "value": f"**{stats['chains_scanned']}** 條", "inline": True},
        {"name": "🎯 推薦代幣", "value": f"**{stats['tokens_found']}** 個", "inline": True},
        {"name": "🆕 新幣偵測", "value": f"**{stats['new_tokens']}** 個", "inline": True},
        {"name": "⚠️ 異常警報", "value": f"**{stats['anomalies']}** 個", "inline": True},
        {"name": "📈 系統準確率", "value": f"**{stats['accuracy']:.1f}%**", "inline": True},
        {"name": "⏱️ 執行耗時", "value": f"**{stats['execution_time']:.2f}s**", "inline": True},
    ]
    
    # 市場情緒判定
    if chains:
        avg_change = sum(c['change_1d'] for c in chains) / len(chains)
        if avg_change > 2:
            market_mood = "🟢 極度樂觀 - 資金大幅流入"
        elif avg_change > 0.5:
            market_mood = "🟢 偏多 - 資金穩定流入"
        elif avg_change > -0.5:
            market_mood = "🟡 中性 - 資金觀望"
        else:
            market_mood = "🔴 偏空 - 資金流出中"
        
        fields.append({"name": "🌡️ 市場情緒", "value": market_mood, "inline": False})
    
    footer_text = f"⏰ 下次掃描: {stats['next_scan']}"
    if stats.get('schedule_interval'):
        footer_text += f" | 掃描間隔: {stats['schedule_interval'] // 60} 分鐘"
    
    return {
        "title": "📊 全鏈資金流向分析報告",
        "description": description,
        "color": 0xF1C40F,
        "fields": fields,
        "footer": {"text": footer_text},
        "timestamp": datetime.utcnow().isoformat()
    }

def create_alert_header_embed():
    """建立警報開頭 Embed"""
    return {
        "title": "🚨 全鏈資金監控警報",
        "description": """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**系統偵測到重要資金動向！**
以下是詳細分析報告：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""",
        "color": 0xFF6B6B,
        "timestamp": datetime.utcnow().isoformat()
    }

def create_high_pressure_alert_embed(tokens_by_chain):
    """建立高買壓警報 Embed"""
    high_pressure_tokens = []
    
    for chain_id, tokens in tokens_by_chain.items():
        for token in tokens:
            if token['pressure'] > BUYING_PRESSURE_ALERT:
                token['chain'] = chain_id
                high_pressure_tokens.append(token)
    
    if not high_pressure_tokens:
        return None
    
    # 按買壓排序
    high_pressure_tokens.sort(key=lambda x: x['pressure'], reverse=True)
    
    description = "**⚠️ 以下代幣買壓係數異常高，請注意風險！**\n\n"
    
    for token in high_pressure_tokens[:5]:
        description += f"""**[{token['symbol']}]({token['url']})** on {token['chain'].upper()}
┣ 🔥 買壓係數: **{token['pressure']:.2f}** (閾值: {BUYING_PRESSURE_ALERT})
┣ 📊 24H 漲跌: {token['change_24h']:+.2f}%
┗ 📈 交易量: {format_large_number(token['volume'])}

"""
    
    return {
        "title": "🔥 高買壓代幣警報",
        "description": description,
        "color": 0xFF4500,
        "fields": [
            {"name": "⚠️ 風險提示", "value": "高買壓可能意味著 FOMO 情緒過熱，追高需謹慎", "inline": False},
        ],
        "footer": {"text": f"買壓閾值: {BUYING_PRESSURE_ALERT} | 買壓 = 24H交易量/流動性"},
        "timestamp": datetime.utcnow().isoformat()
    }


def create_integrated_summary_embed(stats, chains, all_tokens, cex_data, rotation_info, native_strength, new_tokens, cross_flows):
    """
    建立整合版 Discord 通知 (單一 Embed，避免洗版)
    包含：輪動週期、原生幣強弱、熱門代幣、市場情緒
    """
    # 找出最強公鏈和代幣
    best_chain = max(chains, key=lambda x: x['change_1d']) if chains else None
    
    all_token_list = []
    for chain_tokens in all_tokens.values():
        all_token_list.extend(chain_tokens)
    best_token = max(all_token_list, key=lambda x: x['change_24h']) if all_token_list else None
    
    # 輪動週期資訊
    cycle_info = ""
    if rotation_info:
        cycle_info = f"""
**🔄 市場輪動週期:**
{rotation_info['cycle_phase']}
💡 {rotation_info['cycle_signal']}
"""
    
    # 原生幣強弱資訊
    native_info = ""
    if native_strength and len(native_strength) >= 2:
        top2 = native_strength[:2]
        native_info = f"""
**🌐 原生幣強弱 (貨幣匯率):**
🥇 {top2[0]['native_symbol']} ({top2[0]['chain']}) {top2[0]['strength_label']} {top2[0]['change_24h']:+.1f}%
🥈 {top2[1]['native_symbol']} ({top2[1]['chain']}) {top2[1]['strength_label']} {top2[1]['change_24h']:+.1f}%
"""
    
    # 構建描述
    description = f"""
📡 **全鏈資金流向分析報告 v3.0**
━━━━━━━━━━━━━━━━━━━━━━
{cycle_info}
{native_info}
**📊 分析摘要:**
┣ 🔗 公鏈: **{stats['chains_scanned']}**條 | 🎯 代幣: **{stats['tokens_found']}**個
┣ 🆕 新幣: **{stats['new_tokens']}**個 | 📈 準確率: **{stats['accuracy']:.1f}%**
┗ ⏱️ 耗時: **{stats['execution_time']:.1f}s**
"""
    
    if best_chain:
        description += f"\n🏆 **最強公鏈:** {best_chain['chain_name']} ({best_chain['change_1d']:+.2f}%)"
    
    if best_token:
        description += f"\n🔥 **最熱代幣:** {best_token['symbol']} ({best_token['change_24h']:+.2f}%)"
    
    fields = []
    
    # CEX 資金流向 (精簡版)
    if cex_data:
        top_cex = cex_data[:3]
        cex_lines = []
        for cex in top_cex:
            icon = "🟢" if cex['change_1d'] > 0 else "🔴"
            cex_lines.append(f"{icon} {cex['name']}: {cex['change_1d']:+.1f}%")
        fields.append({
            "name": "🏦 CEX 資金",
            "value": "\n".join(cex_lines),
            "inline": True
        })
    
    # 跨鏈流動 (精簡版)
    if cross_flows:
        flow_lines = []
        for f in cross_flows[:3]:
            flow_lines.append(f"{f['from_chain']} ➡️ {f['to_chain']}")
        fields.append({
            "name": "🔄 資金遷移",
            "value": "\n".join(flow_lines),
            "inline": True
        })
    
    # 熱門代幣 Top 3
    if all_token_list:
        sorted_tokens = sorted(all_token_list, key=lambda x: x['pressure'], reverse=True)[:3]
        token_lines = []
        for t in sorted_tokens:
            token_lines.append(f"**{t['symbol']}** {t['change_24h']:+.1f}%")
        fields.append({
            "name": "🔥 熱門代幣",
            "value": "\n".join(token_lines),
            "inline": True
        })
    
    # 新幣預覽
    if new_tokens:
        new_lines = []
        for t in new_tokens[:3]:
            new_lines.append(f"**{t['symbol']}** ({t['chain']})")
        fields.append({
            "name": "🆕 新幣首發",
            "value": "\n".join(new_lines),
            "inline": True
        })
    
    # ==== 🚦 交易信號燈 (新增) ====
    if stats.get('trading_signal'):
        # 根據信號選擇顏色 emoji
        signal = stats['trading_signal']
        if '買入' in signal:
            signal_icon = "🟢"
        elif '減倉' in signal or '離場' in signal:
            signal_icon = "🔴"
        else:
            signal_icon = "🟡"
        
        fields.append({
            "name": "🚦 交易信號",
            "value": f"{signal_icon} **{signal}**",
            "inline": True
        })
    
    if stats.get('market_phase'):
        fields.append({
            "name": "📍 市場階段",
            "value": stats['market_phase'],
            "inline": True
        })
    
    # ==== 📄 HTML 報告連結 ====
    html_filename = stats.get('html_file', '')
    if html_filename:
        # 提取檔名
        report_name = Path(html_filename).name
        report_url = f"{GITHUB_PAGES_BASE_URL}{report_name}"
        dashboard_url = f"{GITHUB_PAGES_BASE_URL}latest_dashboard.html"
        fields.append({
            "name": "📄 詳細報告",
            "value": f"[📊 完整分析報告]({report_url}) | [🎛️ 資金主控台]({dashboard_url})",
            "inline": False
        })
    
    # 下次掃描時間
    footer_text = f"⏰ 下次掃描: {stats['next_scan']}"
    if stats.get('schedule_interval'):
        footer_text += f" | 間隔: {stats['schedule_interval'] // 60}分鐘"
    
    return {
        "title": "🔗 全鏈資金流向監控 v3.0",
        "description": description,
        "color": 0x6366F1,  # 紫色主題
        "fields": fields,
        "footer": {"text": footer_text},
        "timestamp": datetime.utcnow().isoformat()
    }



# ================= 4. 非同步 API 請求模組 (Async API) =================

async def fetch_with_retry(session, url, retries=3, delay=2):
    """帶重試機制的非同步請求 (改進版: 支持 Retry-After header & User-Agent)"""
    # 模擬瀏覽器 User-Agent 以避免被交易所防火牆攔截
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json'
    }
    
    for attempt in range(retries):
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 429:  # Rate limited
                    # 優先使用 Retry-After header
                    retry_after = response.headers.get('Retry-After')
                    if retry_after:
                        try:
                            wait_time = int(retry_after)
                        except ValueError:
                            wait_time = delay * (2 ** attempt)
                    else:
                        wait_time = delay * (2 ** attempt)
                    
                    # 最長等待 60 秒
                    wait_time = min(wait_time, 60)
                    logger.warning(f"⏳ API 限速，等待 {wait_time} 秒... ({url[-50:]})")
                    await asyncio.sleep(wait_time)
                elif response.status >= 500:
                    # 伺服器錯誤，等待後重試
                    logger.warning(f"⚠️ 伺服器錯誤 {response.status}，等待重試...")
                    await asyncio.sleep(delay * (attempt + 1))
                else:
                    logger.warning(f"⚠️ API 回應 {response.status}: {url[-80:]}")
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ 請求超時 (嘗試 {attempt + 1}/{retries}): {url[-80:]}")
        except aiohttp.ClientError as e:
            logger.error(f"❌ 網路請求失敗: {type(e).__name__}: {e}")
        except Exception as e:
            logger.error(f"❌ 未預期的錯誤: {type(e).__name__}: {e}")
        
        if attempt < retries - 1:
            await asyncio.sleep(delay)
    
    return None

async def get_chain_historical_tvl(session, chain_name):
    """獲取單一公鏈的歷史 TVL 數據 (含每週獨立計算)"""
    url = f"https://api.llama.fi/v2/historicalChainTvl/{chain_name}"
    data = await fetch_with_retry(session, url)
    
    if not data or len(data) < 2:
        return None
    
    # 獲取最近的 TVL 數據點
    current_tvl = data[-1].get('tvl', 0)
    
    # 計算 24H 變動 (1天前)
    tvl_1d_ago = data[-2].get('tvl', current_tvl) if len(data) >= 2 else current_tvl
    
    # 計算每週時間點的 TVL
    # W1: 第1週 (0-7天)  → 比較 day 0 和 day 7
    # W2: 第2週 (7-14天) → 比較 day 7 和 day 14
    # W3: 第3週 (14-21天) → 比較 day 14 和 day 21
    # W4: 第4週 (21-28天) → 比較 day 21 和 day 28
    
    tvl_7d_ago = data[-8].get('tvl', current_tvl) if len(data) >= 8 else current_tvl
    tvl_14d_ago = data[-15].get('tvl', current_tvl) if len(data) >= 15 else current_tvl
    tvl_21d_ago = data[-22].get('tvl', current_tvl) if len(data) >= 22 else current_tvl
    tvl_28d_ago = data[-29].get('tvl', current_tvl) if len(data) >= 29 else current_tvl
    tvl_30d_ago = data[-31].get('tvl', current_tvl) if len(data) >= 31 else current_tvl
    tvl_90d_ago = data[-91].get('tvl', current_tvl) if len(data) >= 91 else current_tvl
    
    # 計算變動百分比
    change_1d = ((current_tvl - tvl_1d_ago) / tvl_1d_ago * 100) if tvl_1d_ago > 0 else 0
    change_7d = ((current_tvl - tvl_7d_ago) / tvl_7d_ago * 100) if tvl_7d_ago > 0 else 0
    change_30d = ((current_tvl - tvl_30d_ago) / tvl_30d_ago * 100) if tvl_30d_ago > 0 else 0
    change_90d = ((current_tvl - tvl_90d_ago) / tvl_90d_ago * 100) if tvl_90d_ago > 0 else 0
    
    # 每週獨立計算 (W1 = 最近一週內的變化, W2 = 第二週發生的變化, etc.)
    change_w1 = ((current_tvl - tvl_7d_ago) / tvl_7d_ago * 100) if tvl_7d_ago > 0 else 0
    change_w2 = ((tvl_7d_ago - tvl_14d_ago) / tvl_14d_ago * 100) if tvl_14d_ago > 0 else 0
    change_w3 = ((tvl_14d_ago - tvl_21d_ago) / tvl_21d_ago * 100) if tvl_21d_ago > 0 else 0
    change_w4 = ((tvl_21d_ago - tvl_28d_ago) / tvl_28d_ago * 100) if tvl_28d_ago > 0 else 0
    
    # 計算每週金額變化 (以當週結束時的 TVL 計算)
    amount_24h = current_tvl - tvl_1d_ago
    amount_w1 = current_tvl - tvl_7d_ago
    amount_w2 = tvl_7d_ago - tvl_14d_ago
    amount_w3 = tvl_14d_ago - tvl_21d_ago
    amount_w4 = tvl_21d_ago - tvl_28d_ago
    
    return {
        'tvl': current_tvl,
        'change_1d': round(change_1d, 2),
        'change_7d': round(change_7d, 2),
        'change_30d': round(change_30d, 2),
        'change_90d': round(change_90d, 2),
        # 每週獨立變化
        'change_w1': round(change_w1, 2),
        'change_w2': round(change_w2, 2),
        'change_w3': round(change_w3, 2),
        'change_w4': round(change_w4, 2),
        # 每週金額
        'amount_24h': amount_24h,
        'amount_w1': amount_w1,
        'amount_w2': amount_w2,
        'amount_w3': amount_w3,
        'amount_w4': amount_w4
    }

async def get_cex_data_async(session):
    """
    獲取中心化交易所 (CEX) 的資產數據與資產構成
    來源: DefiLlama Protocols (category='CEX')
    """
    logger.info("🏦 正在獲取 CEX 資產數據...")
    url = "https://api.llama.fi/protocols"
    
    data = await fetch_with_retry(session, url)
    if not data:
        return []
    
    cex_list = []
    for p in data:
        if p.get('category') == 'CEX':
            try:
                tvl = p.get('tvl', 0) or 0
                if tvl < 100_000_000: # 忽略小交易所 (<$100M)
                    continue
                    
                cex_list.append({
                    'name': p['name'],
                    'symbol': p.get('symbol', ''),
                    'slug': p.get('slug', ''), # 重要：獲取 slug
                    'tvl': tvl,
                    'change_1d': p.get('change_1d', 0) or 0,
                    'change_7d': p.get('change_7d', 0) or 0,
                    'logo': p.get('logo', ''),
                    # 初始化新欄位
                    'stablecoin_pct': 0,
                    'non_stablecoin_pct': 0,
                    'inflow_type': '計算中...'
                })
            except (KeyError, TypeError) as e:
                logger.debug(f"跳過無效 CEX 數據: {e}")
                continue
    
    cex_list.sort(key=lambda x: x['tvl'], reverse=True)
    top_cex = cex_list[:10]  # 只處理前 10 大
    
    # 並行獲取詳細資產分佈
    logger.info(f"🔍 正在深入分析前 {len(top_cex)} 大 CEX 的資產構成...")
    
    async def enrich_cex_details(cex):
        slug = cex.get('slug')
        if not slug:
            return
            
        detail_url = f"https://api.llama.fi/protocol/{slug}"
        try:
            detail_data = await fetch_with_retry(session, detail_url)
            if not detail_data or 'tokensInUsd' not in detail_data:
                return
                
            # 獲取最新一筆數據 (如果有 tokensInUsd)
            if not detail_data['tokensInUsd']:
                return
                
            latest = detail_data['tokensInUsd'][-1]
            tokens = latest.get('tokens', {})
            
            if not tokens:
                return
                
            # 計算穩定幣佔比
            # 常見穩定幣清單
            stablecoins = ['USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'USDD', 'BUSD', 'PYUSD', 'GUSD', 'USDE']
            
            total_usd = sum(tokens.values())
            if total_usd == 0:
                return
                
            # 寬鬆匹配: 在清單中 或 包含 'USD' 且非 'USDe' (避免 Ethena 重複計算如果清單已包含) 
            # 簡單起見，匹配清單 + 包含 "USD" 字串的代幣 (通常是穩定幣)
            stable_usd = sum(v for k, v in tokens.items() if k in stablecoins or ('USD' in k and 'WETH' not in k and 'BTC' not in k))
            
            stable_pct = (stable_usd / total_usd) * 100
            non_stable_pct = 100 - stable_pct
            
            cex['stablecoin_pct'] = stable_pct
            cex['non_stablecoin_pct'] = non_stable_pct
            
            # 判斷流向類型
            change_24h = cex['change_1d']
            
            # 閾值設定
            if abs(change_24h) < 0.2:
                 cex['inflow_type'] = "➖ 資金平衡"
            elif change_24h > 0: # 流入
                # 如果是流入，看是什麼資產流入
                # 這裡假設資產分佈代表了流入的成分 (雖然不完全精確，但在大樣本下有效)
                if stable_pct > 40: # 穩定幣佔比超過 40% 且流入 -> 視為有潛在買盤
                    cex['inflow_type'] = "📈 潛在買盤 (穩定幣)"
                else:
                    cex['inflow_type'] = "📉 潛在賣壓 (資產充值)"
            else: # 流出
                if stable_pct > 60: # 穩定幣佔比高但正在流出 -> 購買力減少
                     cex['inflow_type'] = "📉 購買力減弱"
                else:
                    cex['inflow_type'] = "📈 提幣囤貨 (DeFi/冷錢包)"
            
            # --- 新增: 計算歷史 W1-W4 變化 ---
            current_date = latest['date']
            history_data = {}
            
            history_periods = {
                '24h': 1,
                'w1': 7, 
                'w2': 14, 
                'w3': 21, 
                'w4': 28
            }
            
            for period_name, days in history_periods.items():
                target_ts = current_date - (days * 86400)
                
                # 尋找最近記錄 (倒序遍歷)
                closest_record = None
                min_diff = 86400 * 3 # 容許 3 天誤差 (有時數據點會缺失)
                
                for record in reversed(detail_data['tokensInUsd']):
                    diff = abs(record['date'] - target_ts)
                    if diff < min_diff:
                        min_diff = diff
                        closest_record = record
                    
                    if record['date'] < target_ts - 86400*3:
                        break # 太早了，不用再找
                
                if closest_record:
                    past_tokens = closest_record.get('tokens', {})
                    past_total = sum(past_tokens.values())
                    
                    if past_total > 0:
                         past_stable = sum(v for k, v in past_tokens.items() if k in stablecoins or ('USD' in k and 'WETH' not in k and 'BTC' not in k))
                         past_other = past_total - past_stable
                         
                         other_usd = total_usd - stable_usd
                         
                         total_change_pct = ((total_usd - past_total) / past_total) * 100
                         stable_change_usd = stable_usd - past_stable
                         other_change_usd = other_usd - past_other
                         
                         history_data[period_name] = {
                             'total_pct': total_change_pct,
                             'stable_change': stable_change_usd,
                             'other_change': other_change_usd
                         }
            
            cex['history_data'] = history_data
                    
        except Exception as e:
            logger.debug(f"無法獲取 {cex['name']} 詳細資訊: {e}")

    await asyncio.gather(*[enrich_cex_details(cex) for cex in top_cex])
    
    return top_cex


async def get_funding_rates_async(session):
    """
    🔧 獲取期貨資金費率 (Funding Rate) - 使用 CCXT 多交易所備援
    
    支持交易所順序: Binance → Bybit → OKX
    
    資金費率解讀:
    - 正值 > 0.01%: 多頭擁擠，市場過熱
    - 負值 < -0.01%: 空頭擁擠，可能反彈
    - 接近 0: 市場平衡
    """
    logger.info("📊 正在獲取期貨資金費率 (CCXT)...")
    
    funding_data = {
        'btc': {'rate': 0, 'oi_change': 0, 'interpretation': '', 'source': ''},
        'eth': {'rate': 0, 'oi_change': 0, 'interpretation': '', 'source': ''},
    }
    
    # 嘗試使用 CCXT
    try:
        import ccxt
        
        # 交易所優先順序
        exchanges_to_try = [
            ('binance', 'BTC/USDT:USDT', 'ETH/USDT:USDT'),
            ('bybit', 'BTC/USDT:USDT', 'ETH/USDT:USDT'),
            ('okx', 'BTC/USDT:USDT', 'ETH/USDT:USDT'),
        ]
        
        for exchange_id, btc_symbol, eth_symbol in exchanges_to_try:
            try:
                # 使用 asyncio.to_thread 在異步環境中運行同步 CCXT
                def fetch_funding():
                    exchange_class = getattr(ccxt, exchange_id)
                    exchange = exchange_class({
                        'enableRateLimit': True,
                        'timeout': 10000,
                    })
                    
                    rates = {}
                    try:
                        # 獲取 BTC 資金費率
                        btc_funding = exchange.fetchFundingRate('BTC/USDT')
                        if btc_funding and 'fundingRate' in btc_funding:
                            rates['btc'] = btc_funding['fundingRate'] * 100  # 轉為百分比
                    except Exception as e:
                        logger.debug(f"{exchange_id} BTC funding rate error: {e}")
                    
                    try:
                        # 獲取 ETH 資金費率
                        eth_funding = exchange.fetchFundingRate('ETH/USDT')
                        if eth_funding and 'fundingRate' in eth_funding:
                            rates['eth'] = eth_funding['fundingRate'] * 100  # 轉為百分比
                    except Exception as e:
                        logger.debug(f"{exchange_id} ETH funding rate error: {e}")
                    
                    return rates, exchange_id
                
                rates, source = await asyncio.to_thread(fetch_funding)
                
                if rates.get('btc') is not None:
                    funding_data['btc']['rate'] = rates['btc']
                    funding_data['btc']['source'] = source
                    
                if rates.get('eth') is not None:
                    funding_data['eth']['rate'] = rates['eth']
                    funding_data['eth']['source'] = source
                
                # 如果成功獲取到兩個幣種的數據，跳出循環
                if rates.get('btc') is not None and rates.get('eth') is not None:
                    logger.info(f"✅ 資金費率獲取成功 ({source.upper()}): BTC {rates['btc']:.4f}%, ETH {rates['eth']:.4f}%")
                    break
                    
            except Exception as e:
                logger.debug(f"⚠️ {exchange_id} 獲取失敗: {e}")
                continue
        
    except ImportError:
        logger.warning("⚠️ CCXT 未安裝，嘗試使用備用方案...")
        # 備用方案：直接使用 aiohttp 請求 Binance API
        try:
            binance_url = "https://fapi.binance.com/fapi/v1/premiumIndex"
            data = await fetch_with_retry(session, binance_url)
            
            if data:
                for item in data:
                    symbol = item.get('symbol', '')
                    rate = float(item.get('lastFundingRate', 0)) * 100
                    
                    if symbol == 'BTCUSDT':
                        funding_data['btc']['rate'] = rate
                        funding_data['btc']['source'] = 'binance'
                    elif symbol == 'ETHUSDT':
                        funding_data['eth']['rate'] = rate
                        funding_data['eth']['source'] = 'binance'
                        
                logger.info(f"✅ 資金費率獲取成功 (備用): BTC {funding_data['btc']['rate']:.4f}%, ETH {funding_data['eth']['rate']:.4f}%")
        except Exception as e:
            logger.warning(f"⚠️ 備用方案也失敗: {e}")
    except Exception as e:
        logger.warning(f"⚠️ 資金費率獲取失敗: {e}")
    
    # 解讀資金費率
    for coin in ['btc', 'eth']:
        rate = funding_data[coin]['rate']
        if rate > 0.05:
            funding_data[coin]['interpretation'] = "🔴 極度過熱 - 多頭擁擠，謹慎追高"
        elif rate > 0.02:
            funding_data[coin]['interpretation'] = "🟠 偏多頭 - 資金成本升高"
        elif rate > 0.005:
            funding_data[coin]['interpretation'] = "🟡 略偏多 - 正常範圍"
        elif rate > -0.005:
            funding_data[coin]['interpretation'] = "🟢 中性 - 市場平衡"
        elif rate > -0.02:
            funding_data[coin]['interpretation'] = "🟡 略偏空 - 正常範圍"
        else:
            funding_data[coin]['interpretation'] = "🟢 空頭擁擠 - 可能反彈機會"
    
    return funding_data


async def get_stablecoin_supply_async(session):
    """
    💵 獲取穩定幣流通量數據
    來源: DefiLlama Stablecoins API
    
    穩定幣流通量解讀:
    - 增加: 新資金入場，利好
    - 減少: 資金流出市場，利空
    """
    logger.info("💵 正在獲取穩定幣流通量...")
    
    stablecoin_data = {
        'total_supply': 0,
        'total_supply_7d': 0,
        'change_24h': 0,
        'change_7d': 0,
        'top_stables': [],
        'interpretation': ''
    }
    
    try:
        # DefiLlama Stablecoins API
        url = "https://stablecoins.llama.fi/stablecoins?includePrices=true"
        data = await fetch_with_retry(session, url)
        
        if data and 'peggedAssets' in data:
            total_supply = 0
            top_stables = []
            
            for stable in data['peggedAssets'][:10]:  # 前 10 大穩定幣
                name = stable.get('name', '')
                symbol = stable.get('symbol', '')
                circulating = stable.get('circulating', {})
                
                # 獲取當前流通量
                peg_usd = circulating.get('peggedUSD', 0) or 0
                
                if peg_usd > 1e9:  # 只追蹤 > $1B 的穩定幣
                    top_stables.append({
                        'name': name,
                        'symbol': symbol,
                        'supply': peg_usd,
                        'change_7d': stable.get('circulatingPrevWeek', {}).get('peggedUSD', 0) or 0
                    })
                    total_supply += peg_usd
            
            stablecoin_data['total_supply'] = total_supply
            stablecoin_data['top_stables'] = sorted(top_stables, key=lambda x: x['supply'], reverse=True)[:5]
            
            # 計算 7D 變化
            total_prev_week = sum(s.get('change_7d', 0) for s in top_stables)
            if total_prev_week > 0:
                stablecoin_data['change_7d'] = ((total_supply - total_prev_week) / total_prev_week) * 100
            
            # 解讀
            if stablecoin_data['change_7d'] > 2:
                stablecoin_data['interpretation'] = "🟢 穩定幣快速增發 → 大量新資金入場"
            elif stablecoin_data['change_7d'] > 0.5:
                stablecoin_data['interpretation'] = "🟢 穩定幣溫和增長 → 資金持續流入"
            elif stablecoin_data['change_7d'] > -0.5:
                stablecoin_data['interpretation'] = "🟡 穩定幣流通量穩定 → 市場平衡"
            elif stablecoin_data['change_7d'] > -2:
                stablecoin_data['interpretation'] = "🟠 穩定幣小幅減少 → 部分資金離場"
            else:
                stablecoin_data['interpretation'] = "🔴 穩定幣大幅減少 → 資金加速流出"
            
            logger.info(f"✅ 穩定幣數據獲取成功: 總量 ${total_supply/1e9:.1f}B")
        else:
            logger.warning("⚠️ 無法獲取穩定幣數據")
            
    except Exception as e:
        logger.warning(f"⚠️ 穩定幣數據獲取失敗: {e}")
    
    return stablecoin_data


async def get_market_indicators_async(session):
    """
    📈 獲取市場輔助指標
    整合：期貨資金費率 + 穩定幣流通量
    """
    funding_data = await get_funding_rates_async(session)
    stablecoin_data = await get_stablecoin_supply_async(session)
    
    return {
        'funding': funding_data,
        'stablecoins': stablecoin_data
    }


async def fetch_dexscreener_sentiment(session):
    # Fallback: DEX Screener (Uniswap/Raydium)
    pairs = {
        'BTC': 'ethereum/0xcbcdf9626bc03e24f779434178a73a0b4bad62ed',
        'ETH': 'ethereum/0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640',
        'SOL': 'solana/8sLbNZoVqBvrBsZRNG3vEPkwxTP67L1JZM74qXwB6u1Q'
    }
    result = {}
    try:
        for symbol, pair_id in pairs.items():
            url = f"https://api.dexscreener.com/latest/dex/pairs/{pair_id}"
            data = await fetch_with_retry(session, url)
            
            if data and data.get('pair'):
                p = data['pair']
                result[symbol] = {
                    'price': float(p.get('priceUsd', 0)),
                    'change': float(p.get('priceChange', {}).get('h24', 0)),
                    'volume': float(p.get('volume', {}).get('h24', 0)),
                    'funding_rate': 0.0,
                    'rate_status': 'N/A (DEX)'
                }
    except Exception:
        pass
    return result if len(result) == 3 else None

async def get_chain_momentum_async(session):
    """非同步獲取公鏈資金動能 (使用歷史數據計算真實變動)"""
    logger.info("📡 正在獲取 DefiLlama 公鏈數據...")
    
    # 1. 獲取所有公鏈的基本數據
    data = await fetch_with_retry(session, "https://api.llama.fi/v2/chains")
    if not data:
        return []
    
    # 轉換為 DataFrame 並排序
    import pandas as pd
    df = pd.DataFrame(data)
    df = df.sort_values(by='tvl', ascending=False).head(TOP_N_CHAINS)
    
    # 2. 篩選出我們支援的公鏈
    supported_chains = []
    for _, row in df.iterrows():
        chain_name = row['name']
        search_id = CHAIN_MAPPING.get(chain_name)
        if search_id:
            supported_chains.append({
                'name': chain_name,
                'search_id': search_id,
                'base_tvl': row['tvl']
            })
    
    logger.info(f"⚡ 正在並行獲取 {len(supported_chains)} 條公鏈的歷史 TVL 數據...")
    
    # 3. 並行獲取所有公鏈的歷史 TVL 數據
    tasks = [get_chain_historical_tvl(session, chain['name']) for chain in supported_chains]
    historical_results = await asyncio.gather(*tasks)
    
    candidates = []
    outflow_chains = []
    
    for chain_info, hist_data in zip(supported_chains, historical_results):
        if not hist_data:
            # 如果無法獲取歷史數據，使用基本 TVL 但變動為 0
            hist_data = {
                'tvl': chain_info['base_tvl'],
                'change_1d': 0,
                'change_7d': 0,
                'change_30d': 0,
                'change_90d': 0
            }
        
        chain_name = chain_info['name']
        search_id = chain_info['search_id']
        tvl = hist_data['tvl']
        change_1d = hist_data['change_1d']
        change_7d = hist_data['change_7d']
        change_30d = hist_data['change_30d']
        change_90d = hist_data.get('change_90d', 0)
        
        # 動能判定邏輯
        if change_1d > 3.0:
            status = "🔥 資金暴衝"
        elif change_1d > MOMENTUM_THRESHOLD and change_7d > 0 and (change_1d * 7) > change_7d:
            status = "🚀 加速流入"
        elif change_1d > MOMENTUM_THRESHOLD:
            status = "🟢 穩健增長"
        elif change_1d < -MOMENTUM_THRESHOLD:
            status = "⚠️ 資金流出"
            outflow_chains.append({
                "chain_name": chain_name,
                "change_1d": change_1d
            })
            # 仍然加入候選，方便分析
        
        # 只要變動超過閾值（正或負）都加入
        if abs(change_1d) > abs(MOMENTUM_THRESHOLD) or abs(change_7d) > 1:
            candidates.append({
                "chain_name": chain_name,
                "search_id": search_id,
                "tvl": tvl,
                "change_1d": change_1d,
                "change_7d": change_7d,
                "change_30d": change_30d,
                "change_90d": change_90d,
                # 每週獨立變化
                "change_w1": hist_data.get('change_w1', change_7d),
                "change_w2": hist_data.get('change_w2', 0),
                "change_w3": hist_data.get('change_w3', 0),
                "change_w4": hist_data.get('change_w4', 0),
                # 每週金額
                "amount_24h": hist_data.get('amount_24h', 0),
                "amount_w1": hist_data.get('amount_w1', 0),
                "amount_w2": hist_data.get('amount_w2', 0),
                "amount_w3": hist_data.get('amount_w3', 0),
                "amount_w4": hist_data.get('amount_w4', 0),
                "status": status if change_1d > -MOMENTUM_THRESHOLD else "⚠️ 資金流出"
            })
    
    # 排序：優先顯示漲幅最大的
    candidates.sort(key=lambda x: x['change_1d'], reverse=True)
    
    logger.info(f"✅ 找到 {len(candidates)} 條有顯著資金變動的公鏈")
    
    return candidates, outflow_chains

# 原生幣分類 (用於資金流向分析)
# 注意：需要包含所有常見的 Wrapped 變體和流動性質押代幣
NATIVE_TOKENS = {
    # Ethereum 及其 L2 (都使用 ETH)
    'ETH', 'WETH', 'STETH', 'WSTETH', 'RETH', 'CBETH', 'FRXETH', 'SETH2', 'ANKRETH',
    # Solana
    'SOL', 'WSOL', 'MSOL', 'JITOSOL', 'BSOL', 'STSOL', 'SCNSOL', 'JSOL',
    # BNB Chain
    'BNB', 'WBNB', 'SLIBNB', 'ANKRBNB',
    # Polygon
    'MATIC', 'WMATIC', 'POL', 'WPOL', 'STMATIC',
    # Avalanche
    'AVAX', 'WAVAX', 'SAVAX', 'GGAVAX',
    # Arbitrum (使用 ETH)
    'ARB',  # ARB 是治理代幣，不是原生幣，但仍列入追蹤
    # Optimism (使用 ETH)
    'OP',   # OP 是治理代幣
    # Sui
    'SUI', 'WSUI', 'AFSUI', 'HASUI', 'VSUI',
    # Aptos
    'APT', 'WAPT', 'STAPT', 'TAPT',
    # Sei
    'SEI', 'WSEI',
    # Tron
    'TRX', 'WTRX', 'STRX',
    # Fantom
    'FTM', 'WFTM', 'SFTM',
    # Mantle
    'MNT', 'WMNT',
    # Cronos
    'CRO', 'WCRO', 'LCRO',
    # TON
    'TON', 'WTON', 'TSTON',
    # Cardano
    'ADA', 'WADA',
    # ==== 新增：新興公鏈原生幣 ====
    # Hyperliquid
    'HYPE', 'WHYPE',
    # Injective
    'INJ', 'WINJ',
    # Celestia
    'TIA', 'WTIA', 'STIA',
    # Cosmos
    'ATOM', 'STATOM', 'WATOM',
    # Near
    'NEAR', 'WNEAR', 'STNEAR',
    # Polkadot
    'DOT', 'WDOT', 'LDOT',
    # Hedera
    'HBAR', 'WHBAR',
    # Algorand  
    'ALGO', 'WALGO',
}

# 穩定幣分類 (含歐元穩定幣)
STABLECOINS = {
    # 美元穩定幣
    'USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'USDD', 'BUSD', 'FRAX', 'LUSD', 'USDP',
    'USDE', 'PYUSD', 'GUSD', 'SUSD', 'MIM', 'CRVUSD', 'GHO', 'DOLA', 'USDX', 'UST',
    # 歐元穩定幣
    'EURC', 'EURS', 'EURT', 'CEUR', 'AGEUR', 'SEUR',
    # 其他法幣穩定幣
    'XSGD', 'JPYC', 'CADC', 'NZDS',
}

# BTC 相關
BTC_TOKENS = {
    'BTC', 'WBTC', 'TBTC', 'RENBTC', 'SBTC', 'HBTC', 'BTCB'
}

# ==== 🌍 新增：公鏈 → 原生幣映射 (國家 → 貨幣) ====
CHAIN_TO_NATIVE = {
    'ethereum': 'ETH',
    'solana': 'SOL',
    'bsc': 'BNB',
    'polygon': 'MATIC',
    'avalanche': 'AVAX',
    'arbitrum': 'ETH',  # L2 使用 ETH
    'optimism': 'ETH',  # L2 使用 ETH
    'base': 'ETH',      # L2 使用 ETH
    'sui': 'SUI',
    'aptos': 'APT',
    'tron': 'TRX',
    'fantom': 'FTM',
    'mantle': 'MNT',
    'cronos': 'CRO',
    'ton': 'TON',
    'sei': 'SEI',
    # ==== 新增：新興公鏈映射 ====
    'hyperliquid': 'HYPE',
    'injective': 'INJ',
    'celestia': 'TIA',
    'cosmos': 'ATOM',
    'near': 'NEAR',
    'polkadot': 'DOT',
    'hedera': 'HBAR',
    'algorand': 'ALGO',
}


def analyze_rotation_cycle(flow_analysis):
    """
    🔄 資金輪動週期判斷 (經濟週期分析)
    
    輪動順序：
    穩定幣 → 原生幣 → Altcoin → 穩定幣
       |         |         |         |
      避險    大盤行情   Alpha期    獲利了結
    
    返回：
    - cycle_phase: 當前週期階段
    - cycle_signal: 操作建議
    """
    if not flow_analysis or 'breakdown' not in flow_analysis:
        return {'cycle_phase': '❓ 數據不足', 'cycle_signal': '等待更多數據'}
    
    breakdown = flow_analysis['breakdown']
    
    native_vol_pct = breakdown.get('native', {}).get('volume_pct', 0)
    stable_vol_pct = breakdown.get('stablecoin', {}).get('volume_pct', 0)
    altcoin_vol_pct = breakdown.get('altcoin', {}).get('volume_pct', 0)
    
    # 結合市場情緒
    sentiment = flow_analysis.get('market_sentiment', {})
    buy_sell_ratio = sentiment.get('buy_sell_ratio', 1.0)
    bullish_pct = sentiment.get('bullish_pct', 50)
    
    # 週期判斷邏輯
    if stable_vol_pct > 50:
        # 穩定幣主導 = 避險/觀望
        if buy_sell_ratio < 0.9:
            phase = "🔴 避險期 (Risk-Off)"
            signal = "⚠️ 資金流向穩定幣，市場恐慌，建議減倉觀望"
        else:
            phase = "🟡 蓄勢期 (Accumulation)"
            signal = "👀 資金在穩定幣待命，可能準備進場"
    
    elif native_vol_pct > 40 and altcoin_vol_pct < 30:
        # 原生幣主導 = 大盤行情
        if buy_sell_ratio > 1.1:
            phase = "🟢 大盤行情 (Native Rally)"
            signal = "📈 資金湧入原生幣，大盤主導，可跟隨原生幣趨勢"
        else:
            phase = "🟡 大盤整理"
            signal = "⏳ 原生幣主導但買盤不強，觀察後續"
    
    elif altcoin_vol_pct > 35:
        # Altcoin 主導 = Alpha 機會期
        if buy_sell_ratio > 1.05 and bullish_pct > 55:
            phase = "🚀 Alpha 爆發期 (Altcoin Season)"
            signal = "🔥 資金輪動到個幣，尋找 Alpha 機會！"
        elif buy_sell_ratio < 0.95:
            phase = "📉 Altcoin 獲利了結"
            signal = "⚠️ Altcoin 活躍但賣壓增加，注意止盈"
        else:
            phase = "🟢 Altcoin 活躍期"
            signal = "🎯 個幣機會增加，精選優質項目"
    
    else:
        # 混合狀態
        phase = "🟡 均衡盤整期"
        signal = "👀 資金分散，等待明確方向"
    
    return {
        'cycle_phase': phase,
        'cycle_signal': signal,
        'native_pct': native_vol_pct,
        'stable_pct': stable_vol_pct,
        'altcoin_pct': altcoin_vol_pct
    }


def analyze_cross_chain_native_strength(all_flow_analysis, chains):
    """
    🌐 跨鏈原生幣強弱對比 (國際匯率比較)
    
    比較各公鏈原生幣的：
    1. 價格變動 (1H / 24H)
    2. 交易量變動
    3. 買賣力道
    
    返回：排序後的原生幣強弱列表
    """
    native_strength = []
    
    for chain in chains:
        chain_id = chain.get('search_id', '')
        flow = all_flow_analysis.get(chain_id)
        
        if not flow or not flow.get('native_pairs'):
            continue
        
        native_pairs = flow['native_pairs']
        native_symbol = CHAIN_TO_NATIVE.get(chain_id, chain_id.upper())
        
        # 聚合該鏈所有原生幣交易對的數據
        total_volume = sum(p.get('volume_24h', 0) for p in native_pairs)
        avg_change_1h = sum(p.get('change_1h', 0) for p in native_pairs) / len(native_pairs) if native_pairs else 0
        avg_change_24h = sum(p.get('change_24h', 0) for p in native_pairs) / len(native_pairs) if native_pairs else 0
        total_buys = sum(p.get('buys', 0) for p in native_pairs)
        total_sells = sum(p.get('sells', 0) for p in native_pairs)
        
        buy_sell_ratio = total_buys / total_sells if total_sells > 0 else 1.0
        
        # 計算綜合強弱分數 (0-100)
        # 權重：24H 漲幅 40% + 1H 漲幅 20% + 買賣比 20% + 交易量對比 20%
        score = 50  # 基準分
        score += min(20, max(-20, avg_change_24h * 2))  # 24H 漲幅貢獻
        score += min(10, max(-10, avg_change_1h * 2))   # 1H 漲幅貢獻
        score += min(10, max(-10, (buy_sell_ratio - 1) * 20))  # 買賣比貢獻
        
        # 結合鏈的 TVL 變動
        tvl_change = chain.get('change_1d', 0)
        score += min(10, max(-10, tvl_change * 2))  # TVL 變動貢獻
        
        # 強弱判定
        if score >= 70:
            strength_label = "🟢 極強"
        elif score >= 60:
            strength_label = "🟢 偏強"
        elif score >= 40:
            strength_label = "🟡 中性"
        elif score >= 30:
            strength_label = "🔴 偏弱"
        else:
            strength_label = "🔴 極弱"
        
        native_strength.append({
            'chain': chain['chain_name'],
            'chain_id': chain_id,
            'native_symbol': native_symbol,
            'strength_score': round(score, 1),
            'strength_label': strength_label,
            'change_1h': round(avg_change_1h, 2),
            'change_24h': round(avg_change_24h, 2),
            'volume_24h': total_volume,
            'buy_sell_ratio': round(buy_sell_ratio, 2),
            'tvl_change': chain.get('change_1d', 0)
        })
    
    # 按強弱分數排序
    native_strength.sort(key=lambda x: x['strength_score'], reverse=True)
    
    return native_strength

async def analyze_assets_async(session, chain_id, analyze_all=True):
    """
    非同步分析鏈上資產，並區分資金流向類別
    
    回傳:
    - top_tokens: 熱門個別代幣列表
    - flow_analysis: 資金流向分析 (原生幣/穩定幣/BTC/個別代幣 佔比)
    """
    # 使用 DEX 名稱搜索，這樣能獲得更多該鏈的交易對
    # 針對不同鏈使用不同的搜索關鍵字
    # 針對不同鏈使用多個 DEX 關鍵字以擴大覆蓋範圍
    CHAIN_DEX_KEYWORDS = {
        'tron': ['sunswap'],
        'avalanche': ['traderjoe', 'pangolin'],
        'ethereum': ['uniswap', 'sushiswap', 'curve', 'balancer'],
        'solana': ['raydium', 'orca', 'meteora', 'jupiter'],
        'bsc': ['pancakeswap', 'biswap'],
        'polygon': ['quickswap', 'sushiswap'],
        'arbitrum': ['camelot', 'uniswap', 'sushiswap'],
        'base': ['aerodrome', 'uniswap'],
        'optimism': ['velodrome', 'uniswap'],
        'sui': ['cetus', 'turbos'],
        'aptos': ['liquidswap', 'pancakeswap'],
        'fantom': ['spookyswap', 'equalizer'],
        'cronos': ['vvs', 'mmf'],
        'mantle': ['merchant', 'fusionx'],
        'ton': ['ston', 'dedust'],
        'blast': ['thruster', 'ambient'],
        'linea': ['nile', 'syncswap'],
        'scroll': ['ambient', 'iziswap'],
        'zksync': ['syncswap', 'koi'],
        'cardano': ['minswap'],
    }
    
    keywords = CHAIN_DEX_KEYWORDS.get(chain_id, [chain_id])
    if isinstance(keywords, str):
        keywords = [keywords]
        
    tasks = [fetch_with_retry(session, f"https://api.dexscreener.com/latest/dex/search?q={k}") for k in keywords]
    results = await asyncio.gather(*tasks)
    
    all_pairs = []
    seen_pair_addresses = set()
    
    for data in results:
        if data and 'pairs' in data:
            for pair in data['pairs']:
                pair_addr = pair.get('pairAddress')
                if pair_addr and pair_addr not in seen_pair_addresses:
                    seen_pair_addresses.add(pair_addr)
                    all_pairs.append(pair)
    
    if not all_pairs:
        return [], None
    
    pairs = all_pairs
    
    # 資金流向分類統計
    flow_stats = {
        'native': {'volume': 0, 'liquidity': 0, 'pairs': 0, 'tokens': set(), 'net_flow_count': 0},
        'stablecoin': {'volume': 0, 'liquidity': 0, 'pairs': 0, 'tokens': set(), 'net_flow_count': 0},
        'btc': {'volume': 0, 'liquidity': 0, 'pairs': 0, 'tokens': set(), 'net_flow_count': 0},
        'altcoin': {'volume': 0, 'liquidity': 0, 'pairs': 0, 'tokens': set(), 'net_flow_count': 0},
    }
    
    top_altcoins = []  # 熱門個別代幣
    accumulating_tokens = []  # 穩健吸籌代幣
    
    # ==== 新增：深度市場分析 ====
    from collections import Counter
    market_breadth = {'up': 0, 'down': 0, 'total': 0}
    narrative_keywords = []
    total_pressure = 0
    total_change = 0
    valid_count = 0
    
    seen_symbols = set()
    
    current_time_ms = datetime.now().timestamp() * 1000
    
    for pair in pairs:
        if pair.get('chainId') != chain_id:
            continue
        
        base_symbol = pair['baseToken']['symbol'].upper()
        quote_symbol = pair.get('quoteToken', {}).get('symbol', '').upper()
        
        liquidity = pair.get('liquidity', {}).get('usd', 0) or 0
        volume_24h = pair.get('volume', {}).get('h24', 0) or 0
        pair_created_at = pair.get('pairCreatedAt', current_time_ms)
        
        # 跳過流動性太低的
        if liquidity < 10000:
            continue
            
        # ==== 🛡️ 數據清洗 (Data Cleaning) ====
        # 1. 刷量過濾: 交易量/流動性 > 50倍 (除非是大熱點，否則通常是虛假交易)
        # 用戶是來看趨勢的，不是來看刷量盤的
        turnover = volume_24h / liquidity
        if turnover > 100: # 非常極端的刷量
             continue
             
        # 2. 價格異常過濾
        price_usd = float(pair.get('priceUsd', 0))
        if price_usd == 0:
            continue
            
        # 3. 殭屍盤過濾 (有量無價變動 = 對敲刷量)
        # ==== 📊 市場寬度與風險統計 ====
        price_change_24h = pair.get('priceChange', {}).get('h24', 0) or 0
        
        # 殭屍盤過濾: 交易量 > $50k 但價格完全不動 = 對敲
        if volume_24h > 50000 and abs(price_change_24h) < 0.01:
            continue
        if price_change_24h > 0:
            market_breadth['up'] += 1
        elif price_change_24h < 0:
            market_breadth['down'] += 1
        market_breadth['total'] += 1
        
        # 收集風險指標 (僅針對活躍代幣)
        if volume_24h > 10000:
            pressure = volume_24h / liquidity if liquidity > 0 else 0
            total_pressure += pressure
            total_change += price_change_24h
            valid_count += 1
        
        # ==== 修復：分別統計 Base Token 和 Quote Token 的資金流向 ====
        # 大多數交易對是 Altcoin/原生幣 或 Altcoin/穩定幣 的格式
        # 所以原生幣通常在 Quote 位置
        
        # 判斷 Base Token 類別
        if base_symbol in NATIVE_TOKENS:
            base_category = 'native'
        elif base_symbol in STABLECOINS:
            base_category = 'stablecoin'
        elif base_symbol in BTC_TOKENS:
            base_category = 'btc'
        else:
            base_category = 'altcoin'
        
        # 判斷 Quote Token 類別
        if quote_symbol in NATIVE_TOKENS:
            quote_category = 'native'
        elif quote_symbol in STABLECOINS:
            quote_category = 'stablecoin'
        elif quote_symbol in BTC_TOKENS:
            quote_category = 'btc'
        else:
            quote_category = 'altcoin'
        
        # 統計 Base Token 的交易量 (按 50% 權重，因為交易是雙向的)
        
        # 計算淨流向 (Base 被買 = Base 流入; Quote 被賣 = Quote 流出)
        txns = pair.get('txns', {}).get('h24', {})
        net_txns = txns.get('buys', 0) - txns.get('sells', 0)

        flow_stats[base_category]['volume'] += volume_24h * 0.5
        flow_stats[base_category]['liquidity'] += liquidity * 0.5
        flow_stats[base_category]['pairs'] += 0.5
        flow_stats[base_category]['tokens'].add(base_symbol)
        flow_stats[base_category]['net_flow_count'] += net_txns
        
        # 統計 Quote Token 的交易量 (另外 50% 權重)
        flow_stats[quote_category]['volume'] += volume_24h * 0.5
        flow_stats[quote_category]['liquidity'] += liquidity * 0.5
        flow_stats[quote_category]['pairs'] += 0.5
        flow_stats[quote_category]['tokens'].add(quote_symbol)
        flow_stats[quote_category]['net_flow_count'] -= net_txns
        
        # 收集熱門個別代幣 (排除原生幣、穩定幣、BTC)
        if (base_symbol not in NATIVE_TOKENS and 
            base_symbol not in STABLECOINS and 
            base_symbol not in BTC_TOKENS and 
            base_symbol not in seen_symbols):
            
            if liquidity >= LIQUIDITY_MIN or volume_24h >= VOLUME_MIN:
                # ==== 🎭 收集敘事關鍵字 (Narratives) ====
                # 簡單提取 Symbol 中的關鍵詞 (如 AI, DOGE, TRUMP)
                import re
                words = re.split(r'[^a-zA-Z]', base_symbol)
                for w in words:
                    w = w.upper()
                    if len(w) >= 3 and w not in ['COIN', 'TOKEN', 'INU', 'THE', 'BSC', 'ETH', 'SOL']: # 過濾無意義詞
                         narrative_keywords.append(w)

                price_change = pair.get('priceChange', {}).get('h24', 0) or 0
                price_change_1h = pair.get('priceChange', {}).get('h1', 0) or 0
                price_change_5m = pair.get('priceChange', {}).get('m5', 0) or 0
                buying_pressure = volume_24h / liquidity if liquidity > 0 else 0
                
                txns = pair.get('txns', {}).get('h24', {})
                buys = txns.get('buys', 0)
                sells = txns.get('sells', 0)
                net_flow = "流入" if buys > sells else "流出"
                
                # ==== 🔥 動能狀態分析 (Momentum Analysis) ====
                # 1. 計算量能加速 (5m 成交量 vs 24h 平均)
                # 24h平均每5分鐘量 = volume_24h / (24 * 12)
                avg_5m_vol = volume_24h / 288
                
                # 估算當前 5m 量 (透過買賣單數估算，因為 API 沒直接給 5m volume)
                # 假設平均單筆金額一致
                txns_m5 = pair.get('txns', {}).get('m5', {})
                m5_count = txns_m5.get('buys', 0) + txns_m5.get('sells', 0)
                
                txns_h24 = pair.get('txns', {}).get('h24', {})
                h24_count = txns_h24.get('buys', 0) + txns_h24.get('sells', 0)
                
                # 簡單估算：當前熱度倍數
                if h24_count > 0:
                    activity_ratio = (m5_count * 288) / h24_count
                else:
                    activity_ratio = 0
                
                # 2. 判斷狀態
                if activity_ratio > 3.0 and price_change_5m > 0:
                    status = "🚀 剛剛發動 (爆發)"
                elif activity_ratio > 2.0 and price_change_5m < -2:
                    status = "📉 急速下殺 (恐慌)"
                elif buys > sells * 1.5 and -2 < price_change_1h < 2:
                    status = "🧐 壓價吸籌 (潛伏)"
                elif sells > buys * 1.2 and price_change_1h > 3:
                    status = "⚠️ 拉高出貨 (危險)"
                elif activity_ratio < 0.5:
                    status = "❄️ 交易冷卻"
                else:
                    status = "➡️ 震盪整理"

                seen_symbols.add(base_symbol)
                
                token_data = {
                    "symbol": base_symbol,
                    "price": f"${float(pair.get('priceUsd', 0)):.6f}",
                    "change_5m": price_change_5m,
                    "change_1h": price_change_1h,
                    "change_24h": price_change,
                    "volume": volume_24h,
                    "liquidity": liquidity,
                    "pressure": buying_pressure,
                    "net_flow": net_flow,
                    "txns_diff": buys - sells,
                    "total_txns": buys + sells,
                    "url": pair.get('url', ''),
                    "pair_address": pair.get('pairAddress', ''),
                    "status": status,  # 新增狀態
                    "activity": round(activity_ratio, 1) # 新增活躍度
                }
                
                top_altcoins.append(token_data)
                
                # ==== 🐋 鯨魚吸籌偵測邏輯 (Whale Accumulation) ====
                # 條件 1: 存活時間 > 3 個月 (90天) (或至少 60 天)
                age_days = (current_time_ms - pair_created_at) / (1000 * 60 * 60 * 24)
                is_old_enough = age_days > 60
                
                # 條件 4: 真·鯨魚潛伏模型 (Smart Money Accumulation)
                # 邏輯核心：高流動性 + 高單筆金額 + 溫和買盤優勢 (非散戶FOMO)
                
                txns = pair.get('txns', {}).get('h24', {})
                buys = txns.get('buys', 0)
                sells = txns.get('sells', 0)
                total_txns = buys + sells
                
                if total_txns == 0: continue

                # 基礎指標計算
                net_buy_ratio = (buys / total_txns * 100)
                avg_txn_value = (volume_24h / total_txns)
                
                # ==== 核心篩選器 ====
                
                # 1. 深度門檻: 流動性 > $250k (鯨魚進出場的基礎)
                is_deep = liquidity > 250000
                
                # 2. 大戶特徵: 平均單筆 > $100 (過濾 $10 $20 的散戶/機器人刷單)
                #    這是區分 "散戶熱度" 與 "機構行為" 的關鍵
                is_big_ticket = avg_txn_value > 100
                
                # 3. 吸籌結構: 買盤佔比 50% ~ 85%
                #    >50%: 買方主導
                #    <85%: 排除貔貅盤和過度FOMO。鯨魚吸籌通常是溫和的。
                is_smart_accumulation = (50 < net_buy_ratio <= 85)
                
                # 4. 價格壓抑: -5% < 24H漲幅 < 10%
                #    價格沒漲但有大單在買，才是真正的"潛伏"
                is_price_suppressed = -5 < price_change < 10
                
                if is_old_enough and is_deep and is_big_ticket and is_smart_accumulation and is_price_suppressed:
                    # 計算鯨魚強度 (Whale Score)
                    # 結合 流動性規模 與 單筆金額
                    whale_score = (avg_txn_value / 50) + (liquidity / 1000000)
                    
                    accumulating_token = token_data.copy()
                    accumulating_token.update({
                        'age_days': int(age_days),
                        'buys_24h': buys,
                        'sells_24h': sells,
                        'net_buy_ratio': round(net_buy_ratio, 1),
                        'avg_txn': round(avg_txn_value, 1),
                        'whale_score': round(whale_score, 1),
                        'accumulation_reason': f"單筆${int(avg_txn_value)} | 深度${int(liquidity/1000)}k | 買盤{int(net_buy_ratio)}%"
                    })
                    accumulating_tokens.append(accumulating_token)
    
    # 計算資金流向佔比
    total_volume = sum(s['volume'] for s in flow_stats.values())
    total_liquidity = sum(s['liquidity'] for s in flow_stats.values())
    
    flow_analysis = {
        'total_volume': total_volume,
        'total_liquidity': total_liquidity,
        'breakdown': {}
    }
    
    for category, stats in flow_stats.items():
        volume_pct = (stats['volume'] / total_volume * 100) if total_volume > 0 else 0
        liquidity_pct = (stats['liquidity'] / total_liquidity * 100) if total_liquidity > 0 else 0
        
        flow_analysis['breakdown'][category] = {
            'volume': stats['volume'],
            'volume_pct': round(volume_pct, 1),
            'liquidity': stats['liquidity'],
            'liquidity_pct': round(liquidity_pct, 1),
            'pairs': stats['pairs'],
            'top_tokens': list(stats['tokens'])[:5],
            'net_flow_count': stats.get('net_flow_count', 0)
        }
    
    # 判斷主要資金流向
    max_category = max(flow_stats.keys(), key=lambda k: flow_stats[k]['volume'])
    flow_analysis['dominant_flow'] = max_category
    flow_analysis['dominant_pct'] = flow_analysis['breakdown'][max_category]['volume_pct']
    
    # ==== 整合深度市場分析 ====
    # 1. 市場寬度 (Market Breadth)
    breadth_ratio = (market_breadth['up'] / market_breadth['total'] * 100) if market_breadth['total'] > 0 else 50
    
    # 2. 過熱指標 (Overheat Index)
    avg_pressure = (total_pressure / valid_count) if valid_count > 0 else 0
    avg_change = (total_change / valid_count) if valid_count > 0 else 0
    
    overheat_score = "neutral"
    if avg_pressure > 1.5 and avg_change > 10:
        overheat_score = "overheated" # 過熱
    elif avg_pressure < 0.3 and avg_change < -5:
        overheat_score = "fear" # 恐慌
        
    flow_analysis['market_depth'] = {
        'breadth_up': market_breadth['up'],
        'breadth_down': market_breadth['down'],
        'breadth_ratio': round(breadth_ratio, 1),
        'avg_pressure': round(avg_pressure, 2),
        'avg_change': round(avg_change, 2),
        'overheat_score': overheat_score,
        'narratives': Counter(narrative_keywords).most_common(5) # 取前 5 大熱詞
    }
    
    # 將穩健吸籌代幣排序（淨買入佔比優先）
    # ==== 🔷 新增：原生幣熱門交易對追蹤 ====
    native_token_pairs = []
    for pair in pairs:
        if pair.get('chainId') != chain_id:
            continue
        
        base_symbol = pair['baseToken']['symbol'].upper()
        
        # 只分析原生幣交易對
        if base_symbol in NATIVE_TOKENS:
            liquidity = pair.get('liquidity', {}).get('usd', 0) or 0
            volume_24h = pair.get('volume', {}).get('h24', 0) or 0
            volume_1h = pair.get('volume', {}).get('h1', 0) or 0
            
            if liquidity >= 50000 and volume_24h >= 10000:
                price_change_24h = pair.get('priceChange', {}).get('h24', 0) or 0
                price_change_1h = pair.get('priceChange', {}).get('h1', 0) or 0
                
                txns = pair.get('txns', {}).get('h24', {})
                buys = txns.get('buys', 0)
                sells = txns.get('sells', 0)
                
                # 動能加速度 (1H 交易量 * 24 vs 24H 交易量)
                momentum_acceleration = (volume_1h * 24 / volume_24h) if volume_24h > 0 else 0
                
                native_token_pairs.append({
                    'symbol': base_symbol,
                    'quote': pair.get('quoteToken', {}).get('symbol', '').upper(),
                    'price': f"${float(pair.get('priceUsd', 0)):.4f}",
                    'change_1h': price_change_1h,
                    'change_24h': price_change_24h,
                    'volume_24h': volume_24h,
                    'volume_1h': volume_1h,
                    'liquidity': liquidity,
                    'buys': buys,
                    'sells': sells,
                    'momentum_accel': round(momentum_acceleration, 2),  # >1 = 加速, <1 = 減速
                    'net_flow': '流入 📈' if buys > sells else '流出 📉',
                    'url': pair.get('url', '')
                })
    
    # 排序原生幣交易對 (按交易量)
    native_token_pairs.sort(key=lambda x: x['volume_24h'], reverse=True)
    flow_analysis['native_pairs'] = native_token_pairs[:5]
    
    # ==== 📊 新增：市場情緒分析 ====
    total_buys = 0
    total_sells = 0
    bullish_tokens = 0
    bearish_tokens = 0
    
    for pair in pairs:
        if pair.get('chainId') != chain_id:
            continue
        txns = pair.get('txns', {}).get('h24', {})
        buys = txns.get('buys', 0)
        sells = txns.get('sells', 0)
        total_buys += buys
        total_sells += sells
        
        price_change = pair.get('priceChange', {}).get('h24', 0) or 0
        if price_change > 0:
            bullish_tokens += 1
        elif price_change < 0:
            bearish_tokens += 1
    
    # 市場情緒計算
    buy_sell_ratio = total_buys / total_sells if total_sells > 0 else 1.0
    bullish_pct = (bullish_tokens / (bullish_tokens + bearish_tokens) * 100) if (bullish_tokens + bearish_tokens) > 0 else 50
    
    if buy_sell_ratio > 1.2 and bullish_pct > 60:
        market_sentiment = '🟢 極度樂觀'
    elif buy_sell_ratio > 1.05 or bullish_pct > 55:
        market_sentiment = '🟢 偏多'
    elif buy_sell_ratio < 0.8 and bullish_pct < 40:
        market_sentiment = '🔴 極度悲觀'
    elif buy_sell_ratio < 0.95 or bullish_pct < 45:
        market_sentiment = '🔴 偏空'
    else:
        market_sentiment = '🟡 中性'
    
    flow_analysis['market_sentiment'] = {
        'sentiment': market_sentiment,
        'buy_sell_ratio': round(buy_sell_ratio, 2),
        'bullish_pct': round(bullish_pct, 1),
        'total_buys': total_buys,
        'total_sells': total_sells
    }
    
    # ==== ⚡ 新增：動能加速度最高的代幣 (短期爆發機會) ====
    momentum_tokens = []
    for pair in pairs:
        if pair.get('chainId') != chain_id:
            continue
        
        base_symbol = pair['baseToken']['symbol'].upper()
        if base_symbol in NATIVE_TOKENS or base_symbol in STABLECOINS or base_symbol in BTC_TOKENS:
            continue
        
        volume_24h = pair.get('volume', {}).get('h24', 0) or 0
        volume_1h = pair.get('volume', {}).get('h1', 0) or 0
        liquidity = pair.get('liquidity', {}).get('usd', 0) or 0
        
        if volume_24h > 50000 and liquidity > 30000 and volume_1h > 0:
            momentum = (volume_1h * 24 / volume_24h) if volume_24h > 0 else 0
            
            # 只要動能加速度 > 1.5 (近 1 小時交易量顯著高於平均)
            if momentum > 1.5:
                price_change_1h = pair.get('priceChange', {}).get('h1', 0) or 0
                price_change_24h = pair.get('priceChange', {}).get('h24', 0) or 0
                
                momentum_tokens.append({
                    'symbol': base_symbol,
                    'momentum_accel': round(momentum, 2),
                    'change_1h': price_change_1h,
                    'change_24h': price_change_24h,
                    'volume_1h': volume_1h,
                    'volume_24h': volume_24h,
                    'liquidity': liquidity,
                    'url': pair.get('url', ''),
                    'alert': '🚀 短期爆發' if momentum > 3 else '📈 動能增強'
                })
    
    momentum_tokens.sort(key=lambda x: x['momentum_accel'], reverse=True)
    flow_analysis['momentum_tokens'] = momentum_tokens[:5]
    
    # 過濾：只保留淨流入 (買 > 賣) 的代幣
    top_altcoins = [t for t in top_altcoins if t.get('txns_diff', 0) > 0]
    
    # 排序熱門代幣 (按交易量排序，展現真實資金規模)
    top_altcoins.sort(key=lambda x: x['volume'], reverse=True)
    
    # 排序吸籌代幣 (按鯨魚強度排序)
    accumulating_tokens.sort(key=lambda x: x.get('whale_score', 0), reverse=True)
    flow_analysis['accumulating_tokens'] = accumulating_tokens[:5]
    
    return top_altcoins[:5], flow_analysis

async def get_trending_tokens_async(session):
    """獲取近期新上線的趨勢代幣"""
    logger.info("🆕 正在掃描新幣首發...")
    
    # DEX Screener Trending API
    url = "https://api.dexscreener.com/token-boosts/latest/v1"
    data = await fetch_with_retry(session, url)
    
    new_tokens = []
    
    if data:
        for token in data[:20]:  # 取前 20 個
            try:
                chain_id = token.get('chainId', '')
                liquidity = token.get('liquidity', {}).get('usd', 0) or 0
                
                # 只保留流動性 > 50K 的
                if liquidity >= LIQUIDITY_MIN:
                    created_at = token.get('pairCreatedAt', 0)
                    age_hours = (time.time() * 1000 - created_at) / (1000 * 60 * 60) if created_at else 999
                    
                    new_tokens.append({
                        "symbol": token.get('baseToken', {}).get('symbol', 'N/A'),
                        "chain": chain_id,
                        "liquidity": liquidity,
                        "url": token.get('url', ''),
                        "age_hours": int(age_hours)
                    })
            except (KeyError, TypeError) as e:
                logger.debug(f"跳過無效新幣數據: {e}")
                continue
    
    return new_tokens

async def detect_cross_chain_flows(inflow_chains, outflow_chains):
    """偵測鏈間資金流動"""
    flows = []
    
    for out_chain in outflow_chains:
        for in_chain in inflow_chains:
            # 如果流出和流入幅度都超過 1%，可能是資金遷移
            if abs(out_chain['change_1d']) > 1 and in_chain['change_1d'] > 1:
                flows.append({
                    "from_chain": out_chain['chain_name'],
                    "from_change": out_chain['change_1d'],
                    "to_chain": in_chain['chain_name'],
                    "to_change": in_chain['change_1d'],
                    "strength": abs(out_chain['change_1d']) + in_chain['change_1d']
                })
    
    # 按強度排序
    flows.sort(key=lambda x: x['strength'], reverse=True)
    return flows[:5]

# ================= 5. 報告生成模組 (Report Export) =================

def export_to_csv(chains, all_tokens, filename=None):
    """匯出 CSV 報告"""
    if not filename:
        filename = REPORT_DIR / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        
        # 公鏈數據
        writer.writerow(['=== 公鏈資金流向 ==='])
        writer.writerow(['公鏈', 'TVL', '24H變動', '7D變動', '狀態'])
        for chain in chains:
            writer.writerow([
                chain['chain_name'],
                f"${chain['tvl']:,.0f}",
                f"{chain['change_1d']:.2f}%",
                f"{chain['change_7d']:.2f}%",
                chain['status']
            ])
        
        writer.writerow([])
        writer.writerow(['=== 熱門代幣 ==='])
        writer.writerow(['鏈', '代幣', '價格', '24H漲跌', '交易量', '流動性', '買壓係數', '連結'])
        
        for chain_id, tokens in all_tokens.items():
            for token in tokens:
                writer.writerow([
                    chain_id,
                    token['symbol'],
                    token['price'],
                    f"{token['change_24h']:.2f}%",
                    f"${token['volume']:,.0f}",
                    f"${token['liquidity']:,.0f}",
                    f"{token['pressure']:.2f}",
                    token['url']
                ])
    
    logger.info(f"📄 CSV 報告已匯出: {filename}")
    return filename

def export_to_json(chains, all_tokens, new_tokens, cross_flows, filename=None):
    """匯出 JSON 報告"""
    if not filename:
        filename = REPORT_DIR / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    report = {
        "generated_at": datetime.now().isoformat(),
        "chains": chains,
        "tokens_by_chain": all_tokens,
        "new_tokens": new_tokens,
        "cross_chain_flows": cross_flows
    }
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    
    logger.info(f"📄 JSON 報告已匯出: {filename}")
    return filename

def export_to_html(chains, all_tokens, all_flow_analysis, new_tokens, long_term_tokens, cross_flows, cex_data, stats, filename=None):
    """匯出 HTML 報告 (含多時間框架 + 資金流向 + 長線追蹤 + CEX 監控)"""
    if not filename:
        filename = REPORT_DIR / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    
    html_template = '''
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔗 全鏈資金流向分析報告</title>
    <style>
        :root {
            --bg-dark: #0a0a0f;
            --bg-card: #12121a;
            --accent: #6366f1;
            --green: #22c55e;
            --red: #ef4444;
            --orange: #f97316;
            --text: #e2e8f0;
            --text-muted: #94a3b8;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-dark);
            color: var(--text);
            line-height: 1.6;
            padding: 1rem;
            font-size: 16px;
            -webkit-text-size-adjust: 100%;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 {
            font-size: clamp(1.5rem, 5vw, 2rem);
            background: linear-gradient(135deg, var(--accent), #a855f7);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
            word-break: break-word;
        }
        h2 { font-size: clamp(1.1rem, 4vw, 1.25rem); }
        .timestamp { color: var(--text-muted); margin-bottom: 1.5rem; font-size: 0.875rem; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 0.75rem;
            margin-bottom: 1.5rem;
        }
        .stat-card {
            background: var(--bg-card);
            padding: 1rem;
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.05);
        }
        .stat-value { font-size: clamp(1.25rem, 4vw, 1.75rem); font-weight: 700; }
        .stat-label { color: var(--text-muted); font-size: 0.75rem; }
        .section { margin-bottom: 1.5rem; }
        .section-title {
            font-size: clamp(1rem, 4vw, 1.25rem);
            margin-bottom: 0.75rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            flex-wrap: wrap;
        }
        .card {
            background: var(--bg-card);
            border-radius: 12px;
            padding: 1rem;
            border: 1px solid rgba(255,255,255,0.05);
            margin-bottom: 1rem;
        }
        .chain-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 0.75rem;
            flex-wrap: wrap;
            gap: 0.5rem;
        }
        .chain-name { font-size: clamp(1rem, 3.5vw, 1.125rem); font-weight: 600; }
        .status-badge {
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.7rem;
            font-weight: 500;
            white-space: nowrap;
        }
        .status-surge { background: rgba(249, 115, 22, 0.2); color: var(--orange); }
        .status-accel { background: rgba(34, 197, 94, 0.2); color: var(--green); }
        .status-stable { background: rgba(99, 102, 241, 0.2); color: var(--accent); }
        .metrics {
            display: flex;
            gap: 0.75rem;
            color: var(--text-muted);
            font-size: 0.75rem;
            flex-wrap: wrap;
        }
        .metrics span { white-space: nowrap; }
        
        /* 表格響應式 */
        .table-wrapper {
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            margin: 0 -1rem;
            padding: 0 1rem;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 0.75rem;
            min-width: 500px;
        }
        th, td {
            padding: 0.5rem 0.75rem;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            font-size: 0.8rem;
            white-space: nowrap;
        }
        th { color: var(--text-muted); font-weight: 500; font-size: 0.7rem; text-transform: uppercase; }
        .positive { color: var(--green); }
        .negative { color: var(--red); }
        a { 
            color: var(--accent); 
            text-decoration: none;
            padding: 0.25rem 0;
            display: inline-block;
        }
        a:hover, a:active { text-decoration: underline; }
        .flow-item {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.75rem 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            flex-wrap: wrap;
        }
        .flow-arrow { color: var(--accent); font-size: 1.25rem; }
        .new-token-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
            gap: 0.75rem;
        }
        .new-token-card {
            background: rgba(233, 30, 99, 0.1);
            border: 1px solid rgba(233, 30, 99, 0.2);
            border-radius: 8px;
            padding: 0.75rem;
        }
        .new-token-card a {
            word-break: break-all;
            font-size: 0.8rem;
        }
        
        /* 資金流向條與進度條 */
        .flow-bar {
            height: 8px;
            background: rgba(255,255,255,0.1);
            border-radius: 4px;
            overflow: hidden;
            margin: 0.5rem 0;
        }
        .flow-bar-fill {
            height: 100%;
            border-radius: 4px;
            transition: width 0.3s ease;
        }
        .tvl-share-bar {
            height: 4px;
            background: rgba(255,255,255,0.05);
            border-radius: 2px;
            overflow: hidden;
            margin-top: 0.5rem;
        }
        .tvl-share-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--accent), #a855f7);
            border-radius: 2px;
        }

        /* 視覺特效 */
        .glow-text {
            color: #fff;
            text-shadow: 0 0 10px rgba(168, 85, 247, 0.5), 0 0 20px rgba(168, 85, 247, 0.3);
            font-weight: 700;
        }
        .gradient-border {
            position: relative;
            background: var(--bg-card);
            background-clip: padding-box;
            border: 1px solid transparent;
            border-radius: 12px;
        }
        .gradient-border::before {
            content: '';
            position: absolute;
            top: 0; right: 0; bottom: 0; left: 0;
            z-index: -1;
            margin: -1px;
            border-radius: inherit;
            background: linear-gradient(to right, var(--accent), #a855f7);
        }
        .chain-card {
            border-left: 3px solid var(--accent);
        }

        /* 手機端優化 */
        @media (max-width: 768px) {
            body { padding: 0.5rem; font-size: 14px; }
            .container { padding: 0; }
            .stats-grid { grid-template-columns: repeat(2, 1fr); gap: 0.5rem; margin-bottom: 1rem; }
            .stat-card { padding: 0.75rem; min-height: 80px; display: flex; flex-direction: column; justify-content: center; }
            .stat-value { font-size: 1.25rem; background: linear-gradient(135deg, #fff, #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
            .card { padding: 0.75rem; margin-bottom: 0.75rem; }
            
            /* 表格優化 */
            .table-wrapper { margin: 0 -0.75rem; padding: 0 0.75rem; }
            table { min-width: 320px; } /* 允許更窄 */
            th, td { padding: 0.5rem 0.25rem; font-size: 0.75rem; }
            th { background: rgba(255,255,255,0.02); }
            
            .hide-mobile { display: none; } /* 隱藏次要資訊 */
            
            .chain-header { flex-direction: row; align-items: center; justify-content: space-between; }
            .chain-name { font-size: 1rem; }
            .metrics { font-size: 0.7rem; gap: 0.5rem; }
            
            .new-token-grid { grid-template-columns: 1fr; }
            
            /* 增加點擊反饋 */
            tr:active { background: rgba(255,255,255,0.05); }
        }
        
        @media (max-width: 480px) {
            h1 { font-size: 1.3rem; line-height: 1.3; }
            h2.section-title { font-size: 1rem; margin-bottom: 0.5rem; }
            td a { display: block; padding: 0.5rem 0; } /* 增大點擊區域 */
            
            /* 極度緊湊模式 */
            .stats-grid { gap: 0.4rem; }
            .stat-card { padding: 0.5rem; }
            .stat-value { font-size: 1.1rem; }
            th, td { padding: 0.4rem 0.2rem; font-size: 0.7rem; }
        }
            
            /* 代幣連結更易點擊 */
            td a { 
                padding: 0.35rem 0; 
                font-weight: 600;
            }
            
            .status-badge { 
                font-size: 0.6rem; 
                padding: 0.2rem 0.4rem;
            }
            
            /* 資金流向更美觀 */
            .flow-chips {
                display: flex;
                flex-wrap: wrap;
                gap: 0.4rem;
            }
            .flow-chip {
                flex: 1 1 45%;
                padding: 0.5rem;
                border-radius: 8px;
                text-align: center;
                font-size: 0.75rem;
            }
            
            /* 鏈卡片優化 */
            .chain-card {
                border-left: 3px solid var(--accent);
            }
            .chain-name { font-size: 1rem; }
            .metrics { 
                font-size: 0.7rem;
                gap: 0.4rem;
            }
            .metrics span {
                padding: 0.2rem 0.4rem;
                background: rgba(255,255,255,0.05);
                border-radius: 4px;
            }
        }
        
        /* 觸控優化 */
        @media (hover: none) and (pointer: coarse) {
            a, button {
                min-height: 44px;
                display: inline-flex;
                align-items: center;
            }
            td a { 
                min-height: 40px; 
                padding: 0.5rem 0.25rem;
            }
            /* 可點擊行 */
            tr:active {
                background: rgba(99, 102, 241, 0.15);
            }
        }
        
        /* 深色主題美化 */
        .glow-text {
            text-shadow: 0 0 10px rgba(99, 102, 241, 0.5);
        }
        .gradient-border {
            border: 1px solid transparent;
            background: linear-gradient(var(--bg-card), var(--bg-card)) padding-box,
                        linear-gradient(135deg, var(--accent), #a855f7) border-box;
        }
        
        /* 資金佔比進度條 */
        .tvl-share-bar {
            height: 6px;
            background: rgba(255,255,255,0.1);
            border-radius: 3px;
            overflow: hidden;
            margin-top: 0.25rem;
        }
        .tvl-share-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--accent), #a855f7);
            border-radius: 3px;
            transition: width 0.5s ease;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔗 全鏈資金流向深度分析報告</h1>
        <p class="timestamp">生成時間: {{ timestamp }}</p>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{{ stats.chains_scanned }}</div>
                <div class="stat-label">掃描公鏈數</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ stats.tokens_found }}</div>
                <div class="stat-label">推薦代幣數</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ stats.new_tokens }}</div>
                <div class="stat-label">新幣偵測</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{{ "%.1f"|format(stats.accuracy) }}%</div>
                <div class="stat-label">系統準確率</div>
            </div>
        </div>
        
        <!-- 🌐 資金流向總覽 (經濟學視角) -->
        <div class="section">
            <h2 class="section-title">🌐 資金流向總覽 (經濟學視角)</h2>
            <div class="card" style="background: linear-gradient(135deg, rgba(99, 102, 241, 0.05), rgba(168, 85, 247, 0.05));">
                
                <!-- 流程圖 -->
                <div style="display: flex; flex-direction: column; gap: 1rem;">
                    
                    <!-- 第一層：總資金 -->
                    <div style="text-align: center;">
                        <div style="display: inline-block; padding: 0.75rem 1.5rem; background: linear-gradient(135deg, var(--accent), #a855f7); border-radius: 12px; color: white; font-weight: 600;">
                            🏦 全球總資金 (CEX + DEX)
                        </div>
                    </div>
                    
                    <!-- 箭頭 -->
                    <div style="text-align: center; font-size: 1.5rem; color: var(--accent);">↓</div>
                    
                    <!-- 第二層：公鏈分配 (按 24H TVL 變動排名) -->
                    <div style="text-align: center;">
                        <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.5rem;">資金流入公鏈 (按 24H TVL 變動排名)</div>
                        <div style="display: flex; justify-content: center; gap: 0.5rem; flex-wrap: wrap;">
                            {% set total_tvl = chains|sum(attribute='tvl') %}
                            {% set sorted_chains = chains|sort(attribute='change_1d', reverse=true) %}
                            {% for chain in sorted_chains[:8] %}
                            {% set share = (chain.tvl / total_tvl * 100) if total_tvl > 0 else 0 %}
                            <div style="padding: 0.4rem 0.75rem; background: var(--bg-card); border-radius: 8px; border: 1px solid {{ 'rgba(34, 197, 94, 0.3)' if chain.change_1d > 0 else 'rgba(239, 68, 68, 0.3)' }}; font-size: 0.75rem;">
                                <div style="font-weight: 600;">{{ chain.chain_name }}</div>
                                <div style="display: flex; gap: 0.5rem; font-size: 0.65rem; margin-top: 0.2rem;">
                                    <span style="color: var(--text-muted);">TVL {{ "%.1f"|format(share) }}%</span>
                                    <span class="{{ 'positive' if chain.change_1d > 0 else 'negative' }}">24H {{ "%+.2f"|format(chain.change_1d) }}%</span>
                                </div>
                            </div>
                            {% endfor %}
                        </div>
                    </div>
                    
                    <!-- 箭頭 -->
                    <div style="text-align: center; font-size: 1.5rem; color: var(--accent);">↓</div>
                    
                    <!-- 第三層：資金分配 (原生幣/穩定幣/個別幣) -->
                    <div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); text-align: center; margin-bottom: 0.75rem;">鏈內資金分配 (貨幣類型)</div>
                        
                        <!-- 計算全球加權資金分配 -->
                        {% set ns = namespace(total_vol=0, native_vol=0, stable_vol=0, altcoin_vol=0) %}
                        {% for chain_id, flow in all_flow_analysis.items() %}
                            {% if flow and flow.breakdown %}
                                {% set ns.total_vol = ns.total_vol + flow.total_volume %}
                                {% set ns.native_vol = ns.native_vol + flow.breakdown.get('native', {}).get('volume', 0) %}
                                {% set ns.stable_vol = ns.stable_vol + flow.breakdown.get('stablecoin', {}).get('volume', 0) %}
                                {% set ns.altcoin_vol = ns.altcoin_vol + flow.breakdown.get('altcoin', {}).get('volume', 0) %}
                            {% endif %}
                        {% endfor %}
                        
                        {% set avg_native = (ns.native_vol / ns.total_vol * 100) if ns.total_vol > 0 else 0 %}
                        {% set avg_stable = (ns.stable_vol / ns.total_vol * 100) if ns.total_vol > 0 else 0 %}
                        {% set avg_altcoin = (ns.altcoin_vol / ns.total_vol * 100) if ns.total_vol > 0 else 0 %}
                        
                        <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5rem;">
                            <!-- 原生幣 -->
                            <div style="text-align: center; padding: 0.75rem; background: rgba(34, 197, 94, 0.1); border-radius: 10px; border: 1px solid rgba(34, 197, 94, 0.2);">
                                <div style="font-size: 1.25rem;">🪙</div>
                                <div style="font-size: 0.7rem; color: var(--text-muted);">原生幣 (貨幣)</div>
                                <div style="font-size: 1.1rem; font-weight: 700; color: var(--green);">{{ "%.1f"|format(avg_native) }}%</div>
                            </div>
                            <!-- 穩定幣 -->
                            <div style="text-align: center; padding: 0.75rem; background: rgba(99, 102, 241, 0.1); border-radius: 10px; border: 1px solid rgba(99, 102, 241, 0.2);">
                                <div style="font-size: 1.25rem;">💵</div>
                                <div style="font-size: 0.7rem; color: var(--text-muted);">穩定幣 (美元)</div>
                                <div style="font-size: 1.1rem; font-weight: 700; color: var(--accent);">{{ "%.1f"|format(avg_stable) }}%</div>
                            </div>
                            <!-- 個別幣 -->
                            <div style="text-align: center; padding: 0.75rem; background: rgba(249, 115, 22, 0.1); border-radius: 10px; border: 1px solid rgba(249, 115, 22, 0.2);">
                                <div style="font-size: 1.25rem;">🛒</div>
                                <div style="font-size: 0.7rem; color: var(--text-muted);">個別幣 (商品)</div>
                                <div style="font-size: 1.1rem; font-weight: 700; color: var(--orange);">{{ "%.1f"|format(avg_altcoin) }}%</div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- 箭頭 -->
                    <div style="text-align: center; font-size: 1.5rem; color: var(--accent);">↓</div>
                    
                    <!-- 第四層：熱門商品 (淨買入) -->
                    <div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); text-align: center; margin-bottom: 0.5rem;">🔥 熱門商品 (淨買入 Top 5)</div>
                        <div style="display: flex; justify-content: center; gap: 0.4rem; flex-wrap: wrap;">
                            {% set all_tokens_list = [] %}
                            {% for chain_id, tokens in all_tokens.items() %}
                                {% for token in tokens %}
                                    {% if token.txns_diff > 0 %}
                                        {% set _ = all_tokens_list.append(token) %}
                                    {% endif %}
                                {% endfor %}
                            {% endfor %}
                            {% for token in (all_tokens_list|sort(attribute='pressure', reverse=true))[:5] %}
                            <a href="{{ token.url }}" target="_blank" style="padding: 0.35rem 0.6rem; background: rgba(249, 115, 22, 0.15); border-radius: 6px; font-size: 0.7rem; border: 1px solid rgba(249, 115, 22, 0.3); display: inline-flex; align-items: center; gap: 0.25rem;">
                                <span style="font-weight: 600;">{{ token.symbol }}</span>
                                <span class="positive" style="font-size: 0.65rem;">+{{ token.txns_diff }}</span>
                            </a>
                            {% endfor %}
                        </div>
                    </div>
                    
                </div>
                
                <!-- 解讀提示 -->
                <div style="margin-top: 1rem; padding: 0.75rem; background: rgba(255,255,255,0.03); border-radius: 8px; font-size: 0.75rem; color: var(--text-muted);">
                    💡 <strong>解讀：</strong>
                    {% if avg_native > 40 %}
                    資金主要持有原生幣 → 看好大盤趨勢
                    {% elif avg_stable > 45 %}
                    資金主要換成穩定幣 → 避險觀望中
                    {% elif avg_altcoin > 40 %}
                    資金主要投入個別幣 → Alpha 機會活躍
                    {% else %}
                    資金分佈均衡 → 市場處於盤整期
                    {% endif %}
                </div>
            </div>
        </div>

        {% if cex_data %}
        <div class="section">
            <h2 class="section-title">🏦 交易所 (CEX) 資產監控</h2>
            <div class="card"><div class="table-wrapper">
                <table>
                    <thead>
                        <tr>
                            <th>交易所</th>
                            <th>總資產 (TVL)</th>
                            <th>24H 變動</th>
                            <th>7D 變動</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for cex in cex_data[:5] %}
                        <tr>
                            <td style="display:flex; align-items:center;">
                                {% if cex.logo %}<img src="{{ cex.logo }}" style="width:20px; height:20px; margin-right:8px; border-radius:50%;">{% endif %}
                                {{ cex.name }}
                            </td>
                            <td>${{ "{:,.2f}".format(cex.tvl/1000000000) }}B</td>
                            <td class="{{ 'positive' if cex.change_1d > 0 else 'negative' }}">
                                {{ "%+.2f"|format(cex.change_1d) }}%
                            </td>
                            <td class="{{ 'positive' if cex.change_7d > 0 else 'negative' }}">
                                {{ "%+.2f"|format(cex.change_7d) }}%
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        {% endif %}

        {% if cross_flows %}
        <div class="section">
            <h2 class="section-title">🔄 鏈間資金流動</h2>
            <div class="card">
                {% for flow in cross_flows %}
                <div class="flow-item">
                    <span>{{ flow.from_chain }}</span>
                    <span class="negative">({{ "%.2f"|format(flow.from_change) }}%)</span>
                    <span class="flow-arrow">➡️</span>
                    <span>{{ flow.to_chain }}</span>
                    <span class="positive">(+{{ "%.2f"|format(flow.to_change) }}%)</span>
                </div>
                {% endfor %}
            </div>
        </div>
        {% endif %}

        <div class="section">
            <h2 class="section-title">📡 公鏈資金動能 (多時間框架分析)</h2>
            
            <!-- 總資金和佔比摘要 -->
            {% set total_tvl = chains|sum(attribute='tvl') %}
            <div class="card" style="margin-bottom: 1rem; background: linear-gradient(135deg, rgba(99, 102, 241, 0.1), rgba(168, 85, 247, 0.1));">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
                    <div>
                        <div style="font-size: 0.75rem; color: var(--text-muted);">公鏈總鎖倉量</div>
                        <div style="font-size: 1.5rem; font-weight: 700;">${{ "{:,.0f}".format(total_tvl / 1000000000) }}B</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 0.75rem; color: var(--text-muted);">監控公鏈數</div>
                        <div style="font-size: 1.5rem; font-weight: 700;">{{ chains|length }}</div>
                    </div>
                </div>
            </div>
            
            {% for chain in chains %}
            {% set tvl_share = (chain.tvl / total_tvl * 100) if total_tvl > 0 else 0 %}
            <div class="card chain-card">
                <div class="chain-header">
                    <span class="chain-name">🌐 {{ chain.chain_name }}</span>
                    {% if '暴衝' in chain.status %}
                    <span class="status-badge status-surge">{{ chain.status }}</span>
                    {% elif '加速' in chain.status %}
                    <span class="status-badge status-accel">{{ chain.status }}</span>
                    {% else %}
                    <span class="status-badge status-stable">{{ chain.status }}</span>
                    {% endif %}
                </div>
                <div class="metrics">
                    <span>💰 TVL: ${{ "{:,.0f}".format(chain.tvl / 1000000) }}M</span>
                    <span>📊 佔比: {{ "%.1f"|format(tvl_share) }}%</span>
                </div>
                <!-- 資金佔比進度條 -->
                <div class="tvl-share-bar">
                    <div class="tvl-share-fill" style="width: {{ tvl_share }}%;"></div>
                </div>
                
                <!-- 多時間框架分析 -->
                <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.5rem; margin: 1rem 0; padding: 0.75rem; background: rgba(255,255,255,0.03); border-radius: 8px;">
                    <div style="text-align: center;">
                        <div style="font-size: 0.7rem; color: var(--text-muted);">24H</div>
                        <div class="{{ 'positive' if chain.change_1d > 0 else 'negative' }}" style="font-weight: 600;">{{ "%+.2f"|format(chain.change_1d) }}%</div>
                    </div>
                    <div style="text-align: center;">
                        <div style="font-size: 0.7rem; color: var(--text-muted);">1週</div>
                        <div class="{{ 'positive' if chain.change_7d > 0 else 'negative' }}" style="font-weight: 600;">{{ "%+.2f"|format(chain.change_7d) }}%</div>
                    </div>
                    <div style="text-align: center;">
                        <div style="font-size: 0.7rem; color: var(--text-muted);">1月</div>
                        <div class="{{ 'positive' if chain.change_30d > 0 else 'negative' }}" style="font-weight: 600;">{{ "%+.2f"|format(chain.change_30d|default(0)) }}%</div>
                    </div>
                    <div style="text-align: center;">
                        <div style="font-size: 0.7rem; color: var(--text-muted);">3月</div>
                        <div class="{{ 'positive' if chain.change_90d > 0 else 'negative' }}" style="font-weight: 600;">{{ "%+.2f"|format(chain.change_90d|default(0)) }}%</div>
                    </div>
                </div>
                
                <!-- 趨勢判定 -->
                {% set c1d = chain.change_1d %}
                {% set c7d = chain.change_7d %}
                {% set c30d = chain.change_30d|default(0) %}
                {% if c1d > 0 and c7d > 0 and c30d > 0 %}
                <div style="padding: 0.5rem; background: rgba(34, 197, 94, 0.1); border-radius: 6px; margin-bottom: 1rem; font-size: 0.875rem;">
                    📈 <strong>短中長期多頭</strong> - 趨勢向上
                </div>
                {% elif c1d > 0 and c30d < 0 %}
                <div style="padding: 0.5rem; background: rgba(234, 179, 8, 0.1); border-radius: 6px; margin-bottom: 1rem; font-size: 0.875rem;">
                    🔄 <strong>短期反彈中</strong> - 觀察是否持續
                </div>
                {% elif c1d < 0 and c30d > 0 %}
                <div style="padding: 0.5rem; background: rgba(234, 179, 8, 0.1); border-radius: 6px; margin-bottom: 1rem; font-size: 0.875rem;">
                    📉 <strong>短期回調</strong> - 可能是買入機會
                </div>
                {% elif c1d < 0 and c7d < 0 and c30d < 0 %}
                <div style="padding: 0.5rem; background: rgba(239, 68, 68, 0.1); border-radius: 6px; margin-bottom: 1rem; font-size: 0.875rem;">
                    ⚠️ <strong>持續下跌</strong> - 需謹慎
                </div>
                {% else %}
                <div style="padding: 0.5rem; background: rgba(156, 163, 175, 0.1); border-radius: 6px; margin-bottom: 1rem; font-size: 0.875rem;">
                    ➖ <strong>盤整中</strong> - 等待方向
                </div>
                {% endif %}
                
                <!-- 🌡️ 深度市場分析 (寬度 & 敘事) -->
                {% if chain.search_id in all_flow_analysis and all_flow_analysis[chain.search_id].market_depth %}
                {% set depth = all_flow_analysis[chain.search_id].market_depth %}
                <div style="background: rgba(255,255,255,0.02); border-radius: 8px; padding: 0.75rem; margin-bottom: 1rem; border: 1px solid rgba(255,255,255,0.05);">
                    <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.5rem; display: flex; justify-content: space-between;">
                        <span>🌡️ 市場健康度</span>
                        <span style="font-weight: 600;">{{ depth.breadth_ratio }}% 上漲</span>
                    </div>
                    
                    <!-- 市場寬度條 -->
                    <div style="display: flex; height: 6px; border-radius: 3px; overflow: hidden; margin-bottom: 0.75rem;">
                        <div style="width: {{ depth.breadth_ratio }}%; background: var(--green);"></div>
                        <div style="width: {{ 100 - depth.breadth_ratio }}%; background: var(--red);"></div>
                    </div>
                    
                    <!-- 過熱/恐慌標籤 -->
                    <div style="display: flex; gap: 0.5rem; margin-bottom: 0.75rem;">
                        {% if depth.overheat_score == 'overheated' %}
                        <span style="padding: 0.2rem 0.6rem; background: rgba(239, 68, 68, 0.2); color: var(--red); border-radius: 4px; font-size: 0.75rem;">🔥 市場過熱 (風險高)</span>
                        {% elif depth.overheat_score == 'fear' %}
                        <span style="padding: 0.2rem 0.6rem; background: rgba(34, 197, 94, 0.2); color: var(--green); border-radius: 4px; font-size: 0.75rem;">🥶 極度恐慌 (機會?)</span>
                        {% else %}
                        <span style="padding: 0.2rem 0.6rem; background: rgba(255,255,255,0.1); color: var(--text-muted); border-radius: 4px; font-size: 0.75rem;">⚖️ 市場中性</span>
                        {% endif %}
                        
                        <span style="font-size: 0.75rem; color: var(--text-muted); margin-left: auto;">均買壓: {{ depth.avg_pressure }}x</span>
                    </div>
                    
                    <!-- 🎭 熱點敘事 -->
                    {% if depth.narratives %}
                    <div style="border-top: 1px solid rgba(255,255,255,0.05); padding-top: 0.75rem;">
                        <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.5rem;">🎭 資金熱炒題材 (Narratives)</div>
                        <div style="display: flex; flex-wrap: wrap; gap: 0.4rem;">
                            {% for word, count in depth.narratives %}
                            <span style="padding: 0.2rem 0.5rem; background: linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(168, 85, 247, 0.2)); border-radius: 12px; font-size: 0.75rem; border: 1px solid rgba(168, 85, 247, 0.3);">
                                #{{ word }} <span style="font-size: 0.65rem; opacity: 0.7;">({{ count }})</span>
                            </span>
                            {% endfor %}
                        </div>
                    </div>
                    {% endif %}
                </div>
                {% endif %}
                
                <!-- 資金流向分析 -->
                {% if chain.search_id in all_flow_analysis %}
                {% set flow = all_flow_analysis[chain.search_id] %}
                <div style="margin-bottom: 1rem;">
                    <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.5rem;">📊 資金流向分佈 (24H交易量)</div>
                    <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                        {% for cat, data in flow.breakdown.items() %}
                        {% if data.volume_pct > 0 %}
                        {% set net_flow = data.net_flow_count|default(0) %}
                        {% set flow_color = 'var(--green)' if net_flow > 0 else ('var(--red)' if net_flow < 0 else 'inherit') %}
                        {% set flow_text = '流入' if net_flow > 0 else ('流出' if net_flow < 0 else '') %}
                        <span style="padding: 0.25rem 0.5rem; background: {{ 'rgba(34, 197, 94, 0.2)' if cat == flow.dominant_flow else 'rgba(255,255,255,0.05)' }}; border-radius: 4px; font-size: 0.75rem;">
                            {% if cat == 'native' %}🔷 原生幣{% elif cat == 'stablecoin' %}💵 穩定幣{% elif cat == 'btc' %}🟡 BTC{% else %}🚀 Altcoin{% endif %}
                            {{ "%.1f"|format(data.volume_pct) }}%
                            {% if flow_text %}
                            <span style="color: {{ flow_color }}; font-weight: bold; margin-left: 2px;">{{ flow_text }}</span>
                            {% endif %}
                        </span>
                        {% endif %}
                        {% endfor %}
                    </div>
                    {% set alt_data = flow.breakdown.get('altcoin', {}) %}
                    {% set alt_flow = alt_data.net_flow_count|default(0) %}
                    
                    {% if flow.dominant_flow == 'altcoin' and flow.dominant_pct > 30 %}
                        {% if alt_flow > 0 %}
                        <div style="margin-top: 0.5rem; font-size: 0.8rem; color: var(--green);">🎯 Alpha 機會！資金主要流向個別代幣 (淨買入)</div>
                        {% elif alt_flow < 0 %}
                        <div style="margin-top: 0.5rem; font-size: 0.8rem; color: var(--red);">⚠️ 警告！個別代幣主要為拋售流出</div>
                        {% endif %}
                    {% elif flow.dominant_flow == 'stablecoin' and flow.dominant_pct > 40 %}
                    <div style="margin-top: 0.5rem; font-size: 0.8rem; color: var(--orange);">⚠️ 避險情緒，資金流向穩定幣</div>
                    {% endif %}
                </div>
                {% endif %}
                
                <!-- 🐋 鯨魚吸籌代幣 (穩健長線) -->
                {% if chain.search_id in all_flow_analysis and all_flow_analysis[chain.search_id].accumulating_tokens %}
                <div style="background: rgba(99, 102, 241, 0.05); border: 1px solid rgba(99, 102, 241, 0.1); border-radius: 8px; padding: 1rem; margin-bottom: 1rem;">
                    <div style="font-size: 0.9rem; font-weight: 600; color: var(--accent); margin-bottom: 0.75rem;">🐋 鯨魚潛伏 (穩健累積)</div>
                    <table>
                        <thead>
                            <tr>
                                <th>代幣</th>
                                <th>24H漲幅</th>
                                <th>流動性</th>
                                <th>交易量</th>
                                <th>累積方式</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for token in all_flow_analysis[chain.search_id].accumulating_tokens %}
                            <tr>
                                <td><a href="{{ token.url }}" target="_blank">{{ token.symbol }}</a></td>
                                <td class="positive">+{{ "%.2f"|format(token.change_24h) }}%</td>
                                <td>${{ "{:,.0f}".format(token.liquidity) }}</td>
                                <td>${{ "{:,.0f}".format(token.volume) }}</td>
                                <td style="font-size: 0.75rem; color: var(--text-muted);">{{ token.accumulation_reason|default('N/A') }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% endif %}
                
                {% if chain.search_id in all_tokens %}
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>代幣</th>
                                <th>價格</th>
                                <th>24H</th>
                                <th class="hide-mobile">交易量</th>
                                <th>流向</th>
                                <th>狀態/買壓</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for token in all_tokens[chain.search_id] %}
                            <tr>
                                <td><a href="{{ token.url }}" target="_blank">{{ token.symbol }}</a></td>
                                <td>{{ token.price }}</td>
                                <td class="{{ 'positive' if token.change_24h > 0 else 'negative' }}">{{ "%.2f"|format(token.change_24h) }}%</td>
                                <td class="hide-mobile">${{ "{:,.0f}".format(token.volume) }}</td>
                                <td>
                                    {% if '流入' in token.net_flow %}
                                        <span class="positive" style="font-weight:bold;">流入 🟢</span>
                                    {% else %}
                                        <span class="negative" style="font-weight:bold;">流出 🔴</span>
                                    {% endif %}
                                </td>
                                <td>
                                    {% if '🚀' in token.status %}
                                        <span class="status-badge status-surge glow-text">{{ token.status }}</span>
                                    {% elif '🧐' in token.status %}
                                        <span class="status-badge status-accel" style="background: rgba(168, 85, 247, 0.2); color: #a855f7;">{{ token.status }}</span>
                                    {% elif '⚠️' in token.status %}
                                        <span class="status-badge" style="background: rgba(239, 68, 68, 0.2); color: var(--red);">{{ token.status }}</span>
                                    {% else %}
                                        <span style="font-size: 0.75rem;">{{ "%.2f"|format(token.pressure) }}x</span>
                                    {% endif %}
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% endif %}
            </div>
            {% endfor %}
        </div>

        {% if new_tokens %}
        <div class="section">
            <h2 class="section-title">🆕 新幣首發偵測</h2>
            <div class="new-token-grid">
                {% for token in new_tokens[:10] %}
                <div class="new-token-card">
                    <a href="{{ token.url }}" target="_blank"><strong>{{ token.symbol }}</strong></a>
                    <div style="color: var(--text-muted); font-size: 0.875rem; margin-top: 0.5rem;">
                        <div>鏈: {{ token.chain }}</div>
                        <div>流動性: ${{ "{:,.0f}".format(token.liquidity) }}</div>
                        <div>上線: {{ token.age_hours }}h</div>
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
        {% endif %}

        {% if long_term_tokens %}
        <div class="section">
            <h2 class="section-title">🌳 長線價值發現 (90天流動性成長 > 20%)</h2>
            <div class="new-token-grid">
                {% for token in long_term_tokens[:10] %}
                <div class="new-token-card" style="border-color: rgba(34, 197, 94, 0.3); background: rgba(34, 197, 94, 0.05);">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <strong>{{ token.symbol }}</strong>
                        <span class="status-badge" style="background:rgba(34, 197, 94, 0.2); color:#4ade80;">+{{ token.liquidity_growth_pct }}%</span>
                    </div>
                    <div style="color: var(--text-muted); font-size: 0.85rem; margin-top: 0.75rem;">
                        <div>鏈: {{ token.chain_id }}</div>
                        <div>流動性: ${{ "{:,.0f}".format(token.max_liquidity) }}</div>
                        <div style="font-size: 0.75rem; margin-top: 0.25rem;">追蹤: {{ token.first_seen }} 起</div>
                        <div style="font-size: 0.75rem;">出現: {{ token.appearances }} 次</div>
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
        {% endif %}
    </div>
</body>
</html>
    '''
    
    template = Template(html_template)
    html_content = template.render(
        timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        stats=stats,
        chains=chains,
        all_tokens=all_tokens,
        all_flow_analysis=all_flow_analysis,
        new_tokens=new_tokens,
        long_term_tokens=long_term_tokens,
        cross_flows=cross_flows,
        cex_data=cex_data,
          # 修復: 傳遞 Binance 宏觀數據
    )
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    # ==== 新增：同時生成 latest.html (用於 Discord 固定連結) ====
    latest_filename = REPORT_DIR / "latest.html"
    with open(latest_filename, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    logger.info(f"📄 HTML 報告已匯出: {filename} (及 latest.html)")
    
    # 返回 latest.html 的路徑給 Discord 使用，確保連結始終指向最新
    return latest_filename

# ================= 6. 終端機報告模組 (Terminal Report) =================

def print_terminal_report(chains, all_tokens, all_flow_analysis, new_tokens, cross_flows, cex_data, stats):
    """列印終端機報告 (含資金流向分析 + CEX 監控 + 輪動週期)"""
    from tabulate import tabulate
    
    print(f"\n{Fore.YELLOW}{'═'*70}")
    print(f"{Fore.YELLOW} 📡 全鏈資金流向深度分析報告 v3.0 (經濟週期分析版)")
    print(f"{Fore.YELLOW} 🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{Fore.YELLOW}{'═'*70}\n")
    
    # 統計摘要
    print(f"{Fore.CYAN}📊 分析摘要:")
    print(f"   ├─ 掃描公鏈: {stats['chains_scanned']} 條")
    print(f"   ├─ CEX 監控: {len(cex_data)} 家")
    print(f"   ├─ 推薦代幣: {stats['tokens_found']} 個")
    print(f"   ├─ 新幣偵測: {stats['new_tokens']} 個")
    print(f"   ├─ 長線潛力: {stats.get('long_term_tokens', 0)} 個")
    print(f"   ├─ 系統準確率: {stats['accuracy']:.1f}%")
    print(f"   └─ 執行耗時: {stats['execution_time']:.2f} 秒\n")
    
    # ==== 新增：期貨資金費率 + 穩定幣流通量 ====
    market_indicators = stats.get('market_indicators', {})
    if market_indicators:
        funding = market_indicators.get('funding', {})
        stables = market_indicators.get('stablecoins', {})
        
        print(f"{Fore.YELLOW}📈 市場輔助指標:{Style.RESET_ALL}")
        
        # 期貨資金費率
        if funding.get('btc', {}).get('rate', 0) != 0 or funding.get('eth', {}).get('rate', 0) != 0:
            btc_rate = funding.get('btc', {}).get('rate', 0)
            eth_rate = funding.get('eth', {}).get('rate', 0)
            btc_interp = funding.get('btc', {}).get('interpretation', '')
            eth_interp = funding.get('eth', {}).get('interpretation', '')
            
            btc_color = Fore.GREEN if btc_rate < 0.02 else (Fore.RED if btc_rate > 0.03 else Fore.YELLOW)
            eth_color = Fore.GREEN if eth_rate < 0.02 else (Fore.RED if eth_rate > 0.03 else Fore.YELLOW)
            
            print(f"   📊 期貨資金費率 (Funding Rate):")
            print(f"      BTC: {btc_color}{btc_rate:.4f}%{Style.RESET_ALL} - {btc_interp}")
            print(f"      ETH: {eth_color}{eth_rate:.4f}%{Style.RESET_ALL} - {eth_interp}")
        
        # 穩定幣流通量
        if stables.get('total_supply', 0) > 0:
            total_supply = stables.get('total_supply', 0)
            change_7d = stables.get('change_7d', 0)
            interp = stables.get('interpretation', '')
            
            supply_color = Fore.GREEN if change_7d > 0 else Fore.RED
            
            print(f"   💵 穩定幣流通量:")
            print(f"      總量: ${total_supply/1e9:.1f}B ({supply_color}7D: {change_7d:+.2f}%{Style.RESET_ALL})")
            print(f"      {interp}")
            
            # 顯示前 3 大穩定幣
            top_stables = stables.get('top_stables', [])[:3]
            if top_stables:
                stable_str = " | ".join([f"{s['symbol']} ${s['supply']/1e9:.1f}B" for s in top_stables])
                print(f"      Top 3: {stable_str}")
        
        print()
    
    # ==== 🔄 新增：跨鏈原生幣強弱對比 (國際匯率) ====
    native_strength = analyze_cross_chain_native_strength(all_flow_analysis, chains)
    if native_strength:
        print(f"{Fore.CYAN}🌐 跨鏈原生幣強弱對比 (國家貨幣匯率):{Style.RESET_ALL}")
        strength_table = []
        for ns in native_strength[:8]:
            score_color = Fore.GREEN if ns['strength_score'] >= 55 else (Fore.RED if ns['strength_score'] < 45 else Fore.YELLOW)
            c24h_color = Fore.GREEN if ns['change_24h'] > 0 else Fore.RED
            tvl_color = Fore.GREEN if ns['tvl_change'] > 0 else Fore.RED
            
            strength_table.append([
                ns['native_symbol'],
                ns['chain'],
                f"{score_color}{ns['strength_score']:.0f} {ns['strength_label']}{Style.RESET_ALL}",
                f"{c24h_color}{ns['change_24h']:+.2f}%{Style.RESET_ALL}",
                f"{tvl_color}{ns['tvl_change']:+.2f}%{Style.RESET_ALL}",
                f"{ns['buy_sell_ratio']:.2f}"
            ])
        
        print(tabulate(strength_table, 
                       headers=["貨幣", "公鏈", "強弱度", "24H價格", "TVL變動", "買賣比"],
                       tablefmt="simple"))
        
        # 強弱解讀
        if native_strength[0]['strength_score'] - native_strength[-1]['strength_score'] > 30:
            strongest = native_strength[0]
            weakest = native_strength[-1]
            print(f"\n   💡 資金流向: {Fore.GREEN}{strongest['native_symbol']}{Style.RESET_ALL} 最強, "
                  f"{Fore.RED}{weakest['native_symbol']}{Style.RESET_ALL} 最弱")
            print(f"   ➡️  建議關注 {strongest['chain']} 生態的機會")
        print()
    
    # ==== 🔄 新增：輪動週期總體判斷 ====
    # 聚合所有鏈的資金流向
    total_native_pct = 0
    total_stable_pct = 0
    total_altcoin_pct = 0
    chain_count = 0
    
    for chain_id, flow in all_flow_analysis.items():
        if flow and 'breakdown' in flow:
            breakdown = flow['breakdown']
            total_native_pct += breakdown.get('native', {}).get('volume_pct', 0)
            total_stable_pct += breakdown.get('stablecoin', {}).get('volume_pct', 0)
            total_altcoin_pct += breakdown.get('altcoin', {}).get('volume_pct', 0)
            chain_count += 1
    
    if chain_count > 0:
        avg_flow = {
            'breakdown': {
                'native': {'volume_pct': total_native_pct / chain_count},
                'stablecoin': {'volume_pct': total_stable_pct / chain_count},
                'altcoin': {'volume_pct': total_altcoin_pct / chain_count}
            },
            'market_sentiment': {'buy_sell_ratio': 1.0, 'bullish_pct': 50}  # 預設值
        }
        
        rotation = analyze_rotation_cycle(avg_flow)
        
        print(f"{Fore.MAGENTA}{'━'*70}")
        print(f"🔄 全市場輪動週期分析 (經濟週期階段):{Style.RESET_ALL}")
        print(f"   ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓")
        print(f"   ┃  📍 當前階段: {rotation['cycle_phase']:<30}┃")
        print(f"   ┃  💡 操作建議: {rotation['cycle_signal']:<30}┃")
        print(f"   ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛")
        print(f"   資金佔比: 原生幣 {rotation['native_pct']:.1f}% | 穩定幣 {rotation['stable_pct']:.1f}% | Altcoin {rotation['altcoin_pct']:.1f}%")
        print(f"{Fore.MAGENTA}{'━'*70}{Style.RESET_ALL}\n")
    
    # 鏈間資金流動
    if cross_flows:
        print(f"{Fore.MAGENTA}🔄 偵測到鏈間資金遷移:")
        for flow in cross_flows[:3]:
            print(f"   {flow['from_chain']} ({Fore.RED}{flow['from_change']:+.2f}%{Style.RESET_ALL}) "
                  f"➡️ {flow['to_chain']} ({Fore.GREEN}{flow['to_change']:+.2f}%{Style.RESET_ALL})")
        print()
    # CEX 監控報告
    if cex_data:
        print(f"{Fore.BLUE}🏦 交易所 (CEX) 資產監控:{Style.RESET_ALL}")
        cex_table = []
        for cex in cex_data[:5]:
            c1d_color = Fore.GREEN if cex['change_1d'] > 0 else Fore.RED
            c7d_color = Fore.GREEN if cex['change_7d'] > 0 else Fore.RED
            
            # 判斷資金流向
            flow_status = "內流 🟢" if cex['change_1d'] > 0.5 else ("外流 🔴" if cex['change_1d'] < -0.5 else "持平 ⚪")
            
            cex_table.append([
                cex['name'],
                f"${cex['tvl']/1e9:.2f}B",
                f"{c1d_color}{cex['change_1d']:+.2f}%{Style.RESET_ALL}",
                f"{c7d_color}{cex['change_7d']:+.2f}%{Style.RESET_ALL}",
                flow_status
            ])
            
        print(tabulate(cex_table, headers=["交易所", "總資產", "24H變動", "7D變動", "資金狀態"], tablefmt="simple"))
        
        # 宏觀解讀
        total_cex_change = sum(c['change_1d'] for c in cex_data) / len(cex_data)
        if total_cex_change > 1.0:
            print(f"   💡 宏觀解讀: CEX 資產整體增加 ({total_cex_change:+.1f}%)，可能有資金場外入場")
        elif total_cex_change < -1.0:
            print(f"   💡 宏觀解讀: CEX 資產整體減少 ({total_cex_change:+.1f}%)，可能有提幣上鏈行為")
        print()

    # 資金流向類別名稱
    FLOW_NAMES = {
        'native': '🔷 原生幣 (ETH/SOL等)',
        'stablecoin': '💵 穩定幣 (USDT/USDC)',
        'btc': '🟡 BTC 相關',
        'altcoin': '🚀 個別代幣 (Altcoin)'
    }
    
    # 公鏈詳情
    for chain in chains:
        status_color = Fore.YELLOW if "暴衝" in chain['status'] else Fore.GREEN
        print(f"{status_color}🌐 {chain['chain_name']} ({chain['status']})")
        print(f"   ├─ TVL: ${chain['tvl']:,.0f}")
        
        # 多時間框架分析 (24H / 1週 / 1個月 / 3個月)
        c1d = chain['change_1d']
        c7d = chain['change_7d']
        c30d = chain.get('change_30d', 0)
        c90d = chain.get('change_90d', 0)
        
        # 顏色標記
        c1d_color = Fore.GREEN if c1d > 0 else Fore.RED
        c7d_color = Fore.GREEN if c7d > 0 else Fore.RED
        c30d_color = Fore.GREEN if c30d > 0 else Fore.RED
        c90d_color = Fore.GREEN if c90d > 0 else Fore.RED
        
        print(f"   ├─ {c1d_color}24H: {c1d:+.2f}%{Style.RESET_ALL}  |  {c7d_color}1週: {c7d:+.2f}%{Style.RESET_ALL}  |  {c30d_color}1月: {c30d:+.2f}%{Style.RESET_ALL}  |  {c90d_color}3月: {c90d:+.2f}%{Style.RESET_ALL}")
        
        # 趨勢判定
        if c1d > 0 and c7d > 0 and c30d > 0:
            trend = f"{Fore.GREEN}📈 短中長期多頭{Style.RESET_ALL}"
        elif c1d > 0 and c30d < 0:
            trend = f"{Fore.CYAN}🔄 短期反彈中{Style.RESET_ALL}"
        elif c1d < 0 and c30d > 0:
            trend = f"{Fore.YELLOW}📉 短期回調{Style.RESET_ALL}"
        elif c1d < 0 and c7d < 0 and c30d < 0:
            trend = f"{Fore.RED}⚠️ 持續下跌{Style.RESET_ALL}"
        else:
            trend = f"{Fore.WHITE}➖ 盤整中{Style.RESET_ALL}"
        
        print(f"   └─ 趨勢: {trend}")
        
        # 顯示資金流向分析
        flow_analysis = all_flow_analysis.get(chain['search_id'])
        if flow_analysis:
            print(f"\n   {Fore.MAGENTA}📊 資金流向分析 (24H 交易量佔比):{Style.RESET_ALL}")
            
            breakdown = flow_analysis.get('breakdown', {})
            dominant = flow_analysis.get('dominant_flow', '')
            
            for category in ['native', 'stablecoin', 'btc', 'altcoin']:
                if category in breakdown:
                    data = breakdown[category]
                    vol_pct = data['volume_pct']
                    
                    # 選擇顏色和標記
                    if category == dominant:
                        marker = "▶"
                        color = Fore.GREEN
                    else:
                        marker = " "
                        color = Style.RESET_ALL
                    
                    # 進度條
                    bar_len = int(vol_pct / 5)
                    bar = "█" * bar_len + "░" * (20 - bar_len)
                    
                    # 顯示代幣列表
                    top_tokens = data.get('top_tokens', [])[:3]
                    tokens_str = ", ".join(top_tokens) if top_tokens else "-"
                    
                    # 判斷方向
                    net_flow = data.get('net_flow_count', 0)
                    if net_flow > 0:
                        dir_arrow = f" {Fore.GREEN}(流入 🟢){Style.RESET_ALL}"
                    elif net_flow < 0:
                        dir_arrow = f" {Fore.RED}(流出 🔴){Style.RESET_ALL}"
                    else:
                        dir_arrow = ""
                    
                    print(f"   {marker} {color}{FLOW_NAMES.get(category, category):<25} {bar} {vol_pct:>5.1f}%{dir_arrow}{Style.RESET_ALL}")
            
            # 主要資金流向提示
            dominant_pct = flow_analysis.get('dominant_pct', 0)
            if dominant == 'altcoin' and dominant_pct > 30:
                print(f"\n   {Fore.GREEN}💡 觀察: 資金主要流向個別代幣 ({dominant_pct:.1f}%)，關注 Alpha 機會！{Style.RESET_ALL}")
            elif dominant == 'native' and dominant_pct > 50:
                print(f"\n   {Fore.CYAN}💡 觀察: 資金主要流向原生幣 ({dominant_pct:.1f}%)，大盤行情主導{Style.RESET_ALL}")
            elif dominant == 'stablecoin' and dominant_pct > 40:
                print(f"\n   {Fore.YELLOW}⚠️ 警告: 資金主要流向穩定幣 ({dominant_pct:.1f}%)，可能是避險情緒{Style.RESET_ALL}")
        
        tokens = all_tokens.get(chain['search_id'], [])
        if tokens:
            print(f"   {Fore.CYAN}🔍 熱錢流向 Top 5:")
            
            table_data = []
            for token in tokens:
                change_color = Fore.GREEN if token['change_24h'] > 0 else Fore.RED
                pressure_warn = " ⚠️" if token['pressure'] > BUYING_PRESSURE_ALERT else ""
                
                net_flow = token.get('net_flow', 'N/A')
                flow_color = Fore.GREEN if '流入' in net_flow else (Fore.RED if '流出' in net_flow else Fore.WHITE)
                
                table_data.append([
                    token['symbol'],
                    f"{change_color}{token['change_24h']:+.1f}%{Style.RESET_ALL}",
                    f"${token['volume']:,.0f}",
                    f"{token['pressure']:.2f}{pressure_warn}",
                    f"{flow_color}{net_flow}{Style.RESET_ALL}",
                    token['price']
                ])
            
            print(tabulate(table_data,
                          headers=["代幣", "24H", "交易量", "買壓係數", "資金流向", "價格"],
                          tablefmt="simple"))
            print(f"   👉 {tokens[0]['url']}")
        else:
            print(f"   ⚠️ 資金主要流入穩定幣或主流幣")
            
        # 顯示鯨魚潛伏 (穩健累積)
        if flow_analysis and flow_analysis.get('accumulating_tokens'):
            print(f"\n   {Fore.BLUE}🐋 鯨魚潛伏 (穩健累積):{Style.RESET_ALL}")
            acc_tokens = flow_analysis['accumulating_tokens']
            # 準備表格數據，包含累積原因
            acc_table_data = []
            for t in acc_tokens[:5]:
                reason = t.get('accumulation_reason', 'N/A')
                acc_table_data.append([
                    t['symbol'], 
                    f"{Fore.GREEN}{t['change_24h']:+.1f}%{Style.RESET_ALL}", 
                    f"${t['liquidity']:,.0f}", 
                    reason
                ])
            
            print(tabulate(acc_table_data, 
                           headers=["代幣", "24H漲幅", "流動性", "累積判斷"], 
                           tablefmt="simple"))
        
        # ==== 🔷 新增：原生幣熱門交易對 ====
        if flow_analysis and flow_analysis.get('native_pairs'):
            print(f"\n   {Fore.CYAN}🔷 原生幣熱門交易對:{Style.RESET_ALL}")
            native_table = []
            for np in flow_analysis['native_pairs'][:3]:
                accel_color = Fore.GREEN if np['momentum_accel'] > 1 else Fore.RED
                native_table.append([
                    f"{np['symbol']}/{np['quote']}",
                    np['price'],
                    f"{Fore.GREEN if np['change_1h'] > 0 else Fore.RED}{np['change_1h']:+.1f}%{Style.RESET_ALL}",
                    f"${np['volume_24h']:,.0f}",
                    f"{accel_color}{np['momentum_accel']}x{Style.RESET_ALL}",
                    np['net_flow']
                ])
            print(tabulate(native_table, 
                           headers=["交易對", "價格", "1H漲跌", "24H交易量", "動能", "買賣"],
                           tablefmt="simple"))
        
        # ==== 📊 新增：市場情緒 ====
        if flow_analysis and flow_analysis.get('market_sentiment'):
            ms = flow_analysis['market_sentiment']
            print(f"\n   {Fore.YELLOW}📊 市場情緒: {ms['sentiment']}{Style.RESET_ALL}")
            print(f"      買賣比: {ms['buy_sell_ratio']:.2f} | 上漲幣種佔比: {ms['bullish_pct']:.1f}%")
        
        # ==== ⚡ 新增：動能加速代幣 (短期爆發機會) ====
        if flow_analysis and flow_analysis.get('momentum_tokens'):
            print(f"\n   {Fore.MAGENTA}⚡ 動能加速 (短期爆發):{Style.RESET_ALL}")
            mom_table = []
            for mt in flow_analysis['momentum_tokens'][:3]:
                mom_table.append([
                    mt['symbol'],
                    mt['alert'],
                    f"{mt['momentum_accel']}x",
                    f"{Fore.GREEN if mt['change_1h'] > 0 else Fore.RED}{mt['change_1h']:+.1f}%{Style.RESET_ALL}",
                    f"${mt['volume_1h']:,.0f}",
                    f"${mt['liquidity']:,.0f}"
                ])
            print(tabulate(mom_table,
                           headers=["代幣", "狀態", "加速度", "1H漲跌", "1H交易量", "流動性"],
                           tablefmt="simple"))
        
        print(f"\n{'-'*70}\n")
    
    # 新幣偵測
    if new_tokens:
        print(f"{Fore.MAGENTA}🆕 新幣首發偵測 (流動性 > $50K):")
        for token in new_tokens[:5]:
            age_str = f"{token['age_hours']}h" if token['age_hours'] < 24 else f"{token['age_hours']//24}d"
            print(f"   • {token['symbol']} ({token['chain']}) - ${token['liquidity']:,.0f} - 上線 {age_str}")
            print(f"     {token['url']}")
        print()
    
    # 長線成長代幣 (從資料庫歷史追蹤)
    long_term_tokens = get_long_term_growth_tokens()
    if long_term_tokens:
        print(f"{Fore.CYAN}📈 長線潛力股 (3個月流動性成長):")
        for token in long_term_tokens[:5]:
            growth_color = Fore.GREEN if token['liquidity_growth_pct'] > 50 else Fore.YELLOW
            print(f"   • {token['symbol']} ({token['chain_id']}) - "
                  f"{growth_color}+{token['liquidity_growth_pct']:.1f}%{Style.RESET_ALL} 流動性成長")
            print(f"     首次記錄: {token['first_seen']} | 最新記錄: {token['last_seen']} | 出現次數: {token['appearances']}")
        print()
        print(f"   💡 提示: 這些代幣在過去 3 個月內流動性持續增加，可能有機構在累積{Style.RESET_ALL}")
        print()

# ================= 7. 主程式 (Main) =================

async def run_analysis():
    """執行完整分析流程"""
    start_time = time.time()
    
    # 初始化資料庫
    init_database()
    
    async with aiohttp.ClientSession() as session:
        # 1. 獲取公鏈動能
        result = await get_chain_momentum_async(session)
        if not result:
            logger.error("❌ 無法獲取公鏈數據")
            fail_embed = {
                "title": "⚠️ 分析中斷：無法獲取公鏈數據",
                "description": "DefiLlama API 請求失敗或無回應。請檢查 GitHub Actions 日誌詳情。",
                "color": 0xEF4444,
                "timestamp": datetime.utcnow().isoformat()
            }
            await send_discord_notification(session, fail_embed)
            return
        
        active_chains, outflow_chains = result
        
        if not active_chains:
            logger.info(f"目前沒有偵測到顯著資金流入的公鏈 (閾值: {MOMENTUM_THRESHOLD}%)")
            empty_embed = {
                "title": "📊 監控報告：目前市場平淡",
                "description": f"本輪掃描未偵測到變動超過 {MOMENTUM_THRESHOLD}% 的活躍公鏈。\n\n系統將持續監控。",
                "color": 0x9CA3AF,
                "timestamp": datetime.utcnow().isoformat()
            }
            await send_discord_notification(session, empty_embed)
            return
        
        # 儲存公鏈數據
        save_chain_data(active_chains)
        
        # 2. 並行分析所有鏈上資產 (包含資金流向分析)
        logger.info(f"⚡ 正在並行分析 {len(active_chains)} 條鏈上資產及資金流向...")
        tasks = [analyze_assets_async(session, chain['search_id']) for chain in active_chains]
        results = await asyncio.gather(*tasks)
        
        all_tokens = {}  # chain_id -> [tokens]
        all_flow_analysis = {}  # chain_id -> flow_analysis
        total_tokens = 0
        
        for chain, (tokens, flow_analysis) in zip(active_chains, results):
            if tokens:
                all_tokens[chain['search_id']] = tokens
                
                # 合併與儲存 (包含熱門代幣 + 吸籌代幣)
                tokens_to_save = tokens.copy()
                if flow_analysis and flow_analysis.get('accumulating_tokens'):
                    existing_symbols = {t['symbol'] for t in tokens_to_save}
                    for acc_t in flow_analysis['accumulating_tokens']:
                        if acc_t['symbol'] not in existing_symbols:
                            tokens_to_save.append(acc_t)
                            
                save_token_data(chain['search_id'], tokens_to_save)
                total_tokens += len(tokens)
            if flow_analysis:
                all_flow_analysis[chain['search_id']] = flow_analysis
        
        # 3. 新幣偵測
        new_tokens = await get_trending_tokens_async(session)
        
        # 4. 獲取 CEX 數據 (新增) & 宏觀市場情緒
        cex_data = await get_cex_data_async(session)
        
        # 4.5 獲取市場輔助指標 (期貨資金費率 + 穩定幣流通量)
        market_indicators = await get_market_indicators_async(session)
        
        # 5. 鏈間資金流動分析
        cross_flows = await detect_cross_chain_flows(active_chains, outflow_chains)
        
        # 5. 計算統計
        accuracy_data = calculate_system_accuracy()
        long_term_tokens = get_long_term_growth_tokens()  # 長線成長追蹤
        execution_time = time.time() - start_time
        next_scan = (datetime.now() + timedelta(seconds=SCHEDULE_INTERVAL)).strftime('%H:%M:%S') if SCHEDULE_INTERVAL > 0 else "N/A"
        
        stats = {
            'chains_scanned': len(active_chains),
            'tokens_found': total_tokens,
            'new_tokens': len(new_tokens),
            'long_term_tokens': len(long_term_tokens),  # 長線潛力幣數量
            'anomalies': 0,  # TODO: 實作異常偵測計數
            'accuracy': accuracy_data['accuracy'],
            'execution_time': execution_time,
            'next_scan': next_scan,
            'market_indicators': market_indicators  # 期貨資金費率 + 穩定幣流通量
        }
        
        # 6. 終端機報告
        print_terminal_report(active_chains, all_tokens, all_flow_analysis, new_tokens, cross_flows, cex_data, stats)
        
        # 7. 匯出報告
        export_to_csv(active_chains, all_tokens)
        export_to_json(active_chains, all_tokens, new_tokens, cross_flows)
        html_file = export_to_html(active_chains, all_tokens, all_flow_analysis, new_tokens, long_term_tokens, cross_flows, cex_data, stats)
        
        # 讀取完整報告 HTML 內容以供嵌入
        full_report_content = ""
        try:
            with open(html_file, 'r', encoding='utf-8') as f:
                full_report_content = f.read()
        except Exception as e:
            logger.error(f"讀取完整報告失敗: {e}")

        # 7.5 生成資金流向主控台報告 (新增)
        try:
            from capital_flow_dashboard import (
                run_command_center_analysis,
                print_command_center_terminal,
                identify_whale_accumulation_targets,
                generate_cex_dex_summary,
                analyze_cex_flows,
                CapitalFlowSummary,
                CEXDEXSummary
            )
            
            command_center_summary, command_center_html = await run_command_center_analysis(
                active_chains, all_tokens, all_flow_analysis, cex_data, market_indicators,
                full_report_html=full_report_content
            )
            
            # 生成 CEX+DEX 整合數據
            cex_dex_summary = None
            if cex_data:
                cex_dex_summary = generate_cex_dex_summary(active_chains, cex_data, all_flow_analysis)
            
            # 儲存主控台報告 (現在是已整合的版本)
            dashboard_file = REPORT_DIR / f"dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            with open(dashboard_file, 'w', encoding='utf-8') as f:
                f.write(command_center_html)
            
            # 同時更新 latest_dashboard.html
            latest_dashboard = REPORT_DIR / "latest_dashboard.html"
            with open(latest_dashboard, 'w', encoding='utf-8') as f:
                f.write(command_center_html)
            
            logger.info(f"🎛️ 資金流向主控台報告已生成: {dashboard_file}")
            
            # 輸出主控台摘要 (含 CEX+DEX)
            whale_targets = identify_whale_accumulation_targets(all_flow_analysis)
            print_command_center_terminal(command_center_summary, whale_targets, cex_dex_summary)
            
            # 添加主控台連結和 CEX+DEX 數據到 stats
            stats['dashboard_file'] = str(latest_dashboard)
            stats['trading_signal'] = command_center_summary.trading_signal.value
            stats['market_phase'] = command_center_summary.market_phase.value
            
            if cex_dex_summary:
                stats['cex_dex_total_tvl'] = cex_dex_summary.total_market_tvl
                stats['cex_share_pct'] = cex_dex_summary.cex_share_pct
                stats['dex_share_pct'] = cex_dex_summary.dex_share_pct
                stats['capital_direction'] = cex_dex_summary.capital_direction
            
        except ImportError as e:
            logger.warning(f"⚠️ 無法載入資金流向主控台模組: {e}")
        except Exception as e:
            logger.error(f"❌ 資金流向主控台分析失敗: {e}")
        
        # 8. Discord 通知 (精簡版 - 避免洗版)
        logger.info("📤 正在發送 Discord 精簡通知...")
        
        # 添加 schedule_interval 到 stats
        stats['schedule_interval'] = SCHEDULE_INTERVAL
        stats['html_file'] = str(html_file)
        
        # ==== 只發送 1 個整合摘要通知 ====
        # 計算輪動週期
        total_native_pct = 0
        total_stable_pct = 0
        total_altcoin_pct = 0
        chain_count = 0
        
        for chain_id, flow in all_flow_analysis.items():
            if flow and 'breakdown' in flow:
                breakdown = flow['breakdown']
                total_native_pct += breakdown.get('native', {}).get('volume_pct', 0)
                total_stable_pct += breakdown.get('stablecoin', {}).get('volume_pct', 0)
                total_altcoin_pct += breakdown.get('altcoin', {}).get('volume_pct', 0)
                chain_count += 1
        
        rotation_info = None
        if chain_count > 0:
            avg_flow = {
                'breakdown': {
                    'native': {'volume_pct': total_native_pct / chain_count},
                    'stablecoin': {'volume_pct': total_stable_pct / chain_count},
                    'altcoin': {'volume_pct': total_altcoin_pct / chain_count}
                },
                'market_sentiment': {'buy_sell_ratio': 1.0, 'bullish_pct': 50}
            }
            rotation_info = analyze_rotation_cycle(avg_flow)
        
        # 計算跨鏈原生幣強弱
        native_strength = analyze_cross_chain_native_strength(all_flow_analysis, active_chains)
        
        # 發送整合摘要 (單一通知)
        integrated_embed = create_integrated_summary_embed(
            stats, active_chains, all_tokens, cex_data, 
            rotation_info, native_strength, new_tokens, cross_flows
        )
        await send_discord_notification(session, integrated_embed)
        
        logger.info(f"✅ 分析完成！耗時 {execution_time:.2f} 秒，已發送 Discord 精簡通知 (詳細報告見 HTML)")

async def scheduled_run():
    """定時執行"""
    while True:
        try:
            await run_analysis()
        except Exception as e:
            logger.error(f"❌ 執行錯誤: {e}")
            # 嘗試發送崩潰通知
            try:
                async with aiohttp.ClientSession() as session:
                    crash_embed = {
                        "title": "☠️ 嚴重錯誤：系統崩潰",
                        "description": f"執行過程中發生未預期錯誤，系統將在 {SCHEDULE_INTERVAL} 秒後重試。\n\n**錯誤訊息**:\n```{str(e)}```",
                        "color": 0x000000, # Black
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    await send_discord_notification(session, crash_embed)
            except Exception as send_err:
                logger.error(f"無法發送崩潰通知: {send_err}")
                
        if SCHEDULE_INTERVAL <= 0:
            break
        
        logger.info(f"⏰ 下次掃描: {SCHEDULE_INTERVAL} 秒後...")
        await asyncio.sleep(SCHEDULE_INTERVAL)

def main():
    """主入口"""
    print(f"""
{Fore.CYAN}╔══════════════════════════════════════════════════════════════════╗
║  🔗 全鏈資金流向深度分析系統 v2.0                                  ║
║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ║
║  📡 多時間框架動能分析 | 🆕 新幣偵測 | 🔄 跨鏈流動追蹤           ║
║  💾 歷史數據追蹤 | 📊 多格式報告 | 🔔 Discord 即時通知             ║
╚══════════════════════════════════════════════════════════════════╝
{Style.RESET_ALL}""")
    
    if SCHEDULE_INTERVAL > 0:
        logger.info(f"🔁 定時模式啟動，每 {SCHEDULE_INTERVAL//60} 分鐘執行一次 (Ctrl+C 停止)")
    else:
        logger.info("🔍 單次執行模式")
    
    try:
        asyncio.run(scheduled_run())
    except KeyboardInterrupt:
        logger.info("\n👋 程式已停止")

if __name__ == "__main__":
    main()
