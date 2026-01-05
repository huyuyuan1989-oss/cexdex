"""
🎛️ 資金流向主控台 v1.0 - Capital Flow Command Center
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
設計理念：飛機駕駛艙式的市場狀況一目了然系統

核心功能：
├─ 📊 總資金週期比較 (24H vs 上週 vs 近一個月)
├─ ⛓️ 公鏈資金週期比較 (資金流入/流出哪些公鏈)
├─ 💱 幣種類型週期比較 (原生幣/穩定幣/Altcoin 佔比變化)
├─ 🔄 資金轉換追蹤 (轉成 BTC/穩定幣/Altcoin 的形式)
├─ 🚦 交易信號燈 (一眼知道現在適不適合交易)
└─ 📈 大資金動向 (屯什麼幣：避險 vs 進攻)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import sqlite3
import asyncio
import aiohttp
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
import json
import logging

# 設定日誌
logger = logging.getLogger(__name__)

# 資料庫路徑
DB_PATH = Path(__file__).parent / "chain_data.db"


# ================= 1. 資料結構定義 =================

class MarketPhase(Enum):
    """市場階段枚舉"""
    RISK_ON = "🟢 進攻期 (Risk-On)"           # 資金流入 Altcoin
    ACCUMULATION = "🔵 累積期 (Accumulation)"  # 資金流入原生幣
    RISK_OFF = "🔴 避險期 (Risk-Off)"          # 資金流入穩定幣
    OUTFLOW = "⚫ 撤離期 (Outflow)"            # 資金流出市場
    NEUTRAL = "⚪ 觀望期 (Neutral)"            # 資金持平


class TradingSignal(Enum):
    """交易信號燈"""
    STRONG_BUY = "🟢🟢🟢 強烈買入"
    BUY = "🟢🟢 適合買入"
    NEUTRAL = "🟡 觀望"
    SELL = "🔴🔴 謹慎/減倉"
    STRONG_SELL = "🔴🔴🔴 避險/離場"


@dataclass
class PeriodComparison:
    """週期比較數據結構"""
    current_24h: float = 0.0      # 當前 24H 數值
    last_week_avg: float = 0.0    # 上週平均
    last_month_avg: float = 0.0   # 上月平均
    
    change_vs_week: float = 0.0   # 與上週比較變化 %
    change_vs_month: float = 0.0  # 與上月比較變化 %
    
    trend: str = ""               # 趨勢判定
    signal: str = ""              # 操作信號


@dataclass
class ChainFlowData:
    """公鏈資金流向數據"""
    chain_name: str
    chain_id: str
    
    # TVL 數據
    current_tvl: float = 0.0
    tvl_24h_change: float = 0.0
    tvl_7d_change: float = 0.0
    tvl_30d_change: float = 0.0
    
    # 資金流向佔比
    native_pct: float = 0.0       # 原生幣佔比
    stablecoin_pct: float = 0.0   # 穩定幣佔比
    altcoin_pct: float = 0.0      # Altcoin 佔比
    btc_pct: float = 0.0          # BTC 佔比
    
    # 淨流入/流出
    net_flow_direction: str = ""  # "流入" / "流出"
    net_flow_amount: float = 0.0  # 估算金額
    
    # 週期比較
    period_comparison: Optional[PeriodComparison] = None


@dataclass
class CEXFlowData:
    """CEX 交易所資金流向數據"""
    name: str
    symbol: str = ""
    
    # TVL 數據
    tvl: float = 0.0
    tvl_24h_change: float = 0.0
    tvl_7d_change: float = 0.0
    
    # 資金流向判定
    flow_direction: str = ""  # "流入 CEX" / "流出 CEX"
    flow_interpretation: str = ""  # 解讀
    
    # 市場佔比
    market_share: float = 0.0


@dataclass
class CEXDEXSummary:
    """CEX + DEX 整合數據"""
    # 總資金
    total_market_tvl: float = 0.0         # CEX + DEX 總資金
    cex_total_tvl: float = 0.0            # CEX 總資金
    dex_total_tvl: float = 0.0            # DEX 總資金
    
    # 資金佔比
    cex_share_pct: float = 0.0            # CEX 佔比
    dex_share_pct: float = 0.0            # DEX 佔比
    
    # 24H 變化
    cex_24h_change: float = 0.0
    dex_24h_change: float = 0.0
    
    # 7D 變化
    cex_7d_change: float = 0.0
    dex_7d_change: float = 0.0
    
    # 週期比較 (與上週對比)
    cex_share_vs_week: float = 0.0        # CEX 佔比與上週比較
    dex_share_vs_week: float = 0.0        # DEX 佔比與上週比較
    
    # 資金流向判定
    capital_direction: str = ""           # "流入 CEX" / "流出 CEX 到 DEX" / "流出市場"
    capital_interpretation: str = ""      # 解讀
    
    # CEX 明細
    cex_flows: List[CEXFlowData] = field(default_factory=list)


@dataclass
class CapitalFlowSummary:
    """資金流向總覽 - 戰鬥機駕駛艙核心數據"""
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 總體資金
    total_tvl: float = 0.0
    total_tvl_24h_change: float = 0.0
    total_tvl_7d_change: float = 0.0
    total_tvl_30d_change: float = 0.0
    
    # 資金分佈 (全市場)
    global_native_pct: float = 0.0
    global_stablecoin_pct: float = 0.0
    global_altcoin_pct: float = 0.0
    global_btc_pct: float = 0.0
    
    # 上週對比
    last_week_native_pct: float = 0.0
    last_week_stablecoin_pct: float = 0.0
    last_week_altcoin_pct: float = 0.0
    
    # 上月對比
    last_month_native_pct: float = 0.0
    last_month_stablecoin_pct: float = 0.0
    last_month_altcoin_pct: float = 0.0
    
    # 主要資金流向
    dominant_flow_type: str = ""      # 主要流向類型
    dominant_outflow_chain: str = ""  # 主要流出公鏈
    dominant_inflow_chain: str = ""   # 主要流入公鏈
    
    # 市場狀態判定
    market_phase: MarketPhase = MarketPhase.NEUTRAL
    trading_signal: TradingSignal = TradingSignal.NEUTRAL
    
    # ===== 🎯 戰鬥機駕駛艙新增儀表 =====
    
    # 🔴 異常警報系統 (Alert System)
    alerts: List[str] = field(default_factory=list)  # 當前活躍警報
    alert_level: int = 0  # 0=正常, 1=注意, 2=警告, 3=危險
    
    # ⏱️ 時間緊迫性 (Urgency Indicator)
    opportunity_window: str = ""  # 機會窗口描述
    urgency_score: int = 0  # 0-10: 0=不急, 10=立即行動
    
    # 🎯 具體行動建議 (Action Recommendations)
    primary_action: str = ""  # 主要建議行動
    target_chains: List[str] = field(default_factory=list)  # 建議關注的公鏈
    target_assets: List[str] = field(default_factory=list)  # 建議關注的資產類型
    position_suggestion: str = ""  # 倉位建議 (加倉/減倉/觀望)
    
    # 🌡️ 市場情緒溫度計 (Sentiment Thermometer)
    fear_greed_score: int = 50  # 0=極度恐懼, 50=中性, 100=極度貪婪
    sentiment_label: str = ""  # 情緒標籤
    
    # ⚡ 動量雷達 (Momentum Radar)
    momentum_score: int = 0  # -100 到 +100：負=下跌動能, 正=上漲動能
    momentum_direction: str = ""  # 加速/減速/穩定
    velocity_24h: float = 0.0  # 24小時資金流速 (每小時平均變化)
    
    # 📡 急速變化監控 (Rapid Change Monitor)
    rapid_changes: List[str] = field(default_factory=list)  # 過去4小時的急速變化
    
    # 🔔 關鍵閾值狀態 (Threshold Status)
    threshold_breaches: List[str] = field(default_factory=list)  # 突破歷史閾值的項目
    
    # 公鏈明細
    chain_flows: List[ChainFlowData] = field(default_factory=list)



# ================= 2. 資料庫增強 =================

def init_enhanced_database():
    """初始化增強版資料庫表"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # 資金流向快照表 (用於週期比較)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS capital_flow_snapshot (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_date DATE NOT NULL,
                    snapshot_hour INTEGER DEFAULT 0,
                    
                    -- 總體資金
                    total_tvl REAL,
                    total_volume_24h REAL,
                    
                    -- 資金分佈佔比
                    native_pct REAL DEFAULT 0,
                    stablecoin_pct REAL DEFAULT 0,
                    altcoin_pct REAL DEFAULT 0,
                    btc_pct REAL DEFAULT 0,
                    
                    -- 淨流入量
                    net_inflow_native REAL DEFAULT 0,
                    net_inflow_stablecoin REAL DEFAULT 0,
                    net_inflow_altcoin REAL DEFAULT 0,
                    net_inflow_btc REAL DEFAULT 0,
                    
                    -- CEX/DEX 資金
                    cex_tvl REAL DEFAULT 0,
                    dex_tvl REAL DEFAULT 0,
                    
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    
                    UNIQUE(snapshot_date, snapshot_hour)
                )
            ''')
            
            # 公鏈資金流快照表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chain_flow_snapshot (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_date DATE NOT NULL,
                    chain_id TEXT NOT NULL,
                    chain_name TEXT,
                    
                    -- TVL
                    tvl REAL,
                    tvl_change_24h REAL,
                    
                    -- 資金分佈
                    native_pct REAL DEFAULT 0,
                    stablecoin_pct REAL DEFAULT 0,
                    altcoin_pct REAL DEFAULT 0,
                    btc_pct REAL DEFAULT 0,
                    
                    -- 交易量
                    volume_24h REAL DEFAULT 0,
                    
                    -- 買賣統計
                    total_buys INTEGER DEFAULT 0,
                    total_sells INTEGER DEFAULT 0,
                    net_flow_direction TEXT,
                    
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    
                    UNIQUE(snapshot_date, chain_id)
                )
            ''')
            
            # 資金轉換追蹤表 (追蹤資金以什麼形式流出)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS capital_conversion_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    log_date DATE NOT NULL,
                    chain_id TEXT NOT NULL,
                    
                    -- 從什麼類型轉換
                    from_type TEXT,  -- 'native', 'stablecoin', 'altcoin', 'btc'
                    -- 轉換到什麼類型
                    to_type TEXT,
                    
                    -- 估算金額
                    estimated_volume REAL,
                    
                    -- 主要代幣
                    major_tokens TEXT,  -- JSON array
                    
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            logger.info("📦 增強版資料庫表初始化完成")
    except sqlite3.Error as e:
        logger.error(f"❌ 資料庫初始化失敗: {e}")


