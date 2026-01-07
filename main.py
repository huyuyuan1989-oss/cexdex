"""
🚀 Main Pipeline - 資金流向數據管道 v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
功能特色：
- 整合 ChainAnalyzer 和 CEXAnalyzer 執行分析
- 輸出 data.json (即時快照)
- 追加 history.csv (歷史數據供回測)
- 純數據輸出，無 HTML 生成

輸出：
- reports/data.json: 完整快照數據
- reports/history.csv: 歷史追蹤行
"""

import asyncio
import json
import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from data_provider import DataProvider
from analyzer_chain import ChainAnalyzer
from analyzer_cex import CEXAnalyzer
from notification_service import check_and_alert, send_summary_notification

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 輸出路徑
REPORTS_DIR = Path(__file__).parent / "reports"
DATA_JSON_PATH = REPORTS_DIR / "data.json"
HISTORY_CSV_PATH = REPORTS_DIR / "history.csv"

# 分析的公鏈列表
CHAINS_TO_ANALYZE = [
    'ethereum', 'solana', 'bsc', 'arbitrum', 'base',
    'polygon', 'avalanche', 'optimism', 'tron'
]

# CSV 欄位定義
CSV_COLUMNS = [
    'Timestamp',
    'Total_Stablecoin_MarketCap',
    'Binance_Net_Flow',
    'Solana_TVL',
    'Ethereum_TVL'
]


async def run_pipeline() -> Dict[str, Any]:
    """
    執行完整數據管道
    
    Returns:
        聚合後的數據快照
    """
    logger.info("🚀 啟動資金流向數據管道...")
    start_time = datetime.now()
    
    async with DataProvider() as provider:
        # 1. 執行公鏈分析
        logger.info("📊 分析公鏈資金流向...")
        chain_analyzer = ChainAnalyzer(provider)
        chain_data = await chain_analyzer.analyze_multiple_chains(CHAINS_TO_ANALYZE)
        
        # 2. 執行交易所分析
        logger.info("🏦 分析交易所資金流向...")
        cex_analyzer = CEXAnalyzer(provider)
        cex_data = await cex_analyzer.analyze_multiple_exchanges()
        
        # 3. 獲取穩定幣市值
        logger.info("💵 獲取穩定幣市值...")
        stablecoin_marketcap = await _get_stablecoin_marketcap(provider)
    
    # 4. 聚合數據
    timestamp = datetime.now(timezone.utc).isoformat()
    
    snapshot = {
        'timestamp': timestamp,
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'market_sentiment': _determine_overall_sentiment(chain_data, cex_data),
        'chain_flows': chain_data,
        'cex_flows': cex_data,
        'stablecoin_marketcap': stablecoin_marketcap,
        'execution_time_seconds': (datetime.now() - start_time).total_seconds()
    }
    
    # 5. 儲存輸出
    await _save_outputs(snapshot, chain_data, cex_data, stablecoin_marketcap)
    
    # 6. 發送 Discord 通知
    logger.info("🔔 檢查並發送 Discord 警報...")
    alerts_sent = check_and_alert(snapshot)
    if alerts_sent > 0:
        logger.info(f"   → 已發送 {alerts_sent} 個警報")
    
    # 7. 發送摘要通知
    send_summary_notification(snapshot)
    
    logger.info(f"✅ 管道執行完成 ({snapshot['execution_time_seconds']:.2f}s)")
    
    return snapshot


async def _get_stablecoin_marketcap(provider: DataProvider) -> float:
    """
    獲取穩定幣總市值
    """
    try:
        data = await provider.get_stablecoins()
        if data and 'peggedAssets' in data:
            total = 0
            for asset in data['peggedAssets']:
                circulating = asset.get('circulating', {})
                total += circulating.get('peggedUSD', 0) or 0
            return total
    except Exception as e:
        logger.warning(f"無法獲取穩定幣市值: {e}")
    return 0


