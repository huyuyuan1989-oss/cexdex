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
from report_generator import ReportGenerator
from paper_trader import PaperTrader
from analyzer_social import SocialSentimentAnalyzer 
from market_agents import HiveMind # V7 Feature
from rl_optimizer import RLOptimizer # V7 RL Core
from yield_farmer import YieldFarmer # V7 Omni-Chain Yield

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
    執行完整數據管道 (End-to-End Pipeline)
    """
    start_time = datetime.now()
    logger.info("🚀 啟動資金流向數據管道...")
    
    # 初始化組件
    provider = DataProvider()
    analyzer_chain = ChainAnalyzer(provider)
    analyzer_cex = CEXAnalyzer(provider)
    generator = ReportGenerator()
    social_analyzer = SocialSentimentAnalyzer() # V5
    paper_trader = PaperTrader(provider) # V6 Simulation
    hive_mind = HiveMind() # V7
    rl_optimizer = RLOptimizer()
    yield_farmer = YieldFarmer()
    
    async with provider:
        # 1. 並行獲取數據
        logger.info("📊 分析公鏈資金流向...")
        chain_task = analyzer_chain.analyze_multiple_chains(CHAINS_TO_ANALYZE)
        
        logger.info("🏦 分析交易所資金流向...")
        cex_task = analyzer_cex.analyze_multiple_exchanges()
        
        # 並行執行主要分析任務
        chain_data, cex_data = await asyncio.gather(chain_task, cex_task)
        
        # 2. 獲取輔助數據
        logger.info("💵 獲取穩定幣市值...")
        stablecoin_data = await provider.get_stablecoins()
        if stablecoin_data and 'peggedAssets' in stablecoin_data:
            stablecoin_marketcap = sum(a.get('circulating', {}).get('peggedUSD', 0) or 0 for a in stablecoin_data['peggedAssets'])
        else:
            stablecoin_marketcap = 0
            
        logger.info("📈 獲取衍生品數據 (Funding/OI)...")
        derivs_data = await provider.get_derivatives_data() 
        
        logger.info("😨 獲取恐慌貪婪指數...")
        fng_data = await provider.fetch_fear_greed_index()

        # 3. [V5 Feature] Social Sentiment Analysis
        logger.info("🐦 V5 Intelligence: Analyzing Social Sentiment...")
        tokens_to_analyze = set()
        for chain in chain_data.get('chains', []):
            if 'top_protocols' in chain:
                for p in chain['top_protocols']:
                    if p.get('symbol'):
                        tokens_to_analyze.add(p['symbol'])
        
        social_map = {}
        for token in tokens_to_analyze:
            sentiment = await social_analyzer.analyze_token_sentiment(token)
            social_map[token] = sentiment
            if sentiment['score'] > 60:
                logger.info(f"   🔥 Hot Sentiment detected for {token}: {sentiment['narrative']}")

        # 4. 生成統一報告
        logger.info("📝 生成統一分析報告...")
        unified_report = generator.generate_unified_report(
            chain_data=chain_data, 
            cex_data=cex_data, 
            stablecoin_marketcap=stablecoin_marketcap,
            derivs_data=derivs_data,
            fng_data=fng_data,
            social_data=social_map # Pass V5 Intel
        )
        unified_report['meta']['execution_time_seconds'] = (datetime.now() - start_time).total_seconds()
        
        # 5. [V7 Feature] The Hive Mind Debate
        if 'alpha_opportunities' in unified_report:
            logger.info("🧠 V7 Hive Mind: Running Agent Debate...")
            
            # Prepare Global Context
            context = {
                'fng_val': fng_data.get('value', 50),
                'funding_btc': derivs_data.get('funding_rates', {}).get('BTC', 0)
            }
            
            for opp in unified_report['alpha_opportunities']:
                debate_result = hive_mind.debate(opp, context)
                opp['hive_analysis'] = debate_result # Inject V7 Result
                
        
        # 6. [V6 Feature] Paper Trading Simulation
        logger.info("🤖 執行模擬交易引擎 (Paper Trading)...")
        await paper_trader.update_positions() # Update PnL for dirty positions
        
        # 6.1 [V7 Feature] RL Core Optimization
        # Run optimization *after* updating positions to learn from latest PnL
        rl_optimizer.run_optimization()
        
        if 'alpha_opportunities' in unified_report:
            await paper_trader.execute_signals(unified_report['alpha_opportunities'])
            
        # 6.2 [V7 Feature] Yield Farming
        active_pos_count = len([p for p in paper_trader.positions if p['status'] == 'OPEN'])
        yield_data = yield_farmer.optimize_idle_capital(active_pos_count)
        unified_report['yield_farming'] = yield_data
    
    # 7. 儲存輸出
    await _save_outputs(unified_report, chain_data, cex_data, stablecoin_marketcap)
    
    # 8. 發送 Discord 通知
    logger.info("🔔 檢查並發送 Discord 警報...")
    alerts_sent = check_and_alert(unified_report)
    if alerts_sent > 0:
        logger.info(f"   → 已發送 {alerts_sent} 個警報")
    
    # 8. 發送摘要通知
    send_summary_notification(unified_report)
    
    logger.info(f"✅ 管道執行完成 ({unified_report['meta']['execution_time_seconds']:.2f}s)")
    
    return unified_report


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


def _calculate_sentiment_score(
    chain_data: Dict, 
    cex_data: Dict, 
    derivs_data: Dict = None, 
    fng_data: Dict = None
) -> Dict[str, Any]:
    """
    加權情緒評分系統 V3 (AI Weighted Model)
    包含: Smart Money Flow, Derivatives Structure, Macro Sentiment
    """
    derivs_data = derivs_data or {}
    fng_data = fng_data or {}
    factors = []
    total_score = 0
    
    # 1. Smart Money Flow (權重 40%) - 最重要指標
    sm_flow = cex_data.get('summary', {}).get('smart_money_stable_flow', 0)
    score_sm = 0
    if sm_flow > 50_000_000: score_sm = 100    # Strong Buy
    elif sm_flow > 10_000_000: score_sm = 75   # Buy
    elif sm_flow > 0: score_sm = 25            # Weak Buy
    elif sm_flow < -50_000_000: score_sm = -100 # Strong Sell
    elif sm_flow < -10_000_000: score_sm = -75  # Sell
    elif sm_flow < 0: score_sm = -25            # Weak Sell
    
    total_score += score_sm * 0.4
    factors.append({
        'name': '主力動向 (Smart Money)',
        'score': score_sm,
        'weight': '40%',
        'value': f"${sm_flow/1e6:+.1f}M"
    })
    
    # 2. Derivatives Structure (權重 30%)
    funding_btc = derivs_data.get('funding_rates', {}).get('BTC', 0.01)
    score_derivs = 0
    if funding_btc > 0.03: score_derivs = -80      # 極度過熱
    elif funding_btc > 0.01: score_derivs = -40    # 偏多過熱
    elif funding_btc < -0.01: score_derivs = 60    # 軋空預期
    elif funding_btc < -0.02: score_derivs = 90    # 強烈軋空預期
    else: score_derivs = 10                        # 中性偏多 (健康費率)
    
    total_score += score_derivs * 0.3
    factors.append({
        'name': '合約結構 (Derivatives)',
        'score': score_derivs,
        'weight': '30%',
        'value': f"Funding {funding_btc*100:.4f}%"
    })
    
    # 3. Chain Activity (20%)
    chain_summary = chain_data.get('summary', {})
    chain_flow = chain_summary.get('stablecoin_flow_24h', 0)
    score_chain = 0
    if chain_flow > 20_000_000: score_chain = 100
    elif chain_flow > 0: score_chain = 50
    else: score_chain = -50
    
    total_score += score_chain * 0.2
    factors.append({
        'name': '公鏈生態 (On-chain)',
        'score': score_chain,
        'weight': '20%',
        'value': f"${chain_flow/1e6:+.1f}M"
    })
    
    # 4. Macro Sentiment (Contra) (10%)
    fng_val = fng_data.get('value', 50)
    score_macro = 0
    # 逆勢邏輯: 極度恐慌(20)是買點(+80分)
    if fng_val < 20: score_macro = 80       
    elif fng_val < 40: score_macro = 40     
    elif fng_val > 80: score_macro = -80    
    elif fng_val > 60: score_macro = -40    
    
    total_score += score_macro * 0.1
    factors.append({
        'name': '市場情緒 (Sentiment)',
        'score': score_macro,
        'weight': '10%',
        'value': f"F&G {fng_val}"
    })
    
    # 最終評級
    label = 'Neutral'
    if total_score >= 60: label = 'Strong Bullish 🚀'
    elif total_score >= 20: label = 'Bullish 🟢'
    elif total_score <= -60: label = 'Strong Bearish 🩸'
    elif total_score <= -20: label = 'Bearish 🔴'
    
    return {
        'score': round(total_score, 1),
        'label': label,
        'factors': factors
    }


def _determine_overall_sentiment(chain_data: Dict, cex_data: Dict) -> str:
    """
    綜合判斷市場情緒 (向後兼容包裝函數)
    """
    result = _calculate_sentiment_score(chain_data, cex_data)
    return result['label']


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
    # V2 Schema Output
    try:
        print(f"   市場情緒: {snapshot['market_overview']['sentiment']['label']}")
        print(f"   穩定幣市值: ${snapshot['market_overview']['stablecoin_marketcap']/1e9:.1f}B")
        print(f"   分析公鏈數: {snapshot['market_overview']['total_tvl']['dex']:.0f} (Total TVL)") # Simplify print
        print(f"   分析交易所數: {snapshot['cex_analysis']['summary']['exchange_count']}")
    except KeyError:
        # Fallback for older schema or partial data
        print("   (Summary data format changed, check data.json)")
    
    print(f"   執行時間: {snapshot['meta']['execution_time_seconds']:.2f}s")
    print("=" * 60)
    print("📁 輸出文件:")
    print(f"   → {DATA_JSON_PATH}")
    print(f"   → {HISTORY_CSV_PATH}")
    print("=" * 60)


if __name__ == '__main__':
    main()