def save_capital_flow_snapshot(summary: CapitalFlowSummary):
    """儲存資金流向快照"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            today = datetime.now().strftime('%Y-%m-%d')
            hour = datetime.now().hour
            
            cursor.execute('''
                INSERT OR REPLACE INTO capital_flow_snapshot (
                    snapshot_date, snapshot_hour,
                    total_tvl, total_volume_24h,
                    native_pct, stablecoin_pct, altcoin_pct, btc_pct
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                today, hour,
                summary.total_tvl, 0,
                summary.global_native_pct,
                summary.global_stablecoin_pct,
                summary.global_altcoin_pct,
                summary.global_btc_pct
            ))
            
            # 儲存各公鏈數據
            for chain in summary.chain_flows:
                cursor.execute('''
                    INSERT OR REPLACE INTO chain_flow_snapshot (
                        snapshot_date, chain_id, chain_name,
                        tvl, tvl_change_24h,
                        native_pct, stablecoin_pct, altcoin_pct, btc_pct,
                        net_flow_direction
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    today, chain.chain_id, chain.chain_name,
                    chain.current_tvl, chain.tvl_24h_change,
                    chain.native_pct, chain.stablecoin_pct,
                    chain.altcoin_pct, chain.btc_pct,
                    chain.net_flow_direction
                ))
            
            conn.commit()
            logger.info("💾 資金流向快照已儲存")
    except sqlite3.Error as e:
        logger.error(f"❌ 儲存快照失敗: {e}")


def get_historical_snapshots(days_back: int = 30) -> List[dict]:
    """獲取歷史快照數據"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
            
            cursor.execute('''
                SELECT 
                    snapshot_date,
                    AVG(total_tvl) as avg_tvl,
                    AVG(native_pct) as avg_native,
                    AVG(stablecoin_pct) as avg_stable,
                    AVG(altcoin_pct) as avg_altcoin,
                    AVG(btc_pct) as avg_btc
                FROM capital_flow_snapshot
                WHERE snapshot_date >= ?
                GROUP BY snapshot_date
                ORDER BY snapshot_date DESC
            ''', (start_date,))
            
            rows = cursor.fetchall()
            return [
                {
                    'date': row[0],
                    'avg_tvl': row[1] or 0,
                    'native_pct': row[2] or 0,
                    'stablecoin_pct': row[3] or 0,
                    'altcoin_pct': row[4] or 0,
                    'btc_pct': row[5] or 0
                }
                for row in rows
            ]
    except sqlite3.Error as e:
        logger.error(f"❌ 獲取歷史快照失敗: {e}")
        return []


def calculate_period_comparison() -> Dict[str, PeriodComparison]:
    """計算週期比較數據"""
    comparisons = {}
    
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            today = datetime.now().strftime('%Y-%m-%d')
            week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            month_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            
            # 總資金比較
            cursor.execute('''
                SELECT 
                    (SELECT AVG(total_tvl) FROM capital_flow_snapshot WHERE snapshot_date = ?) as current_tvl,
                    (SELECT AVG(total_tvl) FROM capital_flow_snapshot WHERE snapshot_date BETWEEN ? AND ?) as week_avg,
                    (SELECT AVG(total_tvl) FROM capital_flow_snapshot WHERE snapshot_date >= ?) as month_avg
            ''', (today, week_ago, today, month_ago))
            
            row = cursor.fetchone()
            if row and row[0]:
                current = row[0] or 0
                week_avg = row[1] or current
                month_avg = row[2] or current
                
                comparisons['total_tvl'] = PeriodComparison(
                    current_24h=current,
                    last_week_avg=week_avg,
                    last_month_avg=month_avg,
                    change_vs_week=((current - week_avg) / week_avg * 100) if week_avg > 0 else 0,
                    change_vs_month=((current - month_avg) / month_avg * 100) if month_avg > 0 else 0
                )
            
            # 各類型資金佔比比較
            for metric in ['native_pct', 'stablecoin_pct', 'altcoin_pct', 'btc_pct']:
                cursor.execute(f'''
                    SELECT 
                        (SELECT AVG({metric}) FROM capital_flow_snapshot WHERE snapshot_date = ?) as current_val,
                        (SELECT AVG({metric}) FROM capital_flow_snapshot WHERE snapshot_date BETWEEN ? AND ?) as week_avg,
                        (SELECT AVG({metric}) FROM capital_flow_snapshot WHERE snapshot_date >= ?) as month_avg
                ''', (today, week_ago, today, month_ago))
                
                row = cursor.fetchone()
                if row:
                    current = row[0] or 0
                    week_avg = row[1] or 0
                    month_avg = row[2] or 0
                    
                    comparisons[metric] = PeriodComparison(
                        current_24h=current,
                        last_week_avg=week_avg,
                        last_month_avg=month_avg,
                        change_vs_week=current - week_avg,  # 佔比直接相減
                        change_vs_month=current - month_avg
                    )
            
    except sqlite3.Error as e:
        logger.error(f"❌ 計算週期比較失敗: {e}")
    
    return comparisons


# ================= 3. 市場狀態判定引擎 =================

def determine_market_phase(summary: CapitalFlowSummary, 
                           period_comparison: Dict[str, PeriodComparison]) -> MarketPhase:
    """
    判定當前市場階段
    
    邏輯：
    1. Risk-On (進攻期): Altcoin 佔比上升 + 穩定幣佔比下降
    2. Accumulation (累積期): 原生幣佔比上升 + 穩定幣持平
    3. Risk-Off (避險期): 穩定幣佔比上升 + Altcoin 佔比下降
    4. Outflow (撤離期): 總 TVL 下降 + 穩定幣佔比上升
    """
    
    total_change = summary.total_tvl_24h_change
    
    # 獲取佔比變化
    altcoin_change = period_comparison.get('altcoin_pct', PeriodComparison()).change_vs_week
    stable_change = period_comparison.get('stablecoin_pct', PeriodComparison()).change_vs_week
    native_change = period_comparison.get('native_pct', PeriodComparison()).change_vs_week
    
    # 撤離期：總資金下降
    if total_change < -2 and stable_change > 3:
        return MarketPhase.OUTFLOW
    
    # 避險期：穩定幣佔比大幅上升
    if stable_change > 5 and altcoin_change < -3:
        return MarketPhase.RISK_OFF
    
    # 進攻期：Altcoin 佔比上升
    if altcoin_change > 3 and stable_change < 0:
        return MarketPhase.RISK_ON
    
    # 累積期：原生幣佔比上升
    if native_change > 2 and total_change > 0:
        return MarketPhase.ACCUMULATION
    
    return MarketPhase.NEUTRAL


def determine_trading_signal(summary: CapitalFlowSummary,
                             period_comparison: Dict[str, PeriodComparison]) -> TradingSignal:
    """
    生成交易信號燈
    
    判斷邏輯：
    - 強烈買入：總資金流入 + Altcoin 主導 + 週環比上升
    - 買入：資金穩定流入 + 原生幣/Altcoin 佔比上升
    - 觀望：資金持平或混合信號
    - 減倉：穩定幣佔比大幅上升
    - 離場：總資金流出 + 穩定幣主導
    """
    
    tvl_comp = period_comparison.get('total_tvl', PeriodComparison())
    altcoin_comp = period_comparison.get('altcoin_pct', PeriodComparison())
    stable_comp = period_comparison.get('stablecoin_pct', PeriodComparison())
    
    # 評分系統 (-10 到 +10)
    score = 0
    
    # TVL 變化 (權重 40%)
    if tvl_comp.change_vs_week > 5:
        score += 4
    elif tvl_comp.change_vs_week > 2:
        score += 2
    elif tvl_comp.change_vs_week < -5:
        score -= 4
    elif tvl_comp.change_vs_week < -2:
        score -= 2
    
    # Altcoin 佔比變化 (權重 30%)
    if altcoin_comp.change_vs_week > 5:
        score += 3
    elif altcoin_comp.change_vs_week > 2:
        score += 1.5
    elif altcoin_comp.change_vs_week < -5:
        score -= 3
    elif altcoin_comp.change_vs_week < -2:
        score -= 1.5
    
    # 穩定幣佔比變化 (權重 30%) - 穩定幣上升是負面信號
    if stable_comp.change_vs_week > 5:
        score -= 3
    elif stable_comp.change_vs_week > 2:
        score -= 1.5
    elif stable_comp.change_vs_week < -3:
        score += 2  # 穩定幣流出 = 資金進入市場
    
    # 當前 24H 變化加權
    if summary.total_tvl_24h_change > 3:
        score += 1
    elif summary.total_tvl_24h_change < -3:
        score -= 1
    
    # 信號判定
    if score >= 6:
        return TradingSignal.STRONG_BUY
    elif score >= 3:
        return TradingSignal.BUY
    elif score <= -6:
        return TradingSignal.STRONG_SELL
    elif score <= -3:
        return TradingSignal.SELL
    else:
        return TradingSignal.NEUTRAL


