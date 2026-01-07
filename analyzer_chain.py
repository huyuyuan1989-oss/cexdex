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
        分析單一公鏈的 TVL 資金流向
        
        Args:
            chain_name: 公鏈名稱 (例如 'ethereum', 'bsc', 'solana')
        
        Returns:
            結構化分析結果 (可直接 JSON 輸出)
        """
        result = {
            'chain': chain_name,
            'tvl_total': 0,
            'tvl_stable': 0,
            'tvl_volatile': 0,
            'stable_inflow_24h': 0,
            'native_inflow_24h': 0,
            'change_24h_pct': 0,
            'tags': [],
            'error': None
        }
        
        try:
            # 獲取歷史 TVL 數據
            tvl_data = await self.provider.get_chain_tvl(chain_name)
            
            if not tvl_data or len(tvl_data) < 2:
                result['error'] = 'Insufficient TVL data'
                return result
            
            # 計算當前與 24H 前的 TVL
            current = tvl_data[-1]
            previous = tvl_data[-2] if len(tvl_data) >= 2 else current
            
            current_tvl = current.get('tvl', 0)
            previous_tvl = previous.get('tvl', 0)
            
            result['tvl_total'] = current_tvl
            
            # 計算 24H 變動
            if previous_tvl > 0:
                change_24h = current_tvl - previous_tvl
                change_pct = (change_24h / previous_tvl) * 100
                result['change_24h_pct'] = round(change_pct, 2)
            
            # 嘗試區分穩定幣與波動性資產
            # 注意: DefiLlama chain TVL API 不直接提供資產明細
            # 這裡使用穩定幣供應 API 作為補充
            stable_ratio = await self._estimate_stable_ratio(chain_name)
            
            result['tvl_stable'] = current_tvl * stable_ratio
            result['tvl_volatile'] = current_tvl * (1 - stable_ratio)
            
            # 計算穩定幣與原生資產的流入
            total_inflow = current_tvl - previous_tvl
            result['stable_inflow_24h'] = total_inflow * stable_ratio
            result['native_inflow_24h'] = total_inflow * (1 - stable_ratio)
            
            # 生成信號標籤
            result['tags'] = self._generate_tags(
                result['stable_inflow_24h'],
                result['native_inflow_24h'],
                result['change_24h_pct']
            )
            
        except Exception as e:
            logger.error(f"Chain analysis error for {chain_name}: {e}")
            result['error'] = str(e)
        
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
        根據資金流向生成信號標籤
        
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
