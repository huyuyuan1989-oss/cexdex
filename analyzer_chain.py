"""
📊 ChainAnalyzer - 公鏈資金流向分析模組 v1.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
功能特色：
- 區分 Stablecoin TVL vs Volatile TVL
- 計算 stable_inflow_24h / native_inflow_24h
- 返回結構化信號標籤 (Buying Power / Asset Rotation / Capital Flight)

依賴：data_provider.DataProvider
輸出：結構化 Dictionary (可直接 JSON 輸出)
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from data_provider import DataProvider

logger = logging.getLogger(__name__)


class ChainAnalyzer:
    """
    公鏈 TVL 分析器
    
    核心功能：
    - 從歷史 TVL 數據計算資金流向
    - 區分穩定幣與波動性資產的流入/流出
    - 生成買盤/賣壓信號標籤
    """
    
    # 穩定幣標識符 (用於區分穩定幣 TVL)
    STABLECOINS = {
        'USDT', 'USDC', 'DAI', 'FDUSD', 'TUSD', 'BUSD', 'USDD', 
        'PYUSD', 'GUSD', 'LUSD', 'FRAX', 'USDP', 'USDE', 'CRVUSD'
    }
    
    def __init__(self, provider: DataProvider):
        """
        初始化 ChainAnalyzer
        
        Args:
            provider: DataProvider 實例 (需已通過 context manager 啟動)
        """
        self.provider = provider
    
    async def analyze_chain(self, chain_name: str) -> Dict[str, Any]:
        """
        分析單一公鏈的 TVL 資金流向 (多時間週期版本)
        
        Args:
            chain_name: 公鏈名稱 (例如 'ethereum', 'bsc', 'solana')
        
        Returns:
            結構化分析結果 (包含 24H/4H/7D 多時間週期數據)
        """
        result = {
            'chain': chain_name,
            'tvl_total': 0,
            'tvl_stable': 0,
            'tvl_volatile': 0,
            # 24H 數據 (原有)
            'stable_inflow_24h': 0,
            'native_inflow_24h': 0,
            'change_24h_pct': 0,
            # 4H 數據 (新增)
            'stable_inflow_4h': 0,
            'native_inflow_4h': 0,
            'change_4h_pct': 0,
            # 7D 數據 (新增)
            'stable_inflow_7d': 0,
            'native_inflow_7d': 0,
            'change_7d_pct': 0,
            # 分析標籤
            'tags': [],
            'confidence_score': 0,  # 0-100 數據可信度
            'error': None
        }
        
        try:
            # 獲取歷史 TVL 數據
            tvl_data = await self.provider.get_chain_tvl(chain_name)
            
            if not tvl_data or len(tvl_data) < 2:
                result['error'] = 'Insufficient TVL data'
                result['confidence_score'] = 0
                return result
            
            # 計算數據點 (DefiLlama 通常每天一個數據點)
            current = tvl_data[-1]
            current_tvl = current.get('tvl', 0)
            result['tvl_total'] = current_tvl
            
            # 估算每個數據點的時間間隔 (假設每日一個點)
            data_len = len(tvl_data)
            
            # === 24H 計算 (1天前) ===
            if data_len >= 2:
                prev_24h = tvl_data[-2]
                prev_24h_tvl = prev_24h.get('tvl', 0)
                if prev_24h_tvl > 0:
                    change_24h = current_tvl - prev_24h_tvl
                    result['change_24h_pct'] = round((change_24h / prev_24h_tvl) * 100, 2)
            
            # === 4H 計算 (近似: 使用 24H 的 1/6) ===
            # 由於 DefiLlama 只有每日數據，4H 使用 24H 變動的比例估算
            if result['change_24h_pct'] != 0:
                # 假設 4H 是 24H 變動的 ~20-30% (市場波動通常非線性)
                result['change_4h_pct'] = round(result['change_24h_pct'] * 0.25, 2)
            
            # === 7D 計算 (7天前) ===
            if data_len >= 8:
                prev_7d = tvl_data[-8]
                prev_7d_tvl = prev_7d.get('tvl', 0)
                if prev_7d_tvl > 0:
                    change_7d = current_tvl - prev_7d_tvl
                    result['change_7d_pct'] = round((change_7d / prev_7d_tvl) * 100, 2)
            
            # 估算穩定幣比例
            stable_ratio = await self._estimate_stable_ratio(chain_name)
            
            result['tvl_stable'] = current_tvl * stable_ratio
            result['tvl_volatile'] = current_tvl * (1 - stable_ratio)
            
            # 計算各時間週期的穩定幣與原生資產流入
            total_inflow_24h = current_tvl - (tvl_data[-2].get('tvl', current_tvl) if data_len >= 2 else current_tvl)
            result['stable_inflow_24h'] = total_inflow_24h * stable_ratio
            result['native_inflow_24h'] = total_inflow_24h * (1 - stable_ratio)
            
            # 4H 流入 (估算)
            result['stable_inflow_4h'] = result['stable_inflow_24h'] * 0.25
            result['native_inflow_4h'] = result['native_inflow_24h'] * 0.25
            
            # 7D 流入
            if data_len >= 8:
                total_inflow_7d = current_tvl - tvl_data[-8].get('tvl', current_tvl)
                result['stable_inflow_7d'] = total_inflow_7d * stable_ratio
                result['native_inflow_7d'] = total_inflow_7d * (1 - stable_ratio)
            
            # 計算數據可信度 (基於數據完整性)
            confidence = 100
            if data_len < 8:
                confidence -= 30  # 缺少 7D 數據
            if data_len < 2:
                confidence -= 50  # 缺少 24H 數據
            result['confidence_score'] = max(0, confidence)
            
            # 生成信號標籤 (使用增強版)
            result['tags'] = self._generate_tags_enhanced(
                result['stable_inflow_24h'],
                result['native_inflow_24h'],
                result['change_24h_pct'],
                result['change_7d_pct'],
                current_tvl
            )
            
            # 5. [V4 Feature] Deep Dive: 如果信號強烈，抓取該鏈的頭部協議
            # 觸發條件: 24H 穩定幣流入 > 5M (代表有實質資金進場)
            if result.get('stable_inflow_24h', 0) > 5_000_000:
                logger.info(f"🕵️ V4 Deep Dive: Fetching protocols for {chain_name}...")
                top_protocols = await self.provider.get_top_protocols_on_chain(chain_name)
                result['top_protocols'] = top_protocols
            
        except Exception as e:
            logger.error(f"Chain analysis error for {chain_name}: {e}")
            result['error'] = str(e)
            result['confidence_score'] = 0
        
        return result
    
    async def _estimate_stable_ratio(self, chain_name: str) -> float:
        """
        估算鏈上穩定幣佔比
        
        使用 DefiLlama Stablecoins API 獲取鏈上穩定幣供應量
        
        Returns:
            穩定幣佔總 TVL 的比例 (0.0 - 1.0)
        """
        try:
            stablecoin_data = await self.provider.get_stablecoins()
            
            if not stablecoin_data or 'peggedAssets' not in stablecoin_data:
                return 0.3  # 預設估算值
            
            # 計算該鏈的穩定幣總量
            chain_stable_supply = 0
            chain_map = {
                'ethereum': 'Ethereum',
                'bsc': 'BSC',
                'tron': 'Tron',
                'arbitrum': 'Arbitrum',
                'polygon': 'Polygon',
                'avalanche': 'Avalanche',
                'solana': 'Solana',
                'base': 'Base',
                'optimism': 'Optimism'
            }
            
            target_chain = chain_map.get(chain_name.lower(), chain_name)
            
            for asset in stablecoin_data['peggedAssets']:
                chain_data = asset.get('chainCirculating', {})
                if target_chain in chain_data:
                    chain_stable_supply += chain_data[target_chain].get('current', {}).get('peggedUSD', 0)
            
            # 獲取鏈 TVL
            chains = await self.provider.get_chains()
            chain_tvl = 0
            if chains:
                for c in chains:
                    if c.get('name', '').lower() == chain_name.lower():
                        chain_tvl = c.get('tvl', 0)
                        break
            
            if chain_tvl > 0 and chain_stable_supply > 0:
                ratio = min(chain_stable_supply / chain_tvl, 0.8)  # 上限 80%
                return ratio
            
        except Exception as e:
            logger.debug(f"Stable ratio estimation failed: {e}")
        
        return 0.3  # 預設估算值
    
    def _generate_tags(
        self, 
        stable_inflow: float, 
        native_inflow: float,
        change_pct: float
    ) -> List[Dict[str, str]]:
        """
        根據資金流向生成信號標籤 (基礎版本，保留向後兼容)
        
        Returns:
            標籤列表 [{type, signal}, ...]
        """
        tags = []
        
        # 主要信號判斷
        if stable_inflow > 0 and stable_inflow > native_inflow:
            tags.append({
                'type': 'Buying Power',
                'signal': 'Bullish',
                'reason': 'Stablecoin inflow dominant - potential buying pressure'
            })
        elif native_inflow > 0 and native_inflow > stable_inflow:
            tags.append({
                'type': 'Asset Rotation',
                'signal': 'Neutral',
                'reason': 'Native asset inflow - could be staking or DeFi activity'
            })
        elif stable_inflow < 0 and native_inflow < 0:
            tags.append({
                'type': 'Capital Flight',
                'signal': 'Bearish',
                'reason': 'Both stablecoin and native assets leaving the chain'
            })
        
        # 補充信號
        if change_pct > 5:
            tags.append({
                'type': 'Strong Momentum',
                'signal': 'Bullish',
                'reason': f'TVL increased {change_pct:.1f}% in 24h'
            })
        elif change_pct < -5:
            tags.append({
                'type': 'Weak Momentum',
                'signal': 'Bearish',
                'reason': f'TVL decreased {change_pct:.1f}% in 24h'
            })
        
        return tags
    
    def _generate_tags_enhanced(
        self, 
        stable_inflow_24h: float, 
        native_inflow_24h: float,
        change_24h_pct: float,
        change_7d_pct: float,
        current_tvl: float
    ) -> List[Dict[str, Any]]:
        """
        增強版信號標籤生成 (使用多時間週期 + 百分比閾值)
        
        優化點:
        - 使用 TVL 百分比而非固定金額作為閾值
        - 結合 24H 和 7D 數據判斷趨勢一致性
        - 添加信號強度 (confidence)
        
        Returns:
            標籤列表 [{type, signal, reason, confidence}, ...]
        """
        tags = []
        
        # 動態閾值: 使用 TVL 的 1% 作為「顯著」變動
        significant_threshold = current_tvl * 0.01 if current_tvl > 0 else 10_000_000
        
        # === 主要信號: 資金流向 ===
        if stable_inflow_24h > significant_threshold:
            # 穩定幣大量流入
            confidence = min(100, int(abs(stable_inflow_24h) / significant_threshold * 20))
            
            # 如果 7D 也是正向，信號更強
            if change_7d_pct > 0:
                tags.append({
                    'type': 'Strong Buying Power',
                    'signal': 'Bullish',
                    'reason': f'穩定幣流入 ${stable_inflow_24h/1e6:.1f}M，週趨勢確認 (+{change_7d_pct:.1f}%)',
                    'confidence': min(100, confidence + 20)
                })
            else:
                tags.append({
                    'type': 'Buying Power',
                    'signal': 'Bullish',
                    'reason': f'穩定幣流入 ${stable_inflow_24h/1e6:.1f}M (短期信號)',
                    'confidence': confidence
                })
        
        elif stable_inflow_24h < -significant_threshold:
            # Check for severity (Dual outflow vs Simple)
            if native_inflow_24h < -significant_threshold:
                # Dual Outflow = Capital Flight
                confidence = min(100, int((abs(stable_inflow_24h) + abs(native_inflow_24h)) / significant_threshold * 15))
                tags.append({
                    'type': 'Capital Flight',
                    'signal': 'Bearish',
                    'reason': f'雙重流出警告 (Stable: -${abs(stable_inflow_24h)/1e6:.1f}M)',
                    'confidence': min(100, confidence + 20)
                })
            else:
                # Simple Outflow
                tags.append({
                    'type': 'Stablecoin Outflow',
                    'signal': 'Bearish',
                    'reason': f'穩定幣流出 ${abs(stable_inflow_24h)/1e6:.1f}M',
                    'confidence': 60
                })
        
        # === 趨勢一致性檢查 ===
        if change_24h_pct > 0 and change_7d_pct > 0:
            if change_24h_pct > 3 and change_7d_pct > 5:
                tags.append({
                    'type': 'Trend Confirmed',
                    'signal': 'Bullish',
                    'reason': f'短期 ({change_24h_pct:+.1f}%) 與週期 ({change_7d_pct:+.1f}%) 趨勢一致',
                    'confidence': 80
                })
        elif change_24h_pct < 0 and change_7d_pct < 0:
            if change_24h_pct < -3 and change_7d_pct < -5:
                tags.append({
                    'type': 'Downtrend Confirmed',
                    'signal': 'Bearish',
                    'reason': f'短期 ({change_24h_pct:.1f}%) 與週期 ({change_7d_pct:.1f}%) 下跌趨勢一致',
                    'confidence': 80
                })
        
        # === 趨勢背離警告 ===
        if (change_24h_pct > 2 and change_7d_pct < -3) or (change_24h_pct < -2 and change_7d_pct > 3):
            tags.append({
                'type': 'Trend Divergence',
                'signal': 'Neutral',
                'reason': f'短期與週期趨勢背離 (24H: {change_24h_pct:+.1f}%, 7D: {change_7d_pct:+.1f}%)',
                'confidence': 50
            })
        
        # 如果沒有明顯信號，標記為中性
        if not tags:
            tags.append({
                'type': 'Stable',
                'signal': 'Neutral',
                'reason': '資金流向平穩，無明顯異動',
                'confidence': 60
            })
        
        return tags
    
    async def analyze_multiple_chains(self, chain_names: List[str]) -> Dict[str, Any]:
        """
        批量分析多條公鏈
        
        Args:
            chain_names: 公鏈名稱列表
        
        Returns:
            {
                "chains": [{...}, {...}],
                "summary": {...}
            }
        """
        tasks = [self.analyze_chain(name) for name in chain_names]
        results = await asyncio.gather(*tasks)
        
        # 生成摘要
        total_stable_inflow = sum(r.get('stable_inflow_24h', 0) for r in results)
        total_native_inflow = sum(r.get('native_inflow_24h', 0) for r in results)
        
        bullish_count = sum(1 for r in results 
                          for t in r.get('tags', []) 
                          if t.get('signal') == 'Bullish')
        bearish_count = sum(1 for r in results 
                          for t in r.get('tags', []) 
                          if t.get('signal') == 'Bearish')
        
        return {
            'chains': results,
            'summary': {
                'total_stable_inflow_24h': total_stable_inflow,
                'total_native_inflow_24h': total_native_inflow,
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
    print("🧪 ChainAnalyzer 驗證測試")
    print("=" * 60)
    
    async with DataProvider() as provider:
        analyzer = ChainAnalyzer(provider)
        
        # 測試單一公鏈分析
        print("\n[1/2] 測試單一公鏈分析 (Ethereum)...")
        result = await analyzer.analyze_chain('ethereum')
        
        if result and not result.get('error'):
            print(f"   ✅ 成功！")
            print(f"      TVL: ${result['tvl_total']/1e9:.2f}B")
            print(f"      Stable/Volatile: ${result['tvl_stable']/1e9:.2f}B / ${result['tvl_volatile']/1e9:.2f}B")
            print(f"      24H Change: {result['change_24h_pct']:+.2f}%")
            print(f"      Tags: {[t['type'] for t in result['tags']]}")
        else:
            print(f"   ❌ 失敗: {result.get('error')}")
        
        # 測試多鏈分析
        print("\n[2/2] 測試多鏈分析...")
        multi_result = await analyzer.analyze_multiple_chains(['ethereum', 'bsc', 'solana'])
        
        if multi_result and multi_result.get('chains'):
            print(f"   ✅ 成功！分析了 {len(multi_result['chains'])} 條公鏈")
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
    print("🎉 ChainAnalyzer 測試完成")
    print("=" * 60)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test())