def analyze_capital_conversion(all_flow_analysis: dict, chains: list) -> List[dict]:
    """
    分析資金轉換形式
    追蹤資金以什麼形式流出（轉 BTC、轉穩定幣等）
    """
    conversions = []
    
    for chain in chains:
        chain_id = chain.get('search_id', '')
        flow = all_flow_analysis.get(chain_id, {})
        
        if not flow or not flow.get('breakdown'):
            continue
        
        breakdown = flow['breakdown']
        
        # 分析淨流向
        for category in ['native', 'stablecoin', 'btc', 'altcoin']:
            data = breakdown.get(category, {})
            net_flow = data.get('net_flow_count', 0)
            
            if abs(net_flow) > 100:  # 顯著流動
                direction = "流入" if net_flow > 0 else "流出"
                
                conversions.append({
                    'chain': chain.get('chain_name', chain_id),
                    'category': category,
                    'direction': direction,
                    'net_flow_count': net_flow,
                    'volume_pct': data.get('volume_pct', 0),
                    'top_tokens': data.get('top_tokens', [])[:3]
                })
    
    # 按淨流量絕對值排序
    conversions.sort(key=lambda x: abs(x['net_flow_count']), reverse=True)
    
    return conversions[:20]


def identify_whale_accumulation_targets(all_flow_analysis: dict) -> List[dict]:
    """
    識別大資金屯積的目標
    判斷：避險（屯穩定幣）、準備牛市（屯原生幣）、進攻（屯 Altcoin）
    """
    accumulation_summary = {
        'stablecoin': {'total_volume': 0, 'chains': [], 'tokens': []},
        'native': {'total_volume': 0, 'chains': [], 'tokens': []},
        'altcoin': {'total_volume': 0, 'chains': [], 'tokens': []},
        'btc': {'total_volume': 0, 'chains': [], 'tokens': []}
    }
    
    for chain_id, flow in all_flow_analysis.items():
        if not flow or not flow.get('breakdown'):
            continue
        
        breakdown = flow['breakdown']
        
        for category, data in breakdown.items():
            if category not in accumulation_summary:
                continue
            
            net_flow = data.get('net_flow_count', 0)
            volume = data.get('volume', 0)
            
            if net_flow > 0:  # 淨買入
                accumulation_summary[category]['total_volume'] += volume
                accumulation_summary[category]['chains'].append(chain_id)
                accumulation_summary[category]['tokens'].extend(data.get('top_tokens', [])[:3])
    
    # 判定主要屯積方向
    dominant_category = max(
        accumulation_summary.keys(),
        key=lambda k: accumulation_summary[k]['total_volume']
    )
    
    interpretation = ""
    if dominant_category == 'stablecoin':
        interpretation = "⚠️ 大資金流入穩定幣 → 避險情緒主導，市場可能轉弱"
    elif dominant_category == 'native':
        interpretation = "📈 大資金流入原生幣 → 看好大盤，可能準備牛市行情"
    elif dominant_category == 'altcoin':
        interpretation = "🚀 大資金流入個幣 → Alpha 機會活躍，尋找潛力項目"
    elif dominant_category == 'btc':
        interpretation = "🟡 大資金流入 BTC → 傳統避險 + 機構買盤"
    
    return {
        'dominant': dominant_category,
        'interpretation': interpretation,
        'details': accumulation_summary
    }


# ================= 3.4 戰鬥機駕駛艙核心儀表引擎 =================

def calculate_alert_system(summary: 'CapitalFlowSummary', cex_dex_summary: Optional['CEXDEXSummary'] = None) -> Tuple[List[str], int]:
    """
    🔴 異常警報系統 - 偵測需要立即關注的市場異常
    
    Returns:
        alerts: 警報訊息列表
        alert_level: 0=正常, 1=注意, 2=警告, 3=危險
    """
    alerts = []
    max_level = 0
    
    # 1. 24H TVL 急劇變化警報
    if summary.total_tvl_24h_change < -5:
        alerts.append(f"🔴 危險: 24H TVL 急跌 {summary.total_tvl_24h_change:.1f}%，資金大量流出！")
        max_level = max(max_level, 3)
    elif summary.total_tvl_24h_change < -3:
        alerts.append(f"🟠 警告: 24H TVL 下跌 {summary.total_tvl_24h_change:.1f}%，注意風險")
        max_level = max(max_level, 2)
    elif summary.total_tvl_24h_change > 8:
        alerts.append(f"🟢 機會: 24H TVL 大漲 {summary.total_tvl_24h_change:.1f}%，資金快速流入！")
        max_level = max(max_level, 1)
    
    # 2. 穩定幣佔比異常
    if summary.global_stablecoin_pct > 40:
        alerts.append(f"🟠 避險情緒高漲: 穩定幣佔比達 {summary.global_stablecoin_pct:.1f}%，市場恐慌")
        max_level = max(max_level, 2)
    elif summary.global_stablecoin_pct < 15:
        alerts.append(f"🟢 風險偏好上升: 穩定幣佔比僅 {summary.global_stablecoin_pct:.1f}%，資金積極入場")
        max_level = max(max_level, 1)
    
    # 3. CEX 資金異常流動
    if cex_dex_summary:
        if cex_dex_summary.cex_24h_change > 3:
            alerts.append(f"🔴 注意: CEX 資金 24H 增加 {cex_dex_summary.cex_24h_change:.1f}%，可能準備拋售")
            max_level = max(max_level, 2)
        elif cex_dex_summary.cex_24h_change < -3:
            alerts.append(f"🟢 利好: CEX 資金 24H 流出 {abs(cex_dex_summary.cex_24h_change):.1f}%，提幣到錢包")
            max_level = max(max_level, 1)
    
    # 4. 單一公鏈急劇變化
    for chain in summary.chain_flows:
        if chain.tvl_24h_change > 15:
            alerts.append(f"⚡ {chain.chain_name} 24H TVL 暴漲 {chain.tvl_24h_change:.1f}%!")
            max_level = max(max_level, 1)
        elif chain.tvl_24h_change < -10:
            alerts.append(f"⚠️ {chain.chain_name} 24H TVL 暴跌 {chain.tvl_24h_change:.1f}%!")
            max_level = max(max_level, 2)
    
    return alerts[:5], max_level  # 最多返回5個警報


def calculate_fear_greed_index(summary: 'CapitalFlowSummary', period_comparison: Dict[str, 'PeriodComparison']) -> Tuple[int, str]:
    """
    🌡️ 市場情緒溫度計 - 恐懼/貪婪指數
    
    Returns:
        score: 0-100 (0=極度恐懼, 100=極度貪婪)
        label: 情緒標籤
    """
    score = 50  # 起始中性
    
    # 1. TVL 變化 (權重 30)
    if summary.total_tvl_24h_change > 5:
        score += 15
    elif summary.total_tvl_24h_change > 2:
        score += 8
    elif summary.total_tvl_24h_change < -5:
        score -= 15
    elif summary.total_tvl_24h_change < -2:
        score -= 8
    
    # 2. 穩定幣佔比 (權重 25) - 穩定幣高 = 恐懼
    if summary.global_stablecoin_pct > 35:
        score -= 15
    elif summary.global_stablecoin_pct > 28:
        score -= 8
    elif summary.global_stablecoin_pct < 18:
        score += 12
    elif summary.global_stablecoin_pct < 22:
        score += 5
    
    # 3. Altcoin 佔比 (權重 25) - Altcoin 高 = 貪婪
    if summary.global_altcoin_pct > 40:
        score += 15
    elif summary.global_altcoin_pct > 30:
        score += 8
    elif summary.global_altcoin_pct < 15:
        score -= 10
    
    # 4. 週變化趨勢 (權重 20)
    if summary.total_tvl_7d_change > 10:
        score += 10
    elif summary.total_tvl_7d_change > 5:
        score += 5
    elif summary.total_tvl_7d_change < -10:
        score -= 10
    elif summary.total_tvl_7d_change < -5:
        score -= 5
    
    # 限制範圍
    score = max(0, min(100, score))
    
    # 情緒標籤
    if score >= 80:
        label = "🔥 極度貪婪"
    elif score >= 65:
        label = "😊 貪婪"
    elif score >= 55:
        label = "😐 略微貪婪"
    elif score >= 45:
        label = "😶 中性"
    elif score >= 35:
        label = "😟 略微恐懼"
    elif score >= 20:
        label = "😰 恐懼"
    else:
        label = "😱 極度恐懼"
    
    return score, label