def _determine_overall_sentiment(chain_data: Dict, cex_data: Dict) -> str:
    """
    綜合判斷市場情緒
    """
    chain_sentiment = chain_data.get('summary', {}).get('market_sentiment', 'Neutral')
    cex_sentiment = cex_data.get('summary', {}).get('market_sentiment', 'Neutral')
    
    # 簡單邏輯：兩者都看漲 -> Bullish，都看跌 -> Bearish，否則 Neutral
    if chain_sentiment == 'Bullish' and cex_sentiment == 'Bullish':
        return 'Bullish'
    elif chain_sentiment == 'Bearish' and cex_sentiment == 'Bearish':
        return 'Bearish'
    elif chain_sentiment == 'Bullish' or cex_sentiment == 'Bullish':
        return 'Slightly Bullish'
    elif chain_sentiment == 'Bearish' or cex_sentiment == 'Bearish':
        return 'Slightly Bearish'
    return 'Neutral'


async def _save_outputs(
    snapshot: Dict, 
    chain_data: Dict, 
    cex_data: Dict, 
    stablecoin_marketcap: float
):
    """
    儲存輸出文件
    """
    # 確保目錄存在
    REPORTS_DIR.mkdir(exist_ok=True)
    
    # 1. 儲存 data.json
    logger.info(f"💾 儲存快照到 {DATA_JSON_PATH}...")
    with open(DATA_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    
    # 2. 追加 history.csv
    logger.info(f"📝 追加歷史記錄到 {HISTORY_CSV_PATH}...")
    _append_history_csv(chain_data, cex_data, stablecoin_marketcap)


def _append_history_csv(chain_data: Dict, cex_data: Dict, stablecoin_marketcap: float):
    """
    追加一行到 history.csv
    """
    # 提取所需數據
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 從 chain_data 提取 Solana 和 Ethereum TVL
    solana_tvl = 0
    ethereum_tvl = 0
    for chain in chain_data.get('chains', []):
        if chain.get('chain') == 'solana':
            solana_tvl = chain.get('tvl_total', 0)
        elif chain.get('chain') == 'ethereum':
            ethereum_tvl = chain.get('tvl_total', 0)
    
    # 從 cex_data 提取 Binance 淨流入
    binance_net_flow = 0
    for exchange in cex_data.get('exchanges', []):
        if exchange.get('exchange') == 'binance-cex':
            binance_net_flow = exchange.get('net_flow_24h', 0)
            break
    
    # 構建行數據
    row = {
        'Timestamp': timestamp,
        'Total_Stablecoin_MarketCap': stablecoin_marketcap,
        'Binance_Net_Flow': binance_net_flow,
        'Solana_TVL': solana_tvl,
        'Ethereum_TVL': ethereum_tvl
    }
    
    # 檢查 CSV 是否存在
    file_exists = HISTORY_CSV_PATH.exists()
    
    with open(HISTORY_CSV_PATH, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        
        # 如果文件不存在，寫入標題行
        if not file_exists:
            writer.writeheader()
        
        writer.writerow(row)
    
    logger.info(f"   → 已追加: Stablecoin ${stablecoin_marketcap/1e9:.1f}B, "
                f"Binance Flow ${binance_net_flow/1e6:+.1f}M, "
                f"SOL TVL ${solana_tvl/1e9:.1f}B, ETH TVL ${ethereum_tvl/1e9:.1f}B")


def main():
    """
    主入口
    """
    print("=" * 60)
    print("🚀 資金流向數據管道 (Capital Flow Pipeline)")
    print("=" * 60)
    
    snapshot = asyncio.run(run_pipeline())
    
    print("\n" + "=" * 60)
    print("📊 執行結果摘要")
    print("=" * 60)
    print(f"   市場情緒: {snapshot['market_sentiment']}")
    print(f"   穩定幣市值: ${snapshot['stablecoin_marketcap']/1e9:.1f}B")
    print(f"   分析公鏈數: {len(snapshot['chain_flows'].get('chains', []))}")
    print(f"   分析交易所數: {len(snapshot['cex_flows'].get('exchanges', []))}")
    print(f"   執行時間: {snapshot['execution_time_seconds']:.2f}s")
    print("=" * 60)
    print(f"📁 輸出文件:")
    print(f"   → {DATA_JSON_PATH}")
    print(f"   → {HISTORY_CSV_PATH}")
    print("=" * 60)


if __name__ == '__main__':
    main()
