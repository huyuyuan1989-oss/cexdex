"""
🏦 CEXAnalyzer - 交易所資金流向分析模組 v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
功能特色：
- 計算交易所 24H 淨流入/流出
- 區分 Stablecoin Flow vs BTC/ETH Flow
- 返回結構化信號標籤 (Accumulation / Dump Risk / Withdrawal)

依賴：data_provider.DataProvider
輸出：結構化 Dictionary (可直接 JSON 輸出)
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from data_provider import DataProvider

logger = logging.getLogger(__name__)


class CEXAnalyzer:
    """
    中心化交易所資金流向分析器
    
    核心功能：
    - 從 DefiLlama Protocol API 獲取交易所資產明細
    - 區分穩定幣與 BTC/ETH 的流入/流出
    - 生成買入/拋售風險信號標籤
    """
    
    # 穩定幣清單
    STABLECOINS = {
        'USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'BUSD', 'USDD',
        'PYUSD', 'GUSD', 'LUSD', 'FRAX', 'USDP', 'USDE', 'CRVUSD'
    }
    
    # 主要資產 (BTC/ETH 相關)
    MAJOR_ASSETS = {
        'BTC', 'ETH', 'WBTC', 'WETH', 'STETH', 'RETH', 'CBETH', 'WSTETH'
    }
    
    # 預設分析的交易所
    DEFAULT_EXCHANGES = [
        'binance-cex', 'okx', 'bitfinex', 'coinbase', 'kraken',
        'bybit', 'kucoin', 'gate-io', 'htx', 'crypto-com'
    ]
    
    # 信號閾值
    THRESHOLDS = {
        'stablecoin_inflow_bullish': 50_000_000,    # $50M
        'btc_eth_inflow_bearish': 100_000_000,      # $100M
        'significant_flow': 10_000_000,             # $10M
    }
    
    def __init__(self, provider: DataProvider):
        """
        初始化 CEXAnalyzer
        
        Args:
            provider: DataProvider 實例 (需已通過 context manager 啟動)
        """
        self.provider = provider
    
    async def analyze_exchange(self, slug: str) -> Dict[str, Any]:
        """
        分析單一交易所的資金流向 (增強版 - 多時間週期)
        
        Args:
            slug: 交易所 slug (例如 'binance-cex', 'okx')
        
        Returns:
            結構化分析結果 (包含 24H 和估算的 4H 流向)
        """
        result = {
            'exchange': slug,
            'total_tvl': 0,
            # 24H 數據 (原有)
            'net_flow_24h': 0,
            'stablecoin_flow_24h': 0,
            'btc_eth_flow_24h': 0,
            'other_flow_24h': 0,
            # 4H 數據 (新增 - 估算)
            'net_flow_4h': 0,
            'stablecoin_flow_4h': 0,
            'btc_eth_flow_4h': 0,
            # 元數據
            'stablecoin_pct': 0,
            'asset_breakdown': {},
            'tags': [],
            'confidence_score': 0,  # 0-100 數據可信度
            'error': None
        }
        
        try:
            # 獲取交易所詳細資產數據
            detail = await self.provider.get_protocol_detail(slug)
            
            if not detail:
                result['error'] = 'Failed to fetch protocol detail'
                result['confidence_score'] = 0
                return result
            
            if 'tokensInUsd' not in detail or not detail['tokensInUsd']:
                result['error'] = 'No token data available'
                result['confidence_score'] = 0
                return result
            
            # 獲取當前與 24H 前的數據
            history = detail['tokensInUsd']
            
            if len(history) < 2:
                result['error'] = 'Insufficient historical data'
                result['confidence_score'] = 20
                return result
            
            current = history[-1]
            previous = self._find_closest_record(history, current['date'] - 86400)
            
            if not previous:
                previous = history[-2] if len(history) >= 2 else current
            
            # 計算資產明細
            current_tokens = current.get('tokens', {})
            previous_tokens = previous.get('tokens', {})
            
            current_total = sum(current_tokens.values())
            previous_total = sum(previous_tokens.values())
            
            result['total_tvl'] = current_total
            result['net_flow_24h'] = current_total - previous_total
            
            # 分類計算各資產類型的流向
            flows = self._calculate_asset_flows(current_tokens, previous_tokens)
            
            result['stablecoin_flow_24h'] = flows['stablecoin']
            result['btc_eth_flow_24h'] = flows['btc_eth']
            result['other_flow_24h'] = flows['other']
            result['asset_breakdown'] = flows['breakdown']
            
            # === 4H 流向估算 (24H 的 ~25%) ===
            # 由於 DefiLlama 只提供每日數據，4H 使用比例估算
            result['net_flow_4h'] = result['net_flow_24h'] * 0.25
            result['stablecoin_flow_4h'] = result['stablecoin_flow_24h'] * 0.25
            result['btc_eth_flow_4h'] = result['btc_eth_flow_24h'] * 0.25
            
            # 計算穩定幣佔比
            stable_total = sum(v for k, v in current_tokens.items() 
                              if self._is_stablecoin(k))
            result['stablecoin_pct'] = (stable_total / current_total * 100) if current_total > 0 else 0
            
            # 計算數據可信度
            data_age_hours = (int(datetime.now().timestamp()) - current['date']) / 3600 if 'date' in current else 999
            confidence = 100
            if data_age_hours > 24:
                confidence -= 30  # 數據超過 24 小時
            if data_age_hours > 48:
                confidence -= 30  # 數據超過 48 小時
            if len(current_tokens) < 5:
                confidence -= 20  # 資產種類太少
            result['confidence_score'] = max(0, confidence)
            
            # 生成信號標籤
            result['tags'] = self._generate_tags(
                result['stablecoin_flow_24h'],
                result['btc_eth_flow_24h'],
                result['net_flow_24h']
            )
            
        except Exception as e:
            logger.error(f"CEX analysis error for {slug}: {e}")
            result['error'] = str(e)
            result['confidence_score'] = 0
        
        return result
    
    def _find_closest_record(self, history: List[Dict], target_ts: int) -> Optional[Dict]:
        """
        找到最接近目標時間戳的記錄
        """
        closest = None
        min_diff = 86400 * 3  # 容許 3 天誤差
        
        for record in reversed(history):
            diff = abs(record['date'] - target_ts)
            if diff < min_diff:
                min_diff = diff
                closest = record
            if record['date'] < target_ts - 86400 * 3:
                break
        
        return closest
    
    def _is_stablecoin(self, symbol: str) -> bool:
        """判斷是否為穩定幣"""
        return symbol in self.STABLECOINS or 'USD' in symbol.upper()
    
    def _is_major_asset(self, symbol: str) -> bool:
        """判斷是否為主要資產 (BTC/ETH)"""
        return symbol in self.MAJOR_ASSETS
    
    def _calculate_asset_flows(
        self, 
        current: Dict[str, float], 
        previous: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        計算各資產類型的流向
        
        Returns:
            {
                'stablecoin': float,
                'btc_eth': float,
                'other': float,
                'breakdown': [{symbol, flow, category}, ...]
            }
        """
        stablecoin_flow = 0
        btc_eth_flow = 0
        other_flow = 0
        breakdown = []
        
        all_symbols = set(current.keys()) | set(previous.keys())
        
        for symbol in all_symbols:
            curr_val = current.get(symbol, 0)
            prev_val = previous.get(symbol, 0)
            flow = curr_val - prev_val
            
            # 過濾小金額變動
            if abs(flow) < 100_000:  # < $100K
                continue
            
            if self._is_stablecoin(symbol):
                stablecoin_flow += flow
                category = 'stablecoin'
            elif self._is_major_asset(symbol):
                btc_eth_flow += flow
                category = 'btc_eth'
            else:
                other_flow += flow
                category = 'other'
            
            breakdown.append({
                'symbol': symbol,
                'flow': flow,
                'category': category,
                'current_value': curr_val
            })
        
        # 按流量絕對值排序
        breakdown.sort(key=lambda x: abs(x['flow']), reverse=True)
        
        return {
            'stablecoin': stablecoin_flow,
            'btc_eth': btc_eth_flow,
            'other': other_flow,
            'breakdown': breakdown[:10]  # Top 10
        }
    
    def _generate_tags(
        self, 
        stablecoin_flow: float, 
        btc_eth_flow: float,
        net_flow: float
    ) -> List[Dict[str, str]]:
        """
        根據資金流向生成信號標籤
        
        Returns:
            標籤列表 [{type, signal, reason}, ...]
        """
        tags = []
        
        # 穩定幣大量流入 -> 累積買盤
        if stablecoin_flow > self.THRESHOLDS['stablecoin_inflow_bullish']:
            tags.append({
                'type': 'Accumulation',
                'signal': 'Bullish',
                'reason': f'Stablecoin inflow ${stablecoin_flow/1e6:.1f}M - potential buying power'
            })
        
        # BTC/ETH 大量流入 -> 潛在拋售風險
        if btc_eth_flow > self.THRESHOLDS['btc_eth_inflow_bearish']:
            tags.append({
                'type': 'Potential Dump Risk',
                'signal': 'Bearish',
                'reason': f'BTC/ETH inflow ${btc_eth_flow/1e6:.1f}M - may indicate selling intent'
            })
        
        # 穩定幣流出 + BTC/ETH 流出 -> 提幣囤貨
        if stablecoin_flow < -self.THRESHOLDS['significant_flow'] and btc_eth_flow < -self.THRESHOLDS['significant_flow']:
            tags.append({
                'type': 'Withdrawal',
                'signal': 'Bullish',
                'reason': 'Both stablecoins and BTC/ETH withdrawing - accumulation signal'
            })
        
        # 淨流出 -> 提幣
        if net_flow < -self.THRESHOLDS['significant_flow'] * 5:
            tags.append({
                'type': 'Net Outflow',
                'signal': 'Neutral',
                'reason': f'Net outflow ${abs(net_flow)/1e6:.1f}M'
            })
        
        # 淨流入 -> 存幣
        if net_flow > self.THRESHOLDS['significant_flow'] * 5:
            tags.append({
                'type': 'Net Inflow',
                'signal': 'Neutral',
                'reason': f'Net inflow ${net_flow/1e6:.1f}M'
            })
        
        return tags
    
    async def analyze_multiple_exchanges(
        self, 
        slugs: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        批量分析多個交易所 (V2: Integrated Smart Money Filter)
        """
        # Tier 1 Whitelist (Institutional Grade)
        TIER_1_EXCHANGES = {'binance-cex', 'coinbase', 'kraken', 'okx', 'bybit', 'bitfinex'}
        
        if slugs is None:
            # 從 protocols API 獲取 CEX 列表
            cex_list = await self.provider.get_cex_protocols(min_tvl=100_000_000)
            slugs = [c['slug'] for c in cex_list[:20]]  # Analyze Top 20 to catch more signals
        
        tasks = [self.analyze_exchange(slug) for slug in slugs]
        results = await asyncio.gather(*tasks)
        
        # 過濾有效結果
        valid_results = [r for r in results if not r.get('error')]
        
        # 1. 基礎摘要 (All Exchanges)
        total_stablecoin_flow = sum(r.get('stablecoin_flow_24h', 0) for r in valid_results)
        total_btc_eth_flow = sum(r.get('btc_eth_flow_24h', 0) for r in valid_results)
        total_net_flow = sum(r.get('net_flow_24h', 0) for r in valid_results)
        
        # 2. Smart Money Filtering (Tier 1 Only)
        tier1_results = [r for r in valid_results if r['exchange'] in TIER_1_EXCHANGES]
        smart_money_flow = sum(r.get('stablecoin_flow_24h', 0) for r in tier1_results)
        
        bullish_count = sum(1 for r in valid_results 
                          for t in r.get('tags', []) 
                          if t.get('signal') == 'Bullish')
        bearish_count = sum(1 for r in valid_results 
                          for t in r.get('tags', []) 
                          if t.get('signal') == 'Bearish')
        
        return {
            'exchanges': results,
            'summary': {
                'total_stablecoin_flow_24h': total_stablecoin_flow,
                'total_btc_eth_flow_24h': total_btc_eth_flow,
                'total_net_flow_24h': total_net_flow,
                # New Smart Money Metrics
                'smart_money_stable_flow': smart_money_flow,
                'smart_money_dominance': smart_money_flow / total_stablecoin_flow if total_stablecoin_flow != 0 else 0,
                
                'bullish_signals': bullish_count,
                'bearish_signals': bearish_count,
                'market_sentiment': 'Bullish' if bullish_count > bearish_count else 
                                   'Bearish' if bearish_count > bullish_count else 'Neutral'
            }
        }


# ================= 測試入口 =================

async def test():
    """驗證測試"""
    import json
    
    print("=" * 60)
    print("🧪 CEXAnalyzer 驗證測試")
    print("=" * 60)
    
    async with DataProvider() as provider:
        analyzer = CEXAnalyzer(provider)
        
        # 測試單一交易所分析
        print("\n[1/2] 測試單一交易所分析 (Binance)...")
        result = await analyzer.analyze_exchange('binance-cex')
        
        if result and not result.get('error'):
            print(f"   ✅ 成功！")
            print(f"      TVL: ${result['total_tvl']/1e9:.2f}B")
            print(f"      Net Flow 24H: ${result['net_flow_24h']/1e6:+.1f}M")
            print(f"      Stablecoin Flow: ${result['stablecoin_flow_24h']/1e6:+.1f}M")
            print(f"      BTC/ETH Flow: ${result['btc_eth_flow_24h']/1e6:+.1f}M")
            print(f"      Tags: {[t['type'] for t in result['tags']]}")
        else:
            print(f"   ❌ 失敗: {result.get('error')}")
        
        # 測試多交易所分析
        print("\n[2/2] 測試多交易所分析 (Top CEXs)...")
        multi_result = await analyzer.analyze_multiple_exchanges()
        
        if multi_result and multi_result.get('exchanges'):
            valid = sum(1 for e in multi_result['exchanges'] if not e.get('error'))
            print(f"   ✅ 成功！分析了 {valid} 個交易所")
            print(f"      總穩定幣流向: ${multi_result['summary']['total_stablecoin_flow_24h']/1e6:+.1f}M")
            print(f"      總 BTC/ETH 流向: ${multi_result['summary']['total_btc_eth_flow_24h']/1e6:+.1f}M")
            print(f"      市場情緒: {multi_result['summary']['market_sentiment']}")
        else:
            print("   ❌ 失敗")
        
        # 驗證 JSON 序列化
        print("\n[驗證] JSON 序列化...")
        try:
            json_output = json.dumps(result, indent=2)
            print(f"   ✅ JSON 輸出正常 ({len(json_output)} bytes)")
        except Exception as e:
            print(f"   ❌ JSON 序列化失敗: {e}")
    
    print("\n" + "=" * 60)
    print("🎉 CEXAnalyzer 測試完成")
    print("=" * 60)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test())