def calculate_momentum_radar(summary: 'CapitalFlowSummary') -> Tuple[int, str, float]:
    """
    ⚡ 動量雷達 - 資金流動的速度和加速度
    
    Returns:
        momentum_score: -100 到 +100
        direction: 加速/減速/穩定
        velocity: 24小時平均流速 (%/小時)
    """
    # 計算動量分數
    momentum = 0
    
    # 24H 變化貢獻
    momentum += summary.total_tvl_24h_change * 5
    
    # 7D 趨勢一致性加成
    if (summary.total_tvl_24h_change > 0 and summary.total_tvl_7d_change > 0) or \
       (summary.total_tvl_24h_change < 0 and summary.total_tvl_7d_change < 0):
        momentum += summary.total_tvl_7d_change * 2  # 趨勢一致加成
    else:
        momentum -= abs(summary.total_tvl_7d_change)  # 趨勢相反減分
    
    # Altcoin 活躍度加成
    if summary.global_altcoin_pct > 30:
        momentum += 10
    
    # 限制範圍
    momentum = max(-100, min(100, int(momentum)))
    
    # 方向判定
    if summary.total_tvl_24h_change > summary.total_tvl_7d_change / 7:
        direction = "📈 加速上漲" if momentum > 0 else "📉 加速下跌"
    elif abs(summary.total_tvl_24h_change) < 0.5:
        direction = "➡️ 持平穩定"
    else:
        direction = "🔄 動能減弱"
    
    # 24小時平均流速
    velocity = summary.total_tvl_24h_change / 24
    
    return momentum, direction, velocity


def generate_action_recommendations(
    summary: 'CapitalFlowSummary',
    fear_greed_score: int,
    momentum_score: int
) -> Tuple[str, List[str], List[str], str]:
    """
    🎯 具體行動建議生成器
    
    Returns:
        primary_action: 主要建議
        target_chains: 建議關注公鏈
        target_assets: 建議資產類型
        position_suggestion: 倉位建議
    """
    primary_action = ""
    target_chains = []
    target_assets = []
    position_suggestion = ""
    
    # 根據信號判定主要行動
    signal = summary.trading_signal
    
    if signal == TradingSignal.STRONG_BUY:
        primary_action = "🟢 積極進場：市場資金大量流入，把握機會建立多頭倉位"
        position_suggestion = "📈 建議加倉至 70-100%"
    elif signal == TradingSignal.BUY:
        primary_action = "🟢 適度建倉：市場環境向好，可逐步建立部位"
        position_suggestion = "📈 建議加倉至 50-70%"
    elif signal == TradingSignal.NEUTRAL:
        primary_action = "🟡 觀望等待：市場方向不明，保持現有部位或小額試單"
        position_suggestion = "➖ 維持現狀或 30-50%"
    elif signal == TradingSignal.SELL:
        primary_action = "🟠 減少曝險：避險情緒升溫，適度降低倉位"
        position_suggestion = "📉 建議減倉至 20-40%"
    else:  # STRONG_SELL
        primary_action = "🔴 避險優先：資金大量流出，建議以穩定幣避險"
        position_suggestion = "📉 建議減倉至 0-20%"
    
    # 根據資金流向推薦公鏈
    sorted_chains = sorted(summary.chain_flows, key=lambda x: x.tvl_24h_change, reverse=True)
    target_chains = [c.chain_name for c in sorted_chains[:3] if c.tvl_24h_change > 0]
    
    if not target_chains:
        target_chains = ["暫無明顯流入公鏈，建議觀望"]
    
    # 根據市場情緒推薦資產類型
    if fear_greed_score >= 60:
        target_assets = ["🚀 Altcoin (Alpha機會)", "🔷 原生幣 (大盤配置)"]
    elif fear_greed_score >= 40:
        target_assets = ["🔷 原生幣 (穩健配置)", "💵 穩定幣 (部分避險)"]
    else:
        target_assets = ["💵 穩定幣 (避險優先)", "🟡 BTC (避風港)"]
    
    return primary_action, target_chains, target_assets, position_suggestion


def calculate_urgency_score(summary: 'CapitalFlowSummary', alerts: List[str]) -> Tuple[int, str]:
    """
    ⏱️ 時間緊迫性計算
    
    Returns:
        urgency_score: 0-10
        opportunity_window: 機會窗口描述
    """
    urgency = 0
    
    # 警報數量影響緊迫性
    urgency += len(alerts) * 2
    
    # 24H 大幅變化
    if abs(summary.total_tvl_24h_change) > 5:
        urgency += 3
    elif abs(summary.total_tvl_24h_change) > 3:
        urgency += 2
    
    # 趨勢一致性
    if (summary.total_tvl_24h_change > 2 and summary.total_tvl_7d_change > 5) or \
       (summary.total_tvl_24h_change < -2 and summary.total_tvl_7d_change < -5):
        urgency += 2  # 趨勢明確，需要行動
    
    urgency = min(10, urgency)
    
    # 機會窗口描述
    if urgency >= 8:
        window = "⚡ 立即行動：趨勢明確，錯過可能造成損失或錯失機會"
    elif urgency >= 6:
        window = "🔔 24小時內：建議今日內做出決策"
    elif urgency >= 4:
        window = "📅 2-3天內：可以觀察但需密切關注"
    else:
        window = "🕐 可從容規劃：市場穩定，不急於行動"
    
    return urgency, window


def enrich_cockpit_data(
    summary: 'CapitalFlowSummary',
    period_comparison: Dict[str, 'PeriodComparison'],
    cex_dex_summary: Optional['CEXDEXSummary'] = None
) -> 'CapitalFlowSummary':
    """
    為戰鬥機駕駛艙填充所有儀表數據
    """
    # 1. 異常警報系統
    summary.alerts, summary.alert_level = calculate_alert_system(summary, cex_dex_summary)
    
    # 2. 市場情緒溫度計
    summary.fear_greed_score, summary.sentiment_label = calculate_fear_greed_index(summary, period_comparison)
    
    # 3. 動量雷達
    summary.momentum_score, summary.momentum_direction, summary.velocity_24h = calculate_momentum_radar(summary)
    
    # 4. 行動建議
    summary.primary_action, summary.target_chains, summary.target_assets, summary.position_suggestion = \
        generate_action_recommendations(summary, summary.fear_greed_score, summary.momentum_score)
    
    # 5. 時間緊迫性
    summary.urgency_score, summary.opportunity_window = calculate_urgency_score(summary, summary.alerts)
    
    return summary


# ================= 3.5 CEX 分析和 CEX+DEX 整合 =================


def analyze_cex_flows(cex_data: list) -> Tuple[List[CEXFlowData], dict]:
    """
    分析 CEX 交易所資金流向
    
    Returns:
        cex_flows: CEX 資金流向列表
        summary: CEX 分析摘要
    """
    if not cex_data:
        return [], {}
    
    cex_flows = []
    total_cex_tvl = sum(c.get('tvl', 0) for c in cex_data)
    
    # CEX 整體統計
    total_24h_change = 0
    total_7d_change = 0
    inflow_count = 0
    outflow_count = 0
    
    for cex in cex_data:
        tvl = cex.get('tvl', 0)
        change_24h = cex.get('change_1d', 0)
        change_7d = cex.get('change_7d', 0)
        
        # 計算市場佔比
        market_share = (tvl / total_cex_tvl * 100) if total_cex_tvl > 0 else 0
        
        # 判定資金流向
        if change_24h > 0.5:
            flow_direction = "📥 流入 CEX"
            interpretation = "用戶充值增加，可能準備交易或賣出"
            inflow_count += 1
        elif change_24h < -0.5:
            flow_direction = "📤 流出 CEX"
            interpretation = "用戶提幣增加，可能轉向 DeFi 或冷錢包"
            outflow_count += 1
        else:
            flow_direction = "➖ 持平"
            interpretation = "資金流動平衡"
        
        cex_flow = CEXFlowData(
            name=cex.get('name', ''),
            symbol=cex.get('symbol', ''),
            tvl=tvl,
            tvl_24h_change=change_24h,
            tvl_7d_change=change_7d,
            flow_direction=flow_direction,
            flow_interpretation=interpretation,
            market_share=market_share
        )
        cex_flows.append(cex_flow)
        
        # 加權平均
        if total_cex_tvl > 0:
            total_24h_change += tvl * change_24h
            total_7d_change += tvl * change_7d
    
    # 計算加權平均變化
    avg_24h_change = total_24h_change / total_cex_tvl if total_cex_tvl > 0 else 0
    avg_7d_change = total_7d_change / total_cex_tvl if total_cex_tvl > 0 else 0
    
    # CEX 資金流向解讀
    if avg_24h_change > 1:
        cex_trend = "🔴 資金大量流入 CEX → 可能準備賣出，謹慎"
    elif avg_24h_change > 0.3:
        cex_trend = "🟡 資金小幅流入 CEX → 觀望"
    elif avg_24h_change < -1:
        cex_trend = "🟢 資金大量流出 CEX → 用戶提幣，看好後市"
    elif avg_24h_change < -0.3:
        cex_trend = "🟢 資金小幅流出 CEX → DeFi 活動增加"
    else:
        cex_trend = "⚪ CEX 資金流動持平"
    
    summary = {
        'total_tvl': total_cex_tvl,
        'avg_24h_change': avg_24h_change,
        'avg_7d_change': avg_7d_change,
        'inflow_count': inflow_count,
        'outflow_count': outflow_count,
        'trend_interpretation': cex_trend,
        'top_3_by_tvl': sorted(cex_flows, key=lambda x: x.tvl, reverse=True)[:3],
        'top_inflows': sorted([c for c in cex_flows if c.tvl_24h_change > 0], 
                              key=lambda x: x.tvl_24h_change, reverse=True)[:3],
        'top_outflows': sorted([c for c in cex_flows if c.tvl_24h_change < 0], 
                               key=lambda x: x.tvl_24h_change)[:3]
    }
    
    return cex_flows, summary


def generate_cex_dex_summary(
    chains: list,
    cex_data: list,
    all_flow_analysis: dict
) -> CEXDEXSummary:
    """
    生成 CEX + DEX 整合數據
    
    核心分析：
    1. CEX vs DEX 資金佔比
    2. 資金從 CEX 流向 DEX 還是反向
    3. 整體市場資金是增加還是減少
    """
    summary = CEXDEXSummary()
    
    # 計算 DEX TVL (公鏈總 TVL)
    dex_tvl = sum(c.get('tvl', 0) for c in chains)
    
    # 計算 CEX TVL
    cex_tvl = sum(c.get('tvl', 0) for c in cex_data) if cex_data else 0
    
    # 總市場 TVL
    total_tvl = dex_tvl + cex_tvl
    
    summary.total_market_tvl = total_tvl
    summary.cex_total_tvl = cex_tvl
    summary.dex_total_tvl = dex_tvl
    
    # 計算佔比
    if total_tvl > 0:
        summary.cex_share_pct = (cex_tvl / total_tvl) * 100
        summary.dex_share_pct = (dex_tvl / total_tvl) * 100
    
    # 計算加權平均 24H 變化
    if dex_tvl > 0:
        summary.dex_24h_change = sum(c.get('tvl', 0) * c.get('change_1d', 0) for c in chains) / dex_tvl
        summary.dex_7d_change = sum(c.get('tvl', 0) * c.get('change_7d', 0) for c in chains) / dex_tvl
    
    if cex_tvl > 0 and cex_data:
        summary.cex_24h_change = sum(c.get('tvl', 0) * c.get('change_1d', 0) for c in cex_data) / cex_tvl
        summary.cex_7d_change = sum(c.get('tvl', 0) * c.get('change_7d', 0) for c in cex_data) / cex_tvl
    
    # CEX 個別資金流向
    if cex_data:
        cex_flows, _ = analyze_cex_flows(cex_data)
        summary.cex_flows = cex_flows
    
    # 資金流向判定
    # 邏輯：比較 CEX 和 DEX 的資金變化
    if summary.cex_24h_change > 0.5 and summary.dex_24h_change < 0:
        summary.capital_direction = "📥 資金流入 CEX (從 DEX)"
        summary.capital_interpretation = "⚠️ 用戶將資金從 DeFi 轉回交易所，可能準備賣出或觀望"
    elif summary.cex_24h_change < -0.5 and summary.dex_24h_change > 0:
        summary.capital_direction = "📤 資金流出 CEX (到 DEX)"
        summary.capital_interpretation = "🟢 用戶提幣參與 DeFi，市場活躍度上升"
    elif summary.cex_24h_change < -0.5 and summary.dex_24h_change < -0.5:
        summary.capital_direction = "⚫ 資金流出市場"
        summary.capital_interpretation = "🔴 CEX 和 DEX 資金同時減少，市場整體萎縮"
    elif summary.cex_24h_change > 0 and summary.dex_24h_change > 0:
        summary.capital_direction = "🟢 資金流入市場"
        summary.capital_interpretation = "✅ CEX 和 DEX 資金同時增加，新資金入場"
    else:
        summary.capital_direction = "➖ 資金持平"
        summary.capital_interpretation = "市場資金流動平衡，等待方向"
    
    return summary


# ================= 4. 主控台生成器 =================

def generate_command_center_data(
    chains: list,
    all_tokens: dict,
    all_flow_analysis: dict,
    cex_data: list
) -> CapitalFlowSummary:
    """
    生成資金流向主控台數據
    """
    summary = CapitalFlowSummary()
    summary.timestamp = datetime.now()
    
    # 1. 計算總 TVL
    summary.total_tvl = sum(c.get('tvl', 0) for c in chains)
    
    # 計算加權平均 TVL 變化
    if summary.total_tvl > 0:
        weighted_24h = sum(c.get('tvl', 0) * c.get('change_1d', 0) for c in chains) / summary.total_tvl
        weighted_7d = sum(c.get('tvl', 0) * c.get('change_7d', 0) for c in chains) / summary.total_tvl
        weighted_30d = sum(c.get('tvl', 0) * c.get('change_30d', 0) for c in chains) / summary.total_tvl
        
        summary.total_tvl_24h_change = weighted_24h
        summary.total_tvl_7d_change = weighted_7d
        summary.total_tvl_30d_change = weighted_30d
    
    # 2. 計算全市場資金分佈
    total_volume = 0
    total_native_vol = 0
    total_stable_vol = 0
    total_altcoin_vol = 0
    total_btc_vol = 0
    
    for chain_id, flow in all_flow_analysis.items():
        if not flow or not flow.get('breakdown'):
            continue
        
        breakdown = flow['breakdown']
        total_volume += flow.get('total_volume', 0)
        
        total_native_vol += breakdown.get('native', {}).get('volume', 0)
        total_stable_vol += breakdown.get('stablecoin', {}).get('volume', 0)
        total_altcoin_vol += breakdown.get('altcoin', {}).get('volume', 0)
        total_btc_vol += breakdown.get('btc', {}).get('volume', 0)
    
    if total_volume > 0:
        summary.global_native_pct = (total_native_vol / total_volume) * 100
        summary.global_stablecoin_pct = (total_stable_vol / total_volume) * 100
        summary.global_altcoin_pct = (total_altcoin_vol / total_volume) * 100
        summary.global_btc_pct = (total_btc_vol / total_volume) * 100
    
    # 3. 處理各公鏈數據
    for chain in chains:
        chain_id = chain.get('search_id', '')
        flow = all_flow_analysis.get(chain_id, {})
        
        chain_flow = ChainFlowData(
            chain_name=chain.get('chain_name', ''),
            chain_id=chain_id,
            current_tvl=chain.get('tvl', 0),
            tvl_24h_change=chain.get('change_1d', 0),
            tvl_7d_change=chain.get('change_7d', 0),
            tvl_30d_change=chain.get('change_30d', 0)
        )
        
        if flow and flow.get('breakdown'):
            breakdown = flow['breakdown']
            chain_flow.native_pct = breakdown.get('native', {}).get('volume_pct', 0)
            chain_flow.stablecoin_pct = breakdown.get('stablecoin', {}).get('volume_pct', 0)
            chain_flow.altcoin_pct = breakdown.get('altcoin', {}).get('volume_pct', 0)
            chain_flow.btc_pct = breakdown.get('btc', {}).get('volume_pct', 0)
            
            # 計算淨流向
            total_net = sum(
                breakdown.get(cat, {}).get('net_flow_count', 0)
                for cat in ['native', 'stablecoin', 'altcoin', 'btc']
            )
            chain_flow.net_flow_direction = "流入 📈" if total_net > 0 else "流出 📉"
        
        summary.chain_flows.append(chain_flow)
    
    # 4. 找出主要流入/流出公鏈
    if summary.chain_flows:
        sorted_by_change = sorted(summary.chain_flows, key=lambda x: x.tvl_24h_change, reverse=True)
        if sorted_by_change:
            summary.dominant_inflow_chain = sorted_by_change[0].chain_name
            summary.dominant_outflow_chain = sorted_by_change[-1].chain_name
    
    # 5. 判定主要資金流向類型
    max_pct = max(
        summary.global_native_pct,
        summary.global_stablecoin_pct,
        summary.global_altcoin_pct,
        summary.global_btc_pct
    )
    
    if max_pct == summary.global_native_pct:
        summary.dominant_flow_type = "原生幣 (ETH/SOL/BNB等)"
    elif max_pct == summary.global_stablecoin_pct:
        summary.dominant_flow_type = "穩定幣 (USDT/USDC等)"
    elif max_pct == summary.global_altcoin_pct:
        summary.dominant_flow_type = "個幣 (Altcoin)"
    else:
        summary.dominant_flow_type = "BTC 相關"
    
    # 6. 獲取週期比較數據
    period_comparison = calculate_period_comparison()
    
    # 7. 判定市場狀態
    summary.market_phase = determine_market_phase(summary, period_comparison)
    summary.trading_signal = determine_trading_signal(summary, period_comparison)
    
    return summary


# ================= 5. 報告輸出 =================

def generate_alerts_html(alerts: List[str], alert_level: int) -> str:
    """生成警報區塊的 HTML"""
    if not alerts:
        return '''
        <div style="background: rgba(34, 197, 94, 0.1); border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 8px; padding: 0.75rem; margin-bottom: 0.5rem;">
            <span style="color: var(--green);">✅ 系統正常 - 無異常警報</span>
        </div>
        '''
    
    # 根據警報級別選擇顏色
    if alert_level >= 3:
        bg_color = "rgba(239, 68, 68, 0.15)"
        border_color = "rgba(239, 68, 68, 0.5)"
        title = "🚨 危險警報"
    elif alert_level >= 2:
        bg_color = "rgba(249, 115, 22, 0.15)"
        border_color = "rgba(249, 115, 22, 0.5)"
        title = "⚠️ 警告"
    else:
        bg_color = "rgba(251, 191, 36, 0.1)"
        border_color = "rgba(251, 191, 36, 0.3)"
        title = "📢 通知"
    
    alerts_html = "".join([f'<div style="margin: 0.25rem 0; font-size: 0.9rem;">{alert}</div>' for alert in alerts])
    
    return f'''
    <div style="background: {bg_color}; border: 1px solid {border_color}; border-radius: 8px; padding: 0.75rem; margin-bottom: 0.5rem;">
        <div style="font-weight: 600; margin-bottom: 0.5rem;">{title}</div>
        {alerts_html}
    </div>
    '''


def generate_cex_dex_html_section(cex_dex_summary: CEXDEXSummary, cex_summary: Optional[dict]) -> str:
    """生成 CEX+DEX 整合數據的 HTML 區塊"""
    if not cex_dex_summary:
        return ""
    
    # 預先計算 CSS class
    cex_change_class = "positive" if cex_dex_summary.cex_24h_change > 0 else "negative"
    dex_change_class = "positive" if cex_dex_summary.dex_24h_change > 0 else "negative"
    
    html = f'''
    <div class="card" style="background: linear-gradient(135deg, rgba(251, 191, 36, 0.05), rgba(249, 115, 22, 0.05)); border: 1px solid rgba(251, 191, 36, 0.2);">
        <div class="card-title">🏦 CEX + DEX 資金整合分析</div>
        
        <!-- CEX vs DEX 佔比 -->
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem;">
            <div style="text-align: center; padding: 1rem; background: rgba(251, 191, 36, 0.1); border-radius: 10px;">
                <div style="font-size: 0.8rem; color: var(--text-muted);">🏦 CEX 交易所</div>
                <div style="font-size: 1.75rem; font-weight: 700; color: #fbbf24;">${cex_dex_summary.cex_total_tvl/1e9:.1f}B</div>
                <div style="font-size: 0.85rem; color: var(--text-muted);">佔比 {cex_dex_summary.cex_share_pct:.1f}%</div>
                <div class="{cex_change_class}" style="font-size: 0.85rem; margin-top: 0.25rem;">
                    24H: {cex_dex_summary.cex_24h_change:+.2f}%
                </div>
            </div>
            <div style="text-align: center; padding: 1rem; background: rgba(99, 102, 241, 0.1); border-radius: 10px;">
                <div style="font-size: 0.8rem; color: var(--text-muted);">⛓️ DEX 公鏈</div>
                <div style="font-size: 1.75rem; font-weight: 700; color: var(--accent);">${cex_dex_summary.dex_total_tvl/1e9:.1f}B</div>
                <div style="font-size: 0.85rem; color: var(--text-muted);">佔比 {cex_dex_summary.dex_share_pct:.1f}%</div>
                <div class="{dex_change_class}" style="font-size: 0.85rem; margin-top: 0.25rem;">
                    24H: {cex_dex_summary.dex_24h_change:+.2f}%
                </div>
            </div>
        </div>
        
        <!-- 總市場 TVL -->
        <div style="text-align: center; padding: 0.75rem; background: rgba(255,255,255,0.03); border-radius: 8px; margin-bottom: 1rem;">
            <div style="font-size: 0.8rem; color: var(--text-muted);">📊 全市場總資金 (CEX + DEX)</div>
            <div style="font-size: 2rem; font-weight: 700; background: linear-gradient(135deg, #fbbf24, var(--accent)); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
                ${cex_dex_summary.total_market_tvl/1e9:.1f}B
            </div>
        </div>
        
        <!-- 資金流向判定 -->
        <div class="interpretation" style="margin-top: 0;">
            <strong>{cex_dex_summary.capital_direction}</strong><br>
            {cex_dex_summary.capital_interpretation}
        </div>
    </div>
    '''
    
    # CEX 交易所明細
    if cex_summary and cex_summary.get("top_3_by_tvl"):
        cex_rows = ""
        for cex in cex_summary.get("top_3_by_tvl", []):
            c24h_class = "positive" if cex.tvl_24h_change > 0 else "negative"
            c7d_class = "positive" if cex.tvl_7d_change > 0 else "negative"
            cex_rows += f'''
            <tr>
                <td><strong>{cex.name}</strong></td>
                <td>${cex.tvl/1e9:.2f}B</td>
                <td class="{c24h_class}">{cex.tvl_24h_change:+.2f}%</td>
                <td class="{c7d_class}">{cex.tvl_7d_change:+.2f}%</td>
                <td>{cex.market_share:.1f}%</td>
                <td>{cex.flow_direction}</td>
            </tr>
            '''
        
        html += f'''
        <div class="card">
            <div class="card-title">🏦 CEX 交易所資金流向</div>
            <div class="interpretation" style="margin-bottom: 1rem; margin-top: 0;">
                {cex_summary.get("trend_interpretation", "")}
            </div>
            <table>
                <thead>
                    <tr>
                        <th>交易所</th>
                        <th>TVL</th>
                        <th>24H</th>
                        <th>7D</th>
                        <th>市場佔比</th>
                        <th>流向</th>
                    </tr>
                </thead>
                <tbody>
                    {cex_rows}
                </tbody>
            </table>
        </div>
        '''
    
    return html


def generate_command_center_html(
    summary: CapitalFlowSummary,
    period_comparison: Dict[str, PeriodComparison],
    conversions: List[dict],
    whale_targets: dict,
    cex_dex_summary: Optional[CEXDEXSummary] = None,
    cex_summary: Optional[dict] = None
) -> str:
    """生成資金流向主控台 HTML 報告 (含 CEX+DEX 整合)"""
    
    # 交易信號顏色
    signal_colors = {
        TradingSignal.STRONG_BUY: "#22c55e",
        TradingSignal.BUY: "#4ade80",
        TradingSignal.NEUTRAL: "#fbbf24",
        TradingSignal.SELL: "#f87171",
        TradingSignal.STRONG_SELL: "#ef4444"
    }
    
    signal_color = signal_colors.get(summary.trading_signal, "#fbbf24")
    
    # 生成公鏈表格行
    chain_rows = ""
    for chain in sorted(summary.chain_flows, key=lambda x: x.tvl_24h_change, reverse=True):
        change_class = "positive" if chain.tvl_24h_change > 0 else "negative"
        chain_rows += f"""
        <tr>
            <td><strong>{chain.chain_name}</strong></td>
            <td>${chain.current_tvl/1e9:.2f}B</td>
            <td class="{change_class}">{chain.tvl_24h_change:+.2f}%</td>
            <td class="{'positive' if chain.tvl_7d_change > 0 else 'negative'}">{chain.tvl_7d_change:+.2f}%</td>
            <td class="{'positive' if chain.tvl_30d_change > 0 else 'negative'}">{chain.tvl_30d_change:+.2f}%</td>
            <td>{chain.net_flow_direction}</td>
        </tr>
        """
    
    # 資金轉換表格
    conversion_rows = ""
    for conv in conversions[:10]:
        cat_name = {
            'native': '🔷 原生幣',
            'stablecoin': '💵 穩定幣',
            'altcoin': '🚀 Altcoin',
            'btc': '🟡 BTC'
        }.get(conv['category'], conv['category'])
        
        dir_class = "positive" if conv['direction'] == "流入" else "negative"
        conversion_rows += f"""
        <tr>
            <td>{conv['chain']}</td>
            <td>{cat_name}</td>
            <td class="{dir_class}">{conv['direction']}</td>
            <td>{conv['volume_pct']:.1f}%</td>
            <td>{', '.join(conv['top_tokens'][:3])}</td>
        </tr>
        """
    
    html = f"""
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🎛️ 資金流向主控台 - Capital Flow Command Center</title>
    <style>
        :root {{
            --bg-dark: #0a0a0f;
            --bg-card: #12121a;
            --accent: #6366f1;
            --green: #22c55e;
            --red: #ef4444;
            --orange: #f97316;
            --text: #e2e8f0;
            --text-muted: #94a3b8;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Inter', -apple-system, sans-serif;
            background: var(--bg-dark);
            color: var(--text);
            padding: 1rem;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        h1 {{
            font-size: 1.75rem;
            background: linear-gradient(135deg, var(--accent), #a855f7);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }}
        .timestamp {{ color: var(--text-muted); margin-bottom: 1.5rem; }}
        
        /* 交易信號燈 */
        .signal-panel {{
            background: linear-gradient(135deg, rgba(99, 102, 241, 0.1), rgba(168, 85, 247, 0.1));
            border: 2px solid {signal_color};
            border-radius: 16px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            text-align: center;
        }}
        .signal-value {{
            font-size: 2rem;
            font-weight: 700;
            color: {signal_color};
            margin-bottom: 0.5rem;
        }}
        .signal-phase {{
            font-size: 1.25rem;
            color: var(--text);
        }}
        
        /* 數據卡片 */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 1rem;
            margin-bottom: 1.5rem;
        }}
        .stat-card {{
            background: var(--bg-card);
            border-radius: 12px;
            padding: 1rem;
            border: 1px solid rgba(255,255,255,0.05);
        }}
        .stat-label {{ color: var(--text-muted); font-size: 0.75rem; margin-bottom: 0.25rem; }}
        .stat-value {{ font-size: 1.5rem; font-weight: 700; }}
        .stat-change {{ font-size: 0.8rem; margin-top: 0.25rem; }}
        .positive {{ color: var(--green); }}
        .negative {{ color: var(--red); }}
        
        /* 表格 */
        .card {{ background: var(--bg-card); border-radius: 12px; padding: 1rem; margin-bottom: 1rem; }}
        .card-title {{ font-size: 1.1rem; margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem; }}
        th {{ color: var(--text-muted); font-size: 0.7rem; text-transform: uppercase; }}
        
        /* 資金分佈圖 */
        .flow-distribution {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 0.75rem;
            margin-bottom: 1rem;
        }}
        .flow-item {{
            text-align: center;
            padding: 1rem;
            border-radius: 8px;
        }}
        .flow-native {{ background: rgba(34, 197, 94, 0.1); border: 1px solid rgba(34, 197, 94, 0.3); }}
        .flow-stable {{ background: rgba(99, 102, 241, 0.1); border: 1px solid rgba(99, 102, 241, 0.3); }}
        .flow-altcoin {{ background: rgba(249, 115, 22, 0.1); border: 1px solid rgba(249, 115, 22, 0.3); }}
        .flow-btc {{ background: rgba(251, 191, 36, 0.1); border: 1px solid rgba(251, 191, 36, 0.3); }}
        .flow-pct {{ font-size: 1.5rem; font-weight: 700; }}
        .flow-label {{ font-size: 0.75rem; color: var(--text-muted); }}
        
        /* 週期比較 */
        .period-compare {{
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 0.5rem;
            padding: 0.75rem;
            background: rgba(255,255,255,0.02);
            border-radius: 8px;
            margin-top: 0.5rem;
        }}
        .period-item {{ text-align: center; }}
        .period-label {{ font-size: 0.65rem; color: var(--text-muted); }}
        .period-value {{ font-size: 0.9rem; font-weight: 600; }}
        
        /* 解讀區 */
        .interpretation {{
            background: linear-gradient(135deg, rgba(99, 102, 241, 0.05), rgba(168, 85, 247, 0.05));
            border-left: 3px solid var(--accent);
            padding: 1rem;
            border-radius: 0 8px 8px 0;
            margin-top: 1rem;
        }}
        
        @media (max-width: 768px) {{
            .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .flow-distribution {{ grid-template-columns: repeat(2, 1fr); }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎛️ 資金流向主控台</h1>
        <p class="timestamp">更新時間: {summary.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <!-- 交易信號燈 -->
        <div class="signal-panel">
            <div class="signal-value">{summary.trading_signal.value}</div>
            <div class="signal-phase">{summary.market_phase.value}</div>
        </div>
        
        <!-- 🎯 戰鬥機駕駛艙 - 核心儀表板 -->
        <div class="card" style="background: linear-gradient(135deg, rgba(239, 68, 68, 0.05), rgba(249, 115, 22, 0.05)); border: 1px solid rgba(239, 68, 68, 0.3); margin-bottom: 1.5rem;">
            <div class="card-title" style="font-size: 1.2rem;">✈️ 戰鬥儀表板 - Combat Dashboard</div>
            
            <!-- 警報區 -->
            {generate_alerts_html(summary.alerts, summary.alert_level)}
            
            <!-- 核心指標網格 -->
            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin: 1rem 0;">
                <!-- 情緒溫度計 -->
                <div style="text-align: center; padding: 1rem; background: rgba(255,255,255,0.03); border-radius: 10px;">
                    <div style="font-size: 0.75rem; color: var(--text-muted);">🌡️ 恐懼/貪婪</div>
                    <div style="font-size: 2rem; font-weight: 700; color: {'var(--green)' if summary.fear_greed_score >= 50 else 'var(--red)'};">{summary.fear_greed_score}</div>
                    <div style="font-size: 0.85rem;">{summary.sentiment_label}</div>
                </div>
                
                <!-- 動量雷達 -->
                <div style="text-align: center; padding: 1rem; background: rgba(255,255,255,0.03); border-radius: 10px;">
                    <div style="font-size: 0.75rem; color: var(--text-muted);">⚡ 動量雷達</div>
                    <div style="font-size: 2rem; font-weight: 700; color: {'var(--green)' if summary.momentum_score > 0 else ('var(--red)' if summary.momentum_score < 0 else 'var(--text-muted)')};">{summary.momentum_score:+d}</div>
                    <div style="font-size: 0.85rem;">{summary.momentum_direction}</div>
                </div>
                
                <!-- 時間緊迫性 -->
                <div style="text-align: center; padding: 1rem; background: rgba(255,255,255,0.03); border-radius: 10px;">
                    <div style="font-size: 0.75rem; color: var(--text-muted);">⏱️ 緊迫程度</div>
                    <div style="font-size: 2rem; font-weight: 700; color: {'var(--red)' if summary.urgency_score >= 7 else ('var(--orange)' if summary.urgency_score >= 4 else 'var(--green)')};">{summary.urgency_score}/10</div>
                    <div style="font-size: 0.75rem; color: var(--text-muted);">{summary.opportunity_window[:15]}...</div>
                </div>
                
                <!-- 資金流速 -->
                <div style="text-align: center; padding: 1rem; background: rgba(255,255,255,0.03); border-radius: 10px;">
                    <div style="font-size: 0.75rem; color: var(--text-muted);">📊 資金流速</div>
                    <div style="font-size: 2rem; font-weight: 700; color: {'var(--green)' if summary.velocity_24h > 0 else 'var(--red)'};">{summary.velocity_24h:+.3f}%</div>
                    <div style="font-size: 0.85rem; color: var(--text-muted);">每小時變化</div>
                </div>
            </div>
            
            <!-- 行動建議區 -->
            <div style="background: rgba(99, 102, 241, 0.1); border-radius: 10px; padding: 1rem; margin-top: 0.5rem;">
                <div style="font-size: 1.1rem; font-weight: 600; margin-bottom: 0.75rem;">🎯 建議行動</div>
                <div style="font-size: 1rem; margin-bottom: 0.75rem;">{summary.primary_action}</div>
                
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-top: 1rem;">
                    <div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.25rem;">📍 倉位建議</div>
                        <div style="font-weight: 600;">{summary.position_suggestion}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.25rem;">⛓️ 關注公鏈</div>
                        <div style="font-weight: 500;">{', '.join(summary.target_chains[:3])}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.25rem;">💰 資產配置</div>
                        <div style="font-weight: 500;">{', '.join(summary.target_assets[:2])}</div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- 總體數據 -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">📊 全市場 TVL</div>
                <div class="stat-value">${summary.total_tvl/1e9:.2f}B</div>
                <div class="stat-change {'positive' if summary.total_tvl_24h_change > 0 else 'negative'}">
                    24H: {summary.total_tvl_24h_change:+.2f}%
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-label">📈 週變化</div>
                <div class="stat-value {'positive' if summary.total_tvl_7d_change > 0 else 'negative'}">{summary.total_tvl_7d_change:+.2f}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">📅 月變化</div>
                <div class="stat-value {'positive' if summary.total_tvl_30d_change > 0 else 'negative'}">{summary.total_tvl_30d_change:+.2f}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">🎯 主要流向</div>
                <div class="stat-value" style="font-size: 1rem;">{summary.dominant_flow_type}</div>
            </div>
        </div>
        
        <!-- 資金分佈 -->
        <div class="card">
            <div class="card-title">💰 全市場資金分佈</div>
            <div class="flow-distribution">
                <div class="flow-item flow-native">
                    <div class="flow-pct" style="color: var(--green);">{summary.global_native_pct:.1f}%</div>
                    <div class="flow-label">🔷 原生幣</div>
                </div>
                <div class="flow-item flow-stable">
                    <div class="flow-pct" style="color: var(--accent);">{summary.global_stablecoin_pct:.1f}%</div>
                    <div class="flow-label">💵 穩定幣</div>
                </div>
                <div class="flow-item flow-altcoin">
                    <div class="flow-pct" style="color: var(--orange);">{summary.global_altcoin_pct:.1f}%</div>
                    <div class="flow-label">🚀 Altcoin</div>
                </div>
                <div class="flow-item flow-btc">
                    <div class="flow-pct" style="color: #fbbf24;">{summary.global_btc_pct:.1f}%</div>
                    <div class="flow-label">🟡 BTC</div>
                </div>
            </div>
            
            <!-- 週期比較 -->
            <div class="period-compare">
                <div class="period-item">
                    <div class="period-label">當前</div>
                    <div class="period-value">穩定幣 {summary.global_stablecoin_pct:.1f}%</div>
                </div>
                <div class="period-item">
                    <div class="period-label">vs 上週</div>
                    <div class="period-value {'positive' if summary.global_stablecoin_pct < summary.last_week_stablecoin_pct else 'negative'}">
                        {summary.global_stablecoin_pct - summary.last_week_stablecoin_pct:+.1f}%
                    </div>
                </div>
                <div class="period-item">
                    <div class="period-label">vs 上月</div>
                    <div class="period-value {'positive' if summary.global_stablecoin_pct < summary.last_month_stablecoin_pct else 'negative'}">
                        {summary.global_stablecoin_pct - summary.last_month_stablecoin_pct:+.1f}%
                    </div>
                </div>
            </div>
            
            <div class="interpretation">
                <strong>💡 大資金動向解讀：</strong><br>
                {whale_targets.get('interpretation', '數據分析中...')}
            </div>
        </div>
        
        <!-- CEX + DEX 整合數據 -->
        {generate_cex_dex_html_section(cex_dex_summary, cex_summary) if cex_dex_summary else ""}
        
        <!-- 公鏈資金週期比較 -->
        <div class="card">
            <div class="card-title">⛓️ 公鏈資金週期比較</div>
            <table>
                <thead>
                    <tr>
                        <th>公鏈</th>
                        <th>TVL</th>
                        <th>24H</th>
                        <th>7D</th>
                        <th>30D</th>
                        <th>流向</th>
                    </tr>
                </thead>
                <tbody>
                    {chain_rows}
                </tbody>
            </table>
        </div>
        
        <!-- 資金轉換追蹤 -->
        <div class="card">
            <div class="card-title">🔄 資金轉換追蹤 (資金以什麼形式流動)</div>
            <table>
                <thead>
                    <tr>
                        <th>公鏈</th>
                        <th>類型</th>
                        <th>方向</th>
                        <th>佔比</th>
                        <th>主要代幣</th>
                    </tr>
                </thead>
                <tbody>
                    {conversion_rows}
                </tbody>
            </table>
        </div>
        
        <!-- 操作建議 -->
        <div class="card">
            <div class="card-title">📋 操作建議</div>
            <div class="interpretation" style="margin-top: 0;">
                <p><strong>當前信號：</strong> {summary.trading_signal.value}</p>
                <p><strong>市場階段：</strong> {summary.market_phase.value}</p>
                <br>
                <p><strong>💡 策略建議：</strong></p>
                <ul style="margin-left: 1.5rem; margin-top: 0.5rem;">
                    {"<li>資金正在流入市場，可考慮增加倉位</li>" if summary.total_tvl_24h_change > 0 else "<li>資金正在流出，建議謹慎操作或減倉</li>"}
                    {"<li>Altcoin 活躍度上升，尋找 Alpha 機會</li>" if summary.global_altcoin_pct > 35 else ""}
                    {"<li>穩定幣佔比上升，避險情緒濃厚</li>" if summary.global_stablecoin_pct > 40 else ""}
                    <li>主要關注: {summary.dominant_inflow_chain} (資金流入最多)</li>
                </ul>
            </div>
        </div>
    </div>
</body>
</html>
    """
    
    return html


# ================= 6. 主程式整合 =================

async def run_command_center_analysis(
    chains: list,
    all_tokens: dict,
    all_flow_analysis: dict,
    cex_data: list
) -> Tuple[CapitalFlowSummary, str]:
    """
    執行資金流向主控台分析
    
    Returns:
        summary: 資金流向摘要
        html_content: HTML 報告內容
    """
    # 初始化增強資料庫
    init_enhanced_database()
    
    # 生成主控台數據
    summary = generate_command_center_data(chains, all_tokens, all_flow_analysis, cex_data)
    
    # 獲取週期比較
    period_comparison = calculate_period_comparison()
    
    # 分析資金轉換
    conversions = analyze_capital_conversion(all_flow_analysis, chains)
    
    # 識別大資金動向
    whale_targets = identify_whale_accumulation_targets(all_flow_analysis)
    
    # ===== CEX 分析和 CEX+DEX 整合 =====
    cex_dex_summary = None
    cex_summary = None
    
    if cex_data:
        # 分析 CEX 資金流向
        cex_flows, cex_summary = analyze_cex_flows(cex_data)
        
        # 生成 CEX+DEX 整合數據
        cex_dex_summary = generate_cex_dex_summary(chains, cex_data, all_flow_analysis)
        
        logger.info(f"🏦 CEX 分析完成: {len(cex_flows)} 個交易所")
        logger.info(f"📊 CEX+DEX 總資金: ${cex_dex_summary.total_market_tvl/1e9:.1f}B")
    
    # ===== 🎯 填充戰鬥機駕駛艙儀表數據 =====
    summary = enrich_cockpit_data(summary, period_comparison, cex_dex_summary)
    logger.info(f"✈️ 戰鬥儀表: 情緒={summary.fear_greed_score}, 動量={summary.momentum_score}, 緊迫={summary.urgency_score}")
    
    # 儲存快照
    save_capital_flow_snapshot(summary)
    
    # 生成 HTML (現在包含 CEX+DEX 和戰鬥儀表)
    html_content = generate_command_center_html(
        summary, period_comparison, conversions, whale_targets,
        cex_dex_summary=cex_dex_summary,
        cex_summary=cex_summary
    )
    
    return summary, html_content


def print_command_center_terminal(summary: CapitalFlowSummary, whale_targets: dict, cex_dex_summary: Optional[CEXDEXSummary] = None):
    """終端機輸出主控台摘要 (含 CEX+DEX)"""
    from colorama import Fore, Style
    
    print(f"\n{Fore.CYAN}{'═'*70}")
    print(f" 🎛️ 資金流向主控台 - Capital Flow Command Center")
    print(f" 🕐 {summary.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═'*70}{Style.RESET_ALL}\n")
    
    # 交易信號
    signal_color = Fore.GREEN if 'BUY' in summary.trading_signal.name else (
        Fore.RED if 'SELL' in summary.trading_signal.name else Fore.YELLOW
    )
    
    print(f" {signal_color}┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓")
    print(f" ┃  🚦 交易信號: {summary.trading_signal.value:<35}┃")
    print(f" ┃  📍 市場階段: {summary.market_phase.value:<35}┃")
    print(f" ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛{Style.RESET_ALL}\n")
    
    # 🎯 戰鬥儀表板摘要
    print(f" {Fore.RED}✈️ 戰鬥儀表板:{Style.RESET_ALL}")
    
    fear_color = Fore.GREEN if summary.fear_greed_score >= 50 else Fore.RED
    momentum_color = Fore.GREEN if summary.momentum_score > 0 else Fore.RED
    urgency_color = Fore.RED if summary.urgency_score >= 7 else (Fore.YELLOW if summary.urgency_score >= 4 else Fore.GREEN)
    
    print(f"    🌡️ 恐懼/貪婪: {fear_color}{summary.fear_greed_score}{Style.RESET_ALL} ({summary.sentiment_label})")
    print(f"    ⚡ 動量雷達: {momentum_color}{summary.momentum_score:+d}{Style.RESET_ALL} ({summary.momentum_direction})")
    print(f"    ⏱️ 緊迫程度: {urgency_color}{summary.urgency_score}/10{Style.RESET_ALL}")
    print(f"    🎯 建議行動: {summary.primary_action}")
    print(f"    📍 倉位建議: {summary.position_suggestion}")
    
    # 警報
    if summary.alerts:
        print(f"\n {Fore.RED}🚨 警報:{Style.RESET_ALL}")
        for alert in summary.alerts[:3]:
            print(f"    {alert}")
    print()
    
    # CEX + DEX 總資金
    if cex_dex_summary:
        print(f" {Fore.YELLOW}🏦 CEX + DEX 整合分析:{Style.RESET_ALL}")
        print(f"    📊 全市場總資金: ${cex_dex_summary.total_market_tvl/1e9:.1f}B")
        
        cex_color = Fore.GREEN if cex_dex_summary.cex_24h_change > 0 else Fore.RED
        dex_color = Fore.GREEN if cex_dex_summary.dex_24h_change > 0 else Fore.RED
        
        print(f"    🏦 CEX: ${cex_dex_summary.cex_total_tvl/1e9:.1f}B ({cex_color}{cex_dex_summary.cex_24h_change:+.2f}%{Style.RESET_ALL}) | 佔比 {cex_dex_summary.cex_share_pct:.1f}%")
        print(f"    ⛓️ DEX: ${cex_dex_summary.dex_total_tvl/1e9:.1f}B ({dex_color}{cex_dex_summary.dex_24h_change:+.2f}%{Style.RESET_ALL}) | 佔比 {cex_dex_summary.dex_share_pct:.1f}%")
        print(f"    💡 {cex_dex_summary.capital_direction}")
        print(f"    📝 {cex_dex_summary.capital_interpretation}")
        print()
    
    # 總體數據
    print(f" {Fore.WHITE}📊 DEX 公鏈概況:{Style.RESET_ALL}")
    tvl_color = Fore.GREEN if summary.total_tvl_24h_change > 0 else Fore.RED
    print(f"    TVL: ${summary.total_tvl/1e9:.2f}B ({tvl_color}{summary.total_tvl_24h_change:+.2f}% 24H{Style.RESET_ALL})")
    
    c7d_color = Fore.GREEN if summary.total_tvl_7d_change > 0 else Fore.RED
    c30d_color = Fore.GREEN if summary.total_tvl_30d_change > 0 else Fore.RED
    print(f"    週期比較: {c7d_color}7D {summary.total_tvl_7d_change:+.2f}%{Style.RESET_ALL} | {c30d_color}30D {summary.total_tvl_30d_change:+.2f}%{Style.RESET_ALL}")
    
    # 資金分佈
    print(f"\n {Fore.WHITE}💰 資金分佈:{Style.RESET_ALL}")
    print(f"    🔷 原生幣: {Fore.GREEN}{summary.global_native_pct:.1f}%{Style.RESET_ALL}")
    print(f"    💵 穩定幣: {Fore.CYAN}{summary.global_stablecoin_pct:.1f}%{Style.RESET_ALL}")
    print(f"    🚀 Altcoin: {Fore.YELLOW}{summary.global_altcoin_pct:.1f}%{Style.RESET_ALL}")
    print(f"    🟡 BTC:     {Fore.YELLOW}{summary.global_btc_pct:.1f}%{Style.RESET_ALL}")
    
    # 大資金動向
    print(f"\n {Fore.MAGENTA}🐋 大資金動向:{Style.RESET_ALL}")
    print(f"    {whale_targets.get('interpretation', '分析中...')}")
    
    # 流入/流出公鏈
    print(f"\n {Fore.WHITE}⛓️ 公鏈資金流向:{Style.RESET_ALL}")
    print(f"    📈 最強流入: {Fore.GREEN}{summary.dominant_inflow_chain}{Style.RESET_ALL}")
    print(f"    📉 最大流出: {Fore.RED}{summary.dominant_outflow_chain}{Style.RESET_ALL}")
    
    print(f"\n{Fore.CYAN}{'═'*70}{Style.RESET_ALL}\n")


if __name__ == "__main__":
    # 測試用
    print("💡 此模組需要與 full_chain_monitor.py 整合使用")
    print("請在 full_chain_monitor.py 中導入此模組")
